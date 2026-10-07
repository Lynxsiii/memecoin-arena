"""Phone alerts for the arena, through ntfy and/or a Discord webhook.

One background thread polls the arena every 30 seconds and sends short messages for the things worth
interrupting your day for: big closed trades, rugs, lead changes, plan usage crossing 50/75/90%, Claude
login or usage-limit errors, a stalled arena, and one daily digest. Nothing here changes the arena.

Setup with ntfy (free, no account needed)
  1. Install the ntfy app (Android or iPhone; https://ntfy.sh/app), or open https://ntfy.sh in a browser.
  2. Subscribe to a topic with a hard-to-guess name, e.g. arena-k9x2mq7f3wq. Topics on ntfy.sh are public:
     anyone who guesses the name can read your alerts and post to it, so make it long and random.
  3. Put ARENA_NTFY_TOPIC=arena-k9x2mq7f3wq in .env (same folder as main.py) and restart the arena.

Setup with Discord
  1. In a Discord server you own: channel settings > Integrations > Webhooks > New Webhook > Copy Webhook URL.
  2. Put ARENA_DISCORD_WEBHOOK=https://discord.com/api/webhooks/... in .env and restart the arena.
  3. Never share the URL or commit .env: anyone with the URL can post to that channel.

Both can be on at once. `python notifier.py` sends one test message to whatever is configured.

Environment variables (main.py loads .env before this runs; all optional)
  ARENA_NTFY_TOPIC          ntfy topic name. Unset = ntfy off.
  ARENA_NTFY_SERVER         ntfy server (default https://ntfy.sh), for a self-hosted server.
  ARENA_DISCORD_WEBHOOK     Discord webhook URL. Unset = Discord off.
  ARENA_ALERTS              comma list of alert types to send (default: all of them):
                              trade   a closed trade with |P&L| >= ARENA_ALERT_MIN_PNL
                              rug     a sell that lost >= 50% of its cost, or a held position that lost >= 80%
                                      of its value since the previous poll
                              leader  the arena leader changed (only after 2 polls on top, by >= $5)
                              team    the team with the best average equity per agent changed (Claude, Bots, Copy; same hysteresis)
                              usage   plan usage crossed 50%, 75% or 90% on the 5-hour or weekly window
                              error   a Claude call failed with something that looks like a login or usage limit
                              stall   no tick for more than 3 minutes, and when ticks come back
                              digest  the daily digest: standings, team totals, best/worst trade, usage
                              bust    a Claude went bust and lost a life (critical when it was its last)
  ARENA_ALERT_MIN_PNL       dollars of |P&L| a closed trade needs for a "trade" alert (default 20)
  ARENA_ALERT_DIGEST_AT     local time of the daily digest, HH:MM (default 21:00)
  ARENA_ALERT_QUIET         quiet hours, e.g. 23:00-07:00 (default none). Only critical alerts get through:
                            a stall, usage at 90%, a rug of $50 or more, and the digest if you scheduled it then.
  ARENA_ALERT_MAX_PER_HOUR  most messages per hour (default 12). Several alerts in one poll become one message
                            ("3 rugs in the last minute"); past the cap, alerts wait and arrive as one summary.
  ARENA_ALERT_POLL          seconds between polls (default 30)

Alerts start from the trades and decisions present at startup, so a restart never replays history.
"""
import os
import re
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass
from datetime import datetime

try:
    import requests
except ImportError:  # it's in requirements.txt; stay importable without it so main.py keeps running
    requests = None

EVENTS = ("trade", "rug", "leader", "team", "usage", "error", "stall", "digest", "bust")
TITLES = {"trade": "Big trade", "rug": "Rug", "leader": "New leader", "team": "Team lead flips", "bust": "Bust",
          "usage": "Plan usage", "error": "Claude error", "stall": "Arena stalled", "digest": "Daily digest"}
PLURALS = {"trade": "big trades", "rug": "rugs", "leader": "lead changes", "team": "team lead flips", "bust": "busts",
           "usage": "usage alerts", "error": "Claude errors", "stall": "arena alerts", "digest": "digests"}
USAGE_STEPS = (50, 75, 90)
STALL_AFTER = 180            # seconds without a tick before "stalled"
RUG_SELL_FRAC = 0.5          # a sell that loses this share of its cost is a rug
RUG_DROP_FRAC = 0.8          # a held position that loses this share of its value in one poll is a rug
CRITICAL_RUG_USD = 50.0
LIMIT_ERROR = re.compile(r"limit|login|logged|auth|forbidden|quota|429|too many|credential|expired|sign.?in|"
                         r"usage|billing|subscription", re.I)
LOG = "[notifier]"


# ---------- formatting ----------
def money(x):
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def signed(x):
    return f"+${x:,.2f}" if x >= 0 else f"-${-x:,.2f}"


def parse_hhmm(s):
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", s or "")
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        return None
    return int(m[1]), int(m[2])


@dataclass
class Alert:
    kind: str
    text: str
    at: float
    critical: bool = False
    tags: tuple = ()
    title: str = ""


# ---------- configuration ----------
class Config:
    def __init__(self, env=None):
        g = (env if env is not None else os.environ).get
        self.warnings = []
        self.ntfy_topic = (g("ARENA_NTFY_TOPIC") or "").strip()
        self.ntfy_server = (g("ARENA_NTFY_SERVER") or "https://ntfy.sh").strip().rstrip("/")
        self.discord = (g("ARENA_DISCORD_WEBHOOK") or "").strip()
        self.events = self._events(g("ARENA_ALERTS"))
        self.min_pnl = self._number(g, "ARENA_ALERT_MIN_PNL", 20.0)
        self.max_per_hour = max(1, int(self._number(g, "ARENA_ALERT_MAX_PER_HOUR", 12)))
        self.poll = max(5.0, self._number(g, "ARENA_ALERT_POLL", 30.0))
        self.digest_at = parse_hhmm(g("ARENA_ALERT_DIGEST_AT") or "21:00")
        if self.digest_at is None:
            self.warnings.append(f"ARENA_ALERT_DIGEST_AT={g('ARENA_ALERT_DIGEST_AT')!r} isn't HH:MM; using 21:00")
            self.digest_at = (21, 0)
        self.quiet = self._quiet(g("ARENA_ALERT_QUIET"))
        if self.ntfy_topic and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.ntfy_topic):
            self.warnings.append("ARENA_NTFY_TOPIC may only contain letters, digits, _ and -; ntfy will reject it")
        elif self.ntfy_topic and len(self.ntfy_topic) < 10:
            self.warnings.append("ARENA_NTFY_TOPIC is short and easy to guess; ntfy.sh topics are public")
        if self.discord and not re.match(r"https?://", self.discord):
            self.warnings.append("ARENA_DISCORD_WEBHOOK must be an http(s) URL; ignoring it")
            self.discord = ""
        elif self.discord and not re.match(r"https://(ptb\.|canary\.)?discord(app)?\.com/api/webhooks/", self.discord):
            self.warnings.append("ARENA_DISCORD_WEBHOOK doesn't look like https://discord.com/api/webhooks/...")

    def _number(self, g, name, default):
        raw = g(name)
        if raw in (None, ""):
            return default
        try:
            return float(raw)
        except ValueError:
            self.warnings.append(f"{name}={raw!r} isn't a number; using {default}")
            return default

    def _events(self, raw):
        if not raw or raw.strip().lower() == "all":
            return set(EVENTS)
        wanted = {e.strip().lower() for e in raw.split(",") if e.strip()}
        bad = wanted - set(EVENTS)
        if bad:
            self.warnings.append(f"ARENA_ALERTS has unknown types {', '.join(sorted(bad))}; known: {', '.join(EVENTS)}")
        return wanted & set(EVENTS)

    def _quiet(self, raw):
        if not raw or not raw.strip():
            return None
        parts = raw.split("-")
        a, b = (parse_hhmm(parts[0]), parse_hhmm(parts[1])) if len(parts) == 2 else (None, None)
        if a is None or b is None:
            self.warnings.append(f"ARENA_ALERT_QUIET={raw!r} isn't HH:MM-HH:MM; no quiet hours")
            return None
        return a[0] * 60 + a[1], b[0] * 60 + b[1]


# ---------- channels ----------
class Channel:
    name = "channel"

    def __init__(self):
        self.backoff_until = 0.0
        self.failures = 0

    def post(self, title, body, priority, tags):
        raise NotImplementedError

    def send(self, title, body, priority, tags, now):
        """True if the message was accepted. Failures back off (longer each time, up to 15 minutes)."""
        if now < self.backoff_until:
            return False
        try:
            r = self.post(title, body, priority, tags)
        except Exception as e:  # DNS, timeout, connection refused...
            self._fail(now, f"{type(e).__name__}: {str(e)[:100]}")
            return False
        if r.status_code < 300:
            self.failures = 0
            return True
        retry = None
        if r.status_code == 429:
            try:
                retry = float(r.headers.get("Retry-After") or (r.json() or {}).get("retry_after"))
            except (TypeError, ValueError):
                retry = None
        self._fail(now, f"HTTP {r.status_code} {r.text[:80].strip()}", retry)
        return False

    def _fail(self, now, why, retry=None):
        self.failures += 1
        wait = min(900.0, max(5.0, retry) if retry else 60.0 * 2 ** min(self.failures - 1, 4))
        self.backoff_until = now + wait
        print(f"{LOG} {self.name} failed ({why}); trying again in {wait:.0f}s")


class Ntfy(Channel):
    name = "ntfy"

    def __init__(self, server, topic):
        super().__init__()
        self.url = f"{server}/{topic}"

    def post(self, title, body, priority, tags):
        # Header names as documented at https://docs.ntfy.sh/publish/ (Title, Priority, Tags; priority 1-5).
        headers = {"Title": title.encode("ascii", "ignore").decode() or "Arena",
                   "Priority": str(priority), "Tags": ",".join(tags[:3])}
        return requests.post(self.url, data=body[:3800].encode("utf-8"), headers=headers, timeout=(5, 10))


class Discord(Channel):
    name = "Discord"

    def __init__(self, url):
        super().__init__()
        self.url = url

    def post(self, title, body, priority, tags):
        lines = body.split("\n")
        text = f"**{title}**\n" + ("\n".join(f"- {ln}" for ln in lines) if len(lines) > 1 else body)
        return requests.post(self.url, json={"content": text[:1990]}, timeout=(5, 10))


def build_channels(cfg):
    out = []
    if cfg.ntfy_topic:
        out.append(Ntfy(cfg.ntfy_server, cfg.ntfy_topic))
    if cfg.discord:
        out.append(Discord(cfg.discord))
    return out


# ---------- hysteresis for "who's on top" ----------
TEAM_LABELS = {"claude": "Team Claude", "bots": "Team Bots", "copy": "Team Copy"}


def team_averages(snap):
    """Average equity per agent for each team. Teams differ in size, so totals would favour the bigger one."""
    eq = snap["equity"]
    teams = snap.get("teams") or {n: ("claude" if k == "llm" else "bots") for n, k in snap["kinds"].items()}
    out = {}
    for t in dict.fromkeys(teams.values()):
        xs = [e for n, e in eq.items() if teams.get(n) == t]
        if xs:
            out[TEAM_LABELS.get(t, f"Team {t.title()}")] = sum(xs) / len(xs)
    return out


class Race:
    """A challenger must be on top for `polls` consecutive polls, by at least `margin`, to be the new leader."""

    def __init__(self, margin=5.0, polls=2):
        self.margin, self.polls = margin, polls
        self.leader = self.cand = None
        self.n = 0

    def update(self, scores):
        """Returns (new leader, old leader) when the lead changes, else None."""
        if not scores:
            return None
        top = max(scores, key=scores.get)
        if self.leader not in scores:  # first look (or the leader vanished): no alert
            self.leader, self.cand, self.n = top, None, 0
            return None
        if top == self.leader or scores[top] - scores[self.leader] < self.margin:
            self.cand, self.n = None, 0
            return None
        if self.cand != top:
            self.cand, self.n = top, 0
        self.n += 1
        if self.n < self.polls:
            return None
        old, self.leader, self.cand, self.n = self.leader, top, None, 0
        return top, old


# ---------- the notifier ----------
class Notifier:
    def __init__(self, arena, db, control, cfg, channels, clock=time.time):
        self.arena, self.db, self.control, self.cfg, self.channels, self.clock = arena, db, control, cfg, channels, clock
        self.started = clock()
        self.stop = threading.Event()
        # don't replay history: start from what's already in the database
        self.last_trade_id = max((t["id"] for t in db.trades(1)), default=0)
        self.last_decision_id = max((d["id"] for d in db.decisions(1)), default=0)
        self.pos_values = {}          # (agent, token) -> value at the previous poll
        self.race, self.team_race = Race(), Race()
        self.usage_state = {}         # window kind -> {"reset": resets_at, "fired": set of thresholds}
        self.once_at = {}             # dedupe key -> when it last fired
        self.stalled_since = None
        self._ticks = (None, self.started)
        self.last_digest_day = None
        self.held = []                # alerts waiting to go out (burst, rate limit, or channels down)
        self.sent = deque()           # send times in the last hour
        self.limited = False

    # ----- helpers -----
    def _once(self, key, period):
        now = self.clock()
        if now - self.once_at.get(key, -1e12) < period:
            return False
        self.once_at[key] = now
        if len(self.once_at) > 2000:
            self.once_at = {k: t for k, t in self.once_at.items() if now - t < 86400}
        return True

    def _when(self, ts):
        if not ts:
            return "unknown"
        t, now = datetime.fromtimestamp(ts), datetime.fromtimestamp(self.clock())
        return t.strftime("%H:%M") if t.date() == now.date() else t.strftime("%a %H:%M")

    def _quiet(self, now):
        if not self.cfg.quiet:
            return False
        s, e = self.cfg.quiet
        local = datetime.fromtimestamp(now)
        m = local.hour * 60 + local.minute
        return s <= m < e if s < e else (m >= s or m < e)

    def _snapshot(self, now):
        if not self.arena.lock.acquire(timeout=15):
            if self._once("log:lock", 600):
                print(f"{LOG} the arena is busy; skipping this poll")
            return None
        try:
            eq, pos, kinds, teams = {}, {}, {}, {}
            for name, agent in self.arena.agents.items():
                kinds[name] = agent.kind
                teams[name] = agent.team_name() if hasattr(agent, "team_name") else ("claude" if agent.kind == "llm" else "bots")
                v = self.arena.view(name, now)
                eq[name] = v.get("score_equity", v["equity"])  # lost lives count
                for p in v["positions"]:
                    pos[(name, p["token"])] = (p["symbol"], p["value"], p["cost"])
        finally:
            self.arena.lock.release()
        return {"equity": eq, "positions": pos, "kinds": kinds, "teams": teams}

    # ----- checks: each returns a list of alerts -----
    def _check_trades(self, now):
        new = [t for t in self.db.trades(300) if t["id"] > self.last_trade_id]
        if not new:
            return []
        self.last_trade_id = max(t["id"] for t in new)
        want_trade, want_rug, out = "trade" in self.cfg.events, "rug" in self.cfg.events, []
        for t in reversed(new):  # oldest first
            if t["side"] != "sell" or t["pnl"] is None:
                continue
            pnl, agent, sym = t["pnl"], t["agent"], t["symbol"] or "?"
            cost = (t["usd"] or 0) - pnl
            pct = pnl / cost * 100 if cost > 0 else 0.0
            reason = (t["reason"] or "").strip().replace("\n", " ")[:90]
            if want_rug and cost > 0 and pnl <= -RUG_SELL_FRAC * cost:
                if self._once(f"rug:{agent}:{t['token']}", 3600):
                    out.append(Alert("rug", f"{agent} sold {sym} for {signed(pnl)} ({pct:+.0f}%)" + (f" ({reason})" if reason else ""),
                                     now, critical=-pnl >= CRITICAL_RUG_USD, tags=("rotating_light",)))
                continue
            if want_trade and abs(pnl) >= self.cfg.min_pnl:
                detail = f" ({reason})" if reason else f" ({pct:+.0f}% on {money(cost)})"
                out.append(Alert("trade", f"{agent} sold {sym} for {signed(pnl)}{detail}", now,
                                 tags=("moneybag",) if pnl >= 0 else ("chart_with_downwards_trend",)))
        return out

    def _check_positions(self, snap, now):
        out, current = [], snap["positions"]
        for key, (sym, value, cost) in current.items():
            pv = self.pos_values.get(key)
            if pv is None or pv < 1.0:  # new position, or dust
                continue
            if value <= (1 - RUG_DROP_FRAC) * pv and self._once(f"rug:{key[0]}:{key[1]}", 3600):
                drop = (1 - value / pv) * 100 if pv else 100
                out.append(Alert("rug", f"{key[0]}'s {sym} position fell {drop:.0f}% since the last check, "
                                        f"{money(pv)} to {money(value)}", now,
                                 critical=pv - value >= CRITICAL_RUG_USD, tags=("rotating_light",)))
        self.pos_values = {k: v[1] for k, v in current.items()}
        return out

    def _check_leader(self, snap, now):
        eq = snap["equity"]
        change = self.race.update(eq)
        if not change:
            return []
        new, old = change
        return [Alert("leader", f"{new} takes the lead with {money(eq[new])}, {money(eq[new] - eq[old])} ahead of {old}",
                      now, tags=("trophy",))]

    def _check_teams(self, snap, now):
        avg = team_averages(snap)
        if len(avg) < 2:
            return []
        change = self.team_race.update(avg)
        if not change:
            return []
        new, old = change
        return [Alert("team", f"{new} takes the lead, {money(avg[new])} vs {money(avg[old])} per agent for {old}", now,
                      tags=("crossed_swords",))]

    def _check_busts(self, now):
        """A Claude lost a life (or its last one). Counts are remembered from the first poll, so a restart never re-alerts."""
        out, seen = [], self.__dict__.setdefault("bust_seen", {})
        for name, acct in list(self.arena.accounts.items()):
            busts = acct.get("busts") or []
            before, seen[name] = seen.get(name), len(busts)
            if before is None or len(busts) <= before:
                continue
            info = self.arena.lives_info(name) if hasattr(self.arena, "lives_info") else None
            left = info["lives_left"] if info else max(0, getattr(self.arena, "lives", 3) - len(busts))
            text = (f"{name} went bust with {money(busts[-1].get('equity', 0))} left: "
                    + ("out of lives for this run" if acct.get("out") else f"{left} {'life' if left == 1 else 'lives'} left"))
            out.append(Alert("bust", text, now, critical=bool(acct.get("out")), tags=("skull",)))
        return out

    def _check_usage(self, now):
        out = []
        for w in (self.control.plan() or {}).get("windows") or []:
            pct, kind, reset = w.get("pct"), w.get("kind"), w.get("resets_at")
            if pct is None or kind is None:
                continue
            st = self.usage_state.get(kind)
            rolled = st is not None and ((reset and st["reset"] and abs(reset - st["reset"]) > 120)
                                         or (st["fired"] and pct < min(st["fired"]) - 15))
            if st is None:  # first reading: remember what's already passed, don't alert on it
                self.usage_state[kind] = {"reset": reset, "fired": {s for s in USAGE_STEPS if pct >= s}}
                continue
            if rolled:
                st = self.usage_state[kind] = {"reset": reset, "fired": set()}
            st["reset"] = reset or st["reset"]
            crossed = [s for s in USAGE_STEPS if pct >= s and s not in st["fired"]]
            if not crossed:
                continue
            st["fired"].update(crossed)
            top = max(crossed)
            text = f"{w.get('label') or kind} at {pct:.0f}% (past {top}%)"
            if reset:
                text += f", resets {self._when(reset)}"
            if w.get("full_at"):
                text += f"; full by {self._when(w['full_at'])} at this pace"
            out.append(Alert("usage", text, now, critical=top >= 90, tags=("warning",) if top >= 90 else ("hourglass_flowing_sand",)))
        return out

    def _check_errors(self, now):
        new = [d for d in self.db.decisions(80) if d["id"] > self.last_decision_id]
        if not new:
            return []
        self.last_decision_id = max(d["id"] for d in new)
        groups = {}
        for d in reversed(new):
            err = (d.get("error") or "").strip()
            if not err or not LIMIT_ERROR.search(err):
                continue
            key = re.sub(r"\d+", "#", err.lower())[:200]
            text, agents = groups.setdefault(key, (err, []))
            if d["agent"] not in agents:
                agents.append(d["agent"])
        out = []
        for key, (err, agents) in groups.items():
            if not self._once(f"err:{key}", 3600):
                continue
            who = agents[0] if len(agents) == 1 else (" and ".join(agents) if len(agents) == 2
                                                      else f"{', '.join(agents[:2])} and {len(agents) - 2} more")
            out.append(Alert("error", f"{who} hit a login or usage-limit error: {err.replace(chr(10), ' ')[:160]}", now, tags=("x",)))
        return out

    def _last_tick(self, now):
        """When the arena last wrote equity (its last completed tick)."""
        try:
            with self.db.lock:
                return self.db.conn.execute("SELECT MAX(ts) FROM equity").fetchone()[0]
        except Exception:  # unusual DB: watch the tick counter instead
            ticks = getattr(self.arena, "ticks", None)
            if ticks != self._ticks[0]:
                self._ticks = (ticks, now)
            return self._ticks[1]

    def _check_stall(self, now):
        last = self._last_tick(now)
        if self.stalled_since is None:
            ref = max(last or 0, self.started)  # a gap from before this start isn't a stall
            if now - ref > STALL_AFTER:
                self.stalled_since = ref
                return [Alert("stall", f"Arena stalled: no tick for {(now - ref) / 60:.0f} minutes (last at {self._when(ref)})",
                              now, critical=True, tags=("zzz",))]
            return []
        if last and last > self.stalled_since:
            gap, self.stalled_since = last - self.stalled_since, None
            return [Alert("stall", f"Arena recovered: ticking again after {max(gap, STALL_AFTER) / 60:.0f} minutes without ticks",
                          now, critical=True, tags=("white_check_mark",), title="Arena recovered")]
        return []

    def _check_digest(self, snap, now):
        local = datetime.fromtimestamp(now)
        h, m = self.cfg.digest_at
        due = local.replace(hour=h, minute=m, second=0, microsecond=0)
        if local < due or self.last_digest_day == local.date():
            return []
        self.last_digest_day = local.date()
        if self.started > due.timestamp():  # started after today's digest time: the first one is tomorrow's
            return []
        return [Alert("digest", self._digest_text(snap, now), now, tags=("bar_chart",))]

    def _digest_text(self, snap, now):
        eq, kinds, start = snap["equity"], snap["kinds"], self.arena.start_cash or 1.0
        lines = [f"{i}. {n} {money(e)} ({(e / start - 1) * 100:+.1f}%)"
                 for i, (n, e) in enumerate(sorted(eq.items(), key=lambda kv: -kv[1]), 1)]
        avg = team_averages(snap)
        if len(avg) > 1:
            lines.append("Per agent: " + ", ".join(f"{t} {money(e)} ({(e / start - 1) * 100:+.1f}%)"
                                                   for t, e in sorted(avg.items(), key=lambda kv: -kv[1])))
        day = [t for t in self.db.trades(3000) if (t["ts"] or 0) >= now - 86400]
        sells = [t for t in day if t["side"] == "sell" and t["pnl"] is not None]
        if sells:
            best, worst = max(sells, key=lambda t: t["pnl"]), min(sells, key=lambda t: t["pnl"])
            lines.append(f"Last 24h: {len(day)} trades, {len(sells)} closed. Best {best['agent']} {best['symbol']} "
                         f"{signed(best['pnl'])}, worst {worst['agent']} {worst['symbol']} {signed(worst['pnl'])}.")
        else:
            lines.append(f"Last 24h: {len(day)} trades, none closed.")
        wins = [w for w in (self.control.plan() or {}).get("windows") or [] if w.get("pct") is not None]
        if wins:
            lines.append("Usage: " + ", ".join(f"{(w.get('label') or w['kind'])[:1].lower()}{(w.get('label') or w['kind'])[1:]} "
                                               f"{w['pct']:.0f}%" for w in wins))
        try:
            import analytics
            verdicts = [f"{a['name']} {a['readiness']['passed']}/{a['readiness']['total']}"
                        for a in analytics.compute(self.arena, self.db, getattr(self, "control", None))["agents"]
                        if a.get("readiness") and getattr(self.arena.agents.get(a["name"]), "kind", None) == "llm"]
            if verdicts:
                lines.append("Verdicts: " + ", ".join(verdicts))
        except Exception:
            pass
        return "\n".join(lines)

    # ----- sending -----
    def _compose(self, alerts, now):
        prio = 4 if any(a.critical for a in alerts) else 3
        if len(alerts) == 1:
            a = alerts[0]
            return a.title or TITLES[a.kind], a.text, prio, a.tags
        kinds = {a.kind for a in alerts}
        span = now - min(a.at for a in alerts)
        when = "in the last minute" if span <= 90 else f"in the last {span / 60:.0f} minutes"
        what = PLURALS[next(iter(kinds))] if len(kinds) == 1 else "alerts"
        tags = tuple(dict.fromkeys(t for a in alerts for t in a.tags))
        return f"{len(alerts)} {what} {when}", "\n".join(a.text for a in alerts), prio, tags

    def _dispatch(self, alerts, now):
        if self._quiet(now):
            alerts = [a for a in alerts if a.critical or a.kind == "digest"]
        self.held.extend(alerts)
        del self.held[:-60]
        if not self.held:
            return False
        while self.sent and now - self.sent[0] >= 3600:
            self.sent.popleft()
        if len(self.sent) >= self.cfg.max_per_hour:
            if not self.limited:
                print(f"{LOG} {self.cfg.max_per_hour} messages in the last hour; holding alerts and sending one summary later")
                self.limited = True
            return False
        title, body, prio, tags = self._compose(self.held, now)
        ok = False
        for ch in self.channels:
            ok = ch.send(title, body, prio, tags, now) or ok
        if ok:
            self.held, self.limited = [], False
            self.sent.append(now)
        return ok

    # ----- loop -----
    def poll(self):
        now, ev, alerts = self.clock(), self.cfg.events, []

        def run(name, fn, *args):
            try:
                alerts.extend(fn(*args) or [])
            except Exception as e:
                if self._once(f"log:{name}", 600):
                    print(f"{LOG} {name} check failed: {e}")
                    traceback.print_exc()

        snap = None
        if ev & {"rug", "leader", "team", "digest"}:
            try:
                snap = self._snapshot(now)
            except Exception as e:
                if self._once("log:snapshot", 600):
                    print(f"{LOG} couldn't read the arena: {e}")
        if ev & {"trade", "rug"}:
            run("trade", self._check_trades, now)
        if snap:
            if "rug" in ev:
                run("rug", self._check_positions, snap, now)
            if "leader" in ev:
                run("leader", self._check_leader, snap, now)
            if "team" in ev:
                run("team", self._check_teams, snap, now)
        if "usage" in ev:
            run("usage", self._check_usage, now)
        if "error" in ev:
            run("error", self._check_errors, now)
        if "stall" in ev:
            run("stall", self._check_stall, now)
        if "bust" in ev:
            run("bust", self._check_busts, now)
        if "digest" in ev and snap:
            run("digest", self._check_digest, snap, now)
        self._dispatch(alerts, now)
        return alerts

    def run_forever(self):
        while not self.stop.is_set():
            try:
                self.poll()
            except Exception as e:
                print(f"{LOG} poll failed: {e}")
                traceback.print_exc()
            self.stop.wait(self.cfg.poll)


_instance = None


def start(arena, db, control, env=None):
    """Called by main.py. Starts the alert thread if a channel is configured; returns the Notifier or None."""
    global _instance
    cfg = Config(env)
    for w in cfg.warnings:
        print(f"{LOG} {w}")
    channels = build_channels(cfg)
    if not channels:
        print(f"{LOG} phone alerts off. Put ARENA_NTFY_TOPIC=<topic> or ARENA_DISCORD_WEBHOOK=<url> in .env to turn them on "
              f"(setup steps at the top of notifier.py)")
        return None
    if requests is None:
        print(f"{LOG} the requests package is missing (pip install -r requirements.txt); alerts off")
        return None
    if not cfg.events:
        print(f"{LOG} ARENA_ALERTS turned every alert type off; nothing to send")
        return None
    n = Notifier(arena, db, control, cfg, channels)
    threading.Thread(target=n.run_forever, name="notifier", daemon=True).start()
    quiet = ""
    if cfg.quiet:
        quiet = f"; quiet {cfg.quiet[0] // 60:02d}:{cfg.quiet[0] % 60:02d}-{cfg.quiet[1] // 60:02d}:{cfg.quiet[1] % 60:02d}"
    print(f"{LOG} phone alerts on via {', '.join(c.name for c in channels)}: {', '.join(e for e in EVENTS if e in cfg.events)}"
          f"; digest at {cfg.digest_at[0]:02d}:{cfg.digest_at[1]:02d}{quiet}; max {cfg.max_per_hour}/hour")
    _instance = n
    return n


def _send_test():
    """`python notifier.py`: send one test message to the channels configured in .env."""
    try:
        from main import load_dotenv
        load_dotenv()
    except Exception:
        pass
    cfg = Config()
    for w in cfg.warnings:
        print(f"{LOG} {w}")
    channels = build_channels(cfg)
    if not channels:
        print(f"{LOG} nothing configured: set ARENA_NTFY_TOPIC or ARENA_DISCORD_WEBHOOK in .env first")
        return 1
    if requests is None:
        print(f"{LOG} pip install -r requirements.txt first (the requests package is missing)")
        return 1
    ok = True
    for ch in channels:
        sent = ch.send("Arena test", f"Phone alerts are working. Sent {datetime.now():%H:%M}.", 3, ("white_check_mark",), time.time())
        print(f"{LOG} {ch.name}: {'sent' if sent else 'failed'}")
        ok = ok and sent
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_send_test())
