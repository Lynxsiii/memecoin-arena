"""Team Copy data side: a leaderboard of real Solana memecoin traders and live copy signals from their swaps.

What it does
  1. LEADERBOARD. Polls the recent trades of the pools of every token the market tracks from GeckoTerminal's free
     API (GET /networks/solana/pools/{pool}/trades: the last 300 trades of a pool with the trader's wallet, side,
     amounts, USD value and prices), stores them in its own SQLite tables, keeps 7 days, and every hour (and at
     startup from the stored data) scores every wallet over the last 48 hours: realized P&L per token at average
     cost, plus a conservative unrealized value for what is still held, ROI, win rate, tokens traded, volume.
     Non-human wallets are filtered out (see below) and the best `top_n` wallets are kept.
  2. LIVE COPY SIGNALS. With a Helius API key: one websocket to Helius, `logsSubscribe` {"mentions": [wallet]}
     per top wallet (commitment confirmed). Each notification whose logs show a DEX / aggregator program (plain
     transfers, wraps and compute-budget-only transactions are skipped without a request) is fetched with
     getTransaction (jsonParsed, maxSupportedTransactionVersion 0) and the wallet's pre/post balances decide the
     swap: a non-quote token up while SOL / WSOL / USDC / USDT went down is a buy, the reverse a sell. Transfers,
     wrapping, airdrops and dust under ARENA_TRADERS_MIN_TRADE_USD are ignored. Signals get source "helius" and a
     buy of a token the market does not track calls market.track(mint, source="copy") when the market has it.
     Without a key, or while Helius is down, new GeckoTerminal trades of top wallets become signals with source
     "gecko" (latency = polling interval, a few minutes per pool).

API (used by the arena and the dashboard)
  Tracker(db, market, helius_key=None, top_n=100)
  .start()             background threads, never raises, never blocks
  .top()               [{"rank", "wallet", "pnl_usd", "roi_pct", "trades", "tokens", "win_rate", "volume_usd",
                         "last_trade_ts", ...}] best first
  .signals(since_ts)   [{"id", "ts", "wallet", "rank", "side", "mint", "symbol", "usd", "source", "tx"}] with
                       ts > since_ts, oldest first, at most 500
  .status()            health: threads, Helius connection and credits, GeckoTerminal requests, ranking times
  .stop()              ask the threads to finish (used by tests)

Scoring (window = last ARENA_TRADERS_WINDOW_H hours, trades under ARENA_TRADERS_MIN_TRADE_USD ignored)
  Per wallet and token, in time order: a buy adds to quantity and cost; a sell realizes proceeds minus the average
  cost of what was sold. Sells of more than the wallet bought inside the window (bought earlier, or transferred in)
  are counted at zero profit - their cost is unknown. Still-held quantity is valued at the market's live price when
  the token is tracked, else at the last trade price seen for the token, with a haircut of ARENA_TRADERS_HAIRCUT
  (default 15 %: the arena measured a 7 % round trip and thin memecoin exits fill worse) and at zero when the last
  price is older than 6 hours (the pool is probably dead). ROI = P&L / dollars spent on buys. Win rate = share of
  tokens with a sell that ended with a positive realized P&L. The leaderboard is sorted by P&L in dollars and only
  lists wallets with P&L >= ARENA_TRADERS_MIN_PNL (default 0): nobody is offered for copying while losing. On a
  fresh database the board is therefore empty for a while (the first ranking needs round trips inside the window).

Non-human filter (every number is an environment variable)
  ARENA_TRADERS_MIN_TOKENS=3        at least this many different tokens bought in the window
  ARENA_TRADERS_MIN_VOLUME=500      at least this many dollars traded (buys + sells)
  ARENA_TRADERS_MIN_TRADES=4        at least this many trades
  ARENA_TRADERS_MAX_TRADES=300      more trades than this in the window is a bot
  ARENA_TRADERS_FLIP_SECS=60        a buy followed by a sell of the same token within this is a "flip"
  ARENA_TRADERS_FLIP_SHARE=0.5      a wallet whose flips are at least this share of its round trips (and at least
                                    3 flips) is an MEV / sandwich / arbitrage bot
  ARENA_TRADERS_MIN_AVG_USD=20      average trade smaller than this is a dust / spam bot
  ARENA_TRADERS_MAX_TX_PER_MIN=6    on-chain transaction rate above which a wallet is automated. Pool feeds only
                                    show a slice of a wallet's activity: in the live test the 8 wallets that passed
                                    the trade-based filters turned out to be relayers / fee payers sending 18
                                    transactions a second between them. So, with a Helius key, every candidate is
                                    checked once (getSignaturesForAddress, 50 signatures, 1 credit, cached 6 h) and
                                    rejected above this rate; and any subscribed wallet that produces more than
                                    twice this rate of notifications in a minute is banned and unsubscribed on the
                                    spot. Bans are stored (copy_banned) and survive restarts.
  plus a list of known program, aggregator and fee authorities (KNOWN_NON_HUMAN) that never rank.

Other settings
  ARENA_TRADERS=1                   0 / off disables everything (start() is a no-op, status() says so)
  ARENA_HELIUS_KEY                  Helius API key, used when the constructor gets no helius_key (never logged)
  ARENA_GECKO_URL                   GeckoTerminal base URL (same setting as market.py)
  ARENA_TRADERS_TOP=100             leaderboard size when the constructor does not say
  ARENA_TRADERS_WINDOW_H=48         scoring window in hours
  ARENA_TRADERS_RANK_SECS=3600      seconds between rankings
  ARENA_TRADERS_KEEP_DAYS=7         stored trades older than this are deleted
  ARENA_TRADERS_GECKO_PER_MIN=6     GeckoTerminal trade requests per minute. The public API advertises ~30 a
                                    minute, but measured on 2026-10-06 the trades endpoint allowed about 7 in a
                                    burst and then one every ~12 s (429 with Retry-After 0 on every other request
                                    at 10 a minute), so 6 plus market.py's ~2 stays clear of it. A 429 pauses this
                                    feed 60 s, doubling to 10 min; the market's own GeckoTerminal pause is respected.
                                    With 60 tracked tokens every pool is read about every 10 minutes; the busiest
                                    pools (whose 300 trades cover less than that) are read more often and the quiet
                                    ones less, so the history of the very hottest pools has gaps.
  ARENA_TRADERS_MIN_TRADE_USD=10    trades below this are not stored, scored or signalled
  ARENA_TRADERS_HELIUS_WATCH=100    wallets subscribed over the websocket (the best ones)
  ARENA_TRADERS_HELIUS_PER_DAY=15000  Helius credits this module may spend per UTC day; beyond it swaps are not
                                    fetched (signals fall back to "gecko") until the next day
  ARENA_TRADERS_HELIUS_RPS=4        getTransaction requests per second at most (free plan allows 10 overall)
  ARENA_TRADERS_SIGNAL_MAX_AGE=600  a trade older than this many seconds is history, not a signal

Expected Helius use (free plan, checked on helius.dev/pricing 2026-10-06: 1M credits / month, 10 requests / s,
standard websockets included). RPC calls cost 1 credit each. Each copied wallet transaction that looks like a swap
costs one getTransaction (1 credit); 100 active wallets doing 10-50 swaps a day each is roughly 1,000-5,000 credits
a day, capped by ARENA_TRADERS_HELIUS_PER_DAY at 15,000 (450k a month worst case). Helius meters websocket streams
by data (2 credits per 0.1 MB); a logsNotification is 1-3 KB, so 5,000 notifications a day are another ~100-300
credits. status() reports the connection, subscriptions, notifications and every request made, so the real figure
can be read off the dashboard. The module never prints or stores the key.
"""
import json
import os
import queue
import threading
import time
from collections import deque

import requests

try:
    import websocket  # websocket-client
except ImportError:  # the leaderboard still works without it; only live Helius signals need it
    websocket = None

GECKO = os.environ.get("ARENA_GECKO_URL", "https://api.geckoterminal.com/api/v2").rstrip("/")
GECKO_HEADERS = {"Accept": "application/json;version=20230302", "User-Agent": "memecoin-arena/0.1"}
HELIUS_RPC = "https://mainnet.helius-rpc.com/?api-key={key}"
HELIUS_WS = "wss://mainnet.helius-rpc.com/?api-key={key}"

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCdWzEeDfa"
STABLES = {USDC_MINT, USDT_MINT, "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo"}  # USDC, USDT, PYUSD
QUOTES = STABLES | {SOL_MINT}


def _env_f(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)


ENABLED = os.environ.get("ARENA_TRADERS", "1").strip().lower() not in ("0", "off", "false", "no")
TOP_N = int(_env_f("ARENA_TRADERS_TOP", 100))
WINDOW_H = _env_f("ARENA_TRADERS_WINDOW_H", 48)
RANK_SECS = _env_f("ARENA_TRADERS_RANK_SECS", 3600)
KEEP_DAYS = _env_f("ARENA_TRADERS_KEEP_DAYS", 7)
GECKO_PER_MIN = max(1.0, _env_f("ARENA_TRADERS_GECKO_PER_MIN", 6))
MIN_TRADE_USD = _env_f("ARENA_TRADERS_MIN_TRADE_USD", 10)
MIN_TOKENS = int(_env_f("ARENA_TRADERS_MIN_TOKENS", 3))
MIN_VOLUME = _env_f("ARENA_TRADERS_MIN_VOLUME", 500)
MIN_TRADES = int(_env_f("ARENA_TRADERS_MIN_TRADES", 4))
MAX_TRADES = int(_env_f("ARENA_TRADERS_MAX_TRADES", 300))
FLIP_SECS = _env_f("ARENA_TRADERS_FLIP_SECS", 60)
FLIP_SHARE = _env_f("ARENA_TRADERS_FLIP_SHARE", 0.5)
MIN_AVG_USD = _env_f("ARENA_TRADERS_MIN_AVG_USD", 20)
MAX_TX_PER_MIN = _env_f("ARENA_TRADERS_MAX_TX_PER_MIN", 6)
HAIRCUT = min(1.0, max(0.0, _env_f("ARENA_TRADERS_HAIRCUT", 0.15)))
MIN_PNL = _env_f("ARENA_TRADERS_MIN_PNL", 0)
STALE_PRICE_SECS = 6 * 3600
HELIUS_WATCH = int(_env_f("ARENA_TRADERS_HELIUS_WATCH", 100))
HELIUS_PER_DAY = int(_env_f("ARENA_TRADERS_HELIUS_PER_DAY", 15000))
HELIUS_RPS = max(0.5, _env_f("ARENA_TRADERS_HELIUS_RPS", 4))
SIGNAL_MAX_AGE = _env_f("ARENA_TRADERS_SIGNAL_MAX_AGE", 600)

# Programs, pool authorities and fee accounts that show up as "traders" in pool feeds but are not people.
KNOWN_NON_HUMAN = {
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",   # Jupiter v6
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB",   # Jupiter v4
    "jupoNjAxXgZ4rjzxzPMP4oxduvQsQtZzyknqvzYNrNu",   # Jupiter limit order
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  # Raydium AMM v4
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  # Raydium AMM authority
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK",  # Raydium CLMM
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",  # Raydium CPMM
    "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",   # Raydium LaunchLab
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",   # pump.fun
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",   # PumpSwap
    "CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM",  # pump.fun fee account
    "62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV",  # pump.fun fee account
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",   # Meteora DLMM
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB",  # Meteora DAMM v1
    "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG",   # Meteora DAMM v2
    "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN",   # Meteora DBC
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",   # Orca Whirlpool
    "6m2CDdhRgxpH4WjvdzxAYbGxwdGUz5MziiL5jek2kBma",  # OKX DEX router
    "AxiomfHaWDemCFBLBayqnEnNwE6b7B2Qz3UmzMpgbMG6",  # Axiom fee
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # Token program
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",   # Token-2022
    "11111111111111111111111111111111",              # System program
}
# Top-level programs whose presence alone never means a swap: a transaction made only of these is not fetched.
BORING_PROGRAMS = {
    "ComputeBudget111111111111111111111111111111", "11111111111111111111111111111111",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr",
    "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo", "Vote111111111111111111111111111111111111111",
    "Stake11111111111111111111111111111111111111", "AddressLookupTab1e1111111111111111111111111",
}


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _iso_ts(s):
    """'2026-10-06T15:11:56Z' -> unix seconds (0 when unparsable)."""
    try:
        import calendar
        return float(calendar.timegm(time.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, TypeError):
        return 0.0


def _day_key(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


# --------------------------------------------------------------------------------------------------------------
# Pure functions: scoring and swap parsing. Kept free of I/O so they can be unit-tested with synthetic data.
# --------------------------------------------------------------------------------------------------------------
def score_wallets(trades, now, prices=None, window_h=None):
    """Per-wallet performance from trade rows (dicts with ts, wallet, mint, kind buy|sell, usd, qty, price).
    `prices` maps mint -> (price_usd, ts) for valuing held tokens (the market's live price should win there).
    Returns {wallet: stats}; stats carry everything the leaderboard and the bot filter need."""
    window = (window_h if window_h is not None else WINDOW_H) * 3600
    prices = prices or {}
    rows = sorted((r for r in trades if r.get("usd", 0) >= MIN_TRADE_USD and now - r["ts"] <= window),
                  key=lambda r: (r["ts"], 0 if r["kind"] == "buy" else 1))
    last_price = {}
    for r in rows:
        if r.get("price"):
            lp = last_price.get(r["mint"])
            if not lp or r["ts"] >= lp[1]:
                last_price[r["mint"]] = (r["price"], r["ts"])
    for m, (p, ts) in prices.items():
        if p and p > 0:
            last_price[m] = (p, ts)
    wallets = {}
    for r in rows:
        w = wallets.setdefault(r["wallet"], {
            "trades": 0, "buys": 0, "sells": 0, "volume_usd": 0.0, "spent_usd": 0.0, "realized_usd": 0.0,
            "first_trade_ts": r["ts"], "last_trade_ts": r["ts"], "flips": 0, "round_trips": 0, "same_block": 0,
            "pos": {}, "token_pnl": {}, "tokens_bought": set(), "tokens": set(),
        })
        w["trades"] += 1
        w["volume_usd"] += r["usd"]
        w["last_trade_ts"] = max(w["last_trade_ts"], r["ts"])
        w["tokens"].add(r["mint"])
        pos = w["pos"].setdefault(r["mint"], {"qty": 0.0, "cost": 0.0, "last_buy_ts": None})
        if r["kind"] == "buy":
            w["buys"] += 1
            w["spent_usd"] += r["usd"]
            w["tokens_bought"].add(r["mint"])
            pos["qty"] += r.get("qty") or 0.0
            pos["cost"] += r["usd"]
            pos["last_buy_ts"] = r["ts"]
        else:
            w["sells"] += 1
            q = r.get("qty") or 0.0
            if pos["qty"] > 0 and q > 0:
                sold = min(q, pos["qty"])
                basis = pos["cost"] * sold / pos["qty"]
                proceeds = r["usd"] * sold / q
                pnl = proceeds - basis
                w["realized_usd"] += pnl
                w["token_pnl"][r["mint"]] = w["token_pnl"].get(r["mint"], 0.0) + pnl
                pos["qty"] -= sold
                pos["cost"] -= basis
                if pos["qty"] <= 1e-12:
                    pos["qty"], pos["cost"] = 0.0, 0.0
                w["round_trips"] += 1
                if pos["last_buy_ts"] is not None:
                    gap = r["ts"] - pos["last_buy_ts"]
                    if gap <= FLIP_SECS:
                        w["flips"] += 1
                    if gap <= 1:
                        w["same_block"] += 1
            else:
                # Sold something bought before the window (or received): unknown cost, zero profit, counts as a trade.
                w["token_pnl"].setdefault(r["mint"], 0.0)
    out = {}
    for wallet, w in wallets.items():
        unreal = 0.0
        held = 0
        for mint, pos in w["pos"].items():
            if pos["qty"] <= 0:
                continue
            held += 1
            lp = last_price.get(mint)
            if lp and lp[0] > 0 and now - lp[1] <= STALE_PRICE_SECS:
                unreal += pos["qty"] * lp[0] * (1 - HAIRCUT) - pos["cost"]
            else:
                unreal -= pos["cost"]  # no usable price: assume the position is worth nothing
        closed = [p for p in w["token_pnl"].values()]
        wins = sum(1 for p in closed if p > 0)
        pnl = w["realized_usd"] + unreal
        out[wallet] = {
            "wallet": wallet, "pnl_usd": round(pnl, 2), "realized_usd": round(w["realized_usd"], 2),
            "unrealized_usd": round(unreal, 2),
            "roi_pct": round(pnl / w["spent_usd"] * 100, 1) if w["spent_usd"] > 0 else 0.0,
            "trades": w["trades"], "buys": w["buys"], "sells": w["sells"], "tokens": len(w["tokens"]),
            "tokens_bought": len(w["tokens_bought"]), "held": held,
            "win_rate": round(wins / len(closed) * 100, 1) if closed else None,
            "volume_usd": round(w["volume_usd"], 2), "spent_usd": round(w["spent_usd"], 2),
            "first_trade_ts": w["first_trade_ts"], "last_trade_ts": w["last_trade_ts"],
            "flips": w["flips"], "round_trips": w["round_trips"], "same_block": w["same_block"],
        }
    return out


def human_reason(st, banned=None):
    """Why a wallet is NOT eligible for the leaderboard (None when it is). Order: cheap exclusions first.
    `banned` maps wallets to a reason found at run time (on-chain transaction rate)."""
    if st["wallet"] in KNOWN_NON_HUMAN:
        return "known program / authority"
    if banned and st["wallet"] in banned:
        return "banned: " + str(banned[st["wallet"]])
    if st["trades"] > MAX_TRADES:
        return f"{st['trades']} trades in the window (bot)"
    if st["round_trips"] and st["flips"] >= 3 and st["flips"] / st["round_trips"] >= FLIP_SHARE:
        return f"{st['flips']} of {st['round_trips']} round trips flipped within {FLIP_SECS:.0f}s (MEV / sandwich)"
    if st["same_block"] >= 3 and st["same_block"] / max(1, st["round_trips"]) >= 0.3:
        return f"{st['same_block']} same-block buy+sell pairs (sandwich / arbitrage)"
    if st["trades"] < MIN_TRADES:
        return f"under {MIN_TRADES} trades"
    if st["tokens_bought"] < MIN_TOKENS:
        return f"under {MIN_TOKENS} tokens bought"
    if st["volume_usd"] < MIN_VOLUME:
        return f"under ${MIN_VOLUME:.0f} volume"
    if st["volume_usd"] / max(1, st["trades"]) < MIN_AVG_USD:
        return f"average trade under ${MIN_AVG_USD:.0f} (dust bot)"
    if st["pnl_usd"] < MIN_PNL:
        return "losing"
    return None


def rank_wallets(stats, top_n, banned=None):
    """Eligible wallets sorted best first with a 1-based rank."""
    ok = [s for s in stats.values() if human_reason(s, banned) is None]
    ok.sort(key=lambda s: (-s["pnl_usd"], -s["roi_pct"], -s["volume_usd"]))
    out = []
    for i, s in enumerate(ok[:top_n], 1):
        s = dict(s)
        s["rank"] = i
        out.append(s)
    return out


def logs_look_like_swap(logs):
    """False when every top-level program in the logs is a transfer / wrap / budget program (no request needed)."""
    programs = set()
    for line in logs or []:
        if isinstance(line, str) and line.startswith("Program ") and line.endswith(" invoke [1]"):
            programs.add(line.split()[1])
    if not programs:
        return True  # can't tell, fetch
    return not programs <= BORING_PROGRAMS


def parse_swap(tx, wallet, sol_price):
    """Swap(s) by `wallet` in a getTransaction (jsonParsed) result, from its pre/post balances.
    Returns a list of {"side", "mint", "qty", "usd", "quote_usd"}; [] for transfers, wraps, airdrops, dust, errors."""
    try:
        meta = tx.get("meta") or {}
        if meta.get("err") is not None:
            return []
        msg = (tx.get("transaction") or {}).get("message") or {}
        keys = msg.get("accountKeys") or []
        idx = None
        for i, k in enumerate(keys):
            pk = k.get("pubkey") if isinstance(k, dict) else k
            if pk == wallet:
                idx = i
                break
        lamports = 0
        if idx is not None:
            pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
            if idx < len(pre) and idx < len(post):
                lamports = post[idx] - pre[idx]
                if idx == 0:
                    lamports += meta.get("fee") or 0  # the fee payer's fee is not part of the swap
        deltas = {}
        for sign, side in ((-1, meta.get("preTokenBalances") or []), (1, meta.get("postTokenBalances") or [])):
            for b in side:
                if b.get("owner") != wallet:
                    continue
                ui = b.get("uiTokenAmount") or {}
                amt = ui.get("uiAmount")
                if amt is None:
                    try:
                        amt = int(ui.get("amount") or 0) / 10 ** int(ui.get("decimals") or 0)
                    except (TypeError, ValueError):
                        amt = 0.0
                deltas[b["mint"]] = deltas.get(b["mint"], 0.0) + sign * float(amt)
        sol = lamports / 1e9 + deltas.pop(SOL_MINT, 0.0)
        stable = sum(deltas.pop(m) for m in list(deltas) if m in STABLES)
        tokens = {m: d for m, d in deltas.items() if abs(d) > 0}
        quote_usd = (sol * sol_price if sol_price else 0.0) + stable
        if sol and not sol_price and not stable:
            return []  # cannot value the trade
        received = {m: d for m, d in tokens.items() if d > 0}
        sent = {m: -d for m, d in tokens.items() if d < 0}
        out = []
        if len(received) == 1 and not sent and quote_usd < 0 and -quote_usd >= MIN_TRADE_USD:
            (m, q), = received.items()
            out.append({"side": "buy", "mint": m, "qty": q, "usd": round(-quote_usd, 2), "quote_usd": round(quote_usd, 2)})
        elif len(sent) == 1 and not received and quote_usd > 0 and quote_usd >= MIN_TRADE_USD:
            (m, q), = sent.items()
            out.append({"side": "sell", "mint": m, "qty": q, "usd": round(quote_usd, 2), "quote_usd": round(quote_usd, 2)})
        return out
    except Exception:
        return []


# --------------------------------------------------------------------------------------------------------------
class Tracker:
    """Leaderboard + copy signals. One instance per arena; all public methods are thread-safe and never raise."""

    def __init__(self, db, market, helius_key=None, top_n=None):
        self.db = db
        self.market = market
        self.key = (helius_key or os.environ.get("ARENA_HELIUS_KEY") or "").strip() or None
        self.top_n = int(top_n or TOP_N)
        self.enabled = ENABLED
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.threads = {}
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "memecoin-arena/0.1"
        # leaderboard
        self.leaders = []            # list of stats dicts with rank, best first
        self.leader_set = {}         # wallet -> rank
        self.last_rank_ts = 0.0
        self.rank_note = ""          # "123 wallets scored, 40 eligible"
        self.filtered = {}           # reason -> count from the last ranking
        self.banned = {}             # wallet -> reason (on-chain rate says bot), persisted in copy_banned
        self.activity = {}           # wallet -> (tx per minute from its last 50 signatures, checked ts)
        self.ws_rate = {}            # wallet -> deque of notification timestamps (flood detection)
        # gecko polling
        self.pools = {}              # pool -> {"mint", "symbol", "last", "due", "span", "fails"}
        self.pool_of = {}            # mint -> (pool or None, ts) resolved through /tokens/{mint}/pools
        self.gecko_backoff = 0.0
        self.gecko_backoff_until = 0.0
        self.gecko_times = deque()   # timestamps of this module's GeckoTerminal requests (rolling-minute budget)
        self.gecko_stats = {"requests": 0, "ok": 0, "rate_limited": 0, "errors": 0, "skipped": 0, "trades_new": 0}
        self.started_ts = 0.0
        self.sol_price = 0.0
        self.sol_price_ts = 0.0
        self.symbols = {}            # mint -> symbol (bounded)
        # signals
        self.recent_signals = deque(maxlen=2000)
        self.seen_keys = set()
        self.seen_order = deque(maxlen=5000)
        self.last_signal_ts = 0.0
        self.signal_count = 0
        # helius
        self.ws = None
        self.ws_connected = False
        self.ws_connected_ts = 0.0
        self.ws_subs = {}            # subscription id -> wallet
        self.ws_pending = {}         # request id -> wallet (subscribe) or ("unsub", sub id)
        self.ws_wanted = set()       # wallets we want subscribed
        self.ws_reconnects = 0
        self.ws_next_id = 1
        self.ws_last_msg_ts = 0.0
        self.tx_queue = queue.Queue(maxsize=500)
        self.helius_stats = {"notifications": 0, "skipped_boring": 0, "skipped_failed": 0, "queued": 0,
                             "dropped_full": 0, "requests": 0, "credits_today": 0, "credits_total": 0,
                             "credits_day": _day_key(time.time()), "budget_skipped": 0, "swaps": 0,
                             "not_swap": 0, "tx_missing": 0, "errors": 0, "rate_limited": 0, "sub_errors": 0,
                             "last_rpc_error": None}
        self.helius_rps_times = deque()
        self.errors = deque(maxlen=20)
        self.last_error = None
        self._init_tables()
        self._load_leaders()

    # ---------------- lifecycle ----------------
    def start(self):
        try:
            if not self.enabled:
                return
            if self.threads:
                return
            self.started_ts = time.time()
            for name, fn in (("poll", self._poll_loop), ("tx", self._tx_loop), ("ws", self._ws_loop)):
                if name != "poll" and not self.key:
                    continue
                if name == "ws" and websocket is None:
                    self._err("websocket-client is not installed; live Helius signals are off")
                    continue
                t = threading.Thread(target=self._guard, args=(name, fn), name=f"traders-{name}", daemon=True)
                self.threads[name] = t
                t.start()
        except Exception as e:
            self._err(f"start failed: {e}")

    def stop(self):
        self.stop_event.set()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

    def _guard(self, name, fn):
        """Run a loop body forever; nothing it raises can kill the thread."""
        while not self.stop_event.is_set():
            try:
                fn()
            except Exception as e:
                self._err(f"{name}: {type(e).__name__}: {str(e)[:160]}")
                self.stop_event.wait(5)

    def _err(self, msg):
        if self.key:  # an exception's text can include the request URL, and the Helius URL carries the key
            msg = str(msg).replace(self.key, "***")
        self.last_error = msg
        self.errors.append((time.time(), msg))
        print(f"[traders] {msg}")

    # ---------------- storage ----------------
    def _init_tables(self):
        with self.db.lock:
            c = self.db.conn
            c.execute("""CREATE TABLE IF NOT EXISTS copy_trades(
                id INTEGER PRIMARY KEY, ts REAL, pool TEXT, mint TEXT, symbol TEXT, wallet TEXT, kind TEXT,
                usd REAL, qty REAL, price REAL, tx TEXT, source TEXT,
                UNIQUE(tx, wallet, kind, pool))""")
            c.execute("CREATE INDEX IF NOT EXISTS copy_trades_ts ON copy_trades(ts)")
            c.execute("CREATE INDEX IF NOT EXISTS copy_trades_wallet ON copy_trades(wallet, ts)")
            c.execute("""CREATE TABLE IF NOT EXISTS copy_leaders(
                rank INTEGER, wallet TEXT PRIMARY KEY, stats TEXT, computed_ts REAL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS copy_signals(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, wallet TEXT, rank INTEGER, side TEXT, mint TEXT,
                symbol TEXT, usd REAL, source TEXT, tx TEXT)""")
            c.execute("CREATE INDEX IF NOT EXISTS copy_signals_ts ON copy_signals(ts)")
            c.execute("CREATE TABLE IF NOT EXISTS copy_banned(wallet TEXT PRIMARY KEY, reason TEXT, ts REAL)")
            c.commit()

    def _load_leaders(self):
        """A restart shows the last ranking right away; the poll thread recomputes it from stored trades."""
        try:
            with self.db.lock:
                rows = self.db.conn.execute("SELECT rank, stats, computed_ts FROM copy_leaders ORDER BY rank").fetchall()
                bans = self.db.conn.execute("SELECT wallet, reason FROM copy_banned WHERE ts >= ?",
                                            (time.time() - KEEP_DAYS * 86400,)).fetchall()
            self.banned = {r["wallet"]: r["reason"] for r in bans}
            leaders = []
            for r in rows:
                st = json.loads(r["stats"])
                st["rank"] = r["rank"]
                leaders.append(st)
                self.last_rank_ts = max(self.last_rank_ts, r["computed_ts"] or 0)
            with self.lock:
                self.leaders = leaders
                self.leader_set = {s["wallet"]: s["rank"] for s in leaders}
                self.ws_wanted = set(s["wallet"] for s in leaders[:HELIUS_WATCH])
            with self.db.lock:
                row = self.db.conn.execute("SELECT COALESCE(MAX(id), 0) n FROM copy_signals").fetchone()
                recent = self.db.conn.execute(
                    "SELECT id, ts, wallet, rank, side, mint, symbol, usd, source, tx FROM copy_signals "
                    "ORDER BY id DESC LIMIT 200").fetchall()
            self.signal_count = row["n"] if row else 0
            with self.lock:
                for r in reversed(recent):
                    sig = dict(r)
                    self.recent_signals.append(sig)
                    self.seen_keys.add((sig["tx"] or f"{sig['wallet']}:{sig['ts']}", sig["wallet"], sig["side"], sig["mint"]))
                    self.last_signal_ts = max(self.last_signal_ts, sig["ts"] or 0)
        except Exception as e:
            self._err(f"loading saved leaders failed: {e}")

    def _store_trades(self, rows):
        """Insert trade rows (dicts), ignoring duplicates. Returns the rows that were new."""
        if not rows:
            return []
        new = []
        with self.db.lock:
            c = self.db.conn
            for r in rows:
                cur = c.execute(
                    "INSERT OR IGNORE INTO copy_trades(ts,pool,mint,symbol,wallet,kind,usd,qty,price,tx,source) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (r["ts"], r.get("pool"), r["mint"], r.get("symbol"), r["wallet"], r["kind"], r["usd"],
                     r.get("qty"), r.get("price"), r.get("tx"), r.get("source", "gecko")))
                if cur.rowcount:
                    new.append(r)
            c.commit()
        return new

    def _load_trades(self, since):
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT ts, mint, wallet, kind, usd, qty, price, symbol FROM copy_trades WHERE ts >= ?", (since,)).fetchall()
        return [dict(r) for r in rows]

    def _cleanup(self, now):
        with self.db.lock:
            c = self.db.conn
            c.execute("DELETE FROM copy_trades WHERE ts < ?", (now - KEEP_DAYS * 86400,))
            c.execute("DELETE FROM copy_signals WHERE ts < ?", (now - 2 * 86400,))
            c.commit()

    # ---------------- ranking ----------------
    def rank_now(self):
        """Score every stored trade in the window and replace the leaderboard. Safe to call from anywhere."""
        now = time.time()
        trades = self._load_trades(now - WINDOW_H * 3600)
        prices = {}
        try:
            for t in self.market.candidates():
                if t.get("address") and t.get("price"):
                    prices[t["address"]] = (float(t["price"]), now)
                    self._remember_symbol(t["address"], t.get("symbol"))
        except Exception:
            pass
        for r in trades:
            if r.get("symbol"):
                self._remember_symbol(r["mint"], r["symbol"])
        stats = score_wallets(trades, now, prices)
        leaders = rank_wallets(stats, self.top_n * 2 if self.key else self.top_n, self.banned)
        if self.key:  # on-chain activity check: pool feeds only show a slice of what a wallet does
            checked = 0
            for s in leaders:
                if checked >= 2 * self.top_n or self.stop_event.is_set():
                    break
                a = self.activity.get(s["wallet"])
                if a and now - a[1] < 6 * 3600:
                    s["tx_per_min"] = a[0]
                    continue
                rate = self._tx_rate(s["wallet"])
                checked += 1
                if rate is None:
                    continue
                self.activity[s["wallet"]] = (rate, now)
                s["tx_per_min"] = rate
                if rate > MAX_TX_PER_MIN:
                    self._ban(s["wallet"], f"{rate:.0f} tx/min on-chain", resync=False)
            if len(self.activity) > 5000:
                self.activity = {w: a for w, a in self.activity.items() if now - a[1] < 6 * 3600}
            leaders = [s for s in leaders if s["wallet"] not in self.banned][:self.top_n]
            for i, s in enumerate(leaders, 1):
                s["rank"] = i
        reasons = {}
        for s in stats.values():
            why = human_reason(s, self.banned)
            if why:
                key = why.split(" (")[0]
                if key.startswith("banned"):
                    key = "banned (on-chain tx rate)"
                for k in ("trades in the window", "round trips flipped", "same-block"):
                    if k in why:
                        key = {"trades in the window": "too many trades", "round trips flipped": "flipper (MEV)",
                               "same-block": "same-block (sandwich)"}[k]
                reasons[key] = reasons.get(key, 0) + 1
        with self.lock:
            self.leaders = leaders
            self.leader_set = {s["wallet"]: s["rank"] for s in leaders}
            self.ws_wanted = set(s["wallet"] for s in leaders[:HELIUS_WATCH])
            self.last_rank_ts = now
            self.filtered = reasons
            self.rank_note = f"{len(trades)} trades, {len(stats)} wallets scored, {len(leaders)} ranked"
        try:
            with self.db.lock:
                c = self.db.conn
                c.execute("DELETE FROM copy_leaders")
                c.executemany("INSERT INTO copy_leaders(rank, wallet, stats, computed_ts) VALUES(?,?,?,?)",
                              [(s["rank"], s["wallet"], json.dumps(s), now) for s in leaders])
                c.commit()
        except Exception as e:
            self._err(f"saving leaders failed: {e}")
        print(f"[traders] ranked: {self.rank_note}")
        return leaders

    def _tx_rate(self, wallet):
        """Transactions per minute over the wallet's last 50 signatures (1 Helius credit), or None on failure."""
        res, err = self._rpc("getSignaturesForAddress", [wallet, {"limit": 50, "commitment": "confirmed"}])
        if not isinstance(res, list) or not res:
            return None if err or res is None else 0.0
        times = sorted(s.get("blockTime") or 0 for s in res if s.get("blockTime"))
        if len(times) < 2:
            return 0.0
        span = max(1.0, times[-1] - times[0])
        if len(res) < 50 and span < 3600:
            span = 3600.0  # fewer than 50 transactions ever seen in an hour: not a flood whatever the spacing
        return round((len(times) - 1) / (span / 60.0), 2)

    def _ban(self, wallet, reason, resync=True):
        """Exclude a wallet found to be automated at run time: leaderboard, websocket, queue."""
        with self.lock:
            if wallet in self.banned:
                return
            self.banned[wallet] = reason
            self.leaders = [s for s in self.leaders if s["wallet"] != wallet]
            for i, s in enumerate(self.leaders, 1):
                s["rank"] = i
            self.leader_set = {s["wallet"]: s["rank"] for s in self.leaders}
            self.ws_wanted.discard(wallet)
            self.ws_rate.pop(wallet, None)
        print(f"[traders] banned {wallet[:8]}…: {reason}")
        try:
            with self.db.lock:
                self.db.conn.execute("INSERT OR REPLACE INTO copy_banned(wallet, reason, ts) VALUES(?,?,?)",
                                     (wallet, reason, time.time()))
                self.db.conn.execute("DELETE FROM copy_leaders WHERE wallet=?", (wallet,))
                self.db.conn.commit()
        except Exception as e:
            self._err(f"saving ban failed: {e}")
        if resync:
            self._ws_resync_if_connected()

    def _remember_symbol(self, mint, symbol):
        if mint and symbol and mint not in self.symbols:
            if len(self.symbols) > 5000:
                self.symbols.clear()
            self.symbols[mint] = str(symbol)[:16]

    def _symbol(self, mint):
        try:
            t = self.market.get(mint)
            if t and t.get("symbol"):
                return t["symbol"]
        except Exception:
            pass
        return self.symbols.get(mint) or (mint[:4] + "…" + mint[-4:] if mint else "?")

    # ---------------- public reads ----------------
    def top(self):
        with self.lock:
            return [dict(s) for s in self.leaders]

    def signals(self, since_ts=0):
        try:
            since_ts = float(since_ts or 0)
        except (TypeError, ValueError):
            since_ts = 0.0
        with self.lock:
            out = [dict(s) for s in self.recent_signals if s["ts"] > since_ts]
        if not out and since_ts > 0:
            try:  # older than the in-memory window (restart): read the table
                with self.db.lock:
                    rows = self.db.conn.execute(
                        "SELECT * FROM copy_signals WHERE ts > ? ORDER BY id LIMIT 500", (since_ts,)).fetchall()
                out = [dict(r) for r in rows]
            except Exception:
                out = []
        out.sort(key=lambda s: s["id"])
        return out[-500:]

    def status(self):
        now = time.time()
        with self.lock:
            leaders, wanted, subs = len(self.leaders), len(self.ws_wanted), len(self.ws_subs)
            pending = len(self.ws_pending)
            last_sig, nsig, note, filtered = self.last_signal_ts, self.signal_count, self.rank_note, dict(self.filtered)
        helius = {k: v for k, v in self.helius_stats.items() if k != "credits_day"}
        helius.update(enabled=bool(self.key) and websocket is not None, connected=self.ws_connected,
                      connected_since=self.ws_connected_ts or None, subscribed=subs, pending=pending,
                      wallets_wanted=wanted, reconnects=self.ws_reconnects, last_message_ts=self.ws_last_msg_ts or None,
                      queue=self.tx_queue.qsize(), budget_per_day=HELIUS_PER_DAY)
        return {
            "enabled": self.enabled,
            "running": {n: t.is_alive() for n, t in self.threads.items()},
            "mode": ("helius" if helius["connected"] else "gecko") if self.enabled else "off",
            "leaders": leaders, "top_n": self.top_n, "wallets_watched": subs,
            "last_rank_ts": self.last_rank_ts or None,
            "next_rank_ts": (self.last_rank_ts + (min(RANK_SECS, 600) if (now - self.started_ts < 3600 or not leaders) else RANK_SECS))
                            if self.last_rank_ts else None,   # same schedule as _poll_loop: every 10 min while young or empty
            "rank_note": note, "filtered": filtered, "banned": len(self.banned),
            "gecko": {**self.gecko_stats, "pools": len(self.pools), "per_min": GECKO_PER_MIN,
                      "paused_for": round(max(0.0, self.gecko_backoff_until - now))},
            "helius": helius,
            "signals": nsig, "last_signal_ts": last_sig or None,
            "sol_price": round(self.sol_price, 2) if self.sol_price else None,
            "last_error": self.last_error,
            "errors": [{"ts": ts, "msg": m} for ts, m in list(self.errors)[-5:]],
        }

    # ---------------- GeckoTerminal polling ----------------
    def _gecko_get(self, path):
        now = time.time()
        pause_until = max(self.gecko_backoff_until, _f(getattr(self.market, "gecko_backoff_until", 0)))
        if now < pause_until:
            self.gecko_stats["skipped"] += 1
            return None, "paused"
        while self.gecko_times and now - self.gecko_times[0] > 60:
            self.gecko_times.popleft()
        if len(self.gecko_times) >= GECKO_PER_MIN:  # whatever the path, never more than the budget per minute
            self.gecko_stats["skipped"] += 1
            return None, "paused"
        self.gecko_times.append(now)
        self.gecko_stats["requests"] += 1
        try:
            r = self.s.get(GECKO + path, headers=GECKO_HEADERS, timeout=15)
        except Exception as e:
            self.gecko_stats["errors"] += 1
            return None, f"error {str(e)[:80]}"
        if r.status_code == 429:
            self.gecko_stats["rate_limited"] += 1
            self.gecko_backoff = min(600.0, self.gecko_backoff * 2 if self.gecko_backoff else 60.0)
            pause = max(self.gecko_backoff, _f(r.headers.get("Retry-After")))
            self.gecko_backoff_until = now + pause
            self._err(f"GeckoTerminal rate limit, pausing trade polling {pause:.0f}s")
            return None, "429"
        if r.status_code == 404:
            self.gecko_stats["errors"] += 1
            return None, "404"
        try:
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            self.gecko_stats["errors"] += 1
            return None, f"error {str(e)[:80]}"
        self.gecko_backoff = 0.0
        self.gecko_stats["ok"] += 1
        return data, "ok"

    def _resolve_pool(self, mint):
        """Deepest GeckoTerminal pool for a token when the market has no pair address (cached an hour)."""
        hit = self.pool_of.get(mint)
        now = time.time()
        if hit and now - hit[1] < 3600:
            return hit[0]
        data, status = self._gecko_get(f"/networks/solana/tokens/{mint}/pools?page=1")
        if status == "paused":
            return hit[0] if hit else None
        best, best_liq = None, -1.0
        for p in (data or {}).get("data") or [] if isinstance(data, dict) else []:
            attrs = p.get("attributes") or {}
            liq = _f(attrs.get("reserve_in_usd"))
            if attrs.get("address") and liq > best_liq:
                best, best_liq = attrs["address"], liq
        if len(self.pool_of) > 2000:
            self.pool_of.clear()
        self.pool_of[mint] = (best, now)
        return best

    def _sync_pools(self):
        """Keep self.pools in step with the tokens the market tracks."""
        try:
            cands = list(self.market.candidates())
        except Exception as e:
            self._err(f"market.candidates failed: {e}")
            return
        wanted = {}
        resolves = 0
        for t in cands:
            mint = t.get("address")
            if not mint or mint in QUOTES:
                continue
            pool = t.get("pair")
            if not pool:
                hit = self.pool_of.get(mint)
                if hit and time.time() - hit[1] < 3600:
                    pool = hit[0]
                elif resolves < 2:  # at most two lookups per sync (every 30 s) so a pair-less market can't burst
                    resolves += 1
                    pool = self._resolve_pool(mint)
            if pool:
                wanted[pool] = (mint, t.get("symbol") or "?")
                self._remember_symbol(mint, t.get("symbol"))
        now = time.time()
        for pool, (mint, sym) in wanted.items():
            p = self.pools.get(pool)
            if p is None:
                self.pools[pool] = {"mint": mint, "symbol": sym, "last": 0.0, "due": now, "span": None, "fails": 0}
            else:
                p["mint"], p["symbol"] = mint, sym
        for pool in list(self.pools):
            if pool not in wanted:
                del self.pools[pool]

    def _poll_pool(self, pool, now):
        p = self.pools[pool]
        mint = p["mint"]
        data, status = self._gecko_get(f"/networks/solana/pools/{pool}/trades?trade_volume_in_usd_greater_than={MIN_TRADE_USD:g}")
        p["last"] = now
        if status == "paused":
            p["due"] = now + 30
            return
        if data is None:
            p["fails"] += 1
            p["due"] = now + min(1800, 120 * p["fails"])
            if status == "404":  # the market's pair is not a pool GeckoTerminal knows: try its own listing next time
                alt = self._resolve_pool(mint)
                if alt and alt != pool and alt not in self.pools:
                    self.pools[alt] = {"mint": mint, "symbol": p["symbol"], "last": 0.0, "due": now, "span": None, "fails": 0}
            return
        p["fails"] = 0
        rows = []
        oldest = newest = None
        for tr in (data.get("data") or []) if isinstance(data, dict) else []:
            a = tr.get("attributes") or {}
            ts = _iso_ts(a.get("block_timestamp"))
            if not ts:
                continue
            oldest = ts if oldest is None else min(oldest, ts)
            newest = ts if newest is None else max(newest, ts)
            frm, to = a.get("from_token_address"), a.get("to_token_address")
            if frm == SOL_MINT:
                self._note_sol(_f(a.get("price_from_in_usd")), ts)
            elif to == SOL_MINT:
                self._note_sol(_f(a.get("price_to_in_usd")), ts)
            if to == mint:
                kind, qty, price = "buy", _f(a.get("to_token_amount")), _f(a.get("price_to_in_usd"))
            elif frm == mint:
                kind, qty, price = "sell", _f(a.get("from_token_amount")), _f(a.get("price_from_in_usd"))
            else:
                continue
            usd = _f(a.get("volume_in_usd"))
            wallet = a.get("tx_from_address")
            if not wallet or usd < MIN_TRADE_USD:
                continue
            rows.append({"ts": ts, "pool": pool, "mint": mint, "symbol": p["symbol"], "wallet": wallet, "kind": kind,
                         "usd": round(usd, 4), "qty": qty, "price": price, "tx": a.get("tx_hash"), "source": "gecko"})
        new = self._store_trades(rows)
        self.gecko_stats["trades_new"] += len(new)
        # Busy pools (300 trades cover a short span) are revisited sooner so nothing falls out of the window.
        n_pools = max(1, len(self.pools))
        base = max(60.0, n_pools * 60.0 / GECKO_PER_MIN)
        span = (newest - oldest) if (oldest is not None and newest is not None and newest > oldest) else None
        p["span"] = span
        if span is not None and span < base:
            p["due"] = now + max(30.0, span * 0.7)
        else:
            p["due"] = now + base
        # fresh trades of ranked wallets become signals when Helius is not covering that wallet
        with self.lock:
            ranks = dict(self.leader_set)
            live = self.ws_connected and bool(self.ws_subs)
            covered = set(self.ws_subs.values()) if live else set()
        for r in new:
            rank = ranks.get(r["wallet"])
            if rank and now - r["ts"] <= SIGNAL_MAX_AGE and r["wallet"] not in covered:
                self._emit_signal(r["ts"], r["wallet"], rank, r["kind"], mint, r["symbol"], r["usd"], "gecko", r["tx"])

    def _note_sol(self, price, ts):
        if price > 0 and ts >= self.sol_price_ts:
            self.sol_price, self.sol_price_ts = price, ts

    def _poll_loop(self):
        interval = 60.0 / GECKO_PER_MIN
        try:
            self.rank_now()
        except Exception as e:
            self._err(f"startup ranking failed: {e}")
        last_sync = 0.0
        last_clean = 0.0
        while not self.stop_event.is_set():
            now = time.time()
            if now - last_sync >= 30:
                last_sync = now
                self._sync_pools()
            # A fresh database has nothing to rank for the first hour otherwise: rank every 10 minutes during
            # the first hour after start (and while the board is empty), hourly after that.
            young = now - self.started_ts < 3600 or not self.leaders
            if now - self.last_rank_ts >= (min(RANK_SECS, 600) if young else RANK_SECS):
                self.rank_now()
                self._ws_resync_if_connected()
            if now - last_clean >= 6 * 3600:
                last_clean = now
                try:
                    self._cleanup(now)
                except Exception as e:
                    self._err(f"cleanup failed: {e}")
            due = [pool for pool, p in self.pools.items() if p["due"] <= now]
            if due:
                pool = min(due, key=lambda k: self.pools[k]["due"])
                if pool in self.pools:
                    self._poll_pool(pool, now)
            self.stop_event.wait(interval)

    # ---------------- signals ----------------
    def _emit_signal(self, ts, wallet, rank, side, mint, symbol, usd, source, tx):
        key = (tx or f"{wallet}:{ts}", wallet, side, mint)
        with self.lock:
            if key in self.seen_keys:
                return None
            if len(self.seen_order) == self.seen_order.maxlen:
                old = self.seen_order[0]
                self.seen_keys.discard(old)
            self.seen_order.append(key)
            self.seen_keys.add(key)
        try:
            with self.db.lock:
                cur = self.db.conn.execute(
                    "INSERT INTO copy_signals(ts, wallet, rank, side, mint, symbol, usd, source, tx) VALUES(?,?,?,?,?,?,?,?,?)",
                    (ts, wallet, rank, side, mint, symbol, usd, source, tx))
                sid = cur.lastrowid
                self.db.conn.commit()
        except Exception as e:
            self._err(f"saving signal failed: {e}")
            with self.lock:
                self.signal_count += 1
                sid = self.signal_count
        sig = {"id": sid, "ts": ts, "wallet": wallet, "rank": rank, "side": side, "mint": mint, "symbol": symbol,
               "usd": round(usd, 2), "source": source, "tx": tx}
        with self.lock:
            self.recent_signals.append(sig)
            self.signal_count = max(self.signal_count, sid)
            self.last_signal_ts = max(self.last_signal_ts, ts)
        print(f"[traders] signal #{sid} {source}: #{rank} {wallet[:6]}… {side} ${usd:,.0f} {symbol}")
        return sig

    # ---------------- Helius websocket ----------------
    def _ws_loop(self):
        delay = 5.0
        while not self.stop_event.is_set():
            self.ws_connected = False
            with self.lock:
                self.ws_subs.clear()
                self.ws_pending.clear()
            app = websocket.WebSocketApp(HELIUS_WS.format(key=self.key), on_open=self._ws_open,
                                         on_message=self._ws_message, on_error=self._ws_error, on_close=self._ws_close)
            self.ws = app
            started = time.time()
            try:
                app.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                self._err(f"websocket: {str(e)[:120]}")
            self.ws_connected = False
            if self.stop_event.is_set():
                break
            self.ws_reconnects += 1
            delay = 5.0 if time.time() - started > 300 else min(300.0, delay * 2)
            self.stop_event.wait(delay)

    def _ws_send(self, ws, method, params, tag):
        with self.lock:
            rid = self.ws_next_id
            self.ws_next_id += 1
            self.ws_pending[rid] = tag
        ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}))

    def _ws_open(self, ws):
        self.ws_connected = True
        self.ws_connected_ts = time.time()
        print("[traders] Helius websocket connected")
        self._ws_resync(ws)

    def _ws_resync_if_connected(self):
        ws = self.ws
        if ws is not None and self.ws_connected:
            try:
                self._ws_resync(ws)
            except Exception as e:
                self._err(f"websocket resync failed: {str(e)[:80]}")

    def _ws_resync(self, ws):
        """Subscribe to wanted wallets that aren't yet, unsubscribe the ones that fell off the list."""
        with self.lock:
            have = set(self.ws_subs.values()) | {t for t in self.ws_pending.values() if isinstance(t, str)}
            add = [w for w in self.ws_wanted if w not in have]
            drop = [(sid, w) for sid, w in self.ws_subs.items() if w not in self.ws_wanted]
        for sid, w in drop:
            try:
                self._ws_send(ws, "logsUnsubscribe", [sid], ("unsub", sid))
            except Exception as e:
                self._err(f"unsubscribe failed: {str(e)[:80]}")
        for w in add:
            try:
                self._ws_send(ws, "logsSubscribe", [{"mentions": [w]}, {"commitment": "confirmed"}], w)
            except Exception as e:
                self._err(f"subscribe failed: {str(e)[:80]}")
                break

    def _ws_message(self, ws, raw):
        self.ws_last_msg_ts = time.time()
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        if "id" in msg and msg.get("method") is None:
            with self.lock:
                tag = self.ws_pending.pop(msg["id"], None)
                if tag is None:
                    return
                if "error" in msg:
                    self.helius_stats["sub_errors"] += 1
                    err = msg["error"]
                    self._err(f"Helius {'unsubscribe' if isinstance(tag, tuple) else 'subscribe'} error: {str(err)[:120]}")
                    return
                if isinstance(tag, tuple):
                    self.ws_subs.pop(tag[1], None)
                else:
                    self.ws_subs[msg.get("result")] = tag
            return
        if msg.get("method") != "logsNotification":
            return
        params = msg.get("params") or {}
        with self.lock:
            wallet = self.ws_subs.get(params.get("subscription"))
        if not wallet:
            return
        value = ((params.get("result") or {}).get("value")) or {}
        self.helius_stats["notifications"] += 1
        now = time.time()
        with self.lock:
            if wallet in self.banned:
                return
            d = self.ws_rate.setdefault(wallet, deque(maxlen=64))
            d.append(now)
            flood = len(d) >= 2 * MAX_TX_PER_MIN and now - d[0] <= 60
        if flood:
            self._ban(wallet, f"{len(d)} transactions in {now - d[0]:.0f}s (flood)")
            return
        if value.get("err") is not None:
            self.helius_stats["skipped_failed"] += 1
            return
        if not logs_look_like_swap(value.get("logs")):
            self.helius_stats["skipped_boring"] += 1
            return
        sig = value.get("signature")
        if not sig:
            return
        try:
            self.tx_queue.put_nowait((time.time(), wallet, sig, 0))
            self.helius_stats["queued"] += 1
        except queue.Full:
            self.helius_stats["dropped_full"] += 1

    def _ws_error(self, ws, err):
        self.helius_stats["errors"] += 1
        self._err(f"Helius websocket error: {str(err)[:120]}")

    def _ws_close(self, ws, code, reason):
        self.ws_connected = False
        print(f"[traders] Helius websocket closed ({code} {str(reason)[:60]})")

    # ---------------- Helius transaction fetching ----------------
    def _spend(self, credits=1):
        """Count credits against today's budget. False when the budget is spent."""
        day = _day_key(time.time())
        st = self.helius_stats
        if st["credits_day"] != day:
            st["credits_day"], st["credits_today"] = day, 0
        if st["credits_today"] + credits > HELIUS_PER_DAY:
            st["budget_skipped"] += 1
            return False
        st["credits_today"] += credits
        st["credits_total"] += credits
        return True

    def _rpc(self, method, params, timeout=20):
        """One Helius RPC call under the per-second limit. Returns (result, error_string)."""
        now = time.time()
        while self.helius_rps_times and now - self.helius_rps_times[0] > 1.0:
            self.helius_rps_times.popleft()
        if len(self.helius_rps_times) >= HELIUS_RPS:
            wait = 1.0 - (now - self.helius_rps_times[0])
            if wait > 0:
                time.sleep(wait)
        self.helius_rps_times.append(time.time())
        if not self._spend(1):
            return None, "budget"
        self.helius_stats["requests"] += 1
        try:
            r = self.s.post(HELIUS_RPC.format(key=self.key),
                            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=timeout)
        except Exception as e:
            self.helius_stats["errors"] += 1
            return None, f"{type(e).__name__}"
        if r.status_code == 429:
            self.helius_stats["rate_limited"] += 1
            time.sleep(2)
            return None, "429"
        try:
            data = r.json()
        except ValueError:
            self.helius_stats["errors"] += 1
            self.helius_stats["last_rpc_error"] = f"http {r.status_code}: {r.text[:120]}"
            return None, f"http {r.status_code}"
        if data.get("error"):
            self.helius_stats["errors"] += 1
            self.helius_stats["last_rpc_error"] = str(data["error"])[:160]
            return None, str(data["error"])[:120]
        return data.get("result"), None

    def fetch_transaction(self, signature):
        return self._rpc("getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0,
                                                           "commitment": "confirmed"}])

    def _sol_usd(self):
        try:
            t = self.market.get(SOL_MINT)
            if t and t.get("price"):
                return float(t["price"])
        except Exception:
            pass
        return self.sol_price if time.time() - self.sol_price_ts < 6 * 3600 else 0.0

    def handle_transaction(self, tx, wallet, source="helius"):
        """Parse a fetched transaction for `wallet`, store its swaps, emit signals, ask the market to track new
        buys. Returns the swaps found."""
        swaps = parse_swap(tx, wallet, self._sol_usd())
        if not swaps:
            self.helius_stats["not_swap"] += 1
            return []
        ts = float(tx.get("blockTime") or time.time())
        sig = ((tx.get("transaction") or {}).get("signatures") or [None])[0]
        with self.lock:
            rank = self.leader_set.get(wallet)
        rows = []
        for sw in swaps:
            price = sw["usd"] / sw["qty"] if sw["qty"] else None
            symbol = self._symbol(sw["mint"])
            rows.append({"ts": ts, "pool": None, "mint": sw["mint"], "symbol": symbol, "wallet": wallet, "kind": sw["side"],
                         "usd": sw["usd"], "qty": sw["qty"], "price": price, "tx": sig, "source": source})
        self._store_trades(rows)
        self.helius_stats["swaps"] += len(swaps)
        for sw, r in zip(swaps, rows):
            self._emit_signal(ts, wallet, rank or 0, sw["side"], sw["mint"], r["symbol"], sw["usd"], source, sig)
            if sw["side"] == "buy":
                self._track(sw["mint"])
        return swaps

    def _track(self, mint):
        try:
            if self.market.get(mint) is not None:
                return
        except Exception:
            pass
        fn = getattr(self.market, "track", None)
        if callable(fn):
            try:
                fn(mint, source="copy")
            except Exception as e:
                self._err(f"market.track failed: {str(e)[:80]}")

    def _tx_loop(self):
        while not self.stop_event.is_set():
            try:
                queued_ts, wallet, sig, tries = self.tx_queue.get(timeout=1)
            except queue.Empty:
                continue
            if time.time() - queued_ts > 600 or wallet in self.banned:
                continue  # too old to copy, or a wallet banned since: don't spend a credit on it
            tx, err = self.fetch_transaction(sig)
            if err == "budget":
                continue
            if tx is None:
                if err is None and tries < 2:  # not indexed yet at confirmed: try again shortly
                    time.sleep(2)
                    try:
                        self.tx_queue.put_nowait((queued_ts, wallet, sig, tries + 1))
                    except queue.Full:
                        self.helius_stats["dropped_full"] += 1
                    continue
                if err is None:
                    self.helius_stats["tx_missing"] += 1
                continue
            self.handle_transaction(tx, wallet)

    def recent_signatures(self, wallet, limit=10):
        """Recent signatures of a wallet (1 credit). Used by tests and the dashboard's 'verify' action."""
        res, err = self._rpc("getSignaturesForAddress", [wallet, {"limit": limit, "commitment": "confirmed"}])
        return [s["signature"] for s in res or [] if not s.get("err")] if res else []
