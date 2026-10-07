"""The arena: refreshes the market, fills last tick's orders, asks every agent for new ones, records equity.

Between the 30-second ticks the arena also runs cheap "fast" exit checks (fast_step): it refreshes prices for
the HELD tokens only, fills exits that tripped on the previous fast check, and checks stops / targets /
trailing stops again. No agent is asked for a decision and no equity point is recorded on a fast check;
agents' own orders still fill on the next full tick, as documented.

Settings (environment variables, read when the Arena is built):
  ARENA_FAST_EXIT_SECS=10   seconds between fast exit checks inside a tick (0 disables them). Each check costs
                            one DexScreener request per 30 held tokens in the live market and nothing in the mock.
  ARENA_SHADOW_LEADERS=10   how many top wallets a shadow trader follows (its leader set, re-picked every 6 hours).
  ARENA_LLM_MAX_BUYS_PER_DAY=6, ARENA_LLM_MIN_BUY_USD=50, ARENA_LLM_BUY_COOLDOWN_MIN=30   churn control for Claudes (not bots): at most
                            this many buys in a rolling 24 hours, none smaller than the minimum, this many minutes between
                            buys (0 turns a rule off). A refused buy is listed in acct["recent_failures"] with the reason.
Execution friction (failed transactions, MEV slippage, fees) is configured in exchange.py; Jupiter quotes in
market.py. A failed transaction trades nothing, costs the network fee, is counted in acct["failed"] and
listed in acct["recent_failures"], which view() passes to agents as "recent_failures".

Points and lives. Real P&L (score_equity) subtracts every extra stake, so a bust stays a loss there; it is what
the charts, standings and analytics use. Claudes get ARENA_LIVES=3 lives: under ARENA_BUST_PCT=10 % of the starting
cash a Claude goes bust, everything it holds is sold and it gets a fresh stake; with no lives left it is out for
the run. Its POINTS (the game score it is ranked on) are its profit across lives with losses weighted by life
(ARENA_LIFE_LOSS_WEIGHTS=0.5,0.75,1: a first-life loss counts half), and every time a life first reaches
+ARENA_MILESTONE_PCT=25 % above where it started (+25, +50, ...) it earns a lost life back, or
ARENA_MILESTONE_BONUS=10 points with every life intact. Bots and copy bots have one stake, no busts, points = P&L %.
The strategy room (strategy_room.py) is the Claudes' shared chat about getting better; posts naming a coin are blocked.
"""
import os
import random
import json
import os
import threading
import time
import traceback
from collections import deque

import market_memory
import signals as sig  # structural signals and safety vetoes (named so it can't clash with tracker.signals())
import strategy_room

from exchange import PRIORITY_FEE_USD, buy_fill, early_penalty, fail_probability, liquidation_value, mev_slippage, sell_fill

# Exit plans an agent can attach to a position. Stops and targets compare the market price with the average
# entry price (trailing: with the highest price since buying) and sell the whole position on the next tick,
# like a trigger order on a Solana trading bot. Wake alarms compare with the price when they were set.
EXIT_FIELDS = ("stop_loss_pct", "take_profit_pct", "trailing_pct", "wake_down_pct", "wake_up_pct")
SIGNS = {"stop_loss_pct": -1, "take_profit_pct": 1, "trailing_pct": 1, "wake_down_pct": -1, "wake_up_pct": 1}
LIVES = max(1, int(os.environ.get("ARENA_LIVES", "3") or 3))
BUST_PCT = float(os.environ.get("ARENA_BUST_PCT", "10") or 10)
LOSS_WEIGHTS = [float(x) for x in (os.environ.get("ARENA_LIFE_LOSS_WEIGHTS", "0.5,0.75,1") or "1").split(",") if x.strip()] or [1.0]
MILESTONE_PCT = float(os.environ.get("ARENA_MILESTONE_PCT", "25") or 0)
MILESTONE_BONUS = float(os.environ.get("ARENA_MILESTONE_BONUS", "10") or 0)


# Moonshots: each Claude may hold MOONSHOT_SLOTS small positions aimed at runners ("moonshot": true on a buy), at most
# MOONSHOT_PCT % of equity each, whose stops the arena keeps wide. Closing ANY position at 3x+ of what it cost pays
# runner bonus points (RUNNER_BONUS "multiple:points" tiers, the highest tier reached counts).
MOONSHOT_SLOTS = max(0, int(os.environ.get("ARENA_MOONSHOT_SLOTS", "2") or 0))
MOONSHOT_PCT = float(os.environ.get("ARENA_MOONSHOT_PCT", "5") or 5)
MOONSHOT_MIN_STOP = abs(float(os.environ.get("ARENA_MOONSHOT_MIN_STOP", "50") or 50))
MOONSHOT_MIN_TRAIL = abs(float(os.environ.get("ARENA_MOONSHOT_MIN_TRAIL", "40") or 40))
RUNNER_BONUS = sorted((float(m), float(p)) for m, p in (x.split(":") for x in
                      (os.environ.get("ARENA_RUNNER_BONUS", "3:5,5:10,10:20") or "").split(",") if ":" in x))


def runner_bonus(multiple):
    """Bonus points for closing a position at `multiple` x its cost (0 below the lowest tier)."""
    return max([p for m, p in RUNNER_BONUS if multiple >= m], default=0.0)


# The exit ladder the research recommends (practitioner consensus: take the stake out at 2x, scale out on the way up,
# trail the rest, exit on events), run by the arena on every Claude position. ARENA_MANAGED_EXITS=0 turns it off.
MANAGED_EXITS = os.environ.get("ARENA_MANAGED_EXITS", "1").strip().lower() not in ("0", "off", "false", "no")
LADDER = [(2.0, 0.5), (3.0, 1 / 3), (5.0, 1 / 3), (10.0, 0.5)]   # (multiple of entry, fraction of what's left to sell)
LADDER_TRAIL = [(10.0, 15.0), (5.0, 20.0), (2.0, 30.0)]          # (peak multiple reached, trailing % below the peak)
TIME_STOP_H = float(os.environ.get("ARENA_TIME_STOP_H", "6") or 6)
LIQ_EXIT = 0.5          # sell everything when the pool's liquidity falls under half of what it was at entry
CREATOR_SELL_USD = float(os.environ.get("ARENA_CREATOR_SELL_USD", "100") or 100)
# Churn control for Claudes (bots are exempt): every round trip costs about 5 % in fees and slippage, so a Claude may make at
# most MAX_BUYS_PER_DAY buys in any rolling 24 hours, none under MIN_BUY_USD, and must wait BUY_COOLDOWN_MIN minutes between buys.
MAX_BUYS_PER_DAY = max(0, int(os.environ.get("ARENA_LLM_MAX_BUYS_PER_DAY", "6") or 0))
MIN_BUY_USD = max(0.0, float(os.environ.get("ARENA_LLM_MIN_BUY_USD", "50") or 0))
BUY_COOLDOWN_MIN = max(0.0, float(os.environ.get("ARENA_LLM_BUY_COOLDOWN_MIN", "30") or 0))
SHADOW_LEADERS = int(os.environ.get("ARENA_SHADOW_LEADERS", "10") or 10)  # wallets in a shadow trader's leader set


def ladder_text():
    """The exit ladder in one sentence for the Claudes' brief."""
    if not MANAGED_EXITS:
        return "off in this arena: your own exits are the only ones."
    (m0, f0), rest = LADDER[0], LADDER[1:]
    rungs = f"{f0 * 100:.0f}% of a position at {m0:g}x your entry price, then " + ", ".join(
        f"{f * 100:.0f}% of what's left at {m:g}x" for m, f in rest)
    trail = ", ".join(f"{t:g}% below the peak after {m:g}x" for m, t in sorted(LADDER_TRAIL))
    return (f"the arena sells {rungs}; once a position has doubled, a trailing stop protects the rest "
            f"({trail}); and it sells everything if the position makes no new high for {TIME_STOP_H:g} hours, if the "
            f"creator sells, or if the pool's liquidity falls below half of what it was when you bought.")


def ago_text(secs):
    """'just now', '4 min ago', '2.1 h ago'"""
    return "just now" if secs < 45 else f"{secs / 60:.0f} min ago" if secs < 3600 else f"{secs / 3600:.1f} h ago"


def loss_weight(life):
    """How much a loss in life number `life` (1-based) counts toward points."""
    return LOSS_WEIGHTS[min(life, len(LOSS_WEIGHTS)) - 1]


JOURNAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal_backups")


def backup_journals(db, why, equity=None):
    """Write every Claude journal to journal_backups/<date>_<time>.json (kept even by a full --reset), for learning.
    Returns the file path, or None when there are no journals."""
    journals = db.journals()
    if not journals:
        return None
    os.makedirs(JOURNAL_DIR, exist_ok=True)
    path = os.path.join(JOURNAL_DIR, time.strftime("%Y-%m-%d_%H%M%S") + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"saved": time.strftime("%Y-%m-%d %H:%M:%S"), "why": why,
                   "agents": {a: {"journal": j, "equity": round(equity[a], 2) if equity and a in equity else None}
                              for a, j in journals.items()}}, f, indent=2, ensure_ascii=False)
    return path


class Arena:
    def __init__(self, market, db, agents, start_cash=1000.0, tick=30, clock=None, fast_exit_secs=None):
        self.market, self.db, self.tick = market, db, tick
        self.clock = clock or time.time  # replay.py passes a simulated clock
        self.agents = {a.name: a for a in agents}
        self.start_cash = start_cash
        self.lives = LIVES                           # Claudes only
        self.bust_usd = start_cash * BUST_PCT / 100  # equity under this = bust
        self.pending = []
        self.started = self.clock()
        self.ticks = 0
        self.fast_ticks = 0
        self.lock = threading.Lock()
        self.rng = random.Random()  # for failed transactions; tests may seed or replace it
        if fast_exit_secs is None:
            try:
                fast_exit_secs = float(os.environ.get("ARENA_FAST_EXIT_SECS", "10"))
            except ValueError:
                fast_exit_secs = 10.0
        self.fast_exit_secs = max(0.0, fast_exit_secs)
        self.accounts = {}
        for name, agent in self.agents.items():
            self.accounts[name] = db.load_state(name) or {
                "cash": start_cash, "positions": {}, "recent_sells": {}, "realized": 0.0}
            self.accounts[name].setdefault("exits", {})
            self.accounts[name].setdefault("failed", 0)
            self.accounts[name].setdefault("recent_failures", [])
            agent.note = db.last_note(name) or agent.note
            agent.attach(db)  # lets Claude agents load their saved journal
        self.history = {}  # token -> deque of (ts, price), one point per tick, about an hour
        self._drift = {}   # token -> price multiplier from fills earlier in the current batch
        self.tracker = None  # traders.Tracker (top-100 leaderboard and copy signals), set by main.py
        self.memory = market_memory.MarketMemory() if market_memory.ENABLED else None
        self.run_started = db.load_state("__run_started__") or self.started  # survives restarts; reset_money moves it
        self.liq_history = {}   # token -> deque of (ts, liquidity), for liquidity_vs_1h and the liquidity exit
        self.curve_history = {}  # pump.fun curve coin -> deque of (ts, curve_pct), for curve_pct_10m
        self.vetoes = {}        # token -> reasons a buy is refused (signals.veto_report), refreshed every SIGNALS_SECS
        self.structure = {}     # token -> compact structural view shown to the Claudes
        self.creator_sold = {}  # token -> dollars its creator sold in the last hour (the exit ladder sells on it)
        self._signals_at = 0.0
        if hasattr(market, "risk_cache"):
            market.risk_cache.update(db.load_state("__risk_cache__") or {})

    # ---------- helpers ----------
    def held(self):
        return {a for acct in self.accounts.values() for a in acct["positions"]}

    def _token_for(self, addr, pos=None):
        t = self.market.get(addr)
        if t:
            if pos is not None:
                pos["last_price"], pos["last_liq"] = t["price"], t["liquidity"]
            return t
        if pos and pos.get("last_price"):  # token dropped out of the feed: use last known numbers
            return {"price": pos["last_price"], "liquidity": pos.get("last_liq", 0), "symbol": pos["symbol"],
                    "rating": "red", "flags": ["no longer in market feed"]}
        return None

    def record_prices(self, now):
        for t in self.market.candidates():
            self.history.setdefault(t["address"], deque(maxlen=130)).append((now, t["price"]))
            if t.get("liquidity"):
                self.liq_history.setdefault(t["address"], deque(maxlen=300)).append((now, t["liquidity"]))
            pump = t.get("pump") or {}
            if pump.get("curve_pct") is not None and not pump.get("graduated"):
                self.curve_history.setdefault(t["address"], deque(maxlen=130)).append((now, pump["curve_pct"]))
        if self.ticks % 120 == 0:  # forget tokens the feed dropped over an hour ago
            self.history = {a: h for a, h in self.history.items() if now - h[-1][0] < 3600}
            self.liq_history = {a: h for a, h in self.liq_history.items() if now - h[-1][0] < 3600}
            self.curve_history = {a: h for a, h in self.curve_history.items() if now - h[-1][0] < 3600}

    SIGNALS_SECS = 60  # the pool feed behind the flow signals only changes when a pool is polled (every few minutes)

    def update_signals(self, now, force=False):
        """Recompute vetoes, structure and creator selling for every tracked token (signals.py), at most every
        SIGNALS_SECS. Never raises: on any error the previous values stay."""
        if not force and now - self._signals_at < self.SIGNALS_SECS:
            return
        self._signals_at = now
        try:
            cands = list(self.market.candidates())
            flows = sig.flow_signals(self.db, [t["address"] for t in cands], now)
            creators = {}
            for t in cands:
                c = (t.get("rug") or {}).get("creator") or (t.get("pump") or {}).get("creator")
                if c:
                    creators[t["address"]] = c
            sold = sig.creator_selling(self.db, creators, now - 3600) if creators else {}
            vetoes, structure = {}, {}
            for t in cands:
                a = t["address"]
                mig = sig.minutes_since_graduation(t, now)
                rep_ = sig.veto_report(t, flows.get(a), now, sold.get(a), mig)
                if rep_["vetoes"]:
                    vetoes[a] = rep_["vetoes"]
                trend = sig.liquidity_trend(list(self.liq_history.get(a, ())))
                structure[a] = sig.structural_view(t, flows.get(a), trend, mig, sold.get(a), now)
            self.vetoes, self.structure, self.creator_sold = vetoes, structure, sold
        except Exception as e:
            print(f"[arena] signals failed (keeping the last ones): {e}")

    def warm_history(self, snap):
        """Fill the 30-second price history from one recorded snapshot (startup), so charts aren't empty after a restart."""
        for t in snap.tokens:
            if t.get("address") and t.get("price"):
                self.history.setdefault(t["address"], deque(maxlen=130)).append((snap.ts, t["price"]))

    def chg_since(self, addr, now):
        """Price change (%) from 2, 5, 10, 20 and 30 minutes ago to now, from the arena's own price history.
        For a pump.fun coin still on its curve, also curve_pct_10m: its curve_pct about 10 minutes ago."""
        out = {}
        ch = getattr(self, "curve_history", {}).get(addr)
        if ch:
            past = next((c for ts, c in reversed(ch) if now - ts >= 600 - 15), None)
            if past is not None:
                out["curve_pct_10m"] = past
        h = self.history.get(addr)
        if not h or len(h) < 2:
            return out
        price = h[-1][1]
        for m in (2, 5, 10, 20, 30):
            past = next((p for ts, p in reversed(h) if now - ts >= m * 60 - 15), None)
            if past:
                out[f"{m}m"] = round((price / past - 1) * 100, 1)
        # swing_30m: the typical 2-minute move (std, %) over the last 30 minutes, from every 4th 30-second point
        recent = [p for ts, p in h if now - ts <= 1800][::-1][::4][::-1]
        moves = [(b / a - 1) * 100 for a, b in zip(recent, recent[1:]) if a > 0]
        if len(moves) >= 5:
            mean = sum(moves) / len(moves)
            out["swing_30m"] = round((sum((x - mean) ** 2 for x in moves) / len(moves)) ** 0.5, 1)
        return out

    def smart_money(self, now):
        """The top-100 traders' recent trades, newest first, compact enough for a Claude's look."""
        if not self.tracker:
            return None
        try:
            sigs = self.tracker.signals(now - 1800)[-25:]
        except Exception:
            return None
        return [{"rank": s.get("rank"), "side": s.get("side"), "symbol": s.get("symbol"), "token": s.get("mint"),
                 "usd": round(s.get("usd") or 0), "min_ago": round((now - s["ts"]) / 60, 1),
                 "latency": "seconds" if s.get("source") == "helius" else "minutes"} for s in reversed(sigs)]

    def round_trip(self, now):
        """What a normal round trip costs the Claudes, in % (cached 10 minutes): the median buy cost plus the median
        sell cost of the Claudes' own fills over the last 24 hours, leaving out forced exits (stops and crash exits gap
        below the screen price; that's a trading loss, not a cost), or, until there are enough fills, the fee-and-impact
        estimate for a typical Claude position ($70 in a $30k pool)."""
        at, val = getattr(self, "_rt", (0, None))
        if now - at > 600:
            claudes = [n for n, a in self.agents.items() if a.kind == "llm"]
            val = self.db.typical_round_trip(now - 86400, agents=claudes) if claudes else None
            if val is None:
                from exchange import round_trip_pct
                val = round(round_trip_pct(70, 30000), 1)
            self._rt = (now, val)
        return val

    def reset_money(self, keep_journals):
        """Everyone back to the starting cash with no positions. Trades and equity are archived as a season, every
        Claude journal is backed up to a file first (learning data), and journals are kept or wiped as asked.
        Returns {"season", "backup", "journals"}."""
        with self.lock:
            now = self.clock()
            backup = backup_journals(self.db, f"before money reset {time.strftime('%Y-%m-%d %H:%M', time.localtime(now))}",
                                     {n: self.score_equity(n) for n in self.agents})
            season = self.db.reset_money()
            self.pending = []
            for name, agent in self.agents.items():
                self.accounts[name] = {"cash": self.start_cash, "positions": {}, "recent_sells": {}, "realized": 0.0,
                                       "exits": {}, "failed": 0, "recent_failures": []}
                self.db.save_state(name, self.accounts[name])
                if agent.kind == "llm":
                    agent.ready = None  # an answer still in flight was about the old portfolio
                    if not keep_journals:
                        agent.set_journal([])
            self.started, self.ticks = now, 0
            self.run_started = now
            self.db.save_state("__run_started__", now)
            if strategy_room.ENABLED:
                self.db.add_room_post(now, "arena", f"Money reset: run {season} was archived and a new run started. Everyone "
                                                    f"has ${self.start_cash:,.0f} again and every Claude has {self.lives} lives.")
            self.news = (now, f"Every agent was reset to ${self.start_cash:,.0f} at {time.strftime('%H:%M', time.localtime(now))}; "
                              f"your old positions are gone and your journal was {'kept' if keep_journals else 'cleared'}.")
            print(f"[arena] money reset: season {season} archived, journals {'kept' if keep_journals else 'wiped'}, backup {backup}")
            return {"season": season, "backup": backup, "journals": "kept" if keep_journals else "wiped"}

    def market_ready(self, now):
        ready = getattr(self.market, "ready", None)
        return ready() if ready else True

    def llm_context(self, name, now):
        """Extra things a Claude sees on each look: price paths, its own recent results, the scoreboard."""
        board = sorted(({"name": n, "team": a.team_name() if hasattr(a, "team_name") else ("claude" if a.kind == "llm" else "bots"),
                         "points": round(self.points(n), 1), "pnl_pct": round(self.pnl_pct(n), 1),
                         **({"lives_left": self.lives_info(n)["lives_left"]} if a.kind == "llm" else {}),
                         **({"out": True} if self.accounts[n].get("out") else {})}
                        for n, a in self.agents.items()), key=lambda r: -r["points"])
        return {"chg_since": {t["address"]: self.chg_since(t["address"], now) for t in self.market.candidates()},
                "recent_closed": self.db.recent_sells(name), "scoreboard": board,
                "your_score": self.your_score(name, board, now),
                "structure": self.structure,
                **({"your_leaders": self.leader_view(name, now)} if getattr(self.agents[name], "persona", None) == "shadow" else {}),
                "strategy_room": self.room_view(name, now),
                "market_memory": self.memory.stats(now, self.round_trip(now)) if self.memory else None,
                "measured_round_trip_cost_pct": self.round_trip(now),
                "smart_money": self.smart_money(now),
                "arena_news": self.news[1] if getattr(self, "news", None) and now - self.news[0] < 3600 else None,
                # ARENA_MARKET_MEMORY=0 also hides past trades, so a replay can reproduce the older behaviour
                "token_history": self.db.token_history(name, now - 86400) if self.memory else {}}

    def check_watch(self, now):
        """The market watcher: every tick, wake Claude agents whose watch rules match a token, or whose
        held token drops 15% in 5 minutes. Free: no model call unless something matches."""
        cands = self.market.candidates()
        for name, agent in self.agents.items():
            if agent.kind != "llm" or self.accounts[name].get("out"):
                continue
            rule, held, seen = agent.watch_rule(), self.accounts[name]["positions"], agent.watch_seen
            hits = []
            for t in cands:
                a = t["address"]
                if now - seen.get(a, 0) < 20 * 60:
                    continue
                if a in held:
                    if t.get("chg_m5", 0) <= -15:
                        hits.append(f"{t['symbol']}, which you hold, is down {t['chg_m5']:.0f}% in 5 min")
                        seen[a] = now
                    continue
                if rule and (rule["min_chg_5m"] <= t.get("chg_m5", 0) <= rule["max_chg_5m"]
                             and t.get("vol_h1", 0) >= rule["min_vol_1h"] and t.get("liquidity", 0) >= rule["min_liquidity"]
                             and (t.get("age_min") or 0) >= rule["min_age_min"] and t.get("rating") in rule["ratings"]):
                    hits.append(f"watcher: {t['symbol']} up {t['chg_m5']:.0f}% in 5 min, ${t['vol_h1']:,.0f} 1h volume, "
                                f"${t['liquidity']:,.0f} liquidity, {t['rating']}")
                    seen[a] = now
            for h in hits[:3]:
                agent.wake(h)

    @staticmethod
    def entry_spot(pos):
        """Average market price paid, before fees and impact (older positions fall back to cost per token)."""
        return pos.get("entry_spot") or (pos["cost"] / pos["qty"] if pos["qty"] else 0)

    def equity(self, name):
        acct = self.accounts[name]
        return acct["cash"] + sum(liquidation_value(self._token_for(a, p), p["qty"]) for a, p in acct["positions"].items())

    # ---------- points and lives ----------
    def score_equity(self, name):
        """Equity for scoring: what the agent holds minus every extra stake it got after going bust, so a bust stays a
        loss on the scoreboard instead of a fresh start. Equal to equity() until the first bust."""
        return self.equity(name) - self.start_cash * (self.accounts[name].get("stakes", 1) - 1)

    def pnl_pct(self, name):
        """Real P&L % across all lives (what would have happened to real money)."""
        return (self.score_equity(name) / self.start_cash - 1) * 100

    def points(self, name):
        """The game score. Bots: their P&L %. Claudes: profit across lives, each life's loss weighted by loss_weight(life)
        (gains count in full), plus milestone bonus points."""
        acct = self.accounts[name]
        if self.agents[name].kind != "llm":
            return self.pnl_pct(name)
        total = 0.0
        for life in acct.get("lives_log", []):
            r = life["result"]
            total += r if r >= 0 else loss_weight(life["life"]) * r
        if not acct.get("out"):  # the life being played now
            r = self.equity(name) - acct.get("life_start", self.start_cash)
            total += r if r >= 0 else loss_weight(len(acct.get("busts", [])) + 1) * r
        return total / self.start_cash * 100 + acct.get("bonus", 0.0) + acct.get("runner_bonus", 0.0)

    def lives_info(self, name):
        """{"lives", "lives_left", "out", "busts"} for a Claude, None for bots (they have no extra lives)."""
        if self.agents[name].kind != "llm":
            return None
        acct = self.accounts[name]
        busts = acct.get("busts", [])
        left = 0 if acct.get("out") else max(0, min(self.lives, self.lives - len(busts) + acct.get("hearts", 0)))
        return {"lives": self.lives, "lives_left": left, "out": bool(acct.get("out")), "busts": list(busts),
                "life": len(busts) + 1, "hearts_earned": acct.get("hearts", 0), "bonus": acct.get("bonus", 0.0),
                "runner_bonus": acct.get("runner_bonus", 0.0)}

    def your_score(self, name, board, now):
        claudes = [r for r in board if self.agents[r["name"]].kind == "llm"]
        info = self.lives_info(name) or {}
        acct = self.accounts[name]
        start = acct.get("life_start", self.start_cash)
        life = info.get("life", 1)
        out = {"points": round(self.points(name), 1), "real_pnl_pct": round(self.pnl_pct(name), 1),
               "rank": next(i for i, r in enumerate(board, 1) if r["name"] == name), "of": len(board),
               "rank_among_claudes": next((i for i, r in enumerate(claudes, 1) if r["name"] == name), None),
               "claudes": len(claudes), "lives_left": info.get("lives_left"), "life": life,
               "losses_count_this_life": f"{loss_weight(life):g}x",
               "this_life_pct": round((self.equity(name) / start - 1) * 100, 1) if start else 0.0,
               "stake_now": round(self.equity(name), 2), "bust_below": round(self.bust_usd, 2)}
        if MOONSHOT_SLOTS:
            out["moonshots_open"] = f"{sum(1 for p in acct['positions'].values() if p.get('moonshot'))} of {MOONSHOT_SLOTS}"
        if acct.get("runner_bonus"):
            out["runner_bonus_points"] = acct["runner_bonus"]
        if MILESTONE_PCT > 0:
            k = len(acct.get("milestones", [])) + 1
            out["next_milestone"] = f"+{k * MILESTONE_PCT:g}% this life (equity ${start * (1 + k * MILESTONE_PCT / 100):,.0f})"
        ev = self.accounts[name].get("life_event")
        if ev and now - ev["ts"] < 2 * 3600:
            out["life_event"] = ev["text"]
        return out

    def check_busts(self, now):
        """A Claude whose equity fell under the bust line loses a life: everything is sold (no failed transactions:
        it is closing out), it gets a fresh stake and is woken to take stock. After its last life it is out for the
        run: no more looks, no more trades. Bots never go bust here; they sit at their low."""
        for name, agent in self.agents.items():
            acct = self.accounts[name]
            if agent.kind != "llm" or acct.get("out") or self.equity(name) >= self.bust_usd:
                continue
            self.pending = [(n, o) for n, o in self.pending if n != name]
            for addr in list(acct["positions"]):
                self.execute(name, {"action": "sell", "token": addr, "fraction": 1.0, "exit": True, "force": True,
                                    "reason": f"bust: equity under ${self.bust_usd:,.0f}, closing everything"}, now)
            left = self.equity(name)
            acct.setdefault("busts", []).append({"ts": now, "equity": round(left, 2)})
            used = len(acct["busts"])
            start = acct.get("life_start", self.start_cash)
            acct.setdefault("lives_log", []).append({"life": used, "start": round(start, 2), "end": round(left, 2),
                                                     "result": round(left - start, 2)})
            acct["exits"], acct["milestones"] = {}, []
            if self.lives - used + acct.get("hearts", 0) <= 0:
                acct["out"] = True
                acct["life_start"] = left
                agent.ready = None
                text = (f"You went bust for the {used}{'st' if used == 1 else 'nd' if used == 2 else 'rd' if used == 3 else 'th'} "
                        f"time and are out of lives: you are out for the rest of this run.")
                post = f"{name} went bust again and is out of lives for this run."
            else:
                acct["stakes"] = acct.get("stakes", 1) + 1
                acct["cash"] += self.start_cash
                acct["life_start"] = left + self.start_cash
                lives_left = self.lives - used + acct.get("hearts", 0)
                text = (f"You went bust: your equity fell under ${self.bust_usd:,.0f}, so everything you held was sold "
                        f"(${left:,.2f} left). You got a fresh ${self.start_cash:,.0f} stake and have {lives_left} "
                        f"{'life' if lives_left == 1 else 'lives'} left. That life's loss counts {loss_weight(used):g}x in "
                        f"your points; losses in your next life count {loss_weight(used + 1):g}x. Take stock of what went "
                        f"wrong and write it in your journal before you trade again.")
                post = f"{name} went bust and lost a life ({lives_left} left)."
                agent.wake("you went bust and lost a life; see your_score")
            acct["life_event"] = {"ts": now, "text": text}
            self.db.save_state(name, acct)
            if strategy_room.ENABLED:
                self.db.add_room_post(now, "arena", post)
            print(f"[arena] {name} BUST #{used}: ${left:,.2f} left" + ("  -> OUT" if acct.get("out") else f"  -> new ${self.start_cash:,.0f} stake"))

    def check_milestones(self, now):
        """Every time a Claude's current life first reaches +MILESTONE_PCT, +2x, ... above where it started (on
        liquidation value), it earns a lost life back, or MILESTONE_BONUS points when it has every life."""
        if MILESTONE_PCT <= 0:
            return
        for name, agent in self.agents.items():
            acct = self.accounts[name]
            if agent.kind != "llm" or acct.get("out"):
                continue
            start = acct.get("life_start", self.start_cash)
            if start <= 0:
                continue
            reached = int(((self.equity(name) / start - 1) * 100) // MILESTONE_PCT)
            done = acct.setdefault("milestones", [])
            for k in range(1, reached + 1):
                if k in done:
                    continue
                done.append(k)
                if self.lives_info(name)["lives_left"] < self.lives:
                    acct["hearts"] = acct.get("hearts", 0) + 1
                    what, short = "earned a life back", "earned a life back"
                else:
                    acct["bonus"] = acct.get("bonus", 0.0) + MILESTONE_BONUS
                    what, short = f"earned {MILESTONE_BONUS:g} bonus points (you already have every life)", f"+{MILESTONE_BONUS:g} bonus points"
                acct["life_event"] = {"ts": now, "text": f"This life reached +{k * MILESTONE_PCT:g}% and you {what}."}
                agent.wake(f"your life reached +{k * MILESTONE_PCT:g}%: {short}")
                if strategy_room.ENABLED:
                    self.db.add_room_post(now, "arena", f"{name} is up {k * MILESTONE_PCT:g}% on this life: {short}.")
                print(f"[arena] {name} milestone +{k * MILESTONE_PCT:g}%: {short}")

    # ---------- the shadow trader's leader ----------
    def _leader_trades(self, wallet, since):
        """The leader's trades since `since`, newest first: live signals plus the pool-feed trades the tracker stored."""
        out, seen = [], set()
        try:
            for s in self.tracker.signals(since) if self.tracker else []:
                if s.get("wallet") == wallet:
                    key = (s.get("tx"), s.get("side"), s.get("mint"))
                    seen.add(key)
                    out.append({"ts": s["ts"], "side": s["side"], "token": s["mint"], "symbol": s.get("symbol"),
                                "usd": s.get("usd") or 0, "source": s.get("source")})
            with self.db.lock:
                if self.db.conn.execute("SELECT name FROM sqlite_master WHERE name='copy_trades'").fetchone():
                    for r in self.db.conn.execute("SELECT ts, kind, mint, symbol, usd, tx FROM copy_trades WHERE wallet=? AND ts>=? "
                                                  "ORDER BY ts DESC LIMIT 200", (wallet, since)).fetchall():
                        if (r["tx"], r["kind"], r["mint"]) not in seen:
                            out.append({"ts": r["ts"], "side": r["kind"], "token": r["mint"], "symbol": r["symbol"],
                                        "usd": r["usd"] or 0, "source": "pool feed"})
        except Exception as e:
            print(f"[arena] leader trades failed: {e}")
        return sorted(out, key=lambda x: -x["ts"])

    def shadow_leaders(self, name, now):
        """The wallets a shadow trader follows: the top SHADOW_LEADERS of the tracker's board (by rank) that pass the
        copy-trading research's checks (profitable, 3+ tokens, not a flipper or a hyperactive bot) and traded in the
        last 6 hours. Persisted, so restarts keep the same set; re-picked after 6 hours, or earlier when fewer than half
        of the saved wallets are still on the board."""
        if not self.tracker:
            return []
        key = "__leaders__:" + name
        cur = self.db.load_state(key) or {}
        top = {t["wallet"]: t for t in self.tracker.top()}
        saved = cur.get("wallets") or []
        kept = [top[w] for w in saved if w in top]
        if kept and now - cur.get("picked", 0) < 6 * 3600 and 2 * len(kept) >= len(saved):
            return [{**t, "picked": cur["picked"]} for t in kept]
        fresh = lambda t: now - (t.get("last_trade_ts") or 0) < 6 * 3600
        good = [t for t in top.values() if (t.get("pnl_usd") or 0) > 0 and (t.get("tokens") or 0) >= 3
                and (t.get("flips") or 0) <= 1 and 6 <= (t.get("trades") or 0) <= 150 and fresh(t)]
        pool = good or [t for t in top.values() if fresh(t)]
        if not pool:
            return [{**t, "picked": cur.get("picked", now)} for t in kept]
        pick = sorted(pool, key=lambda t: t.get("rank") or float("inf"))[:SHADOW_LEADERS]
        wallets = [t["wallet"] for t in pick]
        if wallets != saved:
            print(f"[arena] {name} now shadows {len(pick)} wallets: " +
                  ", ".join(f"#{t.get('rank')} {t['wallet'][:6]}…" for t in pick))
        self.db.save_state(key, {"wallets": wallets, "picked": now})
        return [{**t, "picked": now} for t in pick]

    @staticmethod
    def _short_wallet(w):
        return f"{w[:4]}…{w[-4:]}"

    def _match_leader(self, name, following, now):
        """The full wallet of the leader a shadow buy names in "following" (as shown, abbreviated, or the full address), or None."""
        f = str(following or "").strip().replace("...", "…")
        if not f:
            return None
        for lead in self.shadow_leaders(name, now):
            w = lead["wallet"]
            if f in (w, self._short_wallet(w)):
                return w
        return None

    def _shadow_skip(self, t, trades, now):
        """Why a shadow trader should probably NOT copy one of its leader's buys (the research's admission rules):
        a probe (much smaller than the leader's usual buy), a buy big relative to the pool, a coin that already ran
        far since the leader bought, or a coin the arena vetoes. Empty when nothing stands out."""
        if t["side"] != "buy":
            return []
        out = []
        sizes = sorted(x["usd"] for x in trades if x["side"] == "buy" and x["usd"])
        if len(sizes) >= 4 and t["usd"] < 0.5 * sizes[len(sizes) // 2]:
            out.append("probe: much smaller than its usual buy")
        tok = self.market.get(t["token"]) or {}
        if tok.get("liquidity") and t["usd"] > 0.05 * tok["liquidity"]:
            out.append("its own buy was over 5% of the pool")
        hist = self.history.get(t["token"])
        if hist and tok.get("price"):
            then = next((p for ts, p in hist if ts >= t["ts"]), None)
            if then and tok["price"] > then * 1.3:
                out.append(f"already up {(tok['price'] / then - 1) * 100:.0f}% since it bought")
        veto = (getattr(self, "vetoes", {}) or {}).get(t["token"])
        if veto:
            out.append("vetoed: " + "; ".join(veto[:2]))
        return out

    def _leader_entry(self, w, lead, now):
        """One leader as a shadow trader sees it: record, trades of the last 30 minutes, what it still seems to hold."""
        trades = self._leader_trades(w, now - 86400)
        last = {}
        for t in reversed(trades):  # oldest first, so the newest action per token wins
            h = last.setdefault(t["token"], {"token": t["token"], "symbol": t["symbol"], "bought_usd": 0.0, "sold_usd": 0.0})
            h["bought_usd" if t["side"] == "buy" else "sold_usd"] += t["usd"]
            h["last"], h["last_ts"] = t["side"], t["ts"]
        holding = [{"token": h["token"], "symbol": h["symbol"], "bought_usd": round(h["bought_usd"]),
                    "sold_usd": round(h["sold_usd"]), "last_buy_min_ago": round((now - h["last_ts"]) / 60)}
                   for h in sorted(last.values(), key=lambda h: -h["last_ts"]) if h["last"] == "buy"][:5]
        return {"wallet": self._short_wallet(w), "rank": lead.get("rank"),
                "record_48h": {k: lead.get(k) for k in ("pnl_usd", "roi_pct", "win_rate", "trades", "tokens", "volume_usd")},
                "latest_trades": [{"min_ago": round((now - t["ts"]) / 60, 1), "side": t["side"], "symbol": t["symbol"],
                                   "token": t["token"], "usd": round(t["usd"]), "seen_via": t["source"],
                                   **({"skip_reasons": why} if (why := self._shadow_skip(t, trades, now)) else {})}
                                  for t in trades if now - t["ts"] <= 1800][:15],
                "seems_to_hold": holding}

    def leader_view(self, name, now):
        """What a shadow trader sees about its leader set: one entry per leader (see _leader_entry)."""
        leaders = self.shadow_leaders(name, now)
        if not leaders:
            return {"note": "No leaders yet: the top-trader board is still empty. Trade on your own judgment until some appear."}
        return {"leaders": [self._leader_entry(l["wallet"], l, now) for l in leaders],
                "note": "Trades seen via the pool feed arrive minutes late; 'helius' ones within seconds. "
                        "Name the wallet you copy in your buy (\"following\": \"<wallet as shown>\") and the arena sells "
                        "when that wallet sells."}

    # ---------- screens: what each Claude is looking at ----------
    def screens(self, now):
        """For the dashboard's screens: per Claude, the tokens it is focused on (just ordered, mentioned in its last
        thought, held, or bought by its leader) with the arena's own price history and its trades in them."""
        import re
        cands = {t["address"]: t for t in self.market.candidates()}
        by_symbol = {}
        for a, t in cands.items():
            by_symbol.setdefault(str(t.get("symbol") or ""), a)
        out = []
        for name, agent in self.agents.items():
            if agent.kind != "llm":
                continue
            acct = self.accounts[name]
            with self.db.lock:
                last = self.db.conn.execute("SELECT ts, note, orders FROM decisions WHERE agent=? AND error IS NULL "
                                            "ORDER BY ts DESC LIMIT 1", (name,)).fetchone()
                recent = self.db.conn.execute("SELECT ts, side, token, symbol, usd, pnl FROM trades WHERE agent=? AND ts>=? "
                                              "ORDER BY ts DESC", (name, now - 7200)).fetchall()
            note = (last["note"] if last else "") or getattr(agent, "note", "") or ""
            focus, why = [], {}

            def add(addr, w, text):
                if addr and addr not in why and len(focus) < 4:
                    why[addr] = (w, text)
                    focus.append(addr)
            for r in recent:  # what it just traded
                if now - r["ts"] < 1800:
                    add(r["token"], "ordered", f"{'bought' if r['side'] == 'buy' else 'sold'} {ago_text(now - r['ts'])}")
            if last:
                for o in json.loads(last["orders"] or "[]"):
                    sym = o.get("symbol")
                    addr = by_symbol.get(sym) or next((a for a, p in acct["positions"].items() if p["symbol"] == sym), None)
                    add(addr, "ordered", f"ordered {ago_text(now - last['ts'])}")
            for word in re.findall(r"[A-Za-z0-9$][A-Za-z0-9_.$-]{1,15}", note):  # coins named in its last thought
                w = word.strip(".,;:$")
                if len(w) >= 2 and w in by_symbol:
                    add(by_symbol[w], "mentioned", "mentioned in its last look")
            for a, p in sorted(acct["positions"].items(), key=lambda kv: -kv[1]["cost"]):
                add(a, "holding", "holding")
            leader = None
            if getattr(agent, "persona", None) == "shadow":
                leads = self.shadow_leaders(name, now)
                if leads:  # the dashboard shows the top-ranked one; "count" is the size of the set
                    leader = {"wallet": self._short_wallet(leads[0]["wallet"]), "rank": leads[0].get("rank"), "count": len(leads)}
                    buys = sorted((t for l in leads for t in self._leader_trades(l["wallet"], now - 3600) if t["side"] == "buy"),
                                  key=lambda t: -t["ts"])
                    if buys:
                        add(buys[0]["token"], "leader", f"a leader bought it {ago_text(now - buys[0]['ts'])}")
            screens = []
            for a in focus:
                pos = acct["positions"].get(a)
                t = self._token_for(a, pos) or {}
                hist = [[round(ts * 1000), p] for ts, p in self.history.get(a, []) if now - ts <= 3600]
                v = self.view(name, now)
                vp = next((p for p in v["positions"] if p["token"] == a), None)
                screens.append({
                    "token": a, "symbol": t.get("symbol") or (pos or {}).get("symbol") or a[:6], "why": why[a][0], "why_text": why[a][1],
                    "price": t.get("price"), "chg_m5": t.get("chg_m5"), "chg_h1": t.get("chg_h1"), "liquidity": t.get("liquidity"),
                    "rating": t.get("rating"), "age_min": t.get("age_min"),
                    "position": {"cost": vp["cost"], "value": vp["value"], "pnl_pct": vp["pnl_pct"], "held_min": vp["held_min"],
                                 "moonshot": vp.get("moonshot", False), "entry_price": self.entry_spot(pos), "exits": vp["exits"]}
                    if vp and pos else None,
                    "points": hist,
                    "trades": [{"ts": r["ts"], "side": r["side"], "usd": round(r["usd"], 2), "pnl": r["pnl"]} for r in recent if r["token"] == a],
                })
            st = agent.status()
            out.append({"name": name, "avatar": agent.avatar, "persona": getattr(agent, "persona", None),
                        "out": bool(acct.get("out")), "thinking_since": st.get("thinking_since"), "next_run": st.get("next_run"),
                        "last_look": last["ts"] if last else None, "note": note, "leader": leader, "focus": screens})
        return {"now": now, "agents": out}

    # ---------- strategy room ----------
    def room_view(self, name, now):
        """The newest strategy-room posts for a Claude's look, newest first. Blocked posts show only that they were removed."""
        if not strategy_room.ENABLED:
            return None
        out = []
        for p in self.db.room_posts(strategy_room.SHOW):
            if p["ts"] < self.run_started - 60:
                continue  # earlier runs' posts stay on the dashboard, not in the Claudes' room
            item = {"from": p["author"], "min_ago": round((now - p["ts"]) / 60)}
            if p["status"] == "ok":
                item["text"] = p["text"]
            else:
                item["removed"] = f"post removed: it {p['reason']}" + (" (yours)" if p["author"] == name else "")
            out.append(item)
        return out

    def _coin_words(self):
        """Every coin name and symbol the arena knows right now (tracked, held, or traded in the last day), cached per tick."""
        if getattr(self, "_coins_tick", None) != self.ticks:
            toks = list(self.market.candidates())
            toks += [{"symbol": p.get("symbol")} for acct in self.accounts.values() for p in acct["positions"].values()]
            toks += [{"symbol": t.get("symbol")} for t in self.db.trades(500)]
            self._coins, self._coins_tick = strategy_room.coin_words(toks), self.ticks
        return self._coins

    def post_to_room(self, name, ts, text):
        """A Claude's room_post: checked for coins, then saved as "ok" or "blocked". Returns the reason it was blocked, or None."""
        if not strategy_room.ENABLED:
            return None
        clean, reason = strategy_room.check_post(text, self._coin_words())
        if not clean:
            return None
        self.db.add_room_post(ts, name, clean, "blocked" if reason else "ok", reason)
        if reason:
            print(f"[{name}] room post blocked ({reason}): {clean[:80]}")
        return reason

    def view(self, name, now):
        acct = self.accounts[name]
        positions = []
        for a, p in acct["positions"].items():
            t = self._token_for(a, p)
            value = liquidation_value(t, p["qty"])
            entry, spot = self.entry_spot(p), (t or {}).get("price", 0)
            plan = acct["exits"].get(a, {})
            positions.append({
                "price_chg_pct": round((spot / entry - 1) * 100, 1) if entry else 0,
                "exits": {k: plan[k] for k in EXIT_FIELDS if k in plan},
                "token": a, "symbol": p["symbol"], "qty": p["qty"], "cost": round(p["cost"], 2),
                "value": round(value, 2), "pnl_pct": round((value / p["cost"] - 1) * 100, 1) if p["cost"] else 0,
                "held_min": round((now - p["opened"]) / 60, 1), "opened": p["opened"], "moonshot": bool(p.get("moonshot")),
                "rating": (t or {}).get("rating", "red"), "flags": (t or {}).get("flags", []),
            })
        # Failed transactions from the last hour, newest last, so an agent can see "your buy of X failed".
        failures = [f for f in acct.get("recent_failures", []) if now - f["ts"] < 3600][-5:]
        return {"now": now, "cash": acct["cash"], "equity": self.equity(name), "score_equity": self.score_equity(name),
                "points": self.points(name), "pnl_pct": self.pnl_pct(name), "lives": self.lives_info(name), "positions": positions,
                "vetoes": self.vetoes,
                "candidates": self.market.candidates(), "recent_sells": acct["recent_sells"],
                "failed": acct.get("failed", 0), "recent_failures": failures}

    # ---------- order handling ----------
    def validate(self, agent, o, view):
        if not isinstance(o, dict) or o.get("action") not in ("buy", "sell") or not o.get("token"):
            return None
        o["reason"] = str(o.get("reason", ""))[:300]
        held = {p["token"] for p in view["positions"]}
        if o["action"] == "buy":
            try:
                usd = float(o.get("usd", 0))
            except (TypeError, ValueError):
                return None
            veto = self.vetoes.get(o["token"]) if agent.kind == "llm" else None
            if veto:
                o["reason"] = f"{o.get('reason', '')} [refused, vetoed: {'; '.join(veto[:2])}]"[:300]
                if o.get("symbol") in (None, "?"):
                    o["symbol"] = (self.market.get(o["token"]) or {}).get("symbol", "?")
                return None
            if agent.kind == "llm":
                text = self._churn_refusal(agent.name, o, usd, view["now"])
                if text:
                    return self._refuse(agent.name, o, text, view["now"])
            if o.get("moonshot") and agent.kind == "llm" and MOONSHOT_SLOTS:
                acct = self.accounts[agent.name]
                moons = sum(1 for p in acct["positions"].values() if p.get("moonshot")) + \
                    sum(1 for n, x in self.pending if n == agent.name and x.get("moonshot") and x.get("action") == "buy")
                if o["token"] not in held and moons >= MOONSHOT_SLOTS:
                    return None  # every moonshot slot is taken
                usd = min(usd, MOONSHOT_PCT / 100 * view["equity"])
                o["moonshot"] = True
            else:
                o.pop("moonshot", None)
            usd = min(usd, agent.max_trade_frac * view["equity"], view["cash"])
            if usd < 5 or not self.market.get(o["token"]):
                return None
            if o["token"] not in held and len(held) >= agent.max_positions:
                return None
            o["usd"] = usd
            # a shadow buy may name the leader it copies; keep the full wallet, drop anything that matches no leader
            wallet = self._match_leader(agent.name, o.get("following"), view["now"]) \
                if o.get("following") and getattr(agent, "persona", None) == "shadow" else None
            if wallet:
                o["following"] = wallet
            else:
                o.pop("following", None)
        else:
            if o["token"] not in held:
                return None
            try:
                o["fraction"] = max(0.0, min(1.0, float(o.get("fraction", 1.0))))
            except (TypeError, ValueError):
                o["fraction"] = 1.0
        return o

    def _churn_refusal(self, name, o, usd, now):
        """Why a Claude's buy breaks the churn rules (minimum size, then 24 hour cap, then cooldown), or None if it doesn't.
        Buys already queued for the next fill count too, as if they had just happened."""
        if not (MIN_BUY_USD or MAX_BUYS_PER_DAY or BUY_COOLDOWN_MIN):
            return None
        symbol = o.get("symbol")
        if symbol in (None, "?"):
            symbol = (self.market.get(o["token"]) or {}).get("symbol") or str(o["token"])[:6]
        what = f"your buy of {symbol} (${usd:.0f}) was refused"
        if MIN_BUY_USD and usd < MIN_BUY_USD:
            return f"{what}: under the ${MIN_BUY_USD:.0f} minimum"
        with self.db.lock:
            n, last = self.db.conn.execute("SELECT COUNT(*), MAX(ts) FROM trades WHERE agent=? AND side='buy' AND ts>=?",
                                           (name, now - 86400)).fetchone()
        queued = sum(1 for n2, x in self.pending if n2 == name and x.get("action") == "buy")
        n += queued
        if MAX_BUYS_PER_DAY and n >= MAX_BUYS_PER_DAY:
            return f"{what}: {n} buys in the last 24 hours (limit {MAX_BUYS_PER_DAY})"
        if BUY_COOLDOWN_MIN and queued:
            return f"{what}: a buy is already queued ({BUY_COOLDOWN_MIN:g} minute cooldown)"
        if BUY_COOLDOWN_MIN and last is not None and now - last < BUY_COOLDOWN_MIN * 60:
            return f"{what}: {(now - last) / 60:.0f} minutes since your last buy ({BUY_COOLDOWN_MIN:g} minute cooldown)"
        return None

    def _refuse(self, name, o, text, now):
        """Records a refused buy in the agent's recent_failures (shown back to it by view()) and returns None."""
        symbol = o.get("symbol")
        if symbol in (None, "?"):
            symbol = o["symbol"] = (self.market.get(o["token"]) or {}).get("symbol") or str(o["token"])[:6]
        try:
            usd = float(o.get("usd"))
        except (TypeError, ValueError):
            usd = None
        o["reason"] = f"{o.get('reason', '')} [refused: {text.split(': ', 1)[-1]}]"[:300]
        rf = self.accounts[name].setdefault("recent_failures", [])
        rf.append({"ts": now, "action": o["action"], "token": o["token"], "symbol": symbol, "usd": usd,
                   "fraction": None, "reason": o["reason"], "exit": False, "text": text})
        del rf[:-10]
        print(f"[{name}] REFUSED BUY {symbol}: {text.split(': ', 1)[-1]}")
        return None

    def _fail(self, name, o, t, now):
        """A transaction that didn't land: nothing is traded, the network fee is still paid, and the agent is told."""
        acct = self.accounts[name]
        addr = o["token"]
        symbol = (t or {}).get("symbol") or o.get("symbol") or str(addr)[:6]
        fee = min(acct["cash"], PRIORITY_FEE_USD) if acct["cash"] > 0 else 0.0
        acct["cash"] -= fee
        acct["failed"] = acct.get("failed", 0) + 1
        fast = abs((t or {}).get("chg_m5") or 0) > 50
        why = "transaction failed" + (" (congested pool, price moving fast)" if fast else " (dropped by the network)")
        what = f"your buy of {symbol} (${o.get('usd', 0):.0f})" if o["action"] == "buy" else \
            f"your sell of {o.get('fraction', 1.0):.0%} of {symbol}"
        text = f"{what} failed: {why}; nothing was traded" + (f", ${fee:.2f} network fee lost" if fee else "")
        ev = {"ts": now, "action": o["action"], "token": addr, "symbol": symbol, "usd": o.get("usd"),
              "fraction": o.get("fraction"), "reason": o.get("reason", ""), "exit": bool(o.get("exit")), "text": text}
        rf = acct.setdefault("recent_failures", [])
        rf.append(ev)
        del rf[:-10]
        if o["action"] == "sell" and addr in acct["exits"]:
            acct["exits"][addr].pop("fired_at", None)  # a tripped stop retries on the very next check
        print(f"[{name}] FAIL {o['action'].upper()} {symbol:<10} {why}" + (f"  ({o.get('reason', '')})" if o.get("reason") else ""))

    def _drifted(self, t):
        """The token as the next filler in this batch sees it: earlier fills of the same token in the same tick have
        already moved its pool (several agents piling into one token pay for each other's impact)."""
        drift = self._drift.get(t.get("address"), 1.0)
        return ({**t, "price": t["price"] * drift}, drift) if drift != 1.0 else (t, 1.0)

    def _move(self, addr, t, usd):
        """Record how a fill moves the pool for the rest of this batch: constant product, so buying $X into a pool
        with $L liquidity multiplies the price by about (1 + X/(L/2))^2, and selling divides it."""
        x = (t.get("liquidity") or 0) / 2
        if x > 0 and addr:
            self._drift[addr] = self._drift.get(addr, 1.0) * ((1 + abs(usd) / x) ** 2 if usd > 0 else (1 + abs(usd) / x) ** -2)

    def execute(self, name, o, now):
        acct = self.accounts[name]
        addr = o["token"]
        if o["action"] == "buy":
            t = self.market.get(addr)
            usd = min(o["usd"], acct["cash"])
            if not t or usd < 1:
                return
            t, drift = self._drifted(t)
            if self.rng.random() < fail_probability(t):
                self._fail(name, o, t, now)
                return
            quote = getattr(self.market, "quote_buy", None)
            mev = mev_slippage(t, usd) + early_penalty(t, now)  # sandwich bots, and snipers dumping on the first buyers
            real = self.market.get(addr)
            qty, fill = buy_fill(t, usd, quote=(lambda spend: (quote(real, spend) or 0) / drift or None) if quote else None, mev=mev)
            if qty <= 0:
                return
            self._move(addr, t, usd)
            acct["cash"] -= usd
            pos = acct["positions"].setdefault(addr, {"symbol": t["symbol"], "qty": 0.0, "cost": 0.0, "opened": now})
            if o.get("moonshot") and pos["qty"] == 0:
                pos["moonshot"] = True
            if o.get("following"):
                pos["copied_wallet"] = o["following"]  # the shadow's leader-sell exit watches this wallet
            pos["cost_in"] = pos.get("cost_in", pos["cost"]) + usd  # everything ever put in (for the runner bonus)
            pos.setdefault("liq_entry", t.get("liquidity") or 0)
            pos.setdefault("peak_ts", now)
            pos["entry_spot"] = (self.entry_spot(pos) * pos["qty"] + t["price"] * qty) / (pos["qty"] + qty)
            pos["qty"] += qty
            pos["cost"] += usd
            pos["last_price"], pos["last_liq"] = t["price"], t["liquidity"]
            self.db.add_trade(now, name, "buy", addr, t["symbol"], usd, qty, t["price"], fill, None, o["reason"])
            extra = f"  mev -{mev * 100:.1f}%" if mev else ""
            print(f"[{name}] BUY  {t['symbol']:<10} ${usd:8.2f}  fill {fill / t['price'] - 1:+.1%} vs spot{extra}  ({o['reason']})")
        else:
            pos = acct["positions"].get(addr)
            if not pos:
                return
            t = self._token_for(addr, pos)
            if not o.get("force") and self.rng.random() < fail_probability(t):
                self._fail(name, o, t, now)
                return
            frac = o["fraction"]
            qty = pos["qty"] * frac
            real, drift = t, 1.0
            if t:
                t, drift = self._drifted(t)
            quote = getattr(self.market, "quote_sell", None) if t and t.get("address") else None
            proceeds, fill = sell_fill(t, qty, quote=(lambda q: (quote(real, q) or 0) * drift or None) if quote else None) if t else (0.0, 0.0)
            if t:
                self._move(addr, t, -qty * t["price"])
            cost_part = pos["cost"] * frac
            pnl = proceeds - cost_part
            acct["cash"] += proceeds
            acct["realized"] += pnl
            pos["qty"] -= qty
            pos["cost"] -= cost_part
            pos["proceeds"] = pos.get("proceeds", 0.0) + proceeds
            if frac >= 0.999 or pos["qty"] <= 0:
                self._runner_bonus(name, pos, now)
                del acct["positions"][addr]
                acct["exits"].pop(addr, None)
                acct["recent_sells"][addr] = now
            spot = t["price"] if t else 0
            self.db.add_trade(now, name, "sell", addr, pos["symbol"], proceeds, qty, spot, fill, pnl, o["reason"])
            print(f"[{name}] SELL {pos['symbol']:<10} ${proceeds:8.2f}  pnl {pnl:+.2f}  ({o['reason']})")

    def _runner_bonus(self, name, pos, now):
        """A Claude closed a position at 3x+ of everything it put in: bonus points (the coin is never named in the room)."""
        if self.agents[name].kind != "llm" or not pos.get("cost_in"):
            return
        multiple = pos["proceeds"] / pos["cost_in"]
        bonus = runner_bonus(multiple)
        if not bonus:
            return
        acct = self.accounts[name]
        acct["runner_bonus"] = acct.get("runner_bonus", 0.0) + bonus
        kind = "moonshot" if pos.get("moonshot") else "position"
        acct["life_event"] = {"ts": now, "text": f"You closed a {kind} at {multiple:.1f}x what you put in: +{bonus:g} runner bonus points."}
        if strategy_room.ENABLED:
            self.db.add_room_post(now, "arena", f"{name} closed a {kind} at {multiple:.1f}x: +{bonus:g} runner bonus points.")
        print(f"[arena] {name} runner {multiple:.1f}x ({pos['symbol']}): +{bonus:g} bonus points")

    def set_exits(self, name, o, now):
        """Merge exit fields from an order into the agent's plan for that token. Returns False if unusable."""
        token = o.get("token")
        acct = self.accounts[name]
        held = acct["positions"].get(token)
        t = self.market.get(token) or (self._token_for(token, held) if held else None)
        if not token or not t:
            return False
        plan = acct["exits"].setdefault(token, {})
        plan["set_at"] = now
        for f in EXIT_FIELDS:
            if f not in o:
                continue
            if o[f] is None:
                plan.pop(f, None)
                continue
            try:
                plan[f] = SIGNS[f] * abs(float(o[f]))
            except (TypeError, ValueError):
                continue
        if any(f in o for f in ("wake_down_pct", "wake_up_pct")):
            plan["wake_ref"] = t["price"]
        if o.get("moonshot") or (held or {}).get("moonshot"):  # noise must not shake a moonshot out
            if "stop_loss_pct" in plan:
                plan["stop_loss_pct"] = min(plan["stop_loss_pct"], -MOONSHOT_MIN_STOP)
            if "trailing_pct" in plan:
                plan["trailing_pct"] = max(plan["trailing_pct"], MOONSHOT_MIN_TRAIL)
        return True

    def _queued(self, name, token):
        return any(n == name and o.get("token") == token and o.get("action") == "sell" for n, o in self.pending)

    def check_managed(self, now):
        """The exit ladder, trailing stop, time stop and event exits on every Claude position (see LADDER). Sells are
        queued as exits and fill on the next tick or fast check. Also the shadow trader's exit when the leader it copied
        into a position (copied_wallet) sells that token."""
        if not MANAGED_EXITS:
            return
        creator_sold = getattr(self, "creator_sold", {})  # mint -> usd the creator sold lately (signals.py)
        leader_sells = {}  # wallet -> {token: its newest sell}, read once per wallet in this check
        for name, agent in self.agents.items():
            if agent.kind != "llm":
                continue
            acct = self.accounts[name]
            for token, pos in list(acct["positions"].items()):
                if self._queued(name, token):
                    continue
                t = self._token_for(token, pos)
                spot, entry = (t or {}).get("price", 0), self.entry_spot(pos)
                if not spot or not entry:
                    continue
                mult = spot / entry
                if spot > pos.get("peak_price", 0):
                    pos["peak_price"], pos["peak_ts"] = spot, now
                peak_mult = pos["peak_price"] / entry
                sell, why = None, None
                liq, liq0 = (t or {}).get("liquidity") or 0, pos.get("liq_entry") or 0
                if liq0 and liq < liq0 * LIQ_EXIT:
                    sell, why = 1.0, f"liquidity pulled: the pool is down {(1 - liq / liq0) * 100:.0f}% since you bought"
                elif creator_sold.get(token, 0) >= CREATOR_SELL_USD and creator_sold.get(token, 0) > 0:
                    sell, why = 1.0, f"creator sold: ${creator_sold[token]:,.0f} dumped by the token's creator"
                elif getattr(agent, "persona", None) == "shadow" and pos.get("copied_wallet"):
                    w = pos["copied_wallet"]
                    if w not in leader_sells:
                        leader_sells[w] = {}
                        for x in self._leader_trades(w, now - 86400):  # newest first: keep each token's newest sell
                            if x["side"] == "sell":
                                leader_sells[w].setdefault(x["token"], x)
                    s = leader_sells[w].get(token)
                    if s and s["ts"] > pos.get("opened", 0):
                        sell, why = 1.0, f"leader sold: {self._short_wallet(w)}, the wallet you copied, sold this {ago_text(now - s['ts'])}"
                if sell is None:
                    trail = next((tr for m, tr in LADDER_TRAIL if peak_mult >= m), None)
                    if trail is not None and spot <= pos["peak_price"] * (1 - trail / 100):
                        sell, why = 1.0, f"exit ladder trailing stop: {(1 - spot / pos['peak_price']) * 100:.0f}% off the peak (trail {trail:g}% after {peak_mult:.1f}x)"
                    elif now - pos.get("peak_ts", pos.get("opened", now)) >= TIME_STOP_H * 3600:
                        sell, why = 1.0, f"time stop: no new high in {TIME_STOP_H:g} hours"
                    else:
                        done = pos.setdefault("rungs", [])
                        rung = next(((m, f) for m, f in LADDER if mult >= m and m not in done), None)
                        if rung:
                            done.append(rung[0])
                            sell, why = rung[1], f"exit ladder: {mult:.1f}x, selling {rung[1] * 100:.0f}% (the {rung[0]:g}x rung)"
                if sell:
                    self.pending.append((name, {"action": "sell", "token": token, "fraction": sell, "reason": why,
                                                "exit": True, "managed": True}))

    def check_exits(self, now):
        """Every tick and every fast check: fire stops and targets (free, no model call) and wake Claude agents
        whose alarms tripped. A tripped exit is queued once (fired_at) and fills on the next tick or fast check."""
        for name, acct in self.accounts.items():
            agent = self.agents[name]
            for token, plan in list(acct["exits"].items()):
                pos = acct["positions"].get(token)
                if not pos:
                    if now - plan.get("set_at", now) > 600:  # the buy never filled
                        del acct["exits"][token]
                    continue
                t = self._token_for(token, pos)
                spot, entry = (t or {}).get("price", 0), self.entry_spot(pos)
                if not spot or not entry:
                    continue
                plan["peak"] = max(plan.get("peak", entry), spot)
                chg, off_high = (spot / entry - 1) * 100, (1 - spot / plan["peak"]) * 100
                sl, tp, tr = plan.get("stop_loss_pct"), plan.get("take_profit_pct"), plan.get("trailing_pct")
                why = None
                if sl is not None and chg <= sl:
                    why = f"stop loss: {chg:+.1f}% from entry (set at {sl:g}%)"
                elif tp is not None and chg >= tp:
                    why = f"take profit: {chg:+.1f}% from entry (set at +{tp:g}%)"
                elif tr is not None and off_high >= tr:
                    why = f"trailing stop: {off_high:.1f}% off the high (set at {tr:g}%)"
                if why and now - plan.get("fired_at", 0) > 60:
                    plan["fired_at"] = now
                    self.pending.append((name, {"action": "sell", "token": token, "fraction": 1.0, "reason": why,
                                                "exit": True}))
                    continue
                ref = plan.get("wake_ref")
                if ref and agent.kind == "llm":
                    move = (spot / ref - 1) * 100
                    wd, wu = plan.get("wake_down_pct"), plan.get("wake_up_pct")
                    if (wd is not None and move <= wd) or (wu is not None and move >= wu):
                        limits = ", ".join(x for x in (wd is not None and f"down {wd:g}%", wu is not None and f"up +{wu:g}%") if x)
                        agent.wake(f"{pos['symbol']} moved {move:+.1f}% since you set your alarm ({limits})")
                        for k in ("wake_down_pct", "wake_up_pct", "wake_ref"):  # alarms fire once
                            plan.pop(k, None)
            if agent.kind == "llm":
                for token, pos in acct["positions"].items():
                    rating = (self._token_for(token, pos) or {}).get("rating", "red")
                    if rating == "red" and pos.get("last_rating") not in (None, "red"):
                        agent.wake(f"{pos['symbol']}'s risk rating just turned red")
                    pos["last_rating"] = rating

    def save_decisions(self, name, agent):
        while agent.log:
            d = agent.log.popleft()
            keys = ("action", "symbol", "usd", "fraction", "reason", "rejected", "moonshot") + EXIT_FIELDS
            orders = [{k: o.get(k) for k in keys if k in o} for o in d["orders"]
                      if isinstance(o, dict) and o.get("action") != "exits"]
            exits = [{k: o.get(k) for k in ("symbol", "rejected") + EXIT_FIELDS if k in o} for o in d["orders"]
                     if isinstance(o, dict) and o.get("action") == "exits"]
            self.db.add_decision(name, {**d, "exits": exits}, orders)
            if d.get("room_post"):
                self.post_to_room(name, d.get("ts") or self.clock(), d["room_post"])

    # ---------- main loop ----------
    def step(self):
        now = self.clock()
        with self.lock:
            self.market.refresh(self.held())
            pending, self.pending = self.pending, []
            self._drift = {}  # a new batch of fills: no same-tick impact yet
            for name, o in pending:  # orders from last tick fill now, at today's prices
                self.execute(name, o, now)
            self.record_prices(now)
            self.update_signals(now)
            if self.memory:
                self.memory.observe(now, self.market.candidates())
            self.check_exits(now)
            self.check_managed(now)
            self.check_busts(now)
            self.check_milestones(now)
            self.check_watch(now)
            ready = self.market_ready(now) or now - self.started > 300
            signals = None  # the top traders' recent trades, fetched once per tick for whoever needs them
            for name, agent in self.agents.items():
                if self.accounts[name].get("out"):
                    continue  # out of lives: no more looks, no more trades
                if not agent.due(now):
                    continue
                if agent.kind == "llm" and agent.ready is None and not ready:
                    continue  # let the safety checks finish before a Claude's first look
                agent.last_run = now
                v = self.view(name, now)
                if signals is None:
                    try:
                        signals = self.tracker.signals(now - 600) if self.tracker else []
                    except Exception as e:
                        print(f"[arena] couldn't read copy signals: {e}")
                        signals = []
                v["copy_signals"] = signals
                if agent.kind == "llm":
                    v.update(self.llm_context(name, now))
                try:
                    orders = agent.decide(v) or []
                except Exception as e:
                    print(f"[{name}] decide() failed: {e}")
                    traceback.print_exc()
                    orders = []
                for o in orders:
                    if isinstance(o, dict) and o.get("action") == "exits":
                        if not self.set_exits(name, o, now):
                            o["rejected"] = True
                        continue
                    ok = self.validate(agent, o, v)
                    if ok:
                        self.pending.append((name, ok))
                        if ok["action"] == "buy" and any(f in ok for f in EXIT_FIELDS):
                            self.set_exits(name, ok, now)  # exits attached to a buy
                    elif isinstance(o, dict):
                        o["rejected"] = True  # shows up in the decision log
                self.save_decisions(name, agent)
            for name, agent in self.agents.items():
                self.save_decisions(name, agent)  # failed calls log themselves without a tick
            if getattr(self.market, "risk_dirty", False):
                cutoff = now - 3 * 86400
                cache = {a: c for a, c in self.market.risk_cache.items() if c["checked"] > cutoff}
                self.db.save_state("__risk_cache__", cache)
                self.market.risk_dirty = False
            for name, acct in self.accounts.items():
                cutoff = now - 86400
                acct["recent_sells"] = {a: ts for a, ts in acct["recent_sells"].items() if ts > cutoff}
                self.db.add_equity(now, name, self.score_equity(name))
                self.db.save_state(name, acct)
            self.ticks += 1

    def fast_step(self):
        """Between ticks: refresh held tokens' prices, fill the exits that tripped on the previous check, and check
        exits again. No decide(), no watcher, no price history, no equity point. Agents' own orders stay queued
        for the next full tick."""
        now = self.clock()
        with self.lock:
            held = self.held()
            if not held and not any(o.get("exit") for _, o in self.pending):
                return
            refresh_held = getattr(self.market, "refresh_held", None)
            if refresh_held and held:
                refresh_held(held)
            touched = set()
            if any(o.get("exit") for _, o in self.pending):
                rest = []
                self._drift = {}  # a new batch of fills: no same-tick impact yet
                for name, o in self.pending:
                    if o.get("exit"):
                        self.execute(name, o, now)
                        touched.add(name)
                    else:
                        rest.append((name, o))
                self.pending = rest
            self.check_exits(now)
            self.check_managed(now)
            for name in touched:  # a fill between ticks is saved right away so a crash can't replay it
                self.db.save_state(name, self.accounts[name])
            self.fast_ticks += 1

    def run_forever(self):
        fast = f", exit checks every {self.fast_exit_secs:g}s" if self.fast_exit_secs else ""
        print(f"[arena] running with agents: {', '.join(self.agents)}  (tick = {self.tick}s{fast})")
        while True:
            t0 = time.time()
            try:
                self.step()
            except Exception as e:
                print(f"[arena] tick failed: {e}")
                traceback.print_exc()
            while self.fast_exit_secs > 0:
                left = t0 + self.tick - time.time()
                if left < self.fast_exit_secs + 2:  # the next full tick is close enough
                    break
                time.sleep(self.fast_exit_secs)
                try:
                    self.fast_step()
                except Exception as e:
                    print(f"[arena] fast exit check failed: {e}")
                    traceback.print_exc()
            time.sleep(max(0, self.tick - (time.time() - t0)))
