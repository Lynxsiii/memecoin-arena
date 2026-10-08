"""Structural signals and hard vetoes for the arena's candidate tokens (the research report's Tier 0-2 checks).

Source: reports/Solana memecoin trading reality.md, "Measured signals tell you what to avoid", the Tier 0-4
checklist table under "Scams are mostly dumps", and recommendations 2-4. The report's point is that the robust
signals are negative filters: reject the structurally unsafe tokens deterministically, and show the agent
structural evidence (net inflow, round trips, concentration, creator behaviour, time since migration, liquidity
persistence) instead of raw volume and trade counts, which are the most manipulated observables.

Pure and fast: no network, one SQL query per call (chunked only past 500 mints), safe to run every 30-second tick
for ~60 tokens inside the arena lock; flow_signals and creator_selling take `db.lock` themselves for the query.
Nothing here raises on missing data. Measured: 60 mints x 300 trades (18k rows, in-memory DB) ~48 ms, two thirds
of it SQLite handing rows to Python; the live arena.db (~10k pool-feed rows an hour) ~35 ms. The pool feed only
changes when the tracker polls a pool (every few minutes), so a caller may reuse a result for 60-120 s.

API
  flow_signals(db, mints, now=None, window=3600) -> {mint: flow}
      From the tracker's `copy_trades` table (traders.py; GeckoTerminal pool feed, last 300 trades per pool per
      poll, trades under $10 not stored). Only pool-feed rows are used (pool IS NOT NULL): the Helius rows are the
      top wallets' own swaps (pool NULL), a biased sample that duplicates pool-feed trades. Mints without rows in
      the window are omitted; {} when the table does not exist (tracker off). flow keys:
        buy_usd, sell_usd, gross_usd     dollars bought / sold / both in the window
        net_usd, net_share               buy - sell, and that over gross (-1 = all selling, +1 = all buying)
        buyers, sellers, trades          unique buying / selling wallets, trade rows
        round_trip_share                 share of gross volume in trades that have an opposite-side trade of the
                                         same mint by the same wallet within FLIP_SECS (60 s) before or after it:
                                         bump bots, sandwich legs, sub-minute flippers (report Tier 2 "round-trip
                                         ratio: same-wallet buy-then-sell within seconds / total volume")
        top_buyer_share                  the largest single wallet's buys / buy_usd (None without buys)
        bot_share                        share of gross volume from bot-like wallets, where a wallet is bot-like
                                         for this mint when ANY of: it flipped this mint (a round trip as above);
                                         it made >= BOT_MINT_TRADES_H trades of this mint per hour of window; it
                                         made >= BOT_WALLET_TRADES_H trades per hour across all mints of the call
                                         (hyperactive: the report notes 93 of the top 100 pump.fun wallets by
                                         activity are bots). 1 - bot_share is the report's "non-bot share".
        last_trade_min_ago               minutes since the newest row (coverage: pools are polled every few
                                         minutes, busy pools have gaps)
        quality                          "churn": round_trip_share >= CHURN_RT_SHARE and |net_share| <=
                                         CHURN_NET_SHARE (volume is bots trading with themselves, "treat volume as
                                         zero signal"); "organic": round_trip_share < ORGANIC_RT_SHARE and
                                         bot_share <= ORGANIC_BOT_SHARE (report: "require >= 70% non-bot");
                                         "mixed" otherwise; None with fewer than FLOW_MIN_TRADES trades.
  creator_selling(db, mints_to_creator, since) -> {mint: usd_sold}
      Dollars the creator wallet sold of its own token in copy_trades since `since` (all sources, de-duplicated by
      transaction). Every mint with a creator gets an entry (0.0 = none seen); {} without the table. Only sells
      the pool feed caught, signed by the creator wallet itself (a creator selling through other wallets is not
      seen).
  liquidity_trend(history, horizon=3600) -> {"vs_1h_pct", "vs_max_pct", "ref_min", "span_min", "liquidity"} | None
      history = [(ts, liquidity_usd), ...] in any order. vs_1h_pct compares the newest point with the newest point
      at least `horizon` older (or, with a shorter history of at least half the horizon, the oldest point; ref_min
      says how far back the reference really is); vs_max_pct compares it with the highest liquidity in the history
      (0 or negative). None for an empty history.
  minutes_since_graduation(token, now) -> float | None   from token["pump"]["graduated"]
  vetoes(token, flow=None, now=None, **kw) -> [reason, ...]   short human-readable hard rejects ([] = allowed)
  veto_report(token, flow=None, now=None, creator_sold_usd=None, migrated_min_ago=None)
      -> {"vetoes": [...], "flags": [...], "unknowns": [...]}
      vetoes = hard rejects; flags = soft warnings worth showing; unknowns = checks that could not run because the
      data is missing or stale. Missing data is never a veto.
  structural_view(token, flow, liq_trend, migrated_min_ago, creator_sold_usd, now=None, chg=None, prices=None)
      -> dict
      Compact per-candidate evidence for an LLM prompt, only keys with data: net_inflow_1h_usd, net_share,
      buyers_1h, round_trip_share, top_buyer_share, flow_quality, insider_pct, top10_pct, creator_pct,
      creator_sold_usd (0 = creator known, no sells seen), lp_locked_pct (not on pump.fun pools, where LP is
      burned by construction), minutes_since_graduation, liquidity_vs_1h_pct, chart_tell, flags (soft flags, at
      most MAX_VIEW_FLAGS; the chart-tell flag first), vetoes (only when there are any). About 100-320 characters
      of JSON per token. For a coin still on its bonding curve (dex or source "pumpfun", not graduated, curve_pct
      known) also: curve_pct; curve_pct_chg_10m (curve_pace() of `chg`, the arena's chg_since entry for the coin);
      ramp: "early" (curve_pct < RAMP_MIN_PCT), "ramp" (RAMP_MIN_PCT..RAMP_MAX_PCT) or "late" (above); and
      ramp_setup: true when the coin is in the ramp window, has net buying (net_share >= RAMP_MIN_NET_SHARE from
      RAMP_MIN_BUYERS or more buying wallets; without pool-feed flow: buys_h1 > sells_h1 and buys_h1 >=
      RAMP_MIN_BUYERS, transaction counts standing in for wallets), no veto and no chart tell. `prices` is the
      arena's 30-second price history [(ts, price), ...] for chart_tell().
  curve_pace(curve_pct, chg) -> float | None
      Curve fill over the last 10 minutes from a chg_since entry (curve_pct_10m, curve_pct_10m_secs); a coin
      tracked under 10 minutes gets its fill since tracking began scaled to a 10-minute pace; None without a
      reference point.
  chart_tell(prices) -> {"green_run": int, "chart_tell": "straight run" | None}
      Video-1 chart tell from the arena's 30-second price history [(ts, price), ...], oldest first. green_run = how
      many consecutive ticks from the first point did not fall (one dip of at most CHART_WIGGLE_PCT is forgiven);
      "straight run" when the history has at least CHART_MIN_POINTS points, every tick since tracking began is in
      that run, and the price is at least CHART_MIN_MULT x the first point: one straight green run with no red
      candle, the pattern of a bundled launch. A soft flag (structure.flags), never a veto: it is a pattern, not
      proof. Run 9 (2026-10-08).

Vetoes (Tier 0-1 hard rejects with the data this arena has; thresholds below, all overridable):
  mint authority not revoked; freeze authority not revoked (market.py's RPC check, else RugCheck's risk names);
  a honeypot sign (no sell route, sell returns too little, or buys but no sells in the last hour: market.py flags);
  RugCheck marks the token rugged; dangerous Token-2022 extensions (rugdata dangerous_extensions: permanent
  delegate, transfer hook, non-transferable, default frozen, pausable); transfer fee above TRANSFER_FEE_PCT;
  LP under LP_LOCKED_MIN_PCT locked/burned on a non-pump.fun pool under LP_SKIP_LIQ_USD of liquidity; creator with
  a rug history; insider network over INSIDER_PCT; single non-pool wallet over TOP1_PCT; top-10 non-pool
  holders over TOP10_PCT; creator still holding over CREATOR_PCT. Tokens with at least MATURE_HOLDERS holders get
  the top1 / top10 checks as flags only (their top wallets are exchange custody, as rugdata.py notes). Wallets in
  IGNORE_HOLDERS are left out of top1 / top10 and reported as a flag; the default is one wallet identified (by
  inference, not documentation) as pump.fun's Mayhem-mode agent: a System-owned wallet with ~59,600 SOL holding
  46-75% of 31 tracked pump.fun tokens, one of them flagged Mayhem by PumpPortal (Mayhem launches mint a second
  billion tokens to the agent). Churn volume is a flag, never a veto.
  Two rug signatures measured on the arena's own buys (run 8, 2026-10-07/08: 65 Claude buys, 30 dead):
  brand-name impersonation, a symbol or name that is a famous brand (BRAND_NAMES: ChatGPT, Apple, NVIDIA, Tesla,
  Nike, ...; all 18 such buys died, against 26% of the rest); and bundle liquidity, a pump.fun graduate showing at
  least BUNDLE_LIQ_USD of liquidity while under BUNDLE_MAX_AGE_MIN since migration (or, migration time unknown,
  pair age): a normal migration brings ~$12k to the PumpSwap pool, and all 19 buys of graduates showing >= $80k
  minutes after migration died within about an hour, the injected liquidity pulled (~$150k to ~$11k in a minute).
  Bundle balances (run 9, video 1 check A): rugdata records each top holder's SOL balance (`sol`); when at least
  BUNDLE_SOL_MATCH (4) of the top 5 holders (pool / LP / locker accounts excluded by rugdata, the creator and
  IGNORE_HOLDERS left out, in holder order) each carry under BUNDLE_SOL_MAX (0.25) SOL and lie within
  BUNDLE_SOL_SPREAD (0.05) SOL of each other, the coin is vetoed ("identical funding": one bundler topped every
  wallet up with the same amount); BUNDLE_SOL_FLAG (3) such wallets is a soft flag. All 5 balances must be known
  (a missing one means no veto and no flag, listed under unknowns). Video 1's check B, wallets funded in the same
  time window, is NOT built: it needs about 20 signature lookups per token (each top holder's first funding
  transaction), far more RPC than the free tier allows at 4 rug checks a tick.

Settings: every number in THRESHOLDS can be overridden with ARENA_VETO_<KEY> (e.g. ARENA_VETO_TOP1_PCT=25,
ARENA_VETO_BUNDLE_SOL_MAX=0.25, ARENA_VETO_BUNDLE_SOL_SPREAD=0.05, ARENA_VETO_RAMP_MIN_PCT=40);
ARENA_VETO_IGNORE_HOLDERS is a comma-separated wallet list replacing the default; ARENA_VETO_BRAND_EXTRA is a
comma-separated list of names added to BRAND_NAMES.
"""
import contextlib
import os
import re
import sqlite3
import time
from collections import Counter
from operator import itemgetter

# key: default. Each line cites the report passage the number comes from.
_DEFAULTS = {
    # Tier 0, mint state. Report table row "0: mint state": "Token-2022 with permanent delegate, transfer fee/hook,
    # non-transferable; mint or freeze authority not null ... Hard reject". A fee above this percent is a veto, any
    # smaller non-zero fee a flag (it adds 2x the fee to a 5-8% round trip).
    "transfer_fee_pct": 0.5,
    # Tier 0, post-graduation LP. Row "0: post-graduation LP": "LP tokens neither burned nor locked and held by
    # creator cluster: Hard reject"; Solidus "93% of 388,000 Raydium pools showed soft-rug behavior". We cannot see
    # who holds the LP, so: veto when less than this percent is locked/burned (more than half can be pulled).
    "lp_locked_min_pct": 50.0,
    # "pulling LP is not how a $1M+ multi-pool token dies" (rugdata.py RUG_LP_SKIP_LIQ_USD): LP check skipped above.
    "lp_skip_liq_usd": 500_000.0,
    # Tier 1, cluster supply. Row "1: launch structure": "Reject >30% cluster"; Bubblemaps "over 15% serious,
    # over 30% avoid". Veto above insider_pct, flag at or above insider_flag_pct.
    "insider_pct": 30.0,
    "insider_flag_pct": 15.0,
    # Tier 1, single wallet. Row "1: launch structure": "prefer ... no wallet >10%"; rugdata's hard line is 20.
    "top1_pct": 20.0,
    "top1_flag_pct": 10.0,
    # Tier 1, top-10 holders ex-LP. Row "1: launch structure": "prefer top-10 <40%"; veto well past it.
    "top10_pct": 60.0,
    "top10_flag_pct": 40.0,
    # Tier 1, creator holdings. Row "1: launch structure": "prefer ... creator <5%"; deployer "still holding" is a
    # Tier 1 deployer check. Veto above creator_pct, flag at or above creator_flag_pct.
    "creator_pct": 15.0,
    "creator_flag_pct": 5.0,
    # Holder count from which top1 / top10 are flags, not vetoes (rugdata.py RUG_MATURE_HOLDERS: BONK's top 10
    # hold 38%, WIF's 46%, exchange custody).
    "mature_holders": 50_000.0,
    # Tier 2, volume quality. Row "2: volume quality": "Round-trip ratio (same-wallet buy-then-sell within seconds
    # / total volume) ... Treat volume as zero signal when round-trip ratio is high and net inflow low; require
    # >=70% non-bot". flip_secs matches traders.py ARENA_TRADERS_FLIP_SECS.
    "flip_secs": 60.0,
    "bot_mint_trades_h": 8.0,      # trades of one mint per hour by one wallet: top 1% of wallets in the real feed
    "bot_wallet_trades_h": 20.0,   # trades per hour across all tracked mints: top ~0.5% of wallets in the feed
    "flow_min_trades": 5.0,        # fewer trades than this: quality None (too thin to call)
    "churn_rt_share": 0.5,         # churn: at least half the volume is round trips ...
    "churn_net_share": 0.1,        # ... and net flow is within +-10% of gross
    "organic_rt_share": 0.15,      # organic: few round trips ...
    "organic_bot_share": 0.3,      # ... and >= 70% non-bot volume (report)
    "top_buyer_flag_share": 0.5,   # flag when one wallet did at least half the buying ("unique buyers" is gamed)
    "net_sell_flag_share": -0.3,   # flag clear net selling
    "flow_stale_min": 30.0,        # newest pool-feed trade older than this: listed under unknowns (with ~160
                                   # tracked pools each pool is polled about every 25 min; median age seen: 28 min)
    # Timing. Rec 4: "at least 5-15 minutes past migration"; "60% of graduates lose 80% within 20 minutes";
    # Tier 3: "never buy in first ~60 s" (sniper exit window). Flags, not vetoes.
    "fresh_migration_min": 15.0,
    "sniper_window_secs": 60.0,
    # Rug data older than this many hours is still used (stale beats blind) but listed under unknowns.
    "rug_stale_h": 6.0,
    "max_view_flags": 4.0,
    # Bundle liquidity (run 8 measurement, module docstring): a pump.fun graduate showing at least this much
    # liquidity while its pool is younger than bundle_max_age_min minutes is vetoed (normal migration: ~$12k).
    "bundle_liq_usd": 60_000.0,
    "bundle_max_age_min": 180.0,
    # Bundle balances (run 9, module docstring): of the top 5 holders, at least bundle_sol_match each under
    # bundle_sol_max SOL and within bundle_sol_spread SOL of each other is a veto; bundle_sol_flag of them a flag.
    "bundle_sol_max": 0.25,
    "bundle_sol_spread": 0.05,
    "bundle_sol_match": 4.0,
    "bundle_sol_flag": 3.0,
    # Ramp (run 9 replay of 798 run-8 curve coins: buying as the fill crossed 40-60% and selling at graduation or
    # -30% was the only positive entry rule). The window, and the net buying a ramp_setup needs.
    "ramp_min_pct": 40.0,
    "ramp_max_pct": 80.0,
    "ramp_min_net_share": 0.1,
    "ramp_min_buyers": 10.0,
    # Chart tell (run 9, video 1): a straight green run from the first tracked point, at least chart_min_points
    # 30-second points long, ending at chart_min_mult x the first price; one dip of at most chart_wiggle_pct forgiven.
    "chart_min_points": 8.0,
    "chart_min_mult": 2.0,
    "chart_wiggle_pct": 1.0,
}


def _env_f(name, default):
    try:
        v = float(os.environ.get(name, "") or default)
        return v if v == v else float(default)
    except ValueError:
        return float(default)


THRESHOLDS = {k: _env_f("ARENA_VETO_" + k.upper(), v) for k, v in _DEFAULTS.items()}
# Wallets that hold supply by protocol design, left out of top1 / top10 (reported as a flag instead).
_DEFAULT_IGNORE = {
    # pump.fun Mayhem-mode agent: holds ~50% (46-75%) of every Mayhem launch seen in the arena's RugCheck data
    # (2 billion supply, 1 billion minted to the agent, which trades it for 24 h). Seen on 31 tracked tokens.
    "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s": "pump.fun Mayhem agent",
}
_ign = os.environ.get("ARENA_VETO_IGNORE_HOLDERS")
IGNORE_HOLDERS = ({w.strip(): "protocol wallet" for w in _ign.split(",") if w.strip()} if _ign is not None
                  else dict(_DEFAULT_IGNORE))

PUMP_DEXES = {"pumpfun", "pumpswap"}
# Brand-name impersonation (run 8 measurement, module docstring): lowercase, letters and digits only. A symbol or
# name matches when, cleaned the same way, it equals a brand or is a brand followed by one of _BRAND_SUFFIXES or
# by digits only ("apple2", "nikecoin", "teslaai"); a brand inside a longer word ("metamorph", "solcat") does not.
BRAND_NAMES = frozenset({
    "chatgpt", "openai", "gpt", "claude", "anthropic", "gemini", "grok", "xai", "apple", "google", "alphabet",
    "microsoft", "nvidia", "amazon", "meta", "facebook", "instagram", "whatsapp", "tesla", "spacex", "starlink",
    "neuralink", "nike", "adidas", "lego", "disney", "netflix", "youtube", "tiktok", "reddit", "twitter", "bbc",
    "cnn", "coinbase", "binance", "robinhood", "visa", "mastercard", "paypal", "mcdonalds", "starbucks", "cocacola",
    "coke", "pepsi", "walmart", "costco", "ferrari", "porsche", "toyota", "ford", "boeing", "nasa", "pokemon",
    "nintendo", "playstation", "xbox", "marvel", "pixar", "samsung", "intel", "amd", "oracle", "ibm", "uber",
    "airbnb", "spotify", "shopify", "stripe", "bitcoin", "ethereum", "solana", "pumpfun", "dexscreener", "jupiter",
    "phantom",
} | {re.sub(r"[^a-z0-9]", "", b.lower()) for b in os.environ.get("ARENA_VETO_BRAND_EXTRA", "").split(",")} - {""})
_BRAND_SUFFIXES = {"coin", "inu", "ai", "2", "3", "x", "fun", "sol"}
_BRAND_DISPLAY = {"chatgpt": "ChatGPT", "openai": "OpenAI", "gpt": "GPT", "xai": "xAI", "nvidia": "NVIDIA",
                  "spacex": "SpaceX", "tiktok": "TikTok", "youtube": "YouTube", "whatsapp": "WhatsApp", "bbc": "BBC",
                  "cnn": "CNN", "lego": "LEGO", "nasa": "NASA", "amd": "AMD", "ibm": "IBM", "paypal": "PayPal",
                  "playstation": "PlayStation", "mcdonalds": "McDonald's", "cocacola": "Coca-Cola",
                  "pumpfun": "pump.fun", "dexscreener": "DEX Screener"}
# Honeypot-type Token-2022 extensions as RugCheck's risk names say them (fallback for rug data from before
# rugdata.py parsed token_extensions).
_EXT_RISKS = (("permanent delegate", re.compile(r"permanent (delegate|control)", re.I)),
              ("transfer hook", re.compile(r"transfer[ _-]?hook", re.I)),
              ("non-transferable", re.compile(r"non[ _-]?transferable", re.I)),
              ("default frozen", re.compile(r"default account state|frozen by default", re.I)),
              ("pausable", re.compile(r"pausab", re.I)))
_MINT_RISK = re.compile(r"mint authority (still )?enabled", re.I)
_FREEZE_RISK = re.compile(r"freeze authority (still )?enabled", re.I)


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def _conn_lock(db):
    """(connection, lock context) for the arena's DB object, or a bare sqlite3 connection."""
    conn = getattr(db, "conn", db)
    lock = getattr(db, "lock", None)
    return conn, (lock if lock is not None else contextlib.nullcontext())


# ------------------------------------------------------------------------------------------------ flow
def _quality(trades, rt, net, bot):
    th = THRESHOLDS
    if trades < th["flow_min_trades"]:
        return None
    if rt >= th["churn_rt_share"] and abs(net) <= th["churn_net_share"]:
        return "churn"
    if rt < th["organic_rt_share"] and bot <= th["organic_bot_share"]:
        return "organic"
    return "mixed"


def flow_signals(db, mints, now=None, window=3600):
    """{mint: flow dict} over the last `window` seconds of the pool feed (see the module docstring)."""
    mints = [m for m in dict.fromkeys(mints or ()) if isinstance(m, str) and m]
    if not mints or db is None:
        return {}
    now = time.time() if now is None else float(now)
    window = max(1.0, float(window))
    rows = []
    conn, lock = _conn_lock(db)
    try:
        with lock:
            cur = conn.cursor()
            cur.row_factory = None  # plain tuples: several times cheaper than sqlite3.Row for thousands of rows
            try:
                for i in range(0, len(mints), 500):
                    chunk = mints[i:i + 500]
                    # no ORDER BY: grouping in a dict below is cheaper than SQLite's sort without a mint index
                    cur.execute("SELECT mint, wallet, ts, kind = 'buy', usd FROM copy_trades WHERE ts >= ? "
                                "AND ts <= ? AND pool IS NOT NULL AND kind IN ('buy', 'sell') "
                                f"AND mint IN ({','.join('?' * len(chunk))})", (now - window, now, *chunk))
                    rows.extend(cur.fetchall())
            finally:
                cur.close()
    except sqlite3.Error:  # no copy_trades table (tracker off) or the database is busy: no flow this tick
        return {}
    if not rows:
        return {}
    th = THRESHOLDS
    flip = th["flip_secs"]
    hours = window / 3600.0
    bot_mint_n = max(3.0, th["bot_mint_trades_h"] * hours)
    bot_wallet_n = max(3.0, th["bot_wallet_trades_h"] * hours)
    wallet_n = Counter(map(itemgetter(1), rows))
    # (mint, wallet) -> the row itself (one trade, the common case) or a list of rows
    groups = {}
    for r in rows:
        k = r[0], r[1]
        g = groups.get(k)
        if g is None:
            groups[k] = r
        elif type(g) is list:
            g.append(r)
        else:
            groups[k] = [g, r]
    acc = {}
    for (mint, wallet), g in groups.items():
        a = acc.get(mint)
        if a is None:
            a = acc[mint] = _Acc()
        if type(g) is tuple:  # one trade: no round trip possible
            ts, isbuy, usd = g[2], g[3], g[4] or 0.0
            a.trades += 1
            if ts > a.last:
                a.last = ts
            if isbuy:
                a.buy += usd
                a.buyers += 1
                if usd > a.top_buy:
                    a.top_buy = usd
            else:
                a.sell += usd
                a.sellers += 1
            if wallet_n[wallet] >= bot_wallet_n:
                a.bot += usd
            continue
        g.sort(key=_TS)
        n = len(g)
        a.trades += n
        if g[-1][2] > a.last:
            a.last = g[-1][2]
        wb = ws = 0.0
        nb = 0
        for r in g:
            if r[3]:
                wb += r[4] or 0.0
                nb += 1
            else:
                ws += r[4] or 0.0
        a.buy += wb
        a.sell += ws
        if nb:
            a.buyers += 1
            if wb > a.top_buy:
                a.top_buy = wb
        if nb < n:
            a.sellers += 1
        flipped = False
        if 0 < nb < n:
            # mark every trade that has an opposite-side trade within `flip` seconds before or after it
            mark = [False] * n
            prev = [None, None]  # index of the latest sell / buy seen so far
            for i in range(n):
                side = g[i][3]
                j = prev[not side]
                if j is not None and g[i][2] - g[j][2] <= flip:
                    mark[i] = mark[j] = True
                prev[side] = i
            nxt = [None, None]
            for i in range(n - 1, -1, -1):
                side = g[i][3]
                j = nxt[not side]
                if j is not None and g[j][2] - g[i][2] <= flip:
                    mark[i] = True
                nxt[side] = i
            for i in range(n):
                if mark[i]:
                    flipped = True
                    a.rt += g[i][4] or 0.0
        if flipped or n >= bot_mint_n or wallet_n[wallet] >= bot_wallet_n:
            a.bot += wb + ws
    out = {}
    for mint, a in acc.items():
        gross = a.buy + a.sell
        net = a.buy - a.sell
        net_share = net / gross if gross > 0 else 0.0
        rt_share = a.rt / gross if gross > 0 else 0.0
        bot_share = a.bot / gross if gross > 0 else 0.0
        out[mint] = {
            "buy_usd": round(a.buy, 2), "sell_usd": round(a.sell, 2), "gross_usd": round(gross, 2),
            "net_usd": round(net, 2), "net_share": round(net_share, 3),
            "buyers": a.buyers, "sellers": a.sellers, "trades": a.trades,
            "round_trip_share": round(rt_share, 3),
            "top_buyer_share": round(a.top_buy / a.buy, 3) if a.buy > 0 else None,
            "bot_share": round(bot_share, 3),
            "last_trade_min_ago": round(max(0.0, now - a.last) / 60.0, 1),
            "quality": _quality(a.trades, rt_share, net_share, bot_share),
        }
    return out


class _Acc:
    """Per-mint running totals for flow_signals."""
    __slots__ = ("buy", "sell", "rt", "bot", "top_buy", "buyers", "sellers", "trades", "last")

    def __init__(self):
        self.buy = self.sell = self.rt = self.bot = self.top_buy = self.last = 0.0
        self.buyers = self.sellers = self.trades = 0


_TS = itemgetter(2)


def creator_selling(db, mints_to_creator, since):
    """{mint: dollars the creator wallet sold of that mint since `since`} (0.0 = none seen; {} without the table)."""
    pairs = {m: c for m, c in (mints_to_creator or {}).items() if isinstance(m, str) and isinstance(c, str) and m and c}
    if not pairs or db is None:
        return {}
    creators = list(set(pairs.values()))
    rows = []
    conn, lock = _conn_lock(db)
    try:
        with lock:
            cur = conn.cursor()
            cur.row_factory = None
            try:
                for i in range(0, len(creators), 500):
                    chunk = creators[i:i + 500]
                    cur.execute("SELECT id, mint, wallet, usd, tx FROM copy_trades WHERE kind = 'sell' AND ts >= ? "
                                f"AND wallet IN ({','.join('?' * len(chunk))})", (float(since or 0), *chunk))
                    rows.extend(cur.fetchall())
            finally:
                cur.close()
    except sqlite3.Error:
        return {}
    out = {m: 0.0 for m in pairs}
    seen = set()
    for rid, mint, wallet, usd, tx in rows:
        if pairs.get(mint) != wallet:
            continue
        key = (tx, wallet, mint) if tx else rid  # the same swap can be stored by the pool feed and by Helius
        if key in seen:
            continue
        seen.add(key)
        out[mint] += usd or 0.0
    return {m: round(v, 2) for m, v in out.items()}


# ------------------------------------------------------------------------------------------------ liquidity
def liquidity_trend(history, horizon=3600):
    """% change of the newest liquidity vs ~`horizon` seconds earlier and vs the maximum (see module docstring)."""
    pts = []
    for p in history or ():
        try:
            ts, liq = _num(p[0]), _num(p[1])
        except (TypeError, IndexError, KeyError):
            continue
        if ts is not None and liq is not None and liq >= 0:
            pts.append((ts, liq))
    if not pts:
        return None
    pts.sort()
    last_ts, last = pts[-1]
    mx = max(l for _, l in pts)
    ref = None
    for ts, l in pts:  # newest point at least `horizon` older than the newest one
        if ts <= last_ts - horizon:
            ref = (ts, l)
        else:
            break
    if ref is None and last_ts - pts[0][0] >= horizon / 2:
        ref = pts[0]
    return {
        "vs_1h_pct": round((last / ref[1] - 1) * 100, 1) if ref and ref[1] > 0 else None,
        "vs_max_pct": round((last / mx - 1) * 100, 1) if mx > 0 else None,
        "ref_min": round((last_ts - ref[0]) / 60) if ref else None,
        "span_min": round((last_ts - pts[0][0]) / 60),
        "liquidity": last,
    }


def minutes_since_graduation(token, now):
    """Minutes since a pump.fun token migrated, from token["pump"]["graduated"]; None when unknown, when the token
    shows no pump.fun context (market.py stamps "graduated" on any token whose pair moved off a pumpfun dex id), or
    when the stamp is in the future (recordings round it to 6 significant digits, i.e. +-500 s)."""
    t = token or {}
    g = _num((t.get("pump") or {}).get("graduated"))
    if g is None or now is None:
        return None
    rug = t.get("rug") if isinstance(t.get("rug"), dict) else {}
    srcs = set(t.get("sources") or ()) | {t.get("source")}
    if not (str(t.get("dex") or "").lower() in PUMP_DEXES or srcs & {"graduated", "pumpfun"}
            or str(rug.get("main_market_type") or "").startswith("pump_fun") or rug.get("launchpad") == "pump_fun"):
        return None
    if g > float(now) + 60:
        return None
    return max(0.0, (float(now) - g) / 60.0)


# ------------------------------------------------------------------------------------------------ vetoes
def _holders(rug):
    """(top1_pct, top10_pct, [(label, pct)] of ignored protocol wallets) with IGNORE_HOLDERS left out."""
    top1, top10 = _num(rug.get("top1_pct")), _num(rug.get("top10_pct"))
    th = rug.get("top_holders") if isinstance(rug.get("top_holders"), list) else []
    ignored = [(IGNORE_HOLDERS[h.get("owner")], _num(h.get("pct")) or 0.0) for h in th
               if isinstance(h, dict) and h.get("owner") in IGNORE_HOLDERS]
    if ignored:
        rest = [_num(h.get("pct")) or 0.0 for h in th if isinstance(h, dict) and h.get("owner") not in IGNORE_HOLDERS]
        top1 = max(rest, default=0.0)
        top10 = round(sum(sorted(rest, reverse=True)[:10]), 2)
    return top1, top10, ignored


def holder_sols(rug):
    """SOL balances of the top 5 holders (rugdata leaves pool / LP / locker / burn accounts out of top_holders), the
    creator, program-owned owners (rugdata `program_owned`: rent-exempt PDAs, not wallets) and IGNORE_HOLDERS left
    out, in holder order; None for a holder whose balance is unknown. Falls back to
    rugdata's own top5_sol when the holder list carries no balances; [] without either."""
    rug = rug if isinstance(rug, dict) else {}
    th = [h for h in (rug.get("top_holders") if isinstance(rug.get("top_holders"), list) else []) if isinstance(h, dict)]
    if any("sol" in h for h in th):
        creator = rug.get("creator")
        rows = [h for h in th if h.get("owner") not in IGNORE_HOLDERS and not h.get("creator")
                and not h.get("program_owned") and not (creator and h.get("owner") == creator)]
        return [_num(h.get("sol")) for h in rows[:5]]
    top5 = rug.get("top5_sol")
    return [_num(x) for x in top5[:5]] if isinstance(top5, list) else []


def _bundle_group(sols):
    """The largest set of known balances that are all under BUNDLE_SOL_MAX and within BUNDLE_SOL_SPREAD of each other."""
    th = THRESHOLDS
    lows = sorted(s for s in sols if s is not None and s < th["bundle_sol_max"])
    best, i = [], 0
    for j in range(len(lows)):
        while lows[j] - lows[i] >= th["bundle_sol_spread"]:
            i += 1
        if j - i + 1 > len(best):
            best = lows[i:j + 1]
    return best


def curve_pace(curve_pct, chg):
    """curve_pct_chg_10m from a chg_since entry (see the module docstring); None without a reference point."""
    cs = chg or {}
    pct, past = _num(curve_pct), _num(cs.get("curve_pct_10m"))
    if pct is None or past is None:
        return None
    secs = cs.get("curve_pct_10m_secs") or 600
    return round((pct - past) * 600 / min(600, max(105, secs)), 1)


CHART_FLAG = "straight green run since launch, no pullback (bundle pattern)"


def chart_tell(prices):
    """{"green_run", "chart_tell"} from a 30-second price history [(ts, price), ...] (see the module docstring)."""
    th = THRESHOLDS
    ps = [p for p in (_num(x[1]) if isinstance(x, (tuple, list)) and len(x) > 1 else None for x in prices or ())
          if p is not None and p > 0]
    run, wiggled = 0, False
    for a, b in zip(ps, ps[1:]):
        if b >= a:
            run += 1
        elif not wiggled and b >= a * (1 - th["chart_wiggle_pct"] / 100):
            wiggled = True
            run += 1
        else:
            break
    straight = len(ps) >= th["chart_min_points"] and run == len(ps) - 1 and ps[-1] >= ps[0] * th["chart_min_mult"]
    return {"green_run": run, "chart_tell": "straight run" if straight else None}


def _pump_pool(token, rug):
    dex = str(token.get("dex") or "").lower()
    mt = str(rug.get("main_market_type") or "").lower()
    return dex in PUMP_DEXES or mt.startswith("pump_fun") or token.get("source") == "pumpfun"


def _fee(rug):
    fees = [f for f in (_num(rug.get("transfer_fee_pct")), _num(rug.get("transfer_fee_ext_pct"))) if f is not None]
    return max(fees) if fees else None


def brand_match(token):
    """The brand a token's symbol or name impersonates (as written in BRAND_NAMES), or None. See BRAND_NAMES."""
    t = token or {}
    for field in ("symbol", "name"):
        s = re.sub(r"[^a-z0-9]", "", str(t.get(field) or "").lower())
        if not s:
            continue
        if s in BRAND_NAMES:
            return s
        # longest brand first, so "chatgpt2" names chatgpt rather than nothing via "chat"
        for b in sorted((b for b in BRAND_NAMES if s.startswith(b)), key=len, reverse=True):
            rest = s[len(b):]
            if rest in _BRAND_SUFFIXES or rest.isdigit():
                return b
    return None


def veto_report(token, flow=None, now=None, creator_sold_usd=None, migrated_min_ago=None):
    """{"vetoes": [...], "flags": [...], "unknowns": [...]} for one token dict (see the module docstring)."""
    th = THRESHOLDS
    t = token or {}
    vetoes, flags, unknowns = [], [], []

    def veto(text):
        if text not in vetoes:
            vetoes.append(text)

    rug = t.get("rug") if isinstance(t.get("rug"), dict) else None
    rug_ok = rug is not None and not rug.get("error")
    risks = [str(n) for n in (rug.get("rugcheck_risks") or [])] if rug_ok else []
    tflags = [str(f) for f in (t.get("flags") or [])]

    # --- Tier 0: authorities (market.py's RPC check is live; RugCheck's risk names are the fallback)
    risk = t.get("risk") if isinstance(t.get("risk"), dict) else None
    for what, key, pat in (("mint", "mint_revoked", _MINT_RISK), ("freeze", "freeze_revoked", _FREEZE_RISK)):
        revoked = risk.get(key) if risk else None
        if revoked is False or (revoked is None and any(f"{what} authority NOT revoked" in f for f in tflags)):
            veto(f"{what} authority not revoked")
        elif revoked is None:
            if any(pat.search(n) for n in risks):
                veto(f"{what} authority not revoked (RugCheck)")
            elif not rug_ok:
                unknowns.append(f"{what} authority not checked yet")

    # --- Tier 0: honeypot signs
    hp = [f for f in tflags if "honeypot" in f.lower()]
    for f in hp:
        veto(f)
    s = t.get("sellable") if isinstance(t.get("sellable"), dict) else None
    if not hp:
        if s is not None and s.get("ok") is False:
            veto("no sell route found (possible honeypot)")
        elif (_num(t.get("buys_h1")) or 0) > 20 and _num(t.get("sells_h1")) == 0:
            veto("no sells in last hour (possible honeypot)")
    if s is None and not hp:
        unknowns.append("sell route not probed yet")
    if rug_ok and rug.get("rugged"):
        veto("RugCheck marks the token as rugged")

    # --- Tier 0: Token-2022 extensions and transfer fee
    if rug_ok:
        ext = rug.get("dangerous_extensions")
        if ext is None:
            ext = [label for label, pat in _EXT_RISKS if any(pat.search(n) for n in risks)]
            if not ext:
                unknowns.append("Token-2022 extensions not parsed (rug data predates the check)")
        ext = [e for e in ext if not str(e).startswith("transfer fee")]  # the fee check below covers it
        if ext:
            veto("Token-2022 " + ", ".join(ext))
        fee = _fee(rug)
        if fee is not None and fee > th["transfer_fee_pct"]:
            veto(f"{fee:g}% transfer fee")
        elif fee:
            flags.append(f"{fee:g}% transfer fee")
        elif any("fee config" in n.lower() for n in risks):
            flags.append("transfer-fee authority can add a fee")

    # --- Tier 0: LP on non-pump.fun pools
    if rug_ok and not _pump_pool(t, rug):
        lp = _num(rug.get("lp_locked_pct"))
        liq = max(_num(t.get("liquidity")) or 0.0, _num(rug.get("total_liquidity_usd")) or 0.0)
        if lp is None:
            unknowns.append("LP lock unknown")
        elif lp < th["lp_locked_min_pct"] and liq < th["lp_skip_liq_usd"]:
            veto("LP not locked or burned" if lp <= 0 else f"only {lp:.0f}% of LP locked or burned")

    # --- Tier 1: deployer and holders
    if rug_ok:
        if rug.get("creator_rugged_history"):
            veto("creator has rugged tokens before")
        mature = (_num(rug.get("total_holders")) or 0) >= th["mature_holders"]
        top1, top10, ignored = _holders(rug)
        for label, pct in ignored:
            flags.append(f"{label} holds {pct:.0f}% (not counted)")
        if top1 is None:
            unknowns.append("largest holder unknown")
        elif top1 > th["top1_pct"] and not mature:
            veto(f"one wallet holds {top1:.0f}% of supply")
        elif top1 >= th["top1_flag_pct"]:
            flags.append(f"one wallet holds {top1:.0f}%")
        if top10 is None:
            unknowns.append("top-10 holder share unknown")
        elif top10 > th["top10_pct"] and not mature:
            veto(f"top 10 holders own {top10:.0f}% of supply")
        elif top10 >= th["top10_flag_pct"]:
            flags.append(f"top 10 hold {top10:.0f}%")
        ins = _num(rug.get("insider_pct"))
        if ins is None:
            unknowns.append("insider share unknown")
        elif ins > th["insider_pct"]:
            veto(f"insider network holds {ins:.0f}% of supply")
        elif ins >= th["insider_flag_pct"]:
            flags.append(f"insiders hold {ins:.0f}%")
        cp = _num(rug.get("creator_pct"))
        if cp is None:
            unknowns.append("creator holding unknown")
        elif cp > th["creator_pct"]:
            veto(f"creator still holds {cp:.0f}% of supply")
        elif cp >= th["creator_flag_pct"]:
            flags.append(f"creator holds {cp:.0f}%")
        sols = holder_sols(rug)
        if len(sols) >= 5:
            if any(s is None for s in sols):
                unknowns.append("top-holder SOL balances unknown")
            else:
                group = _bundle_group(sols)
                mid = group[len(group) // 2] if group else 0.0
                if len(group) >= th["bundle_sol_match"]:
                    veto(f"bundle: top holders all carry ~{mid:.2f} SOL (identical funding)")
                elif len(group) >= th["bundle_sol_flag"]:
                    flags.append(f"{len(group)} of the top 5 holders carry ~{mid:.2f} SOL each (possible bundle)")
        checked = _num(rug.get("checked")) or _num(t.get("rug_checked"))
        if now is not None and checked and now - checked > th["rug_stale_h"] * 3600:
            unknowns.append(f"rug data {(now - checked) / 3600:.0f} h old")
    elif rug is not None:
        unknowns.append(f"rug data unavailable ({str(rug.get('error'))[:60]})")
    else:
        unknowns.append("no rug data yet (holders, insiders, creator, LP, extensions unknown)")

    # --- rug signatures measured on the arena's own buys (module docstring)
    brand = brand_match(t)
    if brand:
        veto(f"brand-name impersonation ({_BRAND_DISPLAY.get(brand, brand.capitalize())}): every such coin bought "
             f"so far was rugged")
    mig = migrated_min_ago if migrated_min_ago is not None else minutes_since_graduation(t, now)
    age_min = _num(t.get("age_min"))
    liq = _num(t.get("liquidity"))
    graduate = bool((t.get("pump") or {}).get("graduated")) or str(t.get("dex") or "").lower() == "pumpswap"
    pool_min = mig if mig is not None else age_min
    if graduate and liq is not None and pool_min is not None and pool_min < th["bundle_max_age_min"] \
            and liq >= th["bundle_liq_usd"]:
        veto(f"liquidity ${liq / 1000:.0f}k on a {pool_min:.0f}-minute-old graduate: far above a normal migration "
             f"(~$12k), injected liquidity gets pulled")

    # --- Tier 2: volume quality (flags only)
    if flow:
        rt, net = flow.get("round_trip_share") or 0.0, flow.get("net_share") or 0.0
        enough = (flow.get("trades") or 0) >= th["flow_min_trades"]
        if flow.get("quality") == "churn":
            flags.append(f"volume is churn ({rt:.0%} round trips, net {net:+.0%})")
        if enough and (flow.get("bot_share") or 0) > th["organic_bot_share"]:
            flags.append(f"{flow['bot_share']:.0%} of volume from bot-like wallets")
        tb = flow.get("top_buyer_share")
        if enough and tb is not None and tb >= th["top_buyer_flag_share"] and (flow.get("buyers") or 0) > 1:
            flags.append(f"one wallet did {tb:.0%} of the buying")
        if enough and net <= th["net_sell_flag_share"]:
            flags.append(f"net selling ({net:+.0%} of volume)")
        age = _num(flow.get("last_trade_min_ago"))
        if age is not None and age > th["flow_stale_min"]:  # quiet pool or not polled lately: can't tell which
            unknowns.append(f"newest pool-feed trade {age:.0f} min old")
        if not enough:
            unknowns.append(f"only {flow.get('trades') or 0} pool-feed trades in the window")
    else:
        unknowns.append("no pool-feed trades in the window")
    if creator_sold_usd:
        flags.append(f"creator sold ${creator_sold_usd:,.0f}")

    # --- timing (flags only)
    if (mig is not None and mig * 60 < th["sniper_window_secs"]) or \
            (age_min is not None and age_min * 60 < th["sniper_window_secs"]):
        flags.append("inside the first minute (sniper exit window)")
    elif mig is not None and mig < th["fresh_migration_min"]:
        flags.append(f"migrated {mig:.0f} min ago")
    return {"vetoes": vetoes, "flags": flags, "unknowns": unknowns}


def vetoes(token, flow=None, now=None, **kw):
    """Hard-reject reasons for a token ([] = allowed). Missing data never vetoes; see veto_report()."""
    return veto_report(token, flow, now, **kw)["vetoes"]


# ------------------------------------------------------------------------------------------------ LLM view
def ramp_stage(curve_pct):
    """"early" / "ramp" / "late" for a curve fill (RAMP_MIN_PCT..RAMP_MAX_PCT is the ramp); None when unknown."""
    pct = _num(curve_pct)
    if pct is None:
        return None
    return "early" if pct < THRESHOLDS["ramp_min_pct"] else "late" if pct > THRESHOLDS["ramp_max_pct"] else "ramp"


def _net_buying(token, flow):
    """Net buying from many wallets, as ramp_setup needs it (see the module docstring)."""
    th = THRESHOLDS
    if flow:
        return (flow.get("net_share") or 0.0) >= th["ramp_min_net_share"] and \
            (flow.get("buyers") or 0) >= th["ramp_min_buyers"]
    buys, sells = _num(token.get("buys_h1")), _num(token.get("sells_h1"))
    return buys is not None and sells is not None and buys > sells and buys >= th["ramp_min_buyers"]


def structural_view(token, flow, liq_trend, migrated_min_ago, creator_sold_usd, now=None, chg=None, prices=None):
    """Compact structural evidence for one candidate (only keys with data), for an LLM prompt."""
    t = token or {}
    out = {}
    if flow:
        out["net_inflow_1h_usd"] = int(round(flow.get("net_usd") or 0))
        out["net_share"] = round(flow.get("net_share") or 0.0, 2)
        out["buyers_1h"] = flow.get("buyers") or 0
        out["round_trip_share"] = round(flow.get("round_trip_share") or 0.0, 2)
        if flow.get("top_buyer_share") is not None:
            out["top_buyer_share"] = round(flow["top_buyer_share"], 2)
        if flow.get("quality"):
            out["flow_quality"] = flow["quality"]
    rug = t.get("rug") if isinstance(t.get("rug"), dict) and not t["rug"].get("error") else None
    if rug:
        ins = _num(rug.get("insider_pct"))
        if ins is not None:
            out["insider_pct"] = round(ins, 1)
        top10 = _holders(rug)[1]
        if top10 is not None:
            out["top10_pct"] = round(top10, 1)
        cp = _num(rug.get("creator_pct"))
        if cp is not None:
            out["creator_pct"] = round(cp, 1)
    if _num(creator_sold_usd) is not None:  # 0 = creator known, no sells seen; None = creator unknown
        out["creator_sold_usd"] = int(round(creator_sold_usd))
    if rug and _num(rug.get("lp_locked_pct")) is not None and not _pump_pool(t, rug):
        out["lp_locked_pct"] = int(round(rug["lp_locked_pct"]))
    mig = migrated_min_ago if migrated_min_ago is not None else minutes_since_graduation(t, now)
    if mig is not None:
        out["minutes_since_graduation"] = int(round(mig))
    if liq_trend and liq_trend.get("vs_1h_pct") is not None:
        out["liquidity_vs_1h_pct"] = int(round(liq_trend["vs_1h_pct"]))
    rep = veto_report(t, flow, now, creator_sold_usd=creator_sold_usd, migrated_min_ago=mig)
    flags = list(rep["flags"])
    tell = chart_tell(prices)["chart_tell"] if prices else None
    if tell:
        out["chart_tell"] = tell
        flags.insert(0, CHART_FLAG)
    pump = t.get("pump") if isinstance(t.get("pump"), dict) else {}
    pct = _num(pump.get("curve_pct"))
    if pct is not None and not pump.get("graduated") and "pumpfun" in (str(t.get("dex") or "").lower(), t.get("source")):
        out["curve_pct"] = round(pct, 1)
        out["curve_pct_chg_10m"] = curve_pace(pct, chg)
        out["ramp"] = ramp_stage(pct)
        if out["ramp"] == "ramp" and not rep["vetoes"] and not tell and _net_buying(t, flow):
            out["ramp_setup"] = True
    if flags:
        out["flags"] = flags[:int(THRESHOLDS["max_view_flags"])]
    if rep["vetoes"]:
        out["vetoes"] = rep["vetoes"]
    return out

