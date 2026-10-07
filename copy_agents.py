"""Team Copy: agents that follow the top-100 traders (ranked by the arena's leaderboard in traders.py).

Each copy bot follows one slice of the leaderboard and mirrors it mechanically: when one of its traders buys a
token, it buys the same token at a fixed size; when that same trader sells, it sells too. A -30% safety stop and a
6-hour limit keep a forgotten position from riding to zero. The arena hands every agent the recent signals as
`copy_signals` in its view (see arena.llm_context / arena.step); these bots just act on them.

Sonnet Copycat (claude_agents.py, persona "copycat") is the judgment-filtered version: a Claude that sees the same
signals and decides which ones are worth following.
"""
from collections import deque

from agent_base import Agent

COPY_FRACTION = 0.05     # each copied buy is 5% of equity
COPY_WINDOW_SECS = 300   # a buy signal is stale after 5 minutes (the token must get a price by then)
SAFETY_STOP_PCT = -30
TIME_LIMIT_MIN = 360


class CopyBot(Agent):
    team = "copy"
    max_positions = 8

    def __init__(self, name, lo, hi, avatar, fraction=COPY_FRACTION, window_secs=COPY_WINDOW_SECS, from_signal_ts=False):
        super().__init__()
        self.name, self.lo, self.hi, self.avatar = name, lo, hi, avatar
        self.fraction, self.window_secs = fraction, window_secs
        self.from_signal_ts = from_signal_ts  # True: the copy window runs from the leader's trade, not from when we saw it
        self.description = (f"Copies every buy and sell of the traders ranked {lo}-{hi} on the arena's top-100 leaderboard "
                            f"(by profit over the last day): {self.fraction:.0%} of equity per buy, sells when they sell, "
                            f"{SAFETY_STOP_PCT}% safety stop, {TIME_LIMIT_MIN // 60}-hour limit.")
        self.bio = {"copy-a": "Copies the top third of the leaderboard. If the best traders know something, it wants in.",
                    "copy-b": "Copies the middle third: good traders, less crowded trades.",
                    "copy-c": "Copies ranks 67-100, to see whether being on the list at all is what matters."}.get(avatar, "")
        self.catchphrase = {"copy-a": "Whatever they're having.", "copy-b": "Middle of the pack, middle of the trade.",
                            "copy-c": "Last on the list, first in the trade."}.get(avatar, "")
        self.seen = deque(maxlen=5000)    # signal ids already handled
        self.pending = {}                 # mint -> (signal, when we saw it): buys waiting for the token to get a price
        self.copied = {}                  # mint -> wallet we copied into it

    def following(self, top):
        return [t["wallet"] for t in top if self.lo <= t.get("rank", 0) <= self.hi]

    def decide(self, v):
        now, orders = v["now"], []
        held = {p["token"]: p for p in v["positions"]}
        seen = set(self.seen)
        for s in v.get("copy_signals", []):
            if s["id"] in seen or not s.get("rank") or not self.lo <= s["rank"] <= self.hi:
                continue
            self.seen.append(s["id"])
            who = f"#{s['rank']} {s['wallet'][:4]}…{s['wallet'][-4:]}"
            if s["side"] == "buy":
                self.pending.setdefault(s["mint"], (s, (s.get("ts") or now) if self.from_signal_ts else now, who))
                continue
            waiting = self.pending.get(s["mint"])
            if waiting and waiting[0]["wallet"] == s["wallet"]:
                del self.pending[s["mint"]]  # they sold before we could copy the buy
            if s["mint"] in held and self.copied.get(s["mint"]) == s["wallet"]:
                orders.append({"action": "sell", "token": s["mint"], "fraction": 1.0, "reason": f"copying {who}: they sold"})
                self.copied.pop(s["mint"], None)

        tradable = {t["address"] for t in v["candidates"]}
        slots = self.max_positions - len(held)
        for mint, (s, seen_at, who) in list(self.pending.items()):
            if now - seen_at > self.window_secs:
                del self.pending[mint]  # too late to call it copying
                continue
            if mint in held or mint not in tradable:
                continue  # wait until the market has priced it
            if slots <= 0:
                break
            orders.append({"action": "buy", "token": mint, "usd": v["equity"] * self.fraction,
                           "reason": f"copying {who}: they bought ${s.get('usd') or 0:,.0f} of {s.get('symbol') or '?'}"})
            self.copied[mint] = s["wallet"]
            del self.pending[mint]
            slots -= 1

        for p in v["positions"]:
            if p["pnl_pct"] <= SAFETY_STOP_PCT:
                orders.append({"action": "sell", "token": p["token"], "fraction": 1.0, "reason": f"safety stop at {p['pnl_pct']:+.0f}%"})
            elif p["held_min"] >= TIME_LIMIT_MIN:
                orders.append({"action": "sell", "token": p["token"], "fraction": 1.0, "reason": f"{TIME_LIMIT_MIN // 60}-hour limit"})
        return orders


def build_copy_bots():
    return [CopyBot("Copy 1-33", 1, 33, "copy-a"), CopyBot("Copy 34-66", 34, 66, "copy-b"), CopyBot("Copy 67-100", 67, 100, "copy-c")]


def build_copy_top10():
    """Mechanical yardstick for Shadow: copies the 10 best wallets of the realized-profit leaderboard, quickly and big."""
    b = CopyBot("Copy Top 10", 1, 10, "copy-a", fraction=0.10, window_secs=60, from_signal_ts=True)
    b.description = (f"Copies every buy and sell of the top 10 wallets on the arena's leaderboard, ranked by realized "
                     f"profit over the last two days: {b.fraction:.0%} of equity per buy within {b.window_secs}s of their "
                     f"buy, sells when they sell, {SAFETY_STOP_PCT}% safety stop, {TIME_LIMIT_MIN // 60}-hour limit.")
    b.bio = "Copies only the ten wallets with the most realized profit. A yardstick for the Shadow Claude."
    b.catchphrase = "Ten names, no opinions."
    return b
