"""Replay a recorded market day (see recorder.py) and re-run any agents on it, in seconds instead of days.

    python replay.py 2026-10-05                                    # bots only, instant
    python replay.py recordings/2026-10-05.jsonl.gz --agents all --yes
    python replay.py 2026-10-05 --agents claude --from 09:00 --to 12:00 --yes
    python replay.py 2026-10-05 --compare my_brief.txt --yes        # current brief vs. the file, side by side
    python replay.py 2026-10-05 --agents "Sonnet 5.5,Sniper" --brief my_brief.txt --yes --serve 8012

The Claude agents make REAL calls through Claude Code when you replay them (each one counts against your
plan's limits, like the live arena). The usage estimate is printed first and --yes is required to go ahead.
Bots are free and instant. The replay arena is the normal Arena with a simulated clock: a tick per snapshot,
orders fill on the next tick, exits/alarms/watcher run as live. After each tick the replay waits until every
Claude has answered before moving on, so decisions land at the right simulated time (no latency in replay).

Results: a table on the console, and the full trade / decision / equity log in the output database
(default replay_out.db; --compare writes <db>.base.db and <db>.brief.db). --serve PORT then opens the
normal dashboard on the replay database.
"""
import argparse
import collections
import contextlib
import glob
import gzip
import io
import json
import os
import random
import re
import sqlite3
import sys
import time as _time
import traceback
import zlib
from datetime import datetime

from market import SOL_MINT

HERE = os.path.dirname(os.path.abspath(__file__))
Snapshot = collections.namedtuple("Snapshot", "ts sol tokens")
_TS_RE = re.compile(rb'^\{"ts":([0-9][0-9.eE+-]*)')


# ---------------------------------------------------------------- reading recordings
def iter_records(path):
    """Raw JSON records of one recording file. Tolerates a file whose last line was cut off."""
    try:
        with gzip.open(path, "rb") as f:
            for raw in f:
                try:
                    yield json.loads(raw)
                except ValueError:
                    continue  # partial last line
    except EOFError:
        return  # the arena was stopped mid-write: everything flushed before that is already yielded
    except (OSError, zlib.error) as e:
        print(f"[replay] {os.path.basename(path)}: stopped reading early ({e})")


class Decoder:
    """Rebuilds full token dicts from the delta-encoded lines recorder.py writes."""

    def __init__(self):
        self.defs, self.last = {}, {}

    def token(self, entry, ts):
        a = entry["a"]
        last = self.last.setdefault(a, {})
        for k, v in entry.items():
            if k == "a":
                continue
            if k == "-":
                for gone in v:
                    last.pop(gone, None)
            else:
                last[k] = v
        d = self.defs.get(a, {})
        t = {"address": a, **{k: v for k, v in d.items() if k != "born"}, **last, "updated": ts}
        t["age_min"] = (ts - d["born"]) / 60 if d.get("born") is not None else None
        return t

    def snapshot(self, rec):
        ts = rec["ts"]
        for a, s in (rec.get("defs") or {}).items():
            self.defs.setdefault(a, {}).update(s)
        sol = self.token(rec["sol"], ts) if rec.get("sol") else None
        return Snapshot(ts, sol, [self.token(e, ts) for e in rec.get("tokens") or [] if e.get("a")])


def iter_snapshots(paths, start=None, end=None):
    """Snapshots from one or more recording files, in order, optionally limited to [start, end] unix seconds."""
    for path in paths:
        dec = Decoder()  # every file is self-contained
        for rec in iter_records(path):
            ts = rec.get("ts")
            if ts is None:
                continue  # header line
            snap = dec.snapshot(rec)  # decode every line: later lines are deltas against it
            if start is not None and ts < start:
                continue
            if end is not None and ts > end:
                break
            yield snap


def scan(paths):
    """Cheap pass over the files: snapshot count, first/last time and whether it's a mock recording."""
    out = {"count": 0, "first": None, "last": None, "mock": False, "files": list(paths)}
    for path in paths:
        try:
            with gzip.open(path, "rb") as f:
                for raw in f:
                    m = _TS_RE.match(raw)
                    if m and raw.endswith(b"}\n"):
                        ts = float(m.group(1))
                    else:
                        try:
                            rec = json.loads(raw)
                        except ValueError:
                            continue
                        if "hdr" in rec:
                            out["mock"] = out["mock"] or bool(rec["hdr"].get("mock"))
                            continue
                        ts = rec.get("ts")
                        if ts is None:
                            continue
                    out["count"] += 1
                    out["first"] = ts if out["first"] is None else min(out["first"], ts)
                    out["last"] = ts if out["last"] is None else max(out["last"], ts)
        except EOFError:
            pass
        except (OSError, zlib.error) as e:
            print(f"[replay] {os.path.basename(path)}: unreadable ({e})")
    return out


def _segment_key(path):
    stem = os.path.basename(path)[: -len(".jsonl.gz")]
    m = re.fullmatch(r"(mock-)?(\d{4}-\d{2}-\d{2})(?:\.(\d+))?", stem)
    return (m.group(2), int(m.group(3) or 0)) if m else (stem, 0)


def expand_paths(args, rec_dir):
    """Each argument is a recording file, a date (2026-10-05 or mock-2026-10-05) or a directory. A day's
    recording is split into one file per arena start (2026-10-05.jsonl.gz, .1, .2 ...); all are loaded."""
    files = []
    for a in args:
        if os.path.isdir(a):
            files += glob.glob(os.path.join(a, "*.jsonl.gz"))
        elif os.path.isfile(a):
            stem = os.path.basename(a)[: -len(".jsonl.gz")] if a.endswith(".jsonl.gz") else ""
            key = stem[:15] if stem.startswith("mock-") else stem[:10]
            sib = [p for p in glob.glob(os.path.join(os.path.dirname(a) or ".", key + "*.jsonl.gz"))
                   if re.fullmatch(re.escape(key) + r"(\.\d+)?\.jsonl\.gz", os.path.basename(p))] if key else []
            files += sib or [a]
        elif re.fullmatch(r"(mock-)?\d{4}-\d{2}-\d{2}", a):
            found = glob.glob(os.path.join(rec_dir, a + "*.jsonl.gz"))
            found = [p for p in found if re.fullmatch(re.escape(a) + r"(\.\d+)?\.jsonl\.gz", os.path.basename(p))]
            if not found:
                sys.exit(f"no recording for {a} in {rec_dir}")
            files += found
        else:
            sys.exit(f"not a recording file, date or directory: {a}")
    seen, out = set(), []
    for p in sorted(files, key=_segment_key):
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            out.append(ap)
    return out


# ---------------------------------------------------------------- the replay market and clock
class ReplayMarket:
    """The market interface the arena uses, served from recorded snapshots. refresh() moves to the next one."""

    def __init__(self, snapshots):
        self._it = iter(snapshots)
        self._next = next(self._it, None)
        self.now, self.sol, self.tokens, self.count = None, None, {}, 0

    def has_next(self):
        return self._next is not None

    def peek_ts(self):
        return self._next.ts if self._next else None

    def refresh(self, held):
        if self._next is None:
            return  # recording exhausted: keep the last snapshot
        snap = self._next
        self.now, self.sol = snap.ts, snap.sol
        self.tokens = {t["address"]: t for t in snap.tokens if (t.get("price") or 0) > 0}
        self.count += 1
        self._next = next(self._it, None)

    def get(self, addr):
        return self.sol if addr == SOL_MINT else self.tokens.get(addr)

    def candidates(self):
        return list(self.tokens.values())

    def ready(self):
        return True


class SimClock:
    """The arena's clock and, patched in as claude_agents.time, the Claude agents' clock too."""

    def __init__(self, now, fast=False):
        self.now, self.fast = float(now), fast

    def __call__(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, secs):
        if not self.fast and secs > 0:
            _time.sleep(secs)

    def __getattr__(self, name):  # strftime, monotonic, ... stay real
        return getattr(_time, name)


def _hhmm(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def _when(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def max_drawdown(series):
    peak, mdd = 0.0, 0.0
    for _, eq in series:
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, (peak - eq) / peak)
    return mdd * 100


# ---------------------------------------------------------------- agents
def seed_bots(agents, seed):
    """Give every bot with an `rng` a fixed seed (by name), so a replay is repeatable."""
    if seed is None:
        return
    for a in agents:
        rng = getattr(a, "rng", None)
        if isinstance(rng, random.Random):
            rng.seed(f"{seed}:{a.name}")


def apply_brief(agents, brief):
    """Replace LLM_SYSTEM with `brief` for the Claude agents (personas and every {PLACEHOLDER} still apply)."""
    from claude_agents import PERSONAS
    for a in agents:
        if a.kind != "llm":
            continue
        s = brief.rstrip()
        if getattr(a, "persona", None) in PERSONAS:
            s += "\n\n" + PERSONAS[a.persona][1]
        from claude_agents import fill_brief
        a.system = fill_brief(s, a.min_check, a.max_check)


def agent_factory(spec, allow_llm=True):
    """spec: bots | claude | all | 'Name1,Name2'. Returns a zero-arg function building fresh agents."""
    from agents import build_bots
    from claude_agents import build_llm_agents

    spec = (spec or "bots").strip()
    low = spec.lower()

    def build():
        if low == "bots":
            return build_bots()
        llm = build_llm_agents() if allow_llm else []
        if low == "claude":
            return llm
        if low == "all":
            return llm + build_bots()
        everyone = llm + build_bots()
        by_name = {a.name.lower(): a for a in everyone}
        picked = []
        for n in spec.split(","):
            a = by_name.get(n.strip().lower())
            if not a:
                sys.exit(f"no agent called {n.strip()!r}. Available: " + ", ".join(x.name for x in everyone))
            picked.append(a)
        return picked

    return build


def _order_text(o):
    act = str(o.get("action", "?")).upper()
    sym = o.get("symbol") or str(o.get("token", "?"))[:6]
    if act == "BUY":
        try:
            return f"BUY {sym} ${float(o.get('usd')):.0f}"
        except (TypeError, ValueError):
            return f"BUY {sym}"
    if act == "SELL":
        try:
            frac = float(o.get("fraction", 1.0))
            return f"SELL {sym}" + (f" {frac * 100:.0f}%" if frac < 0.999 else "")
        except (TypeError, ValueError):
            return f"SELL {sym}"
    return f"{act} {sym}"


def _report_llm(a, now):
    """Print what a Claude agent just decided (called after its background job finished)."""
    if a.ready is not None:
        orders, rec = a.ready
        acts = ", ".join(_order_text(o) for o in orders if isinstance(o, dict)) or "no orders"
        nm = rec.get("next_min")
        print(f"  {_hhmm(now)} {a.name:<16} {acts}; next look in {nm:g} min  | {str(rec.get('note', ''))[:110]}"
              if nm else f"  {_hhmm(now)} {a.name:<16} {acts}  | {str(rec.get('note', ''))[:110]}")
    elif a.log:
        print(f"  {_hhmm(now)} {a.name:<16} call failed: {a.error}")


# ---------------------------------------------------------------- running
def run(paths, make_agents, start_cash=1000.0, db_path="replay_out.db", start=None, end=None, seed=0,
        quiet=False, fast=False, label="replay", brief=None, tick=30, progress_every=120):
    """Replay the recording with freshly built agents. Returns (arena, db, result rows)."""
    import claude_agents
    from arena import Arena
    from db import DB

    agents = make_agents()
    if not agents:
        sys.exit("no agents to run")
    seed_bots(agents, seed)
    if brief is not None:
        apply_brief(agents, brief)
    market = ReplayMarket(iter_snapshots(paths, start, end))
    if not market.has_next():
        sys.exit("no snapshots in that time range")
    clock = SimClock(market.peek_ts(), fast=fast)
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError as e:
            sys.exit(f"can't replace {db_path} ({e}); close anything that has it open")
    db = DB(db_path)
    with db.lock:  # the replay db is disposable: skip fsyncs (16 commits per tick otherwise dominate the run time)
        db.conn.execute("PRAGMA synchronous=OFF")
        db.conn.execute("PRAGMA journal_mode=MEMORY")
    arena = Arena(market, db, agents, start_cash=start_cash, tick=tick, clock=clock)
    if getattr(arena, "memory", None) and start:  # market memory sees what happened before the window, as it would live
        arena.memory.load(iter_snapshots(paths, start - 86400, start))
    if seed is not None and isinstance(getattr(arena, "rng", None), random.Random):
        arena.rng.seed(f"{seed}:arena")  # failed-transaction dice, so the same seed gives the same replay
    llm = [a for a in agents if a.kind == "llm"]
    print(f"\n[replay] {label}: {', '.join(a.name for a in agents)}  (from {_when(clock.now)}, ${start_cash:g} each)")
    saved_time, claude_agents.time = claude_agents.time, clock
    t_wall, sink, steps = _time.time(), io.StringIO(), 0
    try:
        while market.has_next():
            clock.now = market.peek_ts()
            try:
                if quiet:
                    with contextlib.redirect_stdout(sink):
                        arena.step()
                    sink.seek(0)
                    sink.truncate()
                else:
                    arena.step()
            except Exception as e:
                print(f"[replay] tick failed: {e}")
                traceback.print_exc()
            steps += 1
            for a in llm:  # decisions must land before the simulated clock moves on
                job = a.job
                if job is not None:
                    job.join()
                _report_llm(a, clock.now)
            if progress_every and steps % progress_every == 0:
                top = max(arena.agents, key=arena.equity)
                print(f"[replay] {_hhmm(clock.now)}  tick {steps}  leader {top} "
                      f"{(arena.score_equity(top) / start_cash - 1) * 100:+.1f}%  ({_time.time() - t_wall:.0f}s wall)")
    except KeyboardInterrupt:
        print(f"\n[replay] interrupted at {_hhmm(clock.now)} after {steps} ticks; results so far:")
    finally:
        claude_agents.time = saved_time
    rows = results(arena, db)
    print(f"[replay] {label}: {steps} ticks, {_when(market.now)} end, {_time.time() - t_wall:.1f}s wall-clock, "
          f"log in {db_path}")
    return arena, db, rows


def results(arena, db):
    usage = db.usage_by_agent(0)
    rows = []
    for name, agent in arena.agents.items():
        eq, st, u = arena.score_equity(name), db.sell_stats(name), usage.get(name)
        rows.append({
            "name": name, "team": "claude" if agent.kind == "llm" else "bots",
            "equity": eq, "pnl_pct": (eq / arena.start_cash - 1) * 100,
            "trades": st["trades"], "closed": st["closed"],
            "win_rate": st["wins"] / st["closed"] * 100 if st["closed"] else None,
            "max_dd": max_drawdown(db.equity_series(name)), "open": len(arena.accounts[name]["positions"]),
            "calls": u["calls"] if u else None, "errors": u["errors"] if u else None,
            "cost": u["cost"] if u else None,
            "tokens": (u["in_tok"] + u["cache_read"] + u["cache_write"] + u["out_tok"]) if u else None,
        })
    rows.sort(key=lambda r: -r["equity"])
    return rows


def _num(v, fmt, none="-"):
    return none if v is None else format(v, fmt)


def print_table(rows, title="Results"):
    has_llm = any(r["team"] == "claude" for r in rows)
    head = f"{'Agent':<18}{'Team':<8}{'Equity':>10}{'P&L %':>8}{'Trades':>7}{'Closed':>7}{'Win %':>7}{'MaxDD %':>8}{'Open':>5}"
    if has_llm:
        head += f"{'Calls':>7}{'Err':>5}{'Cost $':>9}{'Tokens':>10}"
    print(f"\n{title}\n{head}\n{'-' * len(head)}")
    for r in rows:
        line = (f"{r['name']:<18}{r['team']:<8}{r['equity']:>10.2f}{r['pnl_pct']:>+8.2f}{r['trades']:>7}{r['closed']:>7}"
                f"{_num(r['win_rate'], '.0f'):>7}{r['max_dd']:>8.1f}{r['open']:>5}")
        if has_llm:
            line += (f"{_num(r['calls'], 'd'):>7}{_num(r['errors'], 'd'):>5}{_num(r['cost'], '.2f'):>9}"
                     f"{_num(r['tokens'], ',d'):>10}")
        print(line)


def print_compare(base, other, base_label="current brief", other_label="new brief"):
    by_b, by_o = {r["name"]: r for r in base}, {r["name"]: r for r in other}
    names = [r["name"] for r in sorted(by_b.values(), key=lambda r: (r["team"] != "claude", -r["pnl_pct"]))]
    names += [n for n in by_o if n not in by_b]
    col = f"{'Equity':>9}{'P&L %':>8}{'Trd':>5}{'Win%':>5}{'DD%':>6}"
    head = f"{'Agent':<18}| {base_label[:30]:<33}| {other_label[:30]:<33}| {'d P&L':>7}"
    sub = f"{'':<18}| {col:<33}| {col:<33}|"
    print(f"\nComparison\n{head}\n{sub}\n{'-' * len(head)}")

    def cell(r):
        if not r:
            return f"{'-':>33}"
        return f"{r['equity']:>9.2f}{r['pnl_pct']:>+8.2f}{r['trades']:>5}{_num(r['win_rate'], '.0f'):>5}{r['max_dd']:>6.1f}"

    for n in names:
        b, o = by_b.get(n), by_o.get(n)
        delta = f"{o['pnl_pct'] - b['pnl_pct']:>+7.2f}" if b and o else f"{'-':>7}"
        print(f"{n:<18}| {cell(b)} | {cell(o)} | {delta}")
    for label, rows in ((base_label, base), (other_label, other)):
        cl = [r for r in rows if r["team"] == "claude"]
        if cl:
            cost = sum(r["cost"] or 0 for r in cl)
            print(f"{label}: Claude average {sum(r['pnl_pct'] for r in cl) / len(cl):+.2f}% "
                  f"(best {max(r['pnl_pct'] for r in cl):+.2f}%, worst {min(r['pnl_pct'] for r in cl):+.2f}%), "
                  f"{sum(r['calls'] or 0 for r in cl)} calls, ${cost:.2f} API-price equivalent")


# ---------------------------------------------------------------- usage estimate
def _history_per_call():
    """Average cost / seconds / tokens per Claude call from the live arena's database, if there is one."""
    path = os.path.join(HERE, "arena.db")
    out = {"cost": 0.05, "secs": 25.0, "tokens": 9000, "source": "a rough default"}
    if not os.path.exists(path):
        return out
    try:
        c = sqlite3.connect(f"file:{os.path.abspath(path).replace(os.sep, '/')}?mode=ro", uri=True)
        n, cost, secs, tok = c.execute(
            "SELECT COUNT(*), TOTAL(cost), TOTAL(secs), TOTAL(in_tok + cache_read + cache_write + out_tok) "
            "FROM decisions WHERE error IS NULL AND cost IS NOT NULL").fetchone()
        c.close()
        if n and n >= 5:
            out.update(cost=cost / n, secs=secs / n if secs else 25.0, tokens=tok / n, source=f"your arena.db ({n} calls)")
    except sqlite3.Error:
        pass
    return out


def estimate(llm_agents, info, start, end, runs=1):
    sim_min = max(0.0, (end - start) / 60)
    per = _history_per_call()
    total = peak = 0.0
    for a in llm_agents:
        calls = sim_min / ((a.min_check + a.max_check) / 2) * 1.2  # +20% for wake-ups
        total += calls
        peak = max(peak, calls)
    total *= runs
    ticks = info["count"] * runs
    wall_lo, wall_hi = peak * runs * per["secs"], min(ticks, total) * per["secs"]
    print(f"\nThis replay makes REAL Claude calls through Claude Code (they count against your plan's limits).")
    print(f"  {len(llm_agents)} Claude agent(s) x {runs} run(s) over {sim_min / 60:.1f} h of market "
          f"(each looks every {min(a.min_check for a in llm_agents):g}-{max(a.max_check for a in llm_agents):g} min)")
    print(f"  ~{total:,.0f} calls, ~{total * per['tokens'] / 1e6:.1f}M tokens, ~${total * per['cost']:.2f} in API-price "
          f"terms (per call: {per['source']})")
    print(f"  wall-clock about {wall_lo / 3600:.1f}-{wall_hi / 3600:.1f} h (calls at the same tick run in parallel)")


def load_dotenv():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _clock_time(s, day_ts, what):
    try:
        h, m = datetime.strptime(s, "%H:%M").hour, datetime.strptime(s, "%H:%M").minute
    except ValueError:
        sys.exit(f"{what} must look like HH:MM, not {s!r}")
    return datetime.fromtimestamp(day_ts).replace(hour=h, minute=m, second=0, microsecond=0).timestamp()


def main(argv=None):
    load_dotenv()
    ap = argparse.ArgumentParser(description="Re-run arena agents on a recorded market day (paper trading).",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("recording", nargs="+", help="recording file, date (2026-10-05, mock-2026-10-05) or directory")
    ap.add_argument("--recordings", default=os.path.join(HERE, "recordings"), help="where dates are looked up")
    ap.add_argument("--agents", default=None, help="bots | claude | all | 'Name1,Name2' (default: bots; all with --brief/--compare)")
    ap.add_argument("--from", dest="t_from", metavar="HH:MM", help="start of day time (local) to replay from")
    ap.add_argument("--to", dest="t_to", metavar="HH:MM", help="time to stop at")
    ap.add_argument("--cash", type=float, default=1000.0, help="starting fake cash per agent")
    ap.add_argument("--db", default=os.path.join(HERE, "replay_out.db"), help="output database (replaced)")
    ap.add_argument("--seed", type=int, default=0, help="seed for the Random bots; same seed, same picks")
    ap.add_argument("--fast", action="store_true", help="no per-trade output and no real sleeps, progress only")
    ap.add_argument("--brief", metavar="FILE", help="run the Claude agents with this file instead of LLM_SYSTEM")
    ap.add_argument("--compare", metavar="FILE", help="run twice: current LLM_SYSTEM, then this brief; print both")
    ap.add_argument("--yes", action="store_true", help="confirm making real Claude calls")
    ap.add_argument("--serve", nargs="?", const=8012, type=int, metavar="PORT", help="then open the dashboard on the result (default port 8012)")
    args = ap.parse_args(argv)

    paths = expand_paths(args.recording, args.recordings)
    info = scan(paths)
    if not info["count"]:
        sys.exit("no snapshots found in " + ", ".join(paths))
    span = info["last"] - info["first"]
    tick = round(span / (info["count"] - 1)) if info["count"] > 1 and span > 0 else 30
    print(f"Recording: {_when(info['first'])} -> {_when(info['last'])} local, {info['count']} snapshots "
          f"(every ~{tick}s){', MOCK market' if info['mock'] else ''}")
    for p in paths:
        print(f"  {p}  ({os.path.getsize(p) / 1e6:.1f} MB)")
    start = _clock_time(args.t_from, info["first"], "--from") if args.t_from else None
    end = _clock_time(args.t_to, info["first"], "--to") if args.t_to else None
    if start is not None and end is not None and end <= start:
        sys.exit("--to must be after --from")

    spec = args.agents or ("all" if (args.brief or args.compare) else "bots")
    make = agent_factory(spec)
    sample = make()
    llm = [a for a in sample if a.kind == "llm"]
    if (args.brief or args.compare) and not llm:
        sys.exit("--brief/--compare need Claude agents, but none were built (is Claude Code installed and logged in, "
                 "and ARENA_LLM not 'off'?)")
    if llm:
        runs = 2 if args.compare else 1
        estimate(llm, info, start or info["first"], end or info["last"], runs)
        if not args.yes:
            sys.exit("Add --yes to go ahead, or use --agents bots for a free replay.")
    brief = open(args.brief, encoding="utf-8").read() if args.brief else None
    common = dict(start_cash=args.cash, start=start, end=end, seed=args.seed, quiet=args.fast, fast=args.fast, tick=tick)

    if args.compare:
        other = open(args.compare, encoding="utf-8").read()
        stem = args.db[:-3] if args.db.endswith(".db") else args.db
        _, _, base_rows = run(paths, make, db_path=stem + ".base.db", label="current brief", brief=brief, **common)
        arena, db, new_rows = run(paths, make, db_path=stem + ".brief.db", label=f"brief {os.path.basename(args.compare)}",
                                  brief=other, **common)
        print_table(base_rows, "Run A: " + ("current LLM_SYSTEM" if not brief else f"brief {os.path.basename(args.brief)}"))
        print_table(new_rows, f"Run B: brief {os.path.basename(args.compare)}")
        print_compare(base_rows, new_rows, "A: current" if not brief else f"A: {os.path.basename(args.brief)}",
                      f"B: {os.path.basename(args.compare)}")
    else:
        arena, db, rows = run(paths, make, db_path=args.db, label=f"brief {os.path.basename(args.brief)}" if brief else "replay",
                              brief=brief, **common)
        print_table(rows)

    if args.serve:
        import main as arena_main
        for k in ("ARENA_NTFY_TOPIC", "ARENA_DISCORD_WEBHOOK"):  # a replay must never send phone alerts
            os.environ.pop(k, None)
        app = arena_main.create_app(arena, db, info["mock"])
        print(f"\nDashboard for this replay: http://localhost:{args.serve}   (Ctrl+C to stop)")
        app.run(host="127.0.0.1", port=args.serve, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
