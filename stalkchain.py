"""StalkChain Data (https://data.stalkchain.com): a paid REST API the arena uses for two things.

1. A pre-buy check on a Claude's buy of a coin it has not checked yet (arena.Arena.validate): who deployed the coin and
   how many of that wallet's earlier launches died (stalkchain_token_deployer, 500 credits), and who the first buyers
   were, how much was sniped or bundled and whether they already sold (stalkchain_token_early_buyers, 500 credits).
   A deployer with a rug history is a veto; heavy sniping or a bundled launch is a flag (signals.stalkchain_verdict).
2. Smart-money entries: every ENTRIES_MIN minutes, the tokens several tracked traders bought in the last hour
   (stalkchain_fomo_multi_trader_entries, 125 credits), shown to the Claudes as smart_entries and force-tracked.

Everything is inert without ARENA_STALKCHAIN_KEY: shared() returns None and nothing calls the network. The response
schemas in the OpenAPI spec are only "{ data, notes?, credits, meta }", so every parser here is defensive: it looks
for the field names the tool descriptions imply, never raises, and returns stable keys with None for what it can't find.

Settings (environment variables, read once at import; main.py loads .env first):
  ARENA_STALKCHAIN_KEY=            the API key (sc_...). Empty = off.
  ARENA_STALKCHAIN_CACHE_H=6       a per-mint lookup is reused for this many hours (no second charge)
  ARENA_STALKCHAIN_DAILY_CREDITS=12000   rolling 24 hour credit budget; past it, paid calls return None (stats "skipped").
                                   Starter = 375,000 credits a month ~ 12,500 a day.
  ARENA_STALKCHAIN_PREBUY=deployer,early_buyers   the pre-buy lookups (also: quality, 250 credits)
  ARENA_STALKCHAIN_RUG_VETO=2      veto a buy when the deployer's earlier launches include this many dead/rugged ones
                                   (or at least half of 2+ launches)
  ARENA_STALKCHAIN_ENTRIES_MIN=30  minutes between smart-money entry polls (0 = off); 48 polls a day = 6,000 credits

Client(key, base=BASE, timeout=4.0, session=None, clock=time.time)
  call(name, **params) -> dict | None   GET /tools/{name}?params. Never raises. None on a timeout, an HTTP error, a
      non-JSON body, an exhausted budget (stats["skipped"]), a bad key (401: logged once, the client stops calling) or
      no paid plan (402, or an error naming the plan / credits: self.paywalled = True, logged once, paid calls are
      skipped for PAYWALL_RETRY_SECS). Any other failure backs paid calls off for ERROR_BACKOFF_SECS, so a down API
      can't add 4 s to every tick. Calls carrying a `token` are cached per (tool, params) for CACHE_H hours.
      Credits are read from the response's `credits` block (cost and balance), falling back to TOOL_CREDITS.
  deployer(mint), early_buyers(mint, limit=20), quality(mint), multi_trader_entries(**kw), account(), health()
  stats: {"calls", "credits", "cached", "skipped", "errors", "balance", "credits_24h", "paywalled"}
Pure helpers (no network): summarize_deployer, summarize_early_buyers, summarize_quality, summarize_entries.
"""
import os
import re
import threading
import time
from collections import deque

import requests

BASE = "https://data.stalkchain.com/api/v1"


def _env_f(name, default):
    try:
        v = float(os.environ.get(name, "") or default)
        return v if v == v else float(default)
    except ValueError:
        return float(default)


KEY = (os.environ.get("ARENA_STALKCHAIN_KEY") or "").strip()
CACHE_H = max(0.0, _env_f("ARENA_STALKCHAIN_CACHE_H", 6))
DAILY_CREDITS = max(0.0, _env_f("ARENA_STALKCHAIN_DAILY_CREDITS", 12000))
PREBUY = [x.strip().lower() for x in (os.environ.get("ARENA_STALKCHAIN_PREBUY", "deployer,early_buyers") or "").split(",")
          if x.strip().lower() in ("deployer", "early_buyers", "quality")]
RUG_VETO = max(1, int(_env_f("ARENA_STALKCHAIN_RUG_VETO", 2)))
ENTRIES_MIN = max(0.0, _env_f("ARENA_STALKCHAIN_ENTRIES_MIN", 30))
SNIPED_FLAG_PCT = 40.0     # sniped share of supply that earns a flag (not a veto)
BUNDLE_FLAG_PCT = 10.0     # bundle share of supply that counts as "bundled" when no explicit flag is given
DEAD_MCAP_USD = 6000.0     # an earlier launch under this market cap that never graduated is dead (pump.fun starts ~$4-5k)
DEAD_LIQ_USD = 1000.0      # ...or under this much liquidity
ERROR_BACKOFF_SECS = 60.0
PAYWALL_RETRY_SECS = 3600.0

TOOL_CREDITS = {"stalkchain_token_deployer": 500, "stalkchain_token_early_buyers": 500, "stalkchain_token_quality": 250,
                "stalkchain_fomo_multi_trader_entries": 125, "stalkchain_account": 0, "stalkchain_health": 0}
FREE = {n for n, c in TOOL_CREDITS.items() if c == 0}
_PAYWALL = re.compile(r"\bplans?\b|out of credits|insufficient credits|no credits", re.I)


def _num(x):
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _data(raw):
    """The `data` part of a response envelope (or the dict itself when there is no envelope)."""
    if not isinstance(raw, dict):
        return {}
    d = raw.get("data", raw)
    return d if isinstance(d, (dict, list)) else {}


def _norm(k):
    return "".join(c for c in str(k).lower() if c.isalnum())


def _pick(d, *names):
    """The first value in dict `d` whose key matches one of `names` (case, '_' and '-' ignored)."""
    if not isinstance(d, dict):
        return None
    want = [_norm(n) for n in names]
    keys = {_norm(k): k for k in d}
    for w in want:
        if w in keys and d[keys[w]] is not None:
            return d[keys[w]]
    return None


def _pct(d, pct_names=(), share_names=()):
    """A percentage from `d`: a key named like a percent is taken as is, a share/ratio (0-1) is scaled to 0-100."""
    v = _num(_pick(d, *pct_names))
    if v is not None:
        return v
    v = _num(_pick(d, *share_names))
    if v is not None:
        return v * 100 if v <= 1 else v
    return None


def _list(d, *names):
    """The first list of dicts under one of `names` in `d` (or `d` itself when it is such a list)."""
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)]
    v = _pick(d, *names)
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]
    if isinstance(v, dict):  # {"items": [...]} one level down
        return _list(v, "items", "list", "results", "tokens")
    return None


def _truthy(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return x > 0
    if isinstance(x, str):
        return x.strip().lower() in ("true", "yes", "1", "rugged", "dead", "sold", "exited")
    return False


def _ts(x):
    """Epoch seconds from epoch seconds / milliseconds or an ISO-8601 string; None otherwise."""
    v = _num(x)
    if v is not None:
        return v / 1000 if v > 1e11 else v
    if isinstance(x, str) and x:
        try:
            from datetime import datetime
            return datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------------------------------- summaries
def summarize_deployer(raw, mint=None):
    """{"deployer", "launched", "rugged", "graduated", "rug_rate"} from a stalkchain_token_deployer response.
    launched / rugged / graduated count the deployer's EARLIER launches (`mint` itself left out). A launch counts as
    rugged when the API marks it rugged / dead, or when it never graduated and now sits under DEAD_MCAP_USD market cap
    or DEAD_LIQ_USD liquidity; launches with no numbers are counted as launched but not judged. Explicit totals the
    API gives (rugCount, launchCount, graduatedCount ...) win over counting. rug_rate = rugged / launched."""
    d = _data(raw)
    d = d if isinstance(d, dict) else ({"launches": d} if d else {})
    dep = _pick(d, "deployer", "deployerWallet", "deployer_address", "creator", "wallet", "owner")
    if isinstance(dep, dict):
        dep = _pick(dep, "address", "wallet", "deployer", "id")
    launches = _list(d, "launches", "tokens", "otherTokens", "other_tokens", "launched", "deployedTokens", "items")
    if launches is None and isinstance(_pick(d, "deployer"), dict):
        launches = _list(_pick(d, "deployer"), "launches", "tokens")
    launched = rugged = graduated = None
    if launches is not None:
        prior = [t for t in launches if not mint or _pick(t, "mint", "address", "token", "tokenAddress") != mint]
        launched, rugged, graduated = len(prior), 0, 0
        for t in prior:
            grad = _truthy(_pick(t, "graduated", "isGraduated", "migrated", "complete"))
            graduated += grad
            flag = _pick(t, "rugged", "isRugged", "rug", "dead", "isDead")
            status = str(_pick(t, "status", "state") or "").lower()
            if _truthy(flag) or status in ("rugged", "dead", "rug"):
                rugged += 1
                continue
            if grad:
                continue
            mc = _num(_pick(t, "marketCap", "market_cap", "mcap", "marketCapUsd", "fdv"))
            liq = _num(_pick(t, "liquidity", "liquidityUsd", "liquidity_usd", "liq"))
            if isinstance(_pick(t, "liquidity"), dict):
                liq = _num(_pick(_pick(t, "liquidity"), "usd"))
            if (mc is not None and mc < DEAD_MCAP_USD) or (liq is not None and liq < DEAD_LIQ_USD):
                rugged += 1
    # explicit totals fill what the list could not give (no list at all, or a summary-only answer)
    totals = {"launched": ("launchCount", "launched", "totalLaunches", "tokenCount", "launchesCount", "totalTokens"),
              "rugged": ("rugCount", "rugged", "rugs", "ruggedCount", "deadCount", "dead"),
              "graduated": ("graduatedCount", "graduated", "graduations", "graduatedTokens")}
    found = {k: _num(_pick(d, *names)) for k, names in totals.items()}
    if launches is None:
        if found["launched"] is not None:
            launched = max(0, int(found["launched"]) - (1 if mint else 0))  # a total includes this coin
        if found["rugged"] is not None:
            rugged = int(found["rugged"])
        if found["graduated"] is not None:
            graduated = int(found["graduated"])
    elif found["rugged"] is not None and int(found["rugged"]) > (rugged or 0):
        rugged = int(found["rugged"])  # the API's own rug count beats our market-cap heuristic when it is higher
    if launched is not None and rugged is not None:
        rugged = min(rugged, launched) if launched else rugged
    rate = round(rugged / launched, 2) if launched and rugged is not None else None
    return {"deployer": dep if isinstance(dep, str) else None, "launched": launched, "rugged": rugged,
            "graduated": graduated, "rug_rate": rate}


def summarize_early_buyers(raw):
    """{"sniped_pct", "bundled", "bundle_pct", "early_buyers_sold_pct", "buyers"} from stalkchain_token_early_buyers.
    sniped_pct: % of supply the snipers took (an explicit field, else the supply share of buyers flagged sniper, else
    the share of early buyers flagged sniper). bundled: an explicit flag, else bundle supply >= BUNDLE_FLAG_PCT % (or
    any bundle when its size is unknown). early_buyers_sold_pct: % of the early buyers that already sold."""
    d = _data(raw)
    d = d if isinstance(d, dict) else {"buyers": d}
    buyers = _list(d, "buyers", "earlyBuyers", "early_buyers", "firstBuyers", "items", "wallets") or []
    sniped = _pct(d, ("snipedPct", "sniped_pct", "sniperPct", "snipersPct", "sniperSupplyPct", "snipedSupplyPct"),
                  ("sniperShare", "snipedShare", "sniperSupplyShare"))
    if sniped is None and buyers:
        snipers = [b for b in buyers if _truthy(_pick(b, "sniper", "isSniper", "sniped")) or
                   str(_pick(b, "type", "label", "kind") or "").lower() == "sniper"]
        shares = [_pct(b, ("supplyPct", "pctSupply", "percentOfSupply", "supply_pct"), ("supplyShare", "share")) for b in snipers]
        if snipers and all(s is not None for s in shares):
            sniped = sum(shares)
        elif any(_pick(b, "sniper", "isSniper", "sniped", "type", "label", "kind") is not None for b in buyers):
            sniped = 100.0 * len(snipers) / len(buyers)
    bundle = _pick(d, "bundles", "bundle", "bundlers", "bundleStats", "bundling")
    bundle_pct = _pct(d, ("bundlePct", "bundledPct", "bundle_pct", "bundleSupplyPct", "bundledSupplyPct"),
                      ("bundleShare", "bundledShare"))
    if bundle_pct is None and isinstance(bundle, dict):
        bundle_pct = _pct(bundle, ("pct", "supplyPct", "initialPct", "boughtPct", "percent", "totalPct"),
                          ("share", "supplyShare"))
    flag = _pick(d, "bundled", "isBundled", "hasBundles")
    if isinstance(flag, bool):
        bundled = flag
    elif bundle_pct is not None:
        bundled = bundle_pct >= BUNDLE_FLAG_PCT
    elif isinstance(bundle, list):
        bundled = len(bundle) > 0
    elif isinstance(bundle, dict) and _num(_pick(bundle, "count", "bundles", "n")) is not None:
        bundled = _num(_pick(bundle, "count", "bundles", "n")) > 0
    else:
        bundled = None
    sold = _pct(d, ("earlyBuyersSoldPct", "soldPct", "sold_pct", "exitedPct", "pctSold"), ("soldShare", "exitedShare"))
    if sold is None and buyers:
        known = [b for b in buyers if _pick(b, "sold", "hasSold", "exited", "soldAll", "status", "holding", "stillHolding") is not None]
        if known:
            out = sum(1 for b in known if _truthy(_pick(b, "sold", "hasSold", "exited", "soldAll")) or
                      str(_pick(b, "status") or "").lower() in ("sold", "exited") or
                      _pick(b, "holding", "stillHolding") is False)
            sold = 100.0 * out / len(known)
    r = lambda x: round(x, 1) if x is not None else None  # noqa: E731
    return {"sniped_pct": r(sniped), "bundled": bundled, "bundle_pct": r(bundle_pct),
            "early_buyers_sold_pct": r(sold), "buyers": len(buyers) or None}


def summarize_quality(raw):
    """{"wash_pct", "verified", "organic_score", "dev_mints"} from stalkchain_token_quality. wash_pct = 100 minus the
    organic share of volume over the longest window that has both numbers (stats24h, 6h, 1h, 5m; buy + sell organic
    volume over buy + sell volume), else an explicit organic share."""
    d = _data(raw)
    d = d if isinstance(d, dict) else {}
    wash = None
    for w in ("24h", "6h", "1h", "5m"):
        s = _pick(d, "stats" + w, "stats_" + w, w)
        if not isinstance(s, dict):
            s = _pick(_pick(d, "stats", "volume", "windows") or {}, w, "stats" + w)
        if not isinstance(s, dict):
            continue
        total = _num(_pick(s, "volume", "totalVolume", "total"))
        organic = _num(_pick(s, "organicVolume", "organic"))
        if total is None and (_num(_pick(s, "buyVolume")) is not None or _num(_pick(s, "sellVolume")) is not None):
            total = (_num(_pick(s, "buyVolume")) or 0) + (_num(_pick(s, "sellVolume")) or 0)
        if organic is None and (_num(_pick(s, "buyOrganicVolume")) is not None or _num(_pick(s, "sellOrganicVolume")) is not None):
            organic = (_num(_pick(s, "buyOrganicVolume")) or 0) + (_num(_pick(s, "sellOrganicVolume")) or 0)
        if total and organic is not None:
            wash = max(0.0, min(100.0, 100.0 * (1 - organic / total)))
            break
    if wash is None:
        org = _pct(d, ("organicPct", "organicVolumePct", "organic_pct"), ("organicShare", "organicVolumeShare"))
        if org is not None:
            wash = max(0.0, min(100.0, 100.0 - org))
        else:
            wash = _pct(d, ("washPct", "wash_pct", "washTradingPct"), ("washShare",))
    ver = _pick(d, "verified", "isVerified")
    audit = _pick(d, "audit") if isinstance(_pick(d, "audit"), dict) else {}
    dev = _num(_pick(audit, "devMints", "dev_mints")) if audit else None
    if dev is None:
        dev = _num(_pick(d, "devMints", "dev_mints"))
    score = _num(_pick(d, "organicScore", "organic_score", "score"))
    return {"wash_pct": round(wash, 1) if wash is not None else None,
            "verified": ver if isinstance(ver, bool) else (_truthy(ver) if ver is not None else None),
            "organic_score": round(score, 1) if score is not None else None,
            "dev_mints": int(dev) if dev is not None else None}


def summarize_entries(raw):
    """[{"mint", "symbol", "traders", "first_ts", "last_ts"}, ...] from stalkchain_fomo_multi_trader_entries, newest
    last entry first; Solana only (rows naming another chain are dropped), rows without a mint dropped."""
    d = _data(raw)
    rows = _list(d, "tokens", "entries", "results", "items", "data") if isinstance(d, dict) else _list(d)
    out = []
    for r in rows or []:
        tok = _pick(r, "token", "mint", "address", "tokenAddress", "ca")
        if isinstance(tok, dict):
            sym = _pick(tok, "symbol", "ticker")
            tok = _pick(tok, "address", "mint", "id")
        else:
            sym = None
        chain = str(_pick(r, "chain", "chainName") or "solana").lower()
        if not isinstance(tok, str) or not tok or chain not in ("solana", "sol", "solana-mainnet"):
            continue
        traders = _pick(r, "traderCount", "traders_count", "distinctTraders", "count", "traders")
        n = len(traders) if isinstance(traders, list) else _num(traders)
        out.append({"mint": tok, "symbol": sym or _pick(r, "symbol", "ticker", "tokenSymbol"),
                    "traders": int(n) if n is not None else None,
                    "first_ts": _ts(_pick(r, "firstEntry", "firstEntryAt", "first_entry", "firstAt", "first", "firstTs")),
                    "last_ts": _ts(_pick(r, "lastEntry", "lastEntryAt", "last_entry", "lastAt", "last", "lastTs"))})
    out.sort(key=lambda e: -(e["last_ts"] or e["first_ts"] or 0))
    return out


# ---------------------------------------------------------------------------------------------------- client
class Client:
    def __init__(self, key, base=BASE, timeout=4.0, session=None, clock=time.time, daily_credits=None, cache_h=None):
        self.key, self.base, self.timeout = key, base.rstrip("/"), timeout
        self.session = session or requests.Session()
        self.clock = clock
        self.daily_credits = DAILY_CREDITS if daily_credits is None else daily_credits
        self.cache_secs = (CACHE_H if cache_h is None else cache_h) * 3600
        self.cache = {}            # (name, params) -> (ts, response)
        self.spent = deque()       # (ts, credits) of billed calls, last 24 hours
        self.paywalled = False
        self.unauthorized = False
        self._paywalled_at = 0.0
        self._backoff_until = 0.0
        self._said = set()
        self.lock = threading.Lock()
        self.stats = {"calls": 0, "credits": 0, "cached": 0, "skipped": 0, "errors": 0, "balance": None,
                      "credits_24h": 0, "paywalled": False}

    def _say(self, what, text):
        if what not in self._said:
            self._said.add(what)
            print(f"[stalkchain] {text}")

    def credits_24h(self, now=None):
        now = self.clock() if now is None else now
        while self.spent and now - self.spent[0][0] >= 86400:
            self.spent.popleft()
        return sum(c for _, c in self.spent)

    def _skip(self, name, now):
        """Why a paid call must not go out now (None = go)."""
        if self.unauthorized:
            return "bad key"
        if name in FREE:
            return None
        if self.paywalled and now - self._paywalled_at < PAYWALL_RETRY_SECS:
            return "no plan"
        if now < self._backoff_until:
            return "backing off after an error"
        if self.credits_24h(now) + TOOL_CREDITS.get(name, 250) > self.daily_credits:
            self._say("budget", f"daily credit budget ({self.daily_credits:g}) reached; paid calls skipped until it frees up")
            return "budget"
        return None

    def call(self, name, **params):
        params = {k: v for k, v in params.items() if v is not None}
        try:
            with self.lock:
                return self._call(name, params)
        except Exception as e:  # never raises
            self.stats["errors"] += 1
            self._say("crash:" + type(e).__name__, f"{name} failed: {e}")
            return None

    def _call(self, name, params):
        now = self.clock()
        ck = (name, tuple(sorted((k, str(v)) for k, v in params.items()))) if "token" in params else None
        if ck and ck in self.cache:
            ts, resp = self.cache[ck]
            if now - ts < self.cache_secs:
                self.stats["cached"] += 1
                return resp
            del self.cache[ck]
        if self._skip(name, now):
            self.stats["skipped"] += 1
            return None
        self.stats["calls"] += 1
        try:
            r = self.session.get(f"{self.base}/tools/{name}", params=params, timeout=self.timeout,
                                 headers={"Authorization": f"Bearer {self.key}", "Accept": "application/json"})
        except requests.RequestException as e:
            self.stats["errors"] += 1
            self._backoff_until = now + ERROR_BACKOFF_SECS
            print(f"[stalkchain] {name}: {type(e).__name__}")
            return None
        try:
            body = r.json()
        except ValueError:
            body = None
        status = getattr(r, "status_code", 0)
        err = body.get("error") if isinstance(body, dict) else None
        err_text = (err.get("message") if isinstance(err, dict) else str(err or "")) or ""
        if status == 401:
            self.stats["errors"] += 1
            self.unauthorized = True
            self._say("401", "the API key was refused (401); StalkChain calls are off until the arena restarts")
            return None
        if status == 402 or (err_text and _PAYWALL.search(err_text)):
            self.stats["errors"] += 1
            self.paywalled = self.stats["paywalled"] = True
            self._paywalled_at = now
            self._say("402", f"no paid plan or out of credits ({status}): {err_text[:120] or 'see https://data.stalkchain.com/#plans'}")
            return None
        if status != 200 or not isinstance(body, dict) or err:
            self.stats["errors"] += 1
            self._backoff_until = now + ERROR_BACKOFF_SECS
            print(f"[stalkchain] {name}: HTTP {status} {err_text[:120]}")
            return None
        self.paywalled = self.stats["paywalled"] = False
        cost, bal = self._credits(body.get("credits"), name)
        if cost:
            self.spent.append((now, cost))
        self.stats["credits"] += cost
        self.stats["credits_24h"] = self.credits_24h(now)
        if bal is not None:
            self.stats["balance"] = bal
        if ck:
            self.cache[ck] = (now, body)
            if len(self.cache) > 5000:  # drop the oldest
                for k in sorted(self.cache, key=lambda k: self.cache[k][0])[:1000]:
                    del self.cache[k]
        return body

    @staticmethod
    def _credits(block, name):
        """(cost, balance) from a response's credits block; the documented price when the block has no cost."""
        cost = bal = None
        if isinstance(block, dict):
            cost = _num(_pick(block, "cost", "charged", "spent", "used", "credits", "callCost", "this_call"))
            bal = _num(_pick(block, "balance", "remaining", "left", "balanceLeft", "balance_after", "creditsLeft"))
        elif _num(block) is not None:
            cost = _num(block)
        if cost is None:
            cost = TOOL_CREDITS.get(name, 250)
        return int(cost), (int(bal) if bal is not None else None)

    # convenience wrappers
    def deployer(self, mint):
        return self.call("stalkchain_token_deployer", token=mint)

    def early_buyers(self, mint, limit=20):
        return self.call("stalkchain_token_early_buyers", token=mint, limit=limit)

    def quality(self, mint):
        return self.call("stalkchain_token_quality", token=mint)

    def multi_trader_entries(self, windowMinutes=60, minTraders=3, side="buy", chain="solana", limit=20):
        return self.call("stalkchain_fomo_multi_trader_entries", windowMinutes=windowMinutes, minTraders=minTraders,
                         side=side, chain=chain, limit=limit)

    def account(self):
        return self.call("stalkchain_account")

    def health(self):
        return self.call("stalkchain_health")


PREBUY_CALLS = {"deployer": ("deployer", summarize_deployer), "early_buyers": ("early_buyers", summarize_early_buyers),
                "quality": ("quality", summarize_quality)}


def prebuy(client, mint, kinds=None):
    """Run the pre-buy lookups for `mint`: {kind: summary} for each lookup that answered (a failed one is missing)."""
    out = {}
    for kind in (PREBUY if kinds is None else kinds):
        meth, summ = PREBUY_CALLS[kind]
        raw = getattr(client, meth)(mint)
        if raw is not None:
            out[kind] = summ(raw, mint) if kind == "deployer" else summ(raw)
    return out


_SHARED = None


def shared():
    """The process-wide client built from ARENA_STALKCHAIN_KEY, or None without a key."""
    global _SHARED
    if _SHARED is None and KEY:
        _SHARED = Client(KEY)
    return _SHARED
