"""Rule-based bots. They cost nothing to run and each one tests a specific idea, so the Claude agents
have something honest to beat. Every bot sees the same view and returns orders:

  {"action": "buy",  "token": "<address>", "usd": 50, "reason": "..."}
  {"action": "sell", "token": "<address>", "fraction": 1.0, "reason": "..."}
"""
import random
import zlib

from agent_base import Agent
from market import SOL_MINT


def rug_checked(t, v):
    """True once the token has been through the rug check (when the market runs one at all). Most rugs that hurt
    the strategy bots were bought in their first minutes, before any check had run."""
    if not any("rug" in c for c in v.get("candidates", [])):
        return True  # mock or replay markets have no rug data
    return isinstance(t.get("rug"), dict) and not t["rug"].get("error")


def _num(x, default=0.0):
    """Coerce a possibly-missing/None field to a float so a bot never raises on bad data."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


class GraduatesAgent(Agent):
    """The research's "buy every graduate" benchmark: every pump.fun coin that graduates to PumpSwap and passes the arena's
    safety vetoes is bought once, WAIT_MIN minutes after migrating (after the snipers' first dump), for a fixed SIZE,
    and held HOLD_H hours. If a Claude can't beat this, its coin picking adds nothing over the filter."""
    name = "Graduates"
    avatar = "graduates"
    interval = 0
    max_positions = 40
    max_trade_frac = 1.0
    WAIT_MIN, HOLD_H, SIZE = 15, 6, 20.0

    def __init__(self):
        super().__init__()
        self.description = (f"Buys every coin that graduates from pump.fun and passes the safety vetoes, {self.WAIT_MIN} minutes "
                             f"after it migrates, ${self.SIZE:g} each, and holds it {self.HOLD_H} hours. The yardstick for "
                             "picking coins after the filter.")
        self.bio = "A diploma-stacking robot that buys every coin that graduates, no questions asked beyond the safety checks."
        self.catchphrase = "Everybody walks the stage."
        self.bought = set()

    def decide(self, v):
        now, orders = v["now"], []
        held = {p["token"] for p in v["positions"]}
        for p in v["positions"]:
            if p["held_min"] >= self.HOLD_H * 60:
                orders.append({"action": "sell", "token": p["token"], "fraction": 1.0, "reason": f"held {self.HOLD_H} hours"})
        vetoes = v.get("vetoes") or {}
        slots = self.max_positions - len(held)
        for t in v["candidates"]:
            if slots <= 0:
                break
            a, grad = t["address"], (t.get("pump") or {}).get("graduated")
            if not grad or a in held or a in self.bought or a in v.get("recent_sells", {}):
                continue
            mins = (now - grad) / 60
            if mins < self.WAIT_MIN or mins > 24 * 60 or vetoes.get(a) or t.get("rating") == "red" or not rug_checked(t, v):
                continue
            orders.append({"action": "buy", "token": a, "usd": self.SIZE,
                           "reason": f"graduated {mins:.0f} min ago and passed the vetoes"})
            self.bought.add(a)
            slots -= 1
        if len(self.bought) > 5000:
            self.bought = set(list(self.bought)[-2000:])
        return orders


class HoldSolAgent(Agent):
    name = "Hold SOL"
    description = "Buys SOL on day one and does nothing. If you can't beat this, just hold SOL."
    avatar = "turtle"
    bio = "A sleepy turtle in Solana purple and green. Bought SOL once, pulled its head into its shell, and has not looked at a chart since."
    catchphrase = "Wake me when it's a new all-time high."
    max_trade_frac = 1.0

    def decide(self, v):
        if v["cash"] > 10 and not v["positions"]:
            return [{"action": "buy", "token": SOL_MINT, "usd": v["cash"], "reason": "buy and hold SOL"}]
        return []


class RandomAgent(Agent):
    name = "Random"
    description = "Buys random tokens, sells after a random time. The control group: a real edge must beat this."
    avatar = "monkey"
    bio = "A monkey with a fistful of darts and no opinions. Hits the board, buys whatever bleeds, and is somehow still in the race."
    catchphrase = "Darts don't do due diligence."

    def __init__(self):
        super().__init__()
        self.rng = random.Random()

    def pool(self, v):
        """Which candidates the coin flip picks from. Subclasses narrow this; nothing else changes."""
        return v["candidates"]

    def decide(self, v):
        orders = []
        for p in v["positions"]:
            limit = 10 + zlib.crc32(f'{p["token"]}{p["opened"]}'.encode()) % 170
            if p["held_min"] >= limit:
                orders.append({"action": "sell", "token": p["token"], "fraction": 1.0,
                               "reason": f"random hold time ({limit} min) is up"})
        pool = self.pool(v)
        if pool and len(v["positions"]) < self.max_positions and self.rng.random() < 0.15:
            t = self.rng.choice(pool)
            orders.append({"action": "buy", "token": t["address"], "usd": v["equity"] * 0.10,
                           "reason": f"coin flip ({len(pool)} tokens in the hat)"})
        return orders


class RulesAgent(Agent):
    name = "Rules"
    description = "Only buys green-rated tokens with upward momentum. Take profit +50%, stop loss -25%, 6h time stop."
    avatar = "robot"
    bio = "A robot with a laminated checklist. Green rating, up on the hour, sells exist: tick, tick, tick, buy. Feelings not installed."
    catchphrase = "Checklist complete. Executing."
    max_positions = 5

    def decide(self, v):
        orders = []
        for p in v["positions"]:
            if p["pnl_pct"] >= 50:
                why = f"take profit at {p['pnl_pct']:+.0f}%"
            elif p["pnl_pct"] <= -25:
                why = f"stop loss at {p['pnl_pct']:+.0f}%"
            elif p["held_min"] >= 360:
                why = "6h time stop"
            else:
                continue
            orders.append({"action": "sell", "token": p["token"], "fraction": 1.0, "reason": why})

        held = {p["token"] for p in v["positions"]}
        if len(held) >= self.max_positions:
            return orders
        picks = [t for t in v["candidates"]
                 if t["rating"] == "green" and t["address"] not in held and rug_checked(t, v)
                 and v["now"] - v["recent_sells"].get(t["address"], 0) > 7200
                 and t["chg_m5"] > 0 and t["chg_h1"] > 0 and t["sells_h1"] > 0]
        if picks:
            t = max(picks, key=lambda t: t["vol_h1"])
            orders.append({"action": "buy", "token": t["address"], "usd": v["equity"] * 0.10,
                           "reason": f"green rating, +{t['chg_h1']:.0f}% 1h, ${t['vol_h1']:,.0f} 1h volume"})
        return orders


class GreenRandomAgent(RandomAgent):
    """Random picks, but only among tokens that pass every risk check. If a Claude can't beat this,
    its edge is just the risk filter. Shares RandomAgent's decide() verbatim: same 15% coin flip per
    tick, same 10% of equity, same hash-based random hold time. Only the hat it draws from differs."""
    name = "Green Random"
    description = "Buys random green-rated tokens and sells after a random time. Random with the risk filter switched on."
    avatar = "monkey-green"
    bio = "Random's cousin in a green blindfold. Same darts, same aim, but someone swapped the board for one with only green-rated coins."
    catchphrase = "Can't see. Still green."

    def pool(self, v):
        return [t for t in v["candidates"] if t.get("rating") == "green" and t.get("address") != SOL_MINT]


class MomentumAgent(Agent):
    name = "Momentum"
    description = ("Buys the strongest 5-minute mover (>+2%, >$20k 1h volume, more buys than sells, not red) and "
                   "rides it with a 12% trailing stop. Take profit +40%, 3h time stop, max 5 positions.")
    avatar = "rocket"
    bio = "A rocket with one instrument: the 5-minute chart. If it's going up, it's going up. Trailing stop doubles as a parachute."
    catchphrase = "Up is a direction. I follow it."
    max_positions = 5
    min_vol_h1 = 20_000
    trail_pct = 12
    take_profit = 40
    time_stop_min = 180
    rebuy_wait = 3600

    def __init__(self):
        super().__init__()
        self.peaks = {}  # (token, opened) -> highest value seen for that position

    def decide(self, v):
        orders = []
        live = set()
        for p in v["positions"]:
            key = (p.get("token"), p.get("opened"))
            live.add(key)
            value = _num(p.get("value"))
            peak = max(self.peaks.get(key, 0.0), value)
            self.peaks[key] = peak
            pnl = _num(p.get("pnl_pct"))
            held = _num(p.get("held_min"))
            off_peak = (1 - value / peak) * 100 if peak > 0 else 0.0
            if pnl >= self.take_profit:
                why = f"take profit at {pnl:+.0f}%"
            elif off_peak >= self.trail_pct:
                why = f"trailing stop: {off_peak:.0f}% off the peak (${peak:,.0f}), now {pnl:+.0f}%"
            elif held >= self.time_stop_min:
                why = f"3h time stop at {pnl:+.0f}%"
            else:
                continue
            orders.append({"action": "sell", "token": p["token"], "fraction": 1.0, "reason": why})
        for key in [k for k in self.peaks if k not in live]:
            del self.peaks[key]

        held = {p.get("token") for p in v["positions"]}
        if len(held) >= self.max_positions:
            return orders
        recent = v.get("recent_sells") or {}
        now = _num(v.get("now"))
        picks = [t for t in v["candidates"]
                 if t.get("address") and t["address"] != SOL_MINT and t["address"] not in held
                 and t.get("rating") != "red"
                 and _num(t.get("vol_h1")) >= self.min_vol_h1
                 and _num(t.get("chg_m5")) > 2
                 and _num(t.get("buys_h1")) > _num(t.get("sells_h1"))
                 and now - _num(recent.get(t["address"]), 0) > self.rebuy_wait]
        if picks:
            t = max(picks, key=lambda t: _num(t.get("chg_m5")))
            orders.append({"action": "buy", "token": t["address"], "usd": v["equity"] * 0.10,
                           "reason": f"strongest 5m mover: {_num(t.get('chg_m5')):+.1f}% in 5 min, "
                                     f"${_num(t.get('vol_h1')):,.0f} 1h volume, "
                                     f"{int(_num(t.get('buys_h1')))} buys vs {int(_num(t.get('sells_h1')))} sells"})
        return orders


class SniperAgent(Agent):
    name = "Sniper"
    description = ("Buys brand-new launches (under 30 minutes old, at least $10k liquidity, not red) with 5% of equity, "
                   "at most one snipe per 5 minutes. Exits at +30%, -20% or after 90 minutes.")
    avatar = "sniper"
    bio = "A hooded owl perched over the launchpad, watching pairs hatch. Takes one shot per fresh token and never stays past 90 minutes."
    catchphrase = "New pair spotted. One shot."
    max_positions = 6
    max_age_min = 30
    min_liquidity = 10_000
    snipe_gap = 300
    take_profit = 30
    stop_loss = -20
    time_stop_min = 90

    def __init__(self):
        super().__init__()
        self.last_snipe = 0.0

    def decide(self, v):
        orders = []
        for p in v["positions"]:
            pnl = _num(p.get("pnl_pct"))
            held = _num(p.get("held_min"))
            if pnl >= self.take_profit:
                why = f"take profit at {pnl:+.0f}% after {held:.0f} min"
            elif pnl <= self.stop_loss:
                why = f"stop loss at {pnl:+.0f}% after {held:.0f} min"
            elif held >= self.time_stop_min:
                why = f"90 min time stop at {pnl:+.0f}%"
            else:
                continue
            orders.append({"action": "sell", "token": p["token"], "fraction": 1.0, "reason": why})

        now = _num(v.get("now"))
        held = {p.get("token") for p in v["positions"]}
        if len(held) >= self.max_positions or now - self.last_snipe < self.snipe_gap:
            return orders
        recent = v.get("recent_sells") or {}
        fresh = [t for t in v["candidates"]
                 if t.get("address") and t["address"] != SOL_MINT and t["address"] not in held
                 and t.get("age_min") is not None and _num(t["age_min"], 1e9) < self.max_age_min
                 and t.get("rating") != "red" and rug_checked(t, v)
                 and _num(t.get("liquidity")) >= self.min_liquidity
                 and now - _num(recent.get(t["address"]), 0) > 3600]
        if fresh:
            t = max(fresh, key=lambda t: (_num(t.get("buys_h1")), _num(t.get("liquidity"))))
            self.last_snipe = now
            orders.append({"action": "buy", "token": t["address"], "usd": v["equity"] * 0.05,
                           "reason": f"fresh launch, {_num(t['age_min']):.0f} min old, "
                                     f"${_num(t.get('liquidity')):,.0f} liquidity, "
                                     f"{int(_num(t.get('buys_h1')))} buys in 1h"})
        return orders


class IndexAgent(Agent):
    name = "Index"
    description = ("Holds an equal-weight basket of the top 10 tokens by 1h volume (red-rated excluded), ~90% invested. "
                   "Re-picks the basket at most once an hour; a held token is only resized when its weight is off by more than 50%.")
    avatar = "index"
    bio = "A round pie-chart creature cut into ten equal slices. Owns a bit of everything busy, rebalances hourly, never picks favourites."
    catchphrase = "A slice of everything, a bet on nothing."
    max_positions = 10
    max_trade_frac = 0.10
    basket_size = 10
    invest_frac = 0.90
    rebalance_every = 3600
    drift_tolerance = 0.50

    def __init__(self):
        super().__init__()
        self.last_rebalance = 0.0
        self.target = []  # addresses in the current basket

    def _top(self, v):
        picks = [t for t in v["candidates"]
                 if t.get("address") and t["address"] != SOL_MINT and t.get("rating") != "red"
                 and _num(t.get("price")) > 0 and _num(t.get("liquidity")) > 0]
        picks.sort(key=lambda t: _num(t.get("vol_h1")), reverse=True)
        return [t["address"] for t in picks[:self.basket_size]]

    def decide(self, v):
        now = _num(v.get("now"))
        equity = _num(v.get("equity"))
        positions = {p.get("token"): p for p in v["positions"]}
        by_addr = {t.get("address"): t for t in v["candidates"]}
        orders = []

        rebalancing = not self.target or now - self.last_rebalance >= self.rebalance_every
        if rebalancing:
            self.target = self._top(v)
            self.last_rebalance = now
        # Tokens that have left the feed can't stay in the basket, whatever the hour.
        target = [a for a in self.target if a in by_addr]
        if not target:
            return orders
        slot = equity * self.invest_frac / len(target)
        rank = {a: i + 1 for i, a in enumerate(target)}
        # Dropout sells fill next tick, so new entrants that don't fit yet wait a tick instead of being rejected.
        room = self.max_positions - len(positions)

        for a, p in positions.items():
            if a in target:
                continue
            sym = p.get("symbol") or a[:6]
            if a not in by_addr:
                why = f"{sym} is no longer in the market feed"
            elif rebalancing:
                why = f"{sym} dropped out of the top {self.basket_size} by 1h volume (${_num(by_addr[a].get('vol_h1')):,.0f})"
            else:
                continue  # already ordered out in an earlier tick; it leaves when the pending sell fills
            orders.append({"action": "sell", "token": a, "fraction": 1.0, "reason": why})

        for a in target:
            t = by_addr[a]
            sym = t.get("symbol") or a[:6]
            p = positions.get(a)
            if p is None:
                usd = min(slot, equity * self.max_trade_frac)
                if usd >= 5 and room > 0:
                    room -= 1
                    orders.append({"action": "buy", "token": a, "usd": usd,
                                   "reason": f"new basket entrant: #{rank[a]} by 1h volume (${_num(t.get('vol_h1')):,.0f}), "
                                             f"target weight {slot / equity * 100:.0f}%"})
                continue
            if not rebalancing:
                continue
            value = _num(p.get("value"))
            if value < slot * (1 - self.drift_tolerance) and slot - value >= 5:
                orders.append({"action": "buy", "token": a, "usd": min(slot - value, equity * self.max_trade_frac),
                               "reason": f"top up {sym}: {value / equity * 100:.0f}% of equity vs "
                                         f"{slot / equity * 100:.0f}% target weight"})
            elif value > slot * (1 + self.drift_tolerance) and value > 0:
                frac = round(1 - slot / value, 3)
                orders.append({"action": "sell", "token": a, "fraction": frac,
                               "reason": f"trim {sym}: {value / equity * 100:.0f}% of equity vs "
                                         f"{slot / equity * 100:.0f}% target weight ({p.get('pnl_pct', 0):+.0f}%)"})
        return orders


class DipBuyerAgent(Agent):
    """Buys sharp 5-minute drops in liquid tokens whose hour is still healthy, betting on a bounce.
    Mascot (for the sprite artist): a grey raccoon with a black eye-mask holding a woven shopping basket, standing
    at the bottom of a V-shaped red dip while a gold coin drops into the basket. Bargain-bin energy, teal/mint accent."""
    name = "Dip Buyer"
    description = ("Buys a token that fell 15%+ in 5 minutes while its hour is still green or its volume is high "
                   "(not red-rated, $30k+ liquidity) with 5% of equity. Exits at +15%, -12% or after 45 minutes; "
                   "waits 2 hours before touching the same token again.")
    avatar = "dip-buyer"
    bio = "A raccoon with a shopping basket who only shows up when something is 15% off. Buys the panic, sells the bounce, never pays retail."
    catchphrase = "Fifteen percent off? Say less."
    max_positions = 5
    size_frac = 0.05
    dip_pct = -15
    min_liquidity = 30_000
    high_vol_h1 = 100_000
    take_profit = 15
    stop_loss = -12
    time_stop_min = 45
    cooldown = 7200

    def __init__(self):
        super().__init__()
        self.last_buy = {}  # token -> when we last bought it

    def decide(self, v):
        orders = []
        now = _num(v.get("now"))
        for p in v["positions"]:
            pnl, held = _num(p.get("pnl_pct")), _num(p.get("held_min"))
            if pnl >= self.take_profit:
                why = f"bounce caught: take profit at {pnl:+.0f}% after {held:.0f} min"
            elif pnl <= self.stop_loss:
                why = f"no bounce: stop loss at {pnl:+.0f}% after {held:.0f} min"
            elif held >= self.time_stop_min:
                why = f"{self.time_stop_min} min time stop at {pnl:+.0f}%, the dip didn't recover"
            else:
                continue
            orders.append({"action": "sell", "token": p["token"], "fraction": 1.0, "reason": why})
        for a in [a for a, ts in self.last_buy.items() if now - ts > self.cooldown]:
            del self.last_buy[a]

        held = {p.get("token") for p in v["positions"]}
        if len(held) >= self.max_positions:
            return orders
        recent = v.get("recent_sells") or {}

        def cooled(addr):  # one try per token per cooldown, counting both our buys and the arena's sell record
            return all(ts is None or now - _num(ts) > self.cooldown for ts in (self.last_buy.get(addr), recent.get(addr)))

        dips = [t for t in v["candidates"]
                if t.get("address") and t["address"] != SOL_MINT and t["address"] not in held
                and t.get("rating") != "red" and rug_checked(t, v)
                and _num(t.get("liquidity")) >= self.min_liquidity
                and _num(t.get("chg_m5")) <= self.dip_pct
                and (_num(t.get("chg_h1")) > 0 or _num(t.get("vol_h1")) >= self.high_vol_h1)
                and _num(t.get("sells_h1")) > 0
                and cooled(t["address"])]
        if dips:
            t = max(dips, key=lambda t: _num(t.get("vol_h1")))  # the most traded dip is the likeliest to bounce
            self.last_buy[t["address"]] = now
            why = (f"{_num(t.get('chg_m5')):+.0f}% in 5 min, {_num(t.get('chg_h1')):+.0f}% on the hour, "
                   f"${_num(t.get('liquidity')):,.0f} liquidity, ${_num(t.get('vol_h1')):,.0f} 1h volume")
            if _num(t.get("chg_h1")) <= 0:
                why += " (hour is red, but the volume is high)"
            orders.append({"action": "buy", "token": t["address"], "usd": v["equity"] * self.size_frac, "reason": why})
        return orders
