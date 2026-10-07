"""Fake exchange: fills trades the way a constant-product AMM pool would, plus fees and real-world friction.

Price impact model (the fallback when no live router quote is available): a pool with $L liquidity has roughly
$L/2 on the quote side (X).
Buying $dx pushes your average fill price to   spot * (1 + dx / X)
Selling tokens worth $v at spot returns        X * v / (X + v)

When the live market can get a Jupiter quote for the exact size (see market.py), that quote replaces the
formula: it already contains the pool's own fee and real price impact across the best route. Either way every
trade also pays FEE (the app/bot fee a Telegram or web trading bot charges, 1% by default) and a fixed network
priority fee in dollars; a failed transaction still pays the network fee, as on Solana.

Friction settings (environment variables, read once at import; the defaults are on):
  ARENA_ROUTE=bot             how you'd trade live, so the results transfer:
                                bot     a Telegram/web trading bot (Axiom, Photon, GMGN): 1% app fee + $0.25 network
                                fomo    the Fomo app: 0.5% with network fees included, reported $0.95 minimum per trade,
                                        sandwich-protected (no MEV slippage)
                                jupiter swapping through Jupiter yourself: no app fee + $0.25 network
                              Every setting below overrides the route's default.
  ARENA_MIN_FEE_USD           smallest app fee charged on a trade (fomo: 0.95; others: 0).
  ARENA_FEE                   app/bot fee per trade as a fraction; overrides the route's default (bot 0.01, jupiter 0).
                              Applied to formula and Jupiter fills alike.
  ARENA_POOL_FEE=0.0025       the pool's own swap fee, added to FORMULA fills only (Jupiter quotes already include it).
  ARENA_PRIORITY_FEE_USD=0.25 fixed network + priority fee per transaction in SOL-equivalent dollars (roughly
                              0.001-0.002 SOL). Charged on buys, sells and FAILED transactions. 0 disables it.
  ARENA_FAIL_RATE=0.05        chance that an order fails (nothing traded). 0 disables failed transactions.
  ARENA_FAIL_RATE_PUMP=0.15   failure chance when |chg_m5| of the token is above ARENA_FAIL_PUMP_CHG (congestion
                              spikes on pumps and dumps).
  ARENA_FAIL_PUMP_CHG=50      the 5-minute price change (%) above which the pump failure rate applies.
  ARENA_MEV_MAX_PCT=3         worst extra adverse slippage on buys from sandwich bots, in %. 0 disables MEV.
  ARENA_MEV_MIN_PCT=0.5       the least extra slippage once a token counts as pumping.
  ARENA_MEV_CHG=10            a buy counts as "into a pump" when the token's chg_m5 is at least this many %.
                              Slippage scales from MIN to MAX with the size of the pump (10% -> 100%) and the trade
                              size relative to 1% of the pool's liquidity.
  ARENA_EARLY_PENALTY_PCT=5   extra adverse slippage on a buy in a token's first ARENA_EARLY_SECS=60 seconds after launch
                              or after graduating to PumpSwap: same-block snipers sell into the first buyers.
  ARENA_SOL_USD=150           SOL price used to place a PumpSwap pool in its market-cap fee tier (formula fills only).

Fomo's fee is tiered by order size (reported by Datawallet, 2026; Fomo's own page could not be fetched): flat $0.10
under $5, 2% from $5 to $47.50, a flat $0.95 from $47.50 to $190, and 0.5% from $190. Pool fees on formula fills:
1.25% on the pump.fun bonding curve, PumpSwap tiered by market cap from 1.25% under 420 SOL down to 0.30% at 98,240 SOL
(pump.fun docs), 0.25% on other pools.
"""
import math
import os


def _env(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


ROUTE = os.environ.get("ARENA_ROUTE", "bot").strip().lower()
ROUTES = {  # (app fee, minimum app fee $, network fee $ per transaction, worst sandwich slippage %)
    "bot": (0.01, 0.0, 0.25, 3.0),
    "fomo": (0.005, 0.95, 0.0, 0.0),
    "jupiter": (0.0, 0.0, 0.25, 3.0),
}
_R = ROUTES.get(ROUTE, ROUTES["bot"])
FEE = _env("ARENA_FEE", _R[0])                                 # app/bot fee per trade
MIN_FEE_USD = max(0.0, _env("ARENA_MIN_FEE_USD", _R[1]))      # the app fee is never less than this
POOL_FEE = max(0.0, _env("ARENA_POOL_FEE", 0.0025))           # pool swap fee, formula fills only
PRIORITY_FEE_USD = max(0.0, _env("ARENA_PRIORITY_FEE_USD", _R[2]))
FAIL_RATE = max(0.0, _env("ARENA_FAIL_RATE", 0.05))
FAIL_RATE_PUMP = max(0.0, _env("ARENA_FAIL_RATE_PUMP", 0.15))
FAIL_PUMP_CHG = _env("ARENA_FAIL_PUMP_CHG", 50)
MEV_MAX_PCT = max(0.0, _env("ARENA_MEV_MAX_PCT", _R[3]))
MEV_MIN_PCT = max(0.0, min(_env("ARENA_MEV_MIN_PCT", 0.5), MEV_MAX_PCT))
MEV_CHG = _env("ARENA_MEV_CHG", 10)
QUOTE_SANITY = 3.0  # a router quote implying a price more than 3x away from spot is distrusted (decimals bug, stale feed)


# Fomo's size tiers: (order below $, ("flat", dollars) or ("pct", fraction)). Ignored when ARENA_FEE or
# ARENA_MIN_FEE_USD is set (then the flat FEE / MIN_FEE_USD rule applies).
FOMO_TIERS = [(5.0, ("flat", 0.10)), (47.5, ("pct", 0.02)), (190.0, ("flat", 0.95)), (float("inf"), ("pct", 0.005))]
TIERED = ROUTE == "fomo" and "ARENA_FEE" not in os.environ and "ARENA_MIN_FEE_USD" not in os.environ
EARLY_PENALTY = max(0.0, _env("ARENA_EARLY_PENALTY_PCT", 5)) / 100
EARLY_SECS = max(0.0, _env("ARENA_EARLY_SECS", 60))
SOL_USD = max(1.0, _env("ARENA_SOL_USD", 150))


def app_fee(usd):
    """The app/bot fee on a trade of `usd`: Fomo's size tiers on the fomo route, else FEE of it (at least MIN_FEE_USD)."""
    if usd <= 0:
        return 0.0
    if TIERED:
        kind, val = next(fee for top, fee in FOMO_TIERS if usd < top)
        return val if kind == "flat" else usd * val
    return max(usd * FEE, MIN_FEE_USD)


def pool_fee(token):
    """The pool's own swap fee for a formula fill (router quotes already include it)."""
    t = token or {}
    if "ARENA_POOL_FEE" in os.environ:
        return POOL_FEE
    dex = str(t.get("dex") or "").lower()
    if t.get("source") == "pumpfun" or dex == "pumpfun":  # still on the bonding curve
        return 0.0125
    if dex == "pumpswap":
        mcap_sol = (t.get("mcap") or 0) / SOL_USD
        if mcap_sol <= 420:
            return 0.0125
        if mcap_sol >= 98240:
            return 0.003
        f = math.log(mcap_sol / 420) / math.log(98240 / 420)  # log-linear between the published end tiers
        return 0.0125 - f * (0.0125 - 0.003)
    return POOL_FEE


def early_penalty(token, now):
    """Extra adverse slippage (fraction) for buying in the first EARLY_SECS after launch or graduation."""
    t = token or {}
    if EARLY_PENALTY <= 0:
        return 0.0
    age = t.get("age_min")
    grad = (t.get("pump") or {}).get("graduated")
    if (age is not None and age * 60 < EARLY_SECS) or (grad and now - grad < EARLY_SECS):
        return EARLY_PENALTY
    return 0.0


def fee_text():
    """How fees work on this route, in a sentence the agents can read."""
    if TIERED:
        return ("Fomo app fee, tiered by order size (2% on orders under $47.50, a flat $0.95 from $47.50 to $190, "
                "0.5% from $190, network fees included)")
    fee = f"{FEE * 100:g}% app fee" + (f" (at least ${MIN_FEE_USD:.2f} per trade)" if MIN_FEE_USD else "")
    net = f" plus a ${PRIORITY_FEE_USD:.2f} network fee" if PRIORITY_FEE_USD else ", network fees included"
    return fee + net


def fail_probability(token):
    """Chance that an order on this token fails outright. Higher while the token is moving fast."""
    if FAIL_RATE <= 0:
        return 0.0
    chg = abs((token or {}).get("chg_m5") or 0.0)
    return FAIL_RATE_PUMP if chg > FAIL_PUMP_CHG else FAIL_RATE


def mev_slippage(token, usd):
    """Extra adverse slippage (fraction) a buy suffers from sandwich bots when buying into a pump.
    0 below MEV_CHG; otherwise MEV_MIN..MEV_MAX scaled by how hard the token is pumping (60%) and how big
    the buy is relative to 1% of the pool (40%)."""
    if MEV_MAX_PCT <= 0 or not token:
        return 0.0
    chg = token.get("chg_m5") or 0.0
    if chg < MEV_CHG:
        return 0.0
    pump = min(1.0, max(0.0, (chg - MEV_CHG) / max(1.0, 100.0 - MEV_CHG)))
    liq = token.get("liquidity") or 0.0
    size = min(1.0, usd / (liq * 0.01)) if liq > 0 else 1.0
    return (MEV_MIN_PCT + (MEV_MAX_PCT - MEV_MIN_PCT) * (0.6 * pump + 0.4 * size)) / 100.0


def _quoted(quote, amount, expect, ratio_fn):
    """Run a router quote callable safely. Returns its result only if it is positive and within QUOTE_SANITY of
    what the spot price implies (ratio_fn(result) is the implied/spot ratio); None otherwise."""
    if quote is None or amount <= 0:
        return None
    try:
        out = quote(amount)
    except Exception as e:
        print(f"[exchange] router quote failed, using the AMM formula: {e}")
        return None
    if not out or out <= 0 or not expect:
        return None
    r = ratio_fn(out)
    if r <= 0 or r > QUOTE_SANITY or r < 1 / QUOTE_SANITY:
        print(f"[exchange] router quote {r:.2f}x away from spot, distrusting it and using the AMM formula")
        return None
    return out


def buy_fill(token, usd, quote=None, mev=0.0):
    """Returns (qty, avg_fill_price). qty 0 means the trade can't fill.
    `quote(spend_usd) -> qty` is an optional live router quote for the exact size (market.quote_buy); when it is
    missing, fails or looks wrong the AMM formula is used. `mev` is extra adverse slippage (fraction) on the fill."""
    x = token.get("liquidity", 0) / 2
    price = token.get("price", 0)
    if price <= 0 or usd <= 0:
        return 0.0, 0.0
    spend = usd - app_fee(usd) - PRIORITY_FEE_USD
    if spend <= 0:
        return 0.0, 0.0
    qty = _quoted(quote, spend, price, lambda q: (spend / q) / price)
    if qty is None:
        if x <= 0:
            return 0.0, 0.0
        qty = spend * (1 - pool_fee(token)) / (price * (1 + spend / x))
    qty *= 1 - max(0.0, min(0.5, mev))
    return qty, spend / qty


def sell_fill(token, qty, quote=None):
    """Returns (usd_proceeds, avg_fill_price). `quote(qty) -> gross_usd` is an optional live router quote."""
    x = token.get("liquidity", 0) / 2
    price = token.get("price", 0)
    if price <= 0 or qty <= 0:
        return 0.0, 0.0
    v = qty * price
    gross = _quoted(quote, qty, price, lambda g: g / v)
    if gross is None:
        if x <= 0:
            return 0.0, 0.0
        gross = x * v / (x + v) * (1 - pool_fee(token))
    proceeds = max(0.0, gross - app_fee(gross) - PRIORITY_FEE_USD)
    return proceeds, proceeds / qty


def liquidation_value(token, qty):
    """What a position is really worth: what you'd get if you sold it all right now (formula only, no network)."""
    if not token:
        return 0.0
    return sell_fill(token, qty)[0]


def round_trip_pct(usd, liquidity=1e12, token=None):
    """What buying `usd` of a token and selling it straight back costs, in % of `usd`: app and network fees plus the
    pool's fee (and price impact when `liquidity` is given). Default liquidity is effectively infinite: fees only.
    `token` (optional) supplies dex/source/mcap for the pool fee."""
    t = {**(token or {}), "price": 1.0, "liquidity": liquidity}
    qty, _ = buy_fill(t, usd)
    if qty <= 0:
        return 100.0
    proceeds, _ = sell_fill(t, qty)
    return (1 - proceeds / usd) * 100


def cost_table(sizes=(25, 50, 100, 250)):
    """'$25: 4.5%, ...' - the fee-only round trip on an ordinary pool at a few position sizes, for the Claudes' brief."""
    return ", ".join(f"${s:g}: {round_trip_pct(s):.1f}%" for s in sizes)
