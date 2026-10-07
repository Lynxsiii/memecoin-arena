"""Market data: live Solana memecoin feed (DexScreener + Solana RPC + Jupiter quotes) and an offline mock market.

Jupiter (https://lite-api.jup.ag, free, no key) is used two ways in the live market, never in MockMarket:
  - Sellability: once a token's authority check is done, the arena asks Jupiter for a quote selling about
    $5 of it for SOL. No route (TOKEN_NOT_TRADABLE / NO_ROUTES_FOUND) flags the token
    "no sell route found (possible honeypot)", a route returning far less than the quoted value flags
    "selling returns only X% of value (sell tax / honeypot)"; both make the risk rating red. Results are cached
    in the same saved risk cache and re-checked every ARENA_SELL_CHECK_SECS.
  - Real fills: Arena.execute asks quote_buy / quote_sell for the exact size; the router's outAmount (SOL
    converted at the DexScreener SOL price, USDC for SOL itself) becomes the fill. Any failure, timeout or
    rate limit falls back to the AMM formula in exchange.py.

Settings (environment variables, read once at import):
  ARENA_JUPITER=1               0/off disables all Jupiter calls (sellability + real fills). Default on.
  ARENA_JUPITER_URL             quote endpoint, default https://lite-api.jup.ag/swap/v1/quote
  ARENA_JUPITER_TIMEOUT=3       seconds per quote request (keep short: fills run inside the tick).
  ARENA_JUPITER_PER_MIN=20      max quote requests per rolling minute; beyond it fills use the formula.
                                A 429 pauses all Jupiter calls for 60 seconds.
  ARENA_QUOTE_CACHE_SECS=10     identical quotes (same mints, size within ~0.5%) are reused for this long.
  ARENA_SELL_CHECKS=3           sellability probes per 30-second tick (one Jupiter request each).
  ARENA_SELL_CHECK_SECS=1800    re-check a token's sellability after this many seconds (not permanent).
  ARENA_SELL_PROBE_USD=5        size of the sellability probe in dollars.
  ARENA_SELL_MIN_RATIO=0.5      a probe returning less than this fraction of its spot value is flagged.

Discovery (where tracked tokens come from; every token carries `source` and `first_seen`):
  - "promoted": DexScreener's paid placements (/token-profiles/latest, /token-boosts/latest, /token-boosts/top).
    Measured over a trading day, the average promoted token lost 5.7% in the hour after it appeared: these are
    marketing, so an arena fed only by them is fishing in a sinking pool.
  - "organic": GeckoTerminal's free public API (https://api.geckoterminal.com/api/v2, no key): Solana's trending
    pools (24-hour and 1-hour rankings, two pages) and newest pools, four requests per discover cycle (every
    120 s) against a free-tier budget of about 30 requests a minute. The tracked token is always the memecoin
    side of the pool: SOL, USDC, USDT and other majors are never tracked, and pools with under
    ARENA_ORGANIC_MIN_LIQ of reserves are ignored (the volume rankings are full of $0-liquidity wash-traded
    shells). A 429 pauses GeckoTerminal for 60 s, doubling up to 10 minutes while it keeps happening; any
    failure just means no organic discoveries this cycle. Prices for every token still come from DexScreener.
  - "both": found by both feeds (sticky once set).
  - "graduated": a pump.fun token that just migrated to its PumpSwap pool (PumpPortal's free migration stream,
    see pumpfun.py). Every graduation is tracked; DexScreener prices the pool (dexId "pumpswap").
  - "pumpfun": a fresh pump.fun bonding-curve launch with traction at second zero. Thousands launch a day, so only
    the ARENA_PUMPFUN_NEW launches per discover cycle with the largest initial market cap (= the creator's own
    buy, which must be > 0 SOL) at or above ARENA_PUMPFUN_MIN_MCAP_SOL are tracked. DexScreener prices bonding curves too (dexId
    "pumpfun", pair = the curve account) but reports no liquidity for them, so the arena fills in the curve's
    virtual reserves (sqrt(mcap_sol * 32.19) SOL each side, the constant-product the curve really trades on).
    Jupiter routes them (label "Pump.fun"), so sellability probes and fills work unchanged. A launch that later
    graduates becomes "graduated". In the pumpfun universe launches are picked by probation instead: every launch
    passing the same creator-buy floor waits up to ARENA_PUMPFUN_PROBATION_MIN minutes, up to 120 of them (least
    recently priced first) are priced on DexScreener each discover cycle (4 requests of 30), and one is tracked
    as soon as its market cap reaches ARENA_PUMPFUN_TRACK_MCAP_USD or its 1h volume ARENA_PUMPFUN_TRACK_VOL_USD
    with at least 40 1h transactions; the rest are forgotten. Every curve token carries pump.curve_pct
    (market cap / the $69,000 graduation cap, 0-100; 100 once graduated) and every priced token `high` (highest
    price seen).
  - "copy": force-tracked with LiveMarket.track() (a trader the arena follows just bought it).
  Every token also carries `sources`, the list of every tag it ever matched, in order; `source` is the first one
  (except promoted + organic -> "both", and pumpfun -> graduated).
  When the pool is full (max_tracked), eviction keeps about ARENA_PUMPFUN_SHARE of the slots for pump.fun tokens
  and splits the rest between organic and promoted by ARENA_ORGANIC_SHARE, dropping first dead tokens (any token
  DexScreener has not priced for 10 minutes and, with ARENA_UNIVERSE=pumpfun, a launch trading at 10% or less of
  its high), then the oldest free token of whichever group is furthest over its share (among pump.fun tokens,
  launches before graduations). Held tokens and tokens protected by track() are never evicted.
  ARENA_DISCOVERY=both          dexscreener | geckoterminal | both: which discovery feeds to use.
  ARENA_ORGANIC_SHARE=0.5       share of the non-pump.fun slots kept for organic tokens (0 = promoted only,
                                1 = organic only).
  ARENA_ORGANIC_MIN_LIQ=5000    GeckoTerminal pools with fewer dollars of reserves than this are not tracked.
  ARENA_GECKO_URL               GeckoTerminal base URL, default https://api.geckoterminal.com/api/v2.
  ARENA_PUMPFUN=1               0/off: no pump.fun feed, no pump.fun tokens, their slots go back to the others
                                (also read by pumpfun.py, which has the websocket settings).
  ARENA_PUMPFUN_SHARE=0.2       share of max_tracked kept for pump.fun tokens (graduated + launches).
  ARENA_PUMPFUN_NEW=2           fresh launches tracked per discover cycle (every 120 s), best first.
  ARENA_PUMPFUN_MIN_MCAP_SOL=30 a launch needs at least this initial market cap in SOL (27.96 = nobody bought;
                                30 means the creator put in about 1 SOL) to be considered.
  ARENA_UNIVERSE=all            all | pumpfun. pumpfun: only pump.fun tokens (graduations + launches through
                                probation); promoted and organic discovery are off, ARENA_PUMPFUN_SHARE is forced
                                to 1, max_tracked defaults to 150 (60 otherwise) and track() refuses mints that
                                are not pump.fun (do not end in "pump" and carry no pump.fun details).
  ARENA_PUMPFUN_PROBATION_MIN=20  pumpfun universe: minutes after its launch a launch stays on probation.
  ARENA_PUMPFUN_TRACK_MCAP_USD=12000  pumpfun universe: market cap in dollars that promotes a launch.
  ARENA_PUMPFUN_TRACK_VOL_USD=8000    pumpfun universe: 1h volume in dollars that promotes a launch (with at
                                least 40 1h buys + sells).

Force-tracking: LiveMarket.track(mint, source="copy", hold_secs=21600, held=()) adds a token the feeds have not
found (no network call; safe under the arena lock), prices it on the next refresh and protects it from eviction
for hold_secs after the last track() call. MockMarket.track() adds a fake token so offline tests work.

Rug data (optional): if a module `rugdata` is importable it is used for deeper checks (holder concentration and
the like). Contract: rugdata.assess(session, mint, decimals=None) -> dict | None (None = transient failure, retried
later) and rugdata.flags(info) -> list of (text, hard) where a hard flag makes the token red. Results live on the
token as t["rug"] (+ t["rug_checked"]) and in the saved risk cache as risk_cache[addr]["rug"] / ["rug_checked"], so
restarts reuse them. Without the module everything works as before.
  ARENA_RUG_CHECKS=4            rugdata.assess calls per 30-second tick, never-checked tokens first (0 disables).
  ARENA_RUG_CHECK_SECS=1800     re-assess a token after this many seconds (holder concentration changes).
"""
import math
import os
import random
import time
from collections import deque

import requests

try:
    import rugdata  # optional sibling module, see the docstring
except ImportError:
    rugdata = None
except Exception as _e:  # a half-written module must never take the arena down
    print(f"[market] rugdata unavailable: {_e}")
    rugdata = None

try:
    import pumpfun  # optional: pump.fun launches and graduations (PumpPortal's free websocket)
except ImportError:
    pumpfun = None
except Exception as _e:
    print(f"[market] pumpfun unavailable: {_e}")
    pumpfun = None

DEX = "https://api.dexscreener.com"
RPC = "https://api.mainnet-beta.solana.com"
GECKO = os.environ.get("ARENA_GECKO_URL", "https://api.geckoterminal.com/api/v2").rstrip("/")
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCdWzEeDfa"
# Quote-side assets: when one of these is a pool's base token the other side is the memecoin; never tracked.
MAJORS = {
    SOL_MINT, USDC_MINT, USDT_MINT,
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",   # cbBTC
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # WBTC (Portal)
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",  # WETH (Portal)
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",   # mSOL
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",  # JitoSOL
    "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo",  # PYUSD
}
# GeckoTerminal listings read per discover cycle (the /pools volume and tx-count rankings were checked and are
# dominated by SOL/USDC pools and $0-liquidity shells, so they are not used).
GECKO_PATHS = (
    "/networks/solana/trending_pools?page=1",
    "/networks/solana/trending_pools?page=1&duration=1h",
    "/networks/solana/trending_pools?page=2",
    "/networks/solana/new_pools?page=1",
)

DISCOVERY = os.environ.get("ARENA_DISCOVERY", "both").strip().lower()
if DISCOVERY not in ("dexscreener", "geckoterminal", "both"):
    DISCOVERY = "both"
ORGANIC_SHARE = min(1.0, max(0.0, float(os.environ.get("ARENA_ORGANIC_SHARE", "0.5") or 0)))
if DISCOVERY == "dexscreener":
    ORGANIC_SHARE = 0.0
elif DISCOVERY == "geckoterminal":
    ORGANIC_SHARE = 1.0
ORGANIC_MIN_LIQ = float(os.environ.get("ARENA_ORGANIC_MIN_LIQ", "5000") or 0)
PUMPFUN_ON = pumpfun is not None and getattr(pumpfun, "ENABLED", False) and getattr(pumpfun, "websocket", None) is not None
PUMPFUN_SHARE = min(1.0, max(0.0, float(os.environ.get("ARENA_PUMPFUN_SHARE", "0.2") or 0))) if PUMPFUN_ON else 0.0
PUMPFUN_NEW = max(0, int(float(os.environ.get("ARENA_PUMPFUN_NEW", "2") or 0)))
PUMPFUN_MIN_MCAP_SOL = float(os.environ.get("ARENA_PUMPFUN_MIN_MCAP_SOL", "30") or 0)
# universe: "all" (promoted + organic + pump.fun) or "pumpfun" (only PumpPortal launches / graduations)
UNIVERSE = os.environ.get("ARENA_UNIVERSE", "all").strip().lower()
if UNIVERSE != "pumpfun":
    UNIVERSE = "all"
if UNIVERSE == "pumpfun":
    PUMPFUN_SHARE = 1.0  # every slot is a pump.fun slot; promoted / organic discovery is off (see _discover)
    if not PUMPFUN_ON:
        print("[market] ARENA_UNIVERSE=pumpfun but the pump.fun feed is off: nothing will be discovered")
PROBATION_MIN = float(os.environ.get("ARENA_PUMPFUN_PROBATION_MIN", "20") or 20)
TRACK_MCAP_USD = float(os.environ.get("ARENA_PUMPFUN_TRACK_MCAP_USD", "12000") or 0)
TRACK_VOL_USD = float(os.environ.get("ARENA_PUMPFUN_TRACK_VOL_USD", "8000") or 0)
TRACK_MIN_TXNS = 40          # 1h buys + sells a launch needs for the volume rule
PROBATION_PER_CYCLE = 120    # launches priced per discover cycle (4 DexScreener requests of 30)
GRADUATION_CAP_USD = 69000   # market cap at which a pump.fun curve completes (for curve_pct)
CURVE_K_SOL = 30.0 * 1.073e9 / 1e9   # pump.fun bonding curve: 30 virtual SOL x 1.073 billion virtual tokens, per token
CURVE_VIRTUAL_SOL = 30.0
# eviction groups: a token's group follows its primary source; anything unknown counts as promoted
SOURCE_GROUP = {"promoted": "promoted", "organic": "organic", "both": "both", "pumpfun": "pumpfun",
                "graduated": "pumpfun"}
GROUPS = ("organic", "promoted", "pumpfun")
RUG_CHECKS = int(float(os.environ.get("ARENA_RUG_CHECKS", "4") or 0))
RUG_CHECK_SECS = float(os.environ.get("ARENA_RUG_CHECK_SECS", "1800") or 1800)

JUP_ON = os.environ.get("ARENA_JUPITER", "1").strip().lower() not in ("0", "off", "false", "no")
JUP_URL = os.environ.get("ARENA_JUPITER_URL", "https://lite-api.jup.ag/swap/v1/quote")
JUP_TIMEOUT = float(os.environ.get("ARENA_JUPITER_TIMEOUT", "3") or 3)
JUP_PER_MIN = int(float(os.environ.get("ARENA_JUPITER_PER_MIN", "20") or 20))
QUOTE_CACHE_SECS = float(os.environ.get("ARENA_QUOTE_CACHE_SECS", "10") or 0)
SELL_CHECKS = int(float(os.environ.get("ARENA_SELL_CHECKS", "3") or 0))
SELL_CHECK_SECS = float(os.environ.get("ARENA_SELL_CHECK_SECS", "1800") or 1800)
SELL_PROBE_USD = float(os.environ.get("ARENA_SELL_PROBE_USD", "5") or 5)
SELL_MIN_RATIO = float(os.environ.get("ARENA_SELL_MIN_RATIO", "0.5") or 0)
NO_ROUTE_CODES = {"TOKEN_NOT_TRADABLE", "NO_ROUTES_FOUND", "COULD_NOT_FIND_ANY_ROUTE", "ROUTE_PLAN_DOES_NOT_CONSUME_ALL_THE_AMOUNT"}
_B58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def plausible_mint(addr):
    """True for strings shaped like a Solana public key (so stub tokens in tests never reach Jupiter)."""
    return isinstance(addr, str) and 32 <= len(addr) <= 44 and set(addr) <= _B58


_rug_flags_warned = False


def _rug_flags(t):
    """(text, hard) pairs from the optional rugdata module for a token that has been assessed; [] otherwise."""
    global _rug_flags_warned
    info = t.get("rug")
    if rugdata is None or info is None:
        return []
    try:
        out = []
        for text, hard in rugdata.flags(info) or []:
            if text:
                out.append((str(text), bool(hard)))
        return out
    except Exception as e:
        if not _rug_flags_warned:
            _rug_flags_warned = True
            print(f"[market] rugdata.flags failed: {str(e)[:120]}")
        return []


def risk_flags(t):
    flags = []
    r = t.get("risk")
    if r is None:
        flags.append("authority check pending")
    else:
        if not r.get("mint_revoked"):
            flags.append("mint authority NOT revoked (dev can print tokens)")
        if not r.get("freeze_revoked"):
            flags.append("freeze authority NOT revoked (dev can freeze wallets)")
    s = t.get("sellable")
    if s:
        if not s.get("ok"):
            flags.append("no sell route found (possible honeypot)")
        elif s.get("ratio") is not None and s["ratio"] < SELL_MIN_RATIO:
            flags.append(f"selling returns only {s['ratio']:.0%} of value (sell tax / honeypot)")
    if t.get("liquidity", 0) < 20_000:
        flags.append("liquidity under $20k")
    if t.get("age_min") is not None and t["age_min"] < 30:
        flags.append("pair younger than 30 min")
    if t.get("buys_h1", 0) > 20 and t.get("sells_h1", 0) == 0:
        flags.append("no sells in last hour (possible honeypot)")
    if t.get("mcap", 0) > 0 and t.get("liquidity", 0) / t["mcap"] < 0.05:
        flags.append("liquidity under 5% of market cap")
    flags.extend(text for text, _ in _rug_flags(t))
    return flags


def risk_rating(flags, hard=False):
    """`hard` is True when the rug data raised a hard flag (see rugdata.flags); that alone makes the token red."""
    if hard or any("NOT revoked" in f or "honeypot" in f for f in flags):
        return "red"
    if not flags:
        return "green"
    return "yellow" if len(flags) <= 2 else "red"


def _annotate(t):
    price = t.get("price") or 0
    if price > 0:
        t["high"] = max(t.get("high") or 0, price)  # highest price seen while tracked (dead-launch eviction)
    pump = t.get("pump")
    if isinstance(pump, dict) and pump.get("graduated"):
        pump["curve_pct"] = 100.0  # the curve completed: never a stale value from the curve days
    elif t.get("dex") == "pumpfun" or t.get("source") == "pumpfun":
        curve_pct = min(100.0, (t.get("mcap") or 0) / GRADUATION_CAP_USD * 100)  # progress toward graduation
        t.setdefault("pump", {})["curve_pct"] = round(curve_pct, 1)
    t["flags"] = risk_flags(t)
    t["rating"] = risk_rating(t["flags"], hard=any(h for _, h in _rug_flags(t)))


def curve_liquidity_usd(mcap_usd, sol_usd):
    """Dollar depth of a pump.fun bonding curve from its market cap: the curve is a constant-product AMM on
    virtual reserves (30 SOL x 1.073 billion tokens at launch), so vSOL = sqrt(mcap_sol * k) and the depth a trade
    sees is vSOL on each side. Returns 0 when either input is missing."""
    if not mcap_usd or not sol_usd or mcap_usd <= 0 or sol_usd <= 0:
        return 0.0
    v_sol = math.sqrt(mcap_usd / sol_usd * CURVE_K_SOL)
    return round(2 * v_sol * sol_usd, 2)


def merge_source(t, src):
    """Record that token `t` was (also) found by `src`. `sources` lists every tag in order; the primary `source`
    is the first one, except: promoted + organic -> "both" (the legacy tag market memory buckets on) and a pump.fun
    launch that graduates -> "graduated". Returns True when the primary source changed."""
    old = t.get("source")
    srcs = t.get("sources")
    if not isinstance(srcs, list):
        srcs = t["sources"] = [old] if old else []
    if src not in srcs:
        srcs.append(src)
    if not old:
        t["source"] = src
    elif old == src:
        return False
    elif {old, src} <= {"promoted", "organic", "both"}:
        t["source"] = "both"
    elif old == "pumpfun" and src == "graduated":
        t["source"] = "graduated"
    return t["source"] != old


def parse_pair(p):
    tx = (p.get("txns") or {}).get("h1") or {}
    vol = p.get("volume") or {}
    ch = p.get("priceChange") or {}
    base = p.get("baseToken") or {}
    created = p.get("pairCreatedAt")
    return {
        "address": base.get("address"),
        "symbol": base.get("symbol") or "?",
        "name": base.get("name") or "",
        "pair": p.get("pairAddress"),    # pool / bonding-curve account (GeckoTerminal trades are per pool)
        "dex": p.get("dexId"),           # e.g. raydium, orca, meteora, pumpswap, pumpfun (= still on the curve)
        "price": _f(p.get("priceUsd")),
        "liquidity": _f((p.get("liquidity") or {}).get("usd")),
        "mcap": _f(p.get("marketCap") or p.get("fdv")),
        "vol_h1": _f(vol.get("h1")),
        "vol_h24": _f(vol.get("h24")),
        "buys_h1": int(_f(tx.get("buys"))),
        "sells_h1": int(_f(tx.get("sells"))),
        "chg_m5": _f(ch.get("m5")),
        "chg_h1": _f(ch.get("h1")),
        "chg_h24": _f(ch.get("h24")),
        "age_min": (time.time() - created / 1000) / 60 if created else None,
        "url": p.get("url", ""),
        "updated": time.time(),
    }


class LiveMarket:
    """Discovers Solana tokens (DexScreener promotions + GeckoTerminal organic listings) and keeps their prices
    fresh from DexScreener."""

    # per-token state that survives a price refresh
    KEEP = ("first_seen", "risk", "decimals", "sellable", "source", "rug", "rug_checked", "rug_tried")
    # same, but only copied when set (so recordings don't fill up with nulls): every source tag the token
    # matched, eviction protection from track(), the pump.fun launch / graduation details
    KEEP_IF_SET = ("sources", "protect_until", "tracked_at", "pump", "high")

    def __init__(self, max_tracked=None, discover_every=120, risk_checks_per_refresh=12):
        self.tokens = {}
        # Safety-check results by token address, saved by the arena so restarts don't start blind.
        # Revoked authority can't be restored, so a fully revoked result never goes stale. The same entries
        # carry the token's decimals, its last sellability probe (sell_ok / sell_ratio / sell_checked) and its
        # last rug-data assessment (rug / rug_checked).
        self.risk_cache = {}
        self.risk_dirty = False
        self.sol = None
        self.max_tracked = max_tracked or (150 if UNIVERSE == "pumpfun" else 60)
        self.discover_every = discover_every
        self.risk_checks = risk_checks_per_refresh
        self.last_discover = 0
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "memecoin-arena/0.1"
        self.jup_times = deque()       # timestamps of recent Jupiter requests (rolling-minute budget)
        self.jup_backoff_until = 0.0   # after a 429
        self.quote_cache = {}          # (in, out, rounded amount) -> (ts, amount, outAmount)
        self.jup_stats = {"requests": 0, "ok": 0, "no_route": 0, "errors": 0, "cache_hits": 0, "skipped": 0}
        self.gecko_backoff = 0.0       # current GeckoTerminal pause length (doubles on repeated 429s)
        self.gecko_backoff_until = 0.0
        self.gecko_stats = {"requests": 0, "ok": 0, "rate_limited": 0, "errors": 0, "skipped": 0}
        self.rug_stats = {"requests": 0, "ok": 0, "pending": 0, "errors": 0}
        self.pump = None                # the shared PumpFeed, started lazily by the first real discovery
        self.pump_since = {"new": 0.0, "grad": 0.0}  # feed timestamps already consumed
        self.pump_stats = {"graduated": 0, "launches": 0, "launches_seen": 0, "skipped_mcap": 0}
        self._pump_meta = {}            # launch / graduation details for tokens about to be created
        self.probation = {}             # pumpfun universe: mint -> launch event + first_seen / polled_at
        self.probation_stats = {"polled": 0, "promoted": 0, "expired": 0}
        self.last_held = set()          # held set from the latest refresh (track() evicts around it)

    def _get(self, url):
        try:
            r = self.s.get(url, timeout=15)
            if r.status_code == 429:
                print("[market] rate limited by DexScreener, will retry next tick")
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"[market] request failed: {e}")
            return None

    # ---------- discovery ----------
    def _discover(self):
        """Token address -> source tag(s) for everything the enabled feeds list right now: "promoted" / "organic" /
        "both", or a list such as ["graduated", "organic"] when the pump.fun feed also names it (first = primary).
        Each feed is independent: one failing never costs the other's results."""
        found = {}
        if UNIVERSE != "pumpfun" and ORGANIC_SHARE < 1:
            for a in self._discover_dexscreener():
                found[a] = "promoted"
        if UNIVERSE != "pumpfun" and ORGANIC_SHARE > 0:
            for a in self._discover_gecko():
                found[a] = "both" if a in found else "organic"
        if PUMPFUN_SHARE > 0:
            try:
                pump = self._discover_pumpfun()
            except Exception as e:  # the feed is optional: never cost the others their results
                print(f"[market] pump.fun discovery failed: {str(e)[:120]}")
                pump = {}
            for a, src in pump.items():
                found[a] = [src, found[a]] if a in found else src
        return found

    def _discover_pumpfun(self):
        """Address -> "graduated" / "pumpfun" from PumpPortal's free stream (pumpfun.py): every migration since the
        last cycle, plus the PUMPFUN_NEW launches of the last cycle with the largest initial market cap (at least
        PUMPFUN_MIN_MCAP_SOL). No network call here; the feed's thread fills the buffers. In the pumpfun universe
        the launches come from _probation_poll instead (which does price them on DexScreener)."""
        if self.pump is None:
            if pumpfun is None:
                return {}
            self.pump = pumpfun.shared()
            if self.pump is None:
                return {}
            # first cycle: only what arrived in the last few minutes, never the whole buffer
            self.pump_since["new"] = time.time() - self.discover_every
            self.pump_since["grad"] = time.time() - 1800
        now = time.time()
        found = {}
        grads = self.pump.graduations(self.pump_since["grad"])
        self.pump_since["grad"] = max([self.pump_since["grad"]] + [g["ts"] for g in grads])
        for g in grads:
            a = g.get("mint")
            if plausible_mint(a) and a not in MAJORS:
                found[a] = "graduated"
                t = self.tokens.get(a)
                if t is not None:
                    t.setdefault("pump", {})["graduated"] = g["ts"]
                else:
                    self._pump_meta[a] = {"graduated": g["ts"]}
        self.pump_stats["graduated"] += sum(1 for a in found if a not in self.tokens)
        if UNIVERSE == "pumpfun":
            for a, src in self._probation_poll(now).items():
                found.setdefault(a, src)
            self._prune_pump_meta(found)
            return found
        launches = self.pump.new_tokens(self.pump_since["new"])
        self.pump_since["new"] = max([self.pump_since["new"]] + [e["ts"] for e in launches])
        self.pump_stats["launches_seen"] += len(launches)
        # traction = the creator's own buy: a real purchase (events with solAmount 0 but a raised market cap turned
        # out to be re-launches of old mints) at or above the market-cap floor
        good = [e for e in launches if plausible_mint(e.get("mint")) and e["mint"] not in found
                and e["mint"] not in self.tokens and (e.get("initial_buy_sol") or 0) > 0
                and (e.get("mcap_sol") or 0) >= PUMPFUN_MIN_MCAP_SOL]
        self.pump_stats["skipped_mcap"] += len(launches) - len(good)
        good.sort(key=lambda e: (-(e.get("mcap_sol") or 0), -(e.get("initial_buy_sol") or 0), -e["ts"]))
        for e in good[:PUMPFUN_NEW]:
            found[e["mint"]] = "pumpfun"
            self._pump_meta[e["mint"]] = {
                "launched": e["ts"], "initial_mcap_sol": round(e.get("mcap_sol") or 0, 2),
                "initial_buy_sol": round(e.get("initial_buy_sol") or 0, 3), "creator": e.get("creator"),
                "curve": e.get("curve"), "symbol": e.get("symbol") or "", "name": e.get("name") or "",
                "mayhem": bool(e.get("mayhem")),
            }
            self.pump_stats["launches"] += 1
        self._prune_pump_meta(found)
        return found

    def _prune_pump_meta(self, found):
        if len(self._pump_meta) > 200:  # metadata for tokens that were never added (evicted before pricing, ...)
            self._pump_meta = {a: m for a, m in self._pump_meta.items() if a in found or a in self.tokens}

    def _probation_poll(self, now):
        """Pumpfun universe: address -> "pumpfun" for the launches that just showed traction. Every launch from
        the feed with a real creator buy at or above PUMPFUN_MIN_MCAP_SOL waits on probation for PROBATION_MIN
        minutes after its launch; each cycle up to PROBATION_PER_CYCLE of them (least recently priced first, then
        oldest) are priced on DexScreener. A launch is promoted when its market cap reaches TRACK_MCAP_USD, or its
        1h volume TRACK_VOL_USD with at least TRACK_MIN_TXNS transactions; its details go to _pump_meta exactly
        like the old best-creator-buy rule, so the new token carries `pump`. Launches that never pass expire."""
        if self.pump is None:
            return {}
        launches = self.pump.new_tokens(self.pump_since["new"])
        self.pump_since["new"] = max([self.pump_since["new"]] + [e["ts"] for e in launches])
        self.pump_stats["launches_seen"] += len(launches)
        for e in launches:
            a = e.get("mint")
            if not plausible_mint(a) or a in self.tokens or a in self._pump_meta or a in self.probation:
                continue
            # traction at second zero = the creator's own buy (see the old rule in _discover_pumpfun)
            if (e.get("initial_buy_sol") or 0) <= 0 or (e.get("mcap_sol") or 0) < PUMPFUN_MIN_MCAP_SOL:
                self.pump_stats["skipped_mcap"] += 1
                continue
            self.probation[a] = {**e, "first_seen": now, "polled_at": 0}
        cutoff = now - PROBATION_MIN * 60
        for a, e in list(self.probation.items()):
            if a in self.tokens or a in self._pump_meta:  # graduated or force-tracked meanwhile
                del self.probation[a]
            elif (e.get("ts") or e["first_seen"]) < cutoff:
                del self.probation[a]
                self.probation_stats["expired"] += 1
        batch = sorted(self.probation, key=lambda a: (self.probation[a]["polled_at"], self.probation[a].get("ts") or 0))
        batch = batch[:PROBATION_PER_CYCLE]
        if not batch:
            return {}
        for a in batch:
            self.probation[a]["polled_at"] = now
        self.probation_stats["polled"] += len(batch)
        found = {}
        for a, t in self._fetch_pairs(batch).items():
            if a not in self.probation:
                continue
            if not (t["mcap"] >= TRACK_MCAP_USD
                    or (t["vol_h1"] >= TRACK_VOL_USD and t["buys_h1"] + t["sells_h1"] >= TRACK_MIN_TXNS)):
                continue
            e = self.probation.pop(a)
            found[a] = "pumpfun"
            self._pump_meta[a] = {
                "launched": e["ts"], "initial_mcap_sol": round(e.get("mcap_sol") or 0, 2),
                "initial_buy_sol": round(e.get("initial_buy_sol") or 0, 3), "creator": e.get("creator"),
                "curve": e.get("curve"), "symbol": e.get("symbol") or "", "name": e.get("name") or "",
                "mayhem": bool(e.get("mayhem")),
            }
            self.pump_stats["launches"] += 1
            self.probation_stats["promoted"] += 1
        return found

    def _new_token(self, a, srcs, now):
        """Create the tracked-token stub for a freshly discovered address (priced on the next fetch)."""
        srcs = [srcs] if isinstance(srcs, str) else [s for s in srcs if s]
        t = {"address": a, "first_seen": now, "price": 0, "source": srcs[0] if srcs else "promoted",
             "sources": list(dict.fromkeys(srcs))}
        meta = self._pump_meta.pop(a, None)
        if meta:
            t["pump"] = {k: v for k, v in meta.items() if k not in ("symbol", "name") and v is not None}
            if meta.get("symbol"):
                t["symbol"], t["name"] = meta["symbol"], meta.get("name", "")
        self.tokens[a] = t
        return t

    def _discover_dexscreener(self):
        """Paid placements: token profiles and boosts."""
        found = []
        for path in ("/token-profiles/latest/v1", "/token-boosts/latest/v1", "/token-boosts/top/v1"):
            data = self._get(DEX + path)
            if isinstance(data, list):
                for d in data:
                    if d.get("chainId") == "solana" and d.get("tokenAddress"):
                        found.append(d["tokenAddress"])
        return list(dict.fromkeys(found))

    def _gecko_get(self, path):
        """One GeckoTerminal request, or None. A 429 (or Retry-After) pauses the feed; the pause doubles while
        the limit keeps being hit, up to 10 minutes, and resets on the next success."""
        now = time.time()
        if now < self.gecko_backoff_until:
            self.gecko_stats["skipped"] += 1
            return None
        self.gecko_stats["requests"] += 1
        try:
            r = self.s.get(GECKO + path, timeout=15, headers={"Accept": "application/json;version=20230302"})
        except Exception as e:
            self.gecko_stats["errors"] += 1
            print(f"[market] GeckoTerminal request failed: {str(e)[:120]}")
            return None
        if r.status_code == 429:
            self.gecko_stats["rate_limited"] += 1
            self.gecko_backoff = min(600.0, self.gecko_backoff * 2 if self.gecko_backoff else 60.0)
            pause = max(self.gecko_backoff, _f(r.headers.get("Retry-After")))
            self.gecko_backoff_until = now + pause
            print(f"[market] rate limited by GeckoTerminal, pausing organic discovery for {pause:.0f}s")
            return None
        try:
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.gecko_stats["errors"] += 1
            print(f"[market] GeckoTerminal error: {str(e)[:120]}")
            return None
        self.gecko_backoff = 0.0
        self.gecko_stats["ok"] += 1
        return data

    @staticmethod
    def _gecko_mint(rel):
        """Mint address from a pool relationship ({"data": {"id": "solana_<mint>"}}), or None."""
        ident = (((rel or {}).get("data") or {}).get("id") or "")
        _, _, mint = ident.partition("_")
        return mint or None

    def _discover_gecko(self):
        """Organic listings: the memecoin side of each trending / new pool, best-ranked first."""
        found = []
        for i, path in enumerate(GECKO_PATHS):
            if i and time.time() >= self.gecko_backoff_until:
                time.sleep(0.5)  # the free tier dislikes bursts more than volume
            data = self._gecko_get(path)
            if not isinstance(data, dict):
                continue
            for p in data.get("data") or []:
                if not isinstance(p, dict):
                    continue
                attrs, rel = p.get("attributes") or {}, p.get("relationships") or {}
                if _f(attrs.get("reserve_in_usd")) < ORGANIC_MIN_LIQ:
                    continue
                base, quote = self._gecko_mint(rel.get("base_token")), self._gecko_mint(rel.get("quote_token"))
                mint = quote if base in MAJORS else base
                if mint and mint not in MAJORS and plausible_mint(mint):
                    found.append(mint)
        return list(dict.fromkeys(found))

    def source_mix(self):
        """How many priced tracked tokens came from each discovery source."""
        out = {"promoted": 0, "organic": 0, "both": 0}
        if PUMPFUN_SHARE > 0:
            out.update(graduated=0, pumpfun=0)
        for t in self.tokens.values():
            if t.get("price", 0) > 0:
                src = t.get("source") or "promoted"
                out[src] = out.get(src, 0) + 1
        return out

    def quota(self):
        """Slots per eviction group: pump.fun tokens get PUMPFUN_SHARE of max_tracked, the rest is split between
        organic and promoted by ORGANIC_SHARE."""
        pump = round(self.max_tracked * PUMPFUN_SHARE)
        rest = self.max_tracked - pump
        organic = round(rest * ORGANIC_SHARE)
        return {"pumpfun": pump, "organic": organic, "promoted": rest - organic}

    def _evict(self, held, now=None):
        """Shrink the pool to max_tracked. Dead tokens go first, oldest first: tokens DexScreener has not priced for
        10 minutes (dead curves, unlisted mints) and, in the pumpfun universe only, launches trading at 10% or less
        of their tracked high. Then slots are shared between the groups by quota() ("both" tokens count for organic and
        promoted and go last): the oldest free token of whichever group is furthest over its share goes, launches
        before graduations in the pump.fun group. Held tokens and tokens protected by track() are never evicted."""
        excess = len(self.tokens) - self.max_tracked
        if excess <= 0:
            return
        now = now or time.time()
        quota = self.quota()
        for _ in range(excess):
            free = {g: [] for g in GROUPS + ("both",)}
            count = {g: 0 for g in GROUPS}
            dead = []
            for a, t in self.tokens.items():
                g = SOURCE_GROUP.get(t.get("source") or "promoted", "promoted")
                for side in (("organic", "promoted") if g == "both" else (g,)):
                    count[side] += 1
                if a in held or (t.get("protect_until") or 0) > now:
                    continue
                free[g].append(a)
                if UNIVERSE == "pumpfun" and t.get("source") == "pumpfun" \
                        and 0 < (t.get("price") or 0) <= 0.1 * (t.get("high") or 0):
                    dead.append(a)  # a launch down 90%+ from its high: the curve is dead
                elif not t.get("price") and now - (t.get("first_seen") or now) > 600:
                    dead.append(a)
            victim = None
            if dead:
                victim = min(dead, key=lambda a: self.tokens[a].get("first_seen", 0))
            else:
                order = sorted(GROUPS, key=lambda g: quota[g] - count[g]) + ["both"]
                for g in order:
                    if free[g]:
                        victim = min(free[g], key=lambda a: (self.tokens[a].get("source") == "graduated",
                                                             self.tokens[a].get("first_seen", 0)))
                        break
            if victim is None:
                break
            del self.tokens[victim]

    def track(self, mint, source="copy", hold_secs=21600, held=()):
        """Force-track `mint` (e.g. a followed trader just bought it) so the next refresh prices it, and protect it
        from eviction until hold_secs after the last track() call. No network call: safe to call from the arena
        thread under the arena lock. An already-tracked token keeps its original source and gains `source` in its
        `sources` list. Other free tokens are evicted to respect max_tracked (`held` = positions to protect, on
        top of the held set from the last refresh). Returns the token dict, or None for an implausible mint, SOL
        or a major, and in the pumpfun universe for anything that is not a pump.fun mint (ends in "pump" or has
        pump.fun details)."""
        if not plausible_mint(mint) or mint == SOL_MINT or mint in MAJORS:
            return None
        t = self.tokens.get(mint)
        if UNIVERSE == "pumpfun" and not (mint.endswith("pump") or mint in self._pump_meta
                                          or (t is not None and t.get("pump"))):
            return None
        now = time.time()
        if t is None:
            t = self._new_token(mint, source, now)
        else:
            merge_source(t, source)
        t["protect_until"] = max(t.get("protect_until") or 0, now + max(0, hold_secs))
        t["tracked_at"] = now
        self._evict(set(held) | set(self.last_held) | {mint}, now)
        return t

    def _fetch_pairs(self, addrs):
        wanted = set(addrs)
        best = {}
        for i in range(0, len(addrs), 30):
            data = self._get(f"{DEX}/tokens/v1/solana/{','.join(addrs[i:i + 30])}")
            if not isinstance(data, list):
                continue
            for p in data:
                t = parse_pair(p)
                a = t["address"]
                if a in wanted and t["price"] > 0 and (a not in best or t["liquidity"] > best[a]["liquidity"]):
                    best[a] = t
        # DexScreener reports no liquidity for pump.fun bonding curves: fill in the curve's own depth
        sol = (best.get(SOL_MINT) or {}).get("price") or self._sol_price()
        for t in best.values():
            if t.get("dex") == "pumpfun" and not t.get("liquidity"):
                t["liquidity"] = curve_liquidity_usd(t.get("mcap"), sol)
        return best

    def _check_risk(self, addr):
        """Mint account info from the RPC: authorities and the token's decimals (needed for router quotes)."""
        body = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                "params": [addr, {"encoding": "jsonParsed"}]}
        try:
            r = self.s.post(RPC, json=body, timeout=15)
            r.raise_for_status()
            info = r.json()["result"]["value"]["data"]["parsed"]["info"]
            out = {"mint_revoked": info.get("mintAuthority") is None,
                   "freeze_revoked": info.get("freezeAuthority") is None}
            if info.get("decimals") is not None:
                out["decimals"] = int(info["decimals"])
            return out
        except Exception:
            return None  # retried on a later tick

    def _merge_pair(self, a, t, now):
        """Replace the tracked token with fresh pair data, keeping the state that isn't in the feed."""
        old = self.tokens.get(a, {})
        t["first_seen"] = old.get("first_seen", now)
        for k in self.KEEP[1:]:
            t[k] = old.get(k)
        for k in self.KEEP_IF_SET:
            if old.get(k) is not None:
                t[k] = old[k]
        for k in ("pair", "dex"):  # a feed answer without the pool address keeps the last known one
            if t.get(k) is None and old.get(k) is not None:
                t[k] = old[k]
        if old.get("dex") == "pumpfun" and t.get("dex") and t["dex"] != "pumpfun":
            # the curve is gone and a real pool answers: it graduated (whether or not the feed told us)
            if (t.get("source") or "") == "pumpfun":
                merge_source(t, "graduated")
            t.setdefault("pump", {}).setdefault("graduated", now)
        self.tokens[a] = t

    # ---------- Jupiter ----------
    def _jup_quote(self, input_mint, output_mint, amount):
        """One ExactIn quote. Returns (outAmount as int or None, status) with status in
        ok / no_route / error / off. Never raises, never waits longer than JUP_TIMEOUT."""
        amount = int(amount)
        if not JUP_ON or amount <= 0 or not plausible_mint(input_mint) or not plausible_mint(output_mint):
            return None, "off"
        now = time.time()
        key = (input_mint, output_mint, float(f"{amount:.3g}"))
        hit = self.quote_cache.get(key)
        if hit and now - hit[0] < QUOTE_CACHE_SECS:
            self.jup_stats["cache_hits"] += 1
            out = hit[2]
            return (int(out * amount / hit[1]) if out else None), ("ok" if out else "no_route")
        if now < self.jup_backoff_until:
            self.jup_stats["skipped"] += 1
            return None, "error"
        while self.jup_times and now - self.jup_times[0] > 60:
            self.jup_times.popleft()
        if len(self.jup_times) >= JUP_PER_MIN:
            self.jup_stats["skipped"] += 1
            return None, "error"
        self.jup_times.append(now)
        self.jup_stats["requests"] += 1
        try:
            r = self.s.get(JUP_URL, params={"inputMint": input_mint, "outputMint": output_mint,
                                            "amount": str(amount), "slippageBps": "100"}, timeout=JUP_TIMEOUT)
        except Exception as e:
            self.jup_stats["errors"] += 1
            print(f"[market] Jupiter quote failed: {str(e)[:120]}")
            return None, "error"
        if r.status_code == 429:
            self.jup_backoff_until = now + 60
            self.jup_stats["errors"] += 1
            print("[market] rate limited by Jupiter, pausing quotes for 60s")
            return None, "error"
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if r.status_code == 200 and data.get("outAmount") is not None:
            try:
                out = int(data["outAmount"])
            except (TypeError, ValueError):
                out = 0
            if out > 0:
                self.jup_stats["ok"] += 1
                self._cache_quote(key, now, amount, out)
                return out, "ok"
        code = str(data.get("errorCode") or "")
        err = str(data.get("error") or r.text[:120]).lower()
        if code in NO_ROUTE_CODES or "not tradable" in err or "no route" in err or "no routes" in err:
            self.jup_stats["no_route"] += 1
            self._cache_quote(key, now, amount, None)
            return None, "no_route"
        self.jup_stats["errors"] += 1
        print(f"[market] Jupiter quote error {r.status_code}: {(data.get('error') or r.text)[:120]}")
        return None, "error"

    def _cache_quote(self, key, now, amount, out):
        if len(self.quote_cache) > 500:
            self.quote_cache = {k: v for k, v in self.quote_cache.items() if now - v[0] < QUOTE_CACHE_SECS}
        self.quote_cache[key] = (now, amount, out)

    def _sol_price(self):
        return (self.sol or {}).get("price") or 0.0

    def quote_buy(self, t, usd):
        """How many tokens `usd` (already net of fees) buys right now according to Jupiter, or None.
        Memecoins are bought with SOL (converted at the DexScreener SOL price); SOL itself with USDC."""
        addr, dec, sol = t.get("address"), t.get("decimals"), self._sol_price()
        if not addr or usd <= 0:
            return None
        if addr == SOL_MINT:
            out, _ = self._jup_quote(USDC_MINT, SOL_MINT, usd * 1e6)
            return out / 1e9 if out else None
        if dec is None or sol <= 0:
            return None
        out, _ = self._jup_quote(SOL_MINT, addr, usd / sol * 1e9)
        return out / 10 ** dec if out else None

    def quote_sell(self, t, qty):
        """Gross dollars Jupiter would return for selling `qty` tokens right now, or None.
        A no-route answer also marks the token unsellable (it goes red on the next annotate)."""
        addr, dec, sol = t.get("address"), t.get("decimals"), self._sol_price()
        if not addr or qty <= 0:
            return None
        if addr == SOL_MINT:
            out, _ = self._jup_quote(SOL_MINT, USDC_MINT, qty * 1e9)
            return out / 1e6 if out else None
        if dec is None or sol <= 0:
            return None
        out, status = self._jup_quote(addr, SOL_MINT, qty * 10 ** dec)
        if status == "no_route" and addr in self.tokens:
            self._set_sellable(addr, {"ok": False, "ratio": None, "checked": time.time()})
        return out / 1e9 * sol if out else None

    def _set_sellable(self, addr, res):
        t = self.tokens.get(addr)
        if t is not None:
            t["sellable"] = res
            if t.get("price"):
                _annotate(t)
        c = self.risk_cache.setdefault(addr, {"checked": 0})
        c.update(sell_ok=res["ok"], sell_ratio=res.get("ratio"), sell_checked=res["checked"])
        self.risk_dirty = True

    def _probe_sellability(self, t, now):
        """Ask Jupiter whether ~$5 of the token can be sold for SOL. Returns a sellable record, or None when the
        answer was transient (network error, rate limit, unknown decimals) so it is retried later."""
        addr, price = t.get("address"), t.get("price") or 0
        if price <= 0:
            return None
        if t.get("decimals") is None:  # tokens rated before decimals were stored: one RPC call fills them in
            info = self._check_risk(addr)
            if not info or info.get("decimals") is None:
                return None
            t["decimals"] = info["decimals"]
            self.risk_cache.setdefault(addr, {"checked": now}).update(decimals=info["decimals"])
            self.risk_dirty = True
        amount = int(SELL_PROBE_USD / price * 10 ** t["decimals"])
        if amount < 1:
            return None
        out, status = self._jup_quote(addr, SOL_MINT, amount)
        if status == "ok":
            sol = self._sol_price()
            ratio = round(out / 1e9 * sol / SELL_PROBE_USD, 3) if sol > 0 else None
            return {"ok": True, "ratio": ratio, "checked": now}
        if status == "no_route":
            return {"ok": False, "ratio": None, "checked": now}
        return None

    def _check_sellability(self, now):
        """Up to SELL_CHECKS probes per tick: never-probed tokens first, then the stalest."""
        if not JUP_ON or SELL_CHECKS <= 0:
            return
        due = [t for t in self.tokens.values()
               if t.get("price") and t.get("risk") is not None and plausible_mint(t.get("address"))
               and (not t.get("sellable") or now - t["sellable"].get("checked", 0) >= SELL_CHECK_SECS)]
        due.sort(key=lambda t: (t.get("sellable") or {}).get("checked", 0))
        for t in due[:SELL_CHECKS]:
            res = self._probe_sellability(t, now)
            if res:
                self._set_sellable(t["address"], res)
                if not res["ok"]:
                    print(f"[market] {t.get('symbol')} failed the sell check: no route (possible honeypot)")
                elif res["ratio"] is not None and res["ratio"] < SELL_MIN_RATIO:
                    print(f"[market] {t.get('symbol')} failed the sell check: returns {res['ratio']:.0%} of value")

    def refresh_held(self, held):
        """Fast path between ticks: refresh prices for the held tokens only (one DexScreener request per 30),
        no discovery, no safety checks, no Jupiter."""
        addrs = [a for a in held if a in self.tokens]
        if not addrs:
            return
        now = time.time()
        for a, t in self._fetch_pairs(addrs).items():
            self._merge_pair(a, t, now)
            _annotate(t)

    def _check_rug(self, now):
        """Up to RUG_CHECKS rugdata assessments per tick: never-assessed tokens first (least recently tried
        among them), then the stalest. A None result is transient and retried later."""
        if rugdata is None or RUG_CHECKS <= 0:
            return
        due = [t for t in self.tokens.values()
               if t.get("price") and plausible_mint(t.get("address"))
               and (t.get("rug") is None or now - (t.get("rug_checked") or 0) >= RUG_CHECK_SECS)]
        due.sort(key=lambda t: (t.get("rug") is not None, (t.get("rug_tried") or 0) if t.get("rug") is None
                                else (t.get("rug_checked") or 0)))
        for t in due[:RUG_CHECKS]:
            a = t["address"]
            t["rug_tried"] = now
            self.rug_stats["requests"] += 1
            try:
                info = rugdata.assess(self.s, a, decimals=t.get("decimals"))
            except Exception as e:
                info = None
                self.rug_stats["errors"] += 1
                print(f"[market] rugdata.assess failed for {t.get('symbol')}: {str(e)[:120]}")
            if not isinstance(info, dict):
                self.rug_stats["pending"] += 1
                continue
            self.rug_stats["ok"] += 1
            t["rug"], t["rug_checked"] = info, now
            c = self.risk_cache.setdefault(a, {"checked": now})
            c["rug"], c["rug_checked"] = info, now
            self.risk_dirty = True
            hard = [text for text, h in _rug_flags(t) if h]
            if hard:
                print(f"[market] {t.get('symbol')} failed the rug check: {hard[0]}")

    def refresh(self, held):
        now = time.time()
        held = set(held)
        self.last_held = held
        if now - self.last_discover >= self.discover_every:
            self.last_discover = now
            try:
                found = self._discover()
            except Exception as e:  # discovery must never break the price refresh
                print(f"[market] discovery failed: {str(e)[:120]}")
                found = {}
            if not isinstance(found, dict):  # a plain list of addresses (old contract) means promoted
                found = {a: "promoted" for a in found}
            new = {}
            for a, srcs in found.items():
                if a == SOL_MINT or a in MAJORS:
                    continue
                srcs = [srcs] if isinstance(srcs, str) else [s for s in (srcs or []) if s]
                if not srcs:
                    srcs = ["promoted"]
                t = self.tokens.get(a)
                if t is None:
                    t = self._new_token(a, srcs, now)
                    new[t["source"]] = new.get(t["source"], 0) + 1
                else:
                    for s in srcs:
                        merge_source(t, s)
            if new:
                print("[market] discovered " + ", ".join(f"{n} {s}" for s, n in sorted(new.items())) + " new tokens")

        self._evict(held, now)

        best = self._fetch_pairs(list(self.tokens) + [SOL_MINT])
        if SOL_MINT in best:
            self.sol = best.pop(SOL_MINT)
            self.sol.update(flags=[], rating="green", risk={"mint_revoked": True, "freeze_revoked": True},
                            decimals=9, sellable={"ok": True, "ratio": 1.0, "checked": now})
        for a, t in best.items():
            self._merge_pair(a, t, now)

        for a, t in self.tokens.items():
            c = self.risk_cache.get(a)
            if not c:
                continue
            if t.get("risk") is None and "mint_revoked" in c and (
                    (c["mint_revoked"] and c["freeze_revoked"]) or now - c["checked"] < 1800):
                t["risk"] = {"mint_revoked": c["mint_revoked"], "freeze_revoked": c["freeze_revoked"]}
            if t.get("decimals") is None and c.get("decimals") is not None:
                t["decimals"] = c["decimals"]
            if not t.get("sellable") and "sell_ok" in c and now - c.get("sell_checked", 0) < SELL_CHECK_SECS:
                t["sellable"] = {"ok": c["sell_ok"], "ratio": c.get("sell_ratio"), "checked": c["sell_checked"]}
            if t.get("rug") is None and isinstance(c.get("rug"), dict):  # stale is better than blind; re-checked by age
                t["rug"], t["rug_checked"] = c["rug"], c.get("rug_checked", 0)

        checks = 0
        for a, t in self.tokens.items():
            if checks >= self.risk_checks:
                break
            if t.get("price") and t.get("risk") is None:
                info = self._check_risk(a)
                if info:
                    t["risk"] = {"mint_revoked": info.get("mint_revoked"), "freeze_revoked": info.get("freeze_revoked")}
                    if info.get("decimals") is not None:
                        t["decimals"] = info["decimals"]
                    self.risk_cache[a] = {**self.risk_cache.get(a, {}), **info, "checked": now}
                    self.risk_dirty = True
                checks += 1
                time.sleep(0.15)

        self._check_sellability(now)
        self._check_rug(now)

        for t in self.tokens.values():
            if t.get("price"):
                _annotate(t)

    def get(self, addr):
        if addr == SOL_MINT:
            return self.sol
        t = self.tokens.get(addr)
        return t if t and t.get("price", 0) > 0 else None

    def candidates(self):
        return [t for t in self.tokens.values() if t.get("price", 0) > 0 and t.get("liquidity", 0) > 0]

    def ready(self):
        """True once most tracked tokens have their safety check done."""
        c = self.candidates()
        return bool(c) and sum(t.get("risk") is not None for t in c) / len(c) >= 0.8


class MockMarket:
    """Fake market with random-walk tokens and occasional rugs. For testing without internet.
    It has no Jupiter and no refresh_held: fills always use the AMM formula and fast exit checks reuse the
    prices from the last tick (free)."""

    def __init__(self, n=30, seed=None, tick=30):
        self.rng = random.Random(seed)
        self.tick = tick
        self.tokens = {}
        self.sol = {"address": SOL_MINT, "symbol": "SOL", "name": "Solana", "price": 150.0,
                    "liquidity": 50_000_000, "mcap": 7e10, "flags": [], "rating": "green",
                    "risk": {"mint_revoked": True, "freeze_revoked": True}}
        self._spawned = 0
        for _ in range(n):
            self._spawn()

    def _spawn(self, kind=None):
        """Add one fake token. Successive spawns cycle pumpfun / graduated / organic so the pump.fun lanes are
        non-empty offline; track() passes kind="organic" to get a plain token without advancing the cycle."""
        rng = self.rng
        if kind is None:
            kind = ("pumpfun", "graduated", "organic")[self._spawned % 3]
            self._spawned += 1
        a = "MOCK" + "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
        liq = rng.uniform(3_000, 200_000)
        mint_ok = rng.random() < 0.8
        t = {
            "address": a, "symbol": "M" + a[-4:], "name": "Mock " + a[-4:],
            "price": rng.uniform(1e-6, 1e-2), "liquidity": liq, "mcap": liq * rng.uniform(3, 30),
            "vol_h1": liq * rng.uniform(0.1, 3), "vol_h24": liq * rng.uniform(1, 20),
            "buys_h1": rng.randint(0, 400), "sells_h1": rng.randint(0, 300),
            "chg_m5": 0.0, "chg_h1": 0.0, "chg_h24": 0.0, "age_min": rng.uniform(0, 600),
            "url": "", "first_seen": time.time(),
            "risk": {"mint_revoked": mint_ok, "freeze_revoked": rng.random() < 0.85},
            "_drift": rng.gauss(-0.0003, 0.001), "_vol": rng.uniform(0.005, 0.04),
            "_rug_p": 0.0002 if mint_ok else 0.001, "_hist": [],
        }
        t["_hist"].append(t["price"])
        t["source"], t["sources"] = kind, [kind]
        if kind == "pumpfun":
            curve_pct = rng.uniform(5, 90)
            t["dex"] = "pumpfun"
            t["mcap"] = curve_pct / 100 * GRADUATION_CAP_USD  # _annotate derives curve_pct from mcap
            t["pump"] = {"launched": t["first_seen"] - t["age_min"] * 60, "curve_pct": round(curve_pct, 1)}
        elif kind == "graduated":
            t["dex"] = "pumpswap"
            t["pump"] = {"graduated": t["first_seen"] - t["age_min"] * 60}
        _annotate(t)
        self.tokens[a] = t

    def refresh(self, held):
        rng = self.rng
        held = set(held)
        for t in self.tokens.values():
            if t.get("_rugged"):
                continue
            r = rng.gauss(t["_drift"], t["_vol"])
            t["price"] *= math.exp(r)
            t["mcap"] *= math.exp(r)
            t["liquidity"] *= math.exp(r / 2)
            if rng.random() < t["_rug_p"]:
                t["liquidity"] *= 0.02
                t["price"] *= 0.05
                t["_rugged"] = True
            h = t["_hist"]
            h.append(t["price"])
            del h[:-300]
            n5, n60 = max(1, 300 // self.tick), max(1, 3600 // self.tick)
            t["chg_m5"] = (t["price"] / h[-min(len(h), n5 + 1)] - 1) * 100
            t["chg_h1"] = (t["price"] / h[-min(len(h), n60 + 1)] - 1) * 100
            t["age_min"] += self.tick / 60
            _annotate(t)
        if rng.random() < 0.3:
            self._spawn()
        dead = [a for a, t in self.tokens.items() if t.get("_rugged") and a not in held
                and (t.get("protect_until") or 0) < time.time()]
        if len(self.tokens) > 60:
            for a in dead[: len(self.tokens) - 60]:
                del self.tokens[a]
        self.sol["price"] *= math.exp(rng.gauss(0, 0.002))

    def get(self, addr):
        return self.sol if addr == SOL_MINT else self.tokens.get(addr)

    def candidates(self):
        return list(self.tokens.values())

    def track(self, mint, source="copy", hold_secs=21600, held=()):
        """Same contract as LiveMarket.track: an unknown mint becomes a fake priced token tagged `source`
        (and protected from the mock's own pruning), a known one just gains the tag. Returns the token dict."""
        if not isinstance(mint, str) or not mint or mint == SOL_MINT:
            return None
        now = time.time()
        t = self.tokens.get(mint)
        if t is None:
            self._spawn("organic")
            a, t = self.tokens.popitem()  # the one just spawned (dicts keep insertion order)
            t.update(address=mint, symbol=("M" + mint[-4:])[:12], name="Mock " + mint[-4:], first_seen=now,
                     source=source, sources=[source], age_min=self.rng.uniform(1, 30))
            self.tokens[mint] = t
        else:
            merge_source(t, source)
        t["protect_until"] = max(t.get("protect_until") or 0, now + max(0, hold_secs))
        t["tracked_at"] = now
        return t
