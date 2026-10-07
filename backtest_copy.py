"""Offline copy-trading backtest: would copying the leaderboard's top wallets have made money, and under which rule?

For every hour H in the span of `copy_trades`, the wallets are ranked exactly as the live tracker does
(traders.score_wallets over the 48 h before H, then traders.rank_wallets under each rule). Every buy one of the top N
makes in [H, H+1h) is "copied": the forward return runs from the recorded market price at buy_ts + 60 s to the
recorded price at buy_ts + horizon, minus a 5-point round-trip cost. Buys with no recorded price within 10 minutes of
either end are skipped (and counted). Only trades before H are used for ranking, so nothing leaks from the future.

  python backtest_copy.py [--db arena.db] [--hours 1 6] [--tops 5 10 20]

Prints a markdown table and writes reports/copy_backtest.md. Opens the database read-only (the arena may be running).
"""
import argparse
import bisect
import glob
import gzip
import json
import os
import sqlite3
import statistics
import sys
import time

from traders import rank_wallets, score_wallets

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = ("pnl", "realized")
ENTRY_DELAY = 60      # seconds between the leader's buy and ours
TOLERANCE = 600       # a price is "at" a time only if a snapshot exists within this many seconds
COST_PCT = 5.0        # round-trip cost in percentage points (fees + slippage both ways)
WINDOW_H = 48
FALLBACK = ("realized", 10)


# ---------------------------------------------------------------- pure helpers (unit-tested)
def price_at(series, t, tol=TOLERANCE):
    """Price of the snapshot nearest to `t` in a sorted [(ts, price)] series, or None if none is within `tol` s."""
    if not series:
        return None
    i = bisect.bisect_left(series, (t,))
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(series):
            d = abs(series[j][0] - t)
            if d <= tol and (best is None or d < best[0]):
                best = (d, series[j][1])
    return best[1] if best else None


def forward_return(px, mint, buy_ts, horizon, cost_pct=COST_PCT):
    """Percent return of buying `mint` at buy_ts + 60 s and selling at buy_ts + `horizon` seconds, minus `cost_pct`
    points. None when either end has no recorded price within 10 minutes."""
    series = px.get(mint)
    entry = price_at(series, buy_ts + ENTRY_DELAY)
    if not entry or entry <= 0:
        return None
    exit_ = price_at(series, buy_ts + horizon)
    if exit_ is None:
        return None
    return (exit_ / entry - 1) * 100 - cost_pct


# ---------------------------------------------------------------- loading
def load_trades(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT ts, wallet, mint, kind, usd, qty, price, symbol FROM copy_trades ORDER BY ts").fetchall()
    finally:
        con.close()
    return [{"ts": r[0], "wallet": r[1], "mint": r[2], "kind": r[3], "usd": r[4] or 0.0, "qty": r[5] or 0.0,
             "price": r[6], "symbol": r[7]} for r in rows]


def load_prices(rec_dir):
    """{mint: [(ts, price)]} from every recording. Lines are delta-encoded per file (a token line without "price"
    keeps its last price; "-" lists removed keys), so the last price is carried per file as replay.Decoder does."""
    px = {}
    for fn in sorted(glob.glob(os.path.join(rec_dir, "*.jsonl.gz"))):
        last = {}
        try:
            with gzip.open(fn, "rt", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    ts = rec.get("ts")
                    if ts is None:
                        continue  # header
                    for e in rec.get("tokens") or []:
                        a = e.get("a")
                        if not a:
                            continue
                        if "price" in e:
                            last[a] = e["price"]
                        elif "price" in (e.get("-") or ()):
                            last.pop(a, None)
                        p = last.get(a)
                        if p:
                            px.setdefault(a, []).append((ts, float(p)))
        except EOFError:
            pass  # live / cut-off file: keep what was read
        except OSError as e:
            print(f"[backtest] {os.path.basename(fn)}: stopped early ({e})", file=sys.stderr)
    for s in px.values():
        s.sort()
    return px


# ---------------------------------------------------------------- backtest
def backtest(trades, px, hours, tops):
    """{(rule, n): {"buys": int, h: [returns]}} for every rule and top-N. `trades` must be sorted by ts."""
    horizons = [int(h * 3600) for h in hours]
    ts_list = [t["ts"] for t in trades]
    out = {(rule, n): {"buys": 0, **{h: [] for h in hours}} for rule in RULES for n in tops}
    fwd_cache = {}
    first = int(trades[0]["ts"] // 3600 + 1) * 3600
    last_ts = trades[-1]["ts"]
    top_max = max(tops)
    n_hours = int((last_ts - first) // 3600) + 1
    H, k = first, 0
    while H <= last_ts:
        k += 1
        t0 = time.time()
        lo = bisect.bisect_left(ts_list, H - WINDOW_H * 3600)
        hi = bisect.bisect_left(ts_list, H)       # strictly before H: no look-ahead
        nxt = bisect.bisect_left(ts_list, H + 3600)
        stats = score_wallets(trades[lo:hi], now=H, window_h=WINDOW_H)
        buys = [i for i in range(hi, nxt) if trades[i]["kind"] == "buy"]
        note = []
        for rule in RULES:
            ranked = [s["wallet"] for s in rank_wallets(stats, top_max, rule=rule)]
            note.append(f"{rule} {len(ranked)}")
            for n in tops:
                leaders = set(ranked[:n])
                cell = out[(rule, n)]
                for i in buys:
                    t = trades[i]
                    if t["wallet"] not in leaders:
                        continue
                    cell["buys"] += 1
                    if i not in fwd_cache:
                        fwd_cache[i] = [forward_return(px, t["mint"], t["ts"], hz) for hz in horizons]
                    for h, r in zip(hours, fwd_cache[i]):
                        if r is not None:
                            cell[h].append(r)
        print(f"[backtest] hour {k}/{n_hours} {time.strftime('%m-%d %H:%M', time.gmtime(H))}Z: "
              f"{hi - lo} trades scored, {len(stats)} wallets, ranked {', '.join(note)}, "
              f"{len(buys)} buys next hour ({time.time() - t0:.1f}s)", file=sys.stderr, flush=True)
        H += 3600
    return out, coverage(trades, px, fwd_cache, hours)


def coverage(trades, px, copied, hours):
    """Of the copied buys with an entry price whose exit time falls inside the recordings, how many had no exit price
    (the coin left the feed): {h: (missing, due)}. Those skips likely hide losers, so the means flatter copying."""
    end = max((s[-1][0] for s in px.values()), default=0)
    out = {}
    for h in hours:
        due = missing = 0
        for i in copied:
            t = trades[i]
            if t["ts"] + h * 3600 > end or price_at(px.get(t["mint"]), t["ts"] + ENTRY_DELAY) is None:
                continue
            due += 1
            missing += price_at(px.get(t["mint"]), t["ts"] + h * 3600) is None
        out[h] = (missing, due)
    return out


def _fmt(x):
    return "-" if x is None else f"{x:+.1f}"


def report(out, hours, tops, span_note, cov=None):
    """(markdown document, table, recommendation line). Best = highest positive mean at 6 h (or the longest horizon)."""
    key_h = 6 if 6 in hours else max(hours)
    head = ["rule", "top N", "buys copied"]
    for h in hours:
        head += [f"{h:g}h priced", f"{h:g}h mean %", f"{h:g}h median %", f"{h:g}h positive"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    best = None
    for rule in RULES:
        for n in tops:
            cell = out[(rule, n)]
            row = [rule, str(n), str(cell["buys"])]
            for h in hours:
                rs = cell[h]
                mean = statistics.fmean(rs) if rs else None
                med = statistics.median(rs) if rs else None
                pos = sum(1 for r in rs if r > 0) / len(rs) * 100 if rs else None
                row += [str(len(rs)), _fmt(mean), _fmt(med), "-" if pos is None else f"{pos:.0f}%"]
                if h == key_h and mean is not None and mean > 0 and (best is None or mean > best[2]):
                    best = (rule, n, mean, len(rs))
            lines.append("| " + " | ".join(row) + " |")
    table = "\n".join(lines)
    if best:
        rec = (f"Recommendation: ARENA_TRADERS_RANK={best[0]} ARENA_SHADOW_LEADERS={best[1]} "
               f"(best {key_h:g}h mean {best[2]:+.1f}% after {COST_PCT:g}-point cost over {best[3]} priced buys)")
    else:
        rec = (f"Recommendation: no copy edge measurable (every {key_h:g}h mean is <= 0 after {COST_PCT:g}-point "
               f"cost); keep ARENA_TRADERS_RANK={FALLBACK[0]} ARENA_SHADOW_LEADERS={FALLBACK[1]}")
    md = ["No copy edge was measurable on 2 days of data.", ""] if not best else []
    md += ["# Copy-trading backtest", "", span_note, "",
           f"Each hour the wallets are ranked from the {WINDOW_H} h of trades before that hour (`traders.score_wallets` "
           f"+ `rank_wallets`, rules `pnl` and `realized`). Every buy a top-N wallet makes in the next hour is copied: "
           f"entry at the recorded price {ENTRY_DELAY} s after their buy, exit at the recorded price at buy time + "
           f"horizon, minus {COST_PCT:g} points of cost. \"priced\" = buys with a recorded price within "
           f"{TOLERANCE // 60} minutes of both ends; the rest are skipped (no recording yet, or the coin left the feed).",
           "", table, ""]
    if cov:
        md += ["Coverage: of the copied buys with an entry price and an exit inside the recordings, "
               + "; ".join(f"{m} of {d} ({m / d * 100:.0f}%) had no price at {h:g}h" for h, (m, d) in cov.items() if d)
               + " (the coin left the feed, or a recording gap). If those were mostly dying coins, the true means "
               "are worse than shown.", ""]
    md += [rec, ""]
    return "\n".join(md), table, rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline copy-trading backtest over copy_trades and recordings.")
    ap.add_argument("--db", default=os.path.join(HERE, "arena.db"))
    ap.add_argument("--hours", type=float, nargs="+", default=[1, 6], help="forward-return horizons in hours")
    ap.add_argument("--tops", type=int, nargs="+", default=[5, 10, 20], help="leaderboard sizes to copy")
    ap.add_argument("--recordings", default=os.path.join(HERE, "recordings"))
    ap.add_argument("--out", default=os.path.join(HERE, "reports", "copy_backtest.md"))
    a = ap.parse_args(argv)
    hours = [int(h) if float(h).is_integer() else h for h in a.hours]
    tops = sorted(set(a.tops))
    t0 = time.time()
    trades = load_trades(a.db)
    if not trades:
        sys.exit("no copy_trades in the database")
    print(f"[backtest] {len(trades)} trades loaded ({time.time() - t0:.0f}s)", file=sys.stderr, flush=True)
    px = load_prices(a.recordings)
    print(f"[backtest] prices for {len(px)} mints, {sum(len(s) for s in px.values())} points "
          f"({time.time() - t0:.0f}s)", file=sys.stderr, flush=True)
    out, cov = backtest(trades, px, hours, tops)
    span_note = (f"Data: {len(trades)} trades from {len({t['wallet'] for t in trades})} wallets, "
                 f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(trades[0]['ts']))}Z to "
                 f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(trades[-1]['ts']))}Z; prices for {len(px)} mints "
                 f"from recordings. Run time {time.time() - t0:.0f} s.")
    md, table, rec = report(out, hours, tops, span_note, cov)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(md)
    print(table)
    print()
    print(rec)
    print(f"[backtest] wrote {a.out} in {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
