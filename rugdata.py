"""Rug-pull data for a Solana token: holder concentration, LP lock, creator/insider holdings, RugCheck risks.

market.py already checks the coarse signals (mint/freeze authority, liquidity, pair age, Jupiter sell route). This
module adds the signals that actually preceded today's rugs: a handful of wallets (or the creator) holding a large
share of supply, liquidity that can be pulled, insider wallet networks and RugCheck's own risk list. It is pure data
collection; market.py calls `assess()` and turns the dict into flags with `flags()`.

Contract (do not change):
  assess(session, mint, decimals=None) -> dict | None
      `session` is a requests.Session. Every network call uses a <= 5 s timeout. Returns None on a transient failure
      (timeout, connection error, 429, 5xx, local rate-limit pause) so the caller retries on a later tick. Returns a
      dict on success - also for an invalid / unknown mint (all fields None, `error` set) so the caller stops asking.
  flags(info) -> list[tuple[str, bool]]
      Human-readable flag texts with a HARD marker (True = the token should be rated red). [] when info is None.

Sources (all free, no API keys; verified with real requests on 2026-10-05):
  1. RugCheck   GET https://api.rugcheck.xyz/v1/tokens/{mint}/report   (one request; ~10 KB for a fresh token, up to
     a few MB for a token with hundreds of pools like BONK; 0.15-0.9 s). Gives score / score_normalised, risks[]
     (name, level good|warn|danger), topHolders[] (20 largest token accounts with owner + insider marker),
     knownAccounts{} (labels pool vault owners as type "AMM", vesting as "LOCKER", the deployer as "CREATOR"),
     markets[] (every pool with its vault addresses and lp.lpLockedPct / lp.lpTotalSupply), creatorBalance,
     graphInsidersDetected + insiderNetworks, tokenMeta.mutable, transferFee, totalHolders, rugged, launchpad.
     Rate limit observed: X-Rate-Limit-Limit 15 per short window; invalid mint -> HTTP 400 {"error": ...}.
  2. Solana JSON-RPC (optional): getTokenSupply + getTokenLargestAccounts (one batched POST) and getMultipleAccounts
     (jsonParsed, to learn each token account's owner), plus one getMultipleAccounts on the owners to see which are
     plain wallets (System-program owned) versus program PDAs (pool vaults, lockers). IMPORTANT: the public endpoint
     https://api.mainnet-beta.solana.com answers getTokenLargestAccounts with HTTP 429 "Too many requests for a
     specific RPC call" and x-ratelimit-method-limit: 0 - the method is disabled on the free tier (verified; the
     free publicnode / dRPC endpoints block it too). The RPC path therefore runs only when RUG_RPC_URL points at an
     RPC that allows it (Helius / QuickNode / Triton free tiers do), or when RUG_RPC_HOLDERS=always.

Holder-concentration heuristic (top1_pct / top10_pct):
  Share of total supply held by the largest and the 10 largest token accounts AFTER removing accounts that are not
  "someone who can dump": pool vaults (token account listed as liquidityA/B of a RugCheck market, or owned by a
  RugCheck knownAccount of type AMM, or owned by a known AMM program / authority: Raydium v4/CPMM/CLMM/LaunchLab,
  pump.fun bonding curve, PumpSwap, Meteora DLMM/DAMM/DBC, Orca Whirlpool), locker / vesting vaults (knownAccount
  type LOCKER or RugCheck lockers), the burn address, and on the RPC path any token account whose owner is a program
  PDA rather than a System-program wallet. Limits: only the 20 largest token accounts are visible (RugCheck and the
  RPC both cap there), one person can spread tokens over many wallets (undercounts), exchange hot wallets and
  unlabelled pools count as holders (overcounts), and the RugCheck snapshot can be minutes old. `holders_note`
  says what was excluded. `creator_pct` = creatorBalance / supply, `insider_pct` = tokens currently held by
  RugCheck's detected insider networks / supply (wallets funded by the deployer or each other).

Creator and Token-2022 extensions (read by signals.py; flags() does not use them):
  creator               the deployer's wallet: RugCheck's top-level `creator`, else the knownAccounts entry of type
                        CREATOR; None when RugCheck names none (common for tokens launched outside pump.fun).
  dangerous_extensions  short names of Token-2022 extensions that can trap a buyer (honeypot levers), from the
                        report's `token_extensions` block and, as a fallback, RugCheck's risk names:
                        "permanent delegate" (permanentDelegate.delegate set; RugCheck risk "Permanent Control
                        Enabled"), "transfer hook" (transferHook program or authority set), "non-transferable",
                        "default frozen" (defaultAccountState frozen: new token accounts start frozen),
                        "pausable" (pausableConfig authority set or paused: transfers can be halted), and
                        "transfer fee N%" when the fee is at least RUG_TRANSFER_FEE_HARD (default 10).
                        [] = checked, nothing found; None = no RugCheck report (unknown).
  transfer_fee_ext_pct  the fee in percent from token_extensions.transferFeeConfig (the higher of the older / newer
                        fee, since a raise takes effect two epochs later); None without that extension. Kept apart
                        from transfer_fee_pct (RugCheck's own `transferFee.pct`) because RugCheck has been seen
                        reporting pct 0 for a mint whose extension charged 200 basis points.

Holder SOL balances (run 9, for signals.py's bundle-balance veto):
  top_holders[i]["sol"]  the holder's OWNER wallet SOL balance (lamports / 1e9; a wallet the chain has no account for
                         is 0.0), from one getMultipleAccounts on the owners (base64, no data, SOL_TIMEOUT = 2 s).
                         Only System-Program-owned wallets (or missing accounts) get a balance: a program-owned owner
                         (PDA, vault) carries the same rent-exempt minimum as every other and would look like
                         identical funding, so it is marked `program_owned` and left out of the bundle check
                         (`sol_skipped` counts them). The RPC holder path
                         already makes that call for its PDA check and records the balances from it; otherwise one
                         extra request per assess() goes to RUG_RPC_URL (getMultipleAccounts works on the public
                         endpoint). A failure leaves `sol` out (unknown, never a veto) and pauses the lookup for
                         SOL_PAUSE_SECS (60) so a dead RPC costs at most one timeout a minute. RUG_HOLDER_SOL=0 turns
                         it off.
  top5_sol               the balances of the top 5 holders in holder order, pool / LP / locker / burn accounts
                         (already out of top_holders), program-owned owners and the creator left out; None for an
                         unknown balance.

LP lock (lp_locked_pct): liquidity-weighted average of lp.lpLockedPct over markets that have LP tokens
  (lp.lpTotalSupply > 0). pump.fun bonding curves and PumpSwap pools report 100 (LP burned), classic Raydium pools
  report the burned/locked share, concentrated-liquidity pools (Orca Whirlpool, Meteora DLMM, Raydium CLMM) have no
  LP tokens and are skipped - None when no market has LP tokens. `lp_locked_main_pct` is the deepest market alone.

Flag thresholds (percent of supply unless noted; every one overridable through the environment):
  RUG_TOP10_HARD=50   RUG_TOP10_SOFT=35      top 10 non-pool token accounts
  RUG_TOP1_HARD=20    RUG_TOP1_SOFT=10       single non-pool token account
  RUG_CREATOR_HARD=20 RUG_CREATOR_SOFT=5     deployer wallet balance
  RUG_INSIDER_HARD=30 RUG_INSIDER_SOFT=5     insider-network holdings (RugCheck graph; when RugCheck's network
                                             total exceeds the supply - it does for WIF - the bounded share of
                                             top-20 accounts RugCheck marks `insider` is used instead)
  RUG_MATURE_HOLDERS=50000                   tokens with at least this many holders only get the HARD
                                             concentration flags: their top wallets are exchange custody (BONK's
                                             top 10 hold 38%, WIF's 46%, neither is a rug signal)
  RUG_LP_SOFT=50                             LP locked/burned below this -> soft flag, only while total liquidity
  RUG_LP_SKIP_LIQ_USD=500000                 is under this (pulling LP is not how a $1M+ multi-pool token dies)
  RUG_TRANSFER_FEE_SOFT=1                    Token-2022 transfer fee percent -> soft flag (hard at >= 10)
  RUG_TRANSFER_FEE_HARD=10                   transfer fee percent that lists "transfer fee N%" in
                                             dangerous_extensions (flags() keeps its own fixed 10)
  RUG_RC_DANGER_SCORE=70  RUG_RC_WARN_SCORE=40   score_normalised cut-offs for rugcheck_level when no risk has
                                             that level itself. Any RugCheck risk at level "danger" -> hard flag,
                                             "warn" -> soft flag. RugCheck's mint/freeze-authority risks are
                                             dropped (market.py reports them), and its holder / LP risks are
                                             dropped whenever this module has its own number for the same thing.
  RUG_SOFT_RISKS=                            comma-separated RugCheck risk names to demote from hard to soft.
Other environment variables:
  RUG_RUGCHECK=1          0/off disables RugCheck.      RUG_RUGCHECK_URL   default https://api.rugcheck.xyz
  RUG_RC_PER_MIN=10       local cap on RugCheck requests per rolling minute (observed server limit 15 per window)
  RUG_TIMEOUT=5           seconds per request (never raised above 5).
  RUG_RPC_URL             default https://api.mainnet-beta.solana.com   RUG_RPC_HOLDERS=auto|always|off
                          auto = RPC holder scan only when the URL is not the public endpoint AND RugCheck gave no
                          holder list; always = also when RugCheck succeeded (RPC numbers then win, they are live).
Rate-limit behaviour: a 429 from RugCheck pauses RugCheck calls for Retry-After (default 30 s); the per-method 429
from the RPC disables the RPC holder scan for 10 minutes; while paused, and when the local per-minute cap is hit,
assess() returns None (retry later) rather than making the request. Request cost: 2 requests per call by default
(RugCheck, then the holders' SOL balances); 3 more when the RPC path runs (which covers the balances itself).
Nothing is cached here beyond the pause timers - the caller keeps
its own risk cache.
"""
import os
import re
import time
from collections import deque

RC_ON = os.environ.get("RUG_RUGCHECK", "1").strip().lower() not in ("0", "off", "false", "no")
RC_URL = os.environ.get("RUG_RUGCHECK_URL", "https://api.rugcheck.xyz").rstrip("/")
RC_PER_MIN = int(float(os.environ.get("RUG_RC_PER_MIN", "10") or 10))
TIMEOUT = min(5.0, float(os.environ.get("RUG_TIMEOUT", "5") or 5))
PUBLIC_RPC = "https://api.mainnet-beta.solana.com"
RPC_URL = os.environ.get("RUG_RPC_URL", PUBLIC_RPC).rstrip("/")
RPC_HOLDERS = os.environ.get("RUG_RPC_HOLDERS", "auto").strip().lower()
RPC_PAUSE_SECS = 600
HOLDER_SOL = os.environ.get("RUG_HOLDER_SOL", "1").strip().lower() not in ("0", "off", "false", "no")
SOL_PAUSE_SECS = 60
SOL_TIMEOUT = 2.0   # seconds for the balance lookup: a slow public RPC must not add 4 x 5 s to a tick
LAMPORTS = 1_000_000_000


def _env(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)


TOP10_HARD, TOP10_SOFT = _env("RUG_TOP10_HARD", 50), _env("RUG_TOP10_SOFT", 35)
TOP1_HARD, TOP1_SOFT = _env("RUG_TOP1_HARD", 20), _env("RUG_TOP1_SOFT", 10)
CREATOR_HARD, CREATOR_SOFT = _env("RUG_CREATOR_HARD", 20), _env("RUG_CREATOR_SOFT", 5)
INSIDER_HARD, INSIDER_SOFT = _env("RUG_INSIDER_HARD", 30), _env("RUG_INSIDER_SOFT", 5)
LP_SOFT, LP_SKIP_LIQ = _env("RUG_LP_SOFT", 50), _env("RUG_LP_SKIP_LIQ_USD", 500_000)
FEE_SOFT = _env("RUG_TRANSFER_FEE_SOFT", 1)
FEE_HARD = _env("RUG_TRANSFER_FEE_HARD", 10)   # only decides when a fee joins dangerous_extensions
MATURE_HOLDERS = _env("RUG_MATURE_HOLDERS", 50_000)
RC_DANGER_SCORE, RC_WARN_SCORE = _env("RUG_RC_DANGER_SCORE", 70), _env("RUG_RC_WARN_SCORE", 40)
SOFT_RISKS = {s.strip().lower() for s in os.environ.get("RUG_SOFT_RISKS", "").split(",") if s.strip()}

BURN = "1nc1nerator11111111111111111111111111111111"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
# Program ids / fixed authorities whose token accounts are pool vaults, not holders.
AMM_OWNERS = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM v4",
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1": "Raydium AMM v4 authority",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium CPMM",
    "GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL": "Raydium CPMM authority",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": "Raydium LaunchLab",
    "WLHv2UAZm6z4KyaaELi5pjdbJh6RESMva1Rnn8pJVVh": "Raydium LaunchLab authority",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pump.fun bonding curve",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "PumpSwap",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora DLMM",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "Meteora DAMM",
    "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG": "Meteora DAMM v2",
    "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN": "Meteora DBC",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
}
# RugCheck risks already reported by market.py (never shown) and those this module measures itself (shown only
# when the module's own number is missing).
_SKIP_RISKS = re.compile(r"mint authority|freeze authority", re.I)
_DUP_RISKS = {"holders": re.compile(r"holder|ownership|concentrat", re.I),
              "lp": re.compile(r"\bLP\b|liquidity.*(lock|unlock)|unlock", re.I),
              "creator": re.compile(r"creator (holds|balance|owns)", re.I)}
_B58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
# Honeypot-type Token-2022 extensions as RugCheck names them in its risk list (fallback when the report has no
# token_extensions block, e.g. older cached reports).
_DANGER_RISKS = (("permanent delegate", re.compile(r"permanent (delegate|control)", re.I)),
                 ("transfer hook", re.compile(r"transfer[ _-]?hook", re.I)),
                 ("non-transferable", re.compile(r"non[ _-]?transferable", re.I)),
                 ("default frozen", re.compile(r"default account state|frozen by default", re.I)),
                 ("pausable", re.compile(r"pausab", re.I)))

_rc_times = deque()       # timestamps of RugCheck requests in the last minute
_rc_paused_until = 0.0
_rpc_paused_until = 0.0
_sol_paused_until = 0.0   # holder SOL balance lookups pause here after a failure
last_cost = {"requests": 0, "seconds": 0.0}   # cost of the most recent assess() call, for the caller's logs


class _Transient(Exception):
    """Timeout / 429 / 5xx: the caller should retry later."""


def _plausible(mint):
    return isinstance(mint, str) and 32 <= len(mint) <= 44 and set(mint) <= _B58


def _f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _pct(x):
    return None if x is None else round(float(x), 2)


# ----------------------------------------------------------------------------------------------- RugCheck
def _rugcheck(session, mint, cost):
    """Full RugCheck report as a dict, None when disabled; raises _Transient on rate limit / server trouble."""
    global _rc_paused_until
    now = time.time()
    if not RC_ON or now < _rc_paused_until:
        return None
    while _rc_times and now - _rc_times[0] > 60:
        _rc_times.popleft()
    if len(_rc_times) >= RC_PER_MIN:
        raise _Transient("rugcheck local rate cap")
    _rc_times.append(now)
    cost["requests"] += 1
    try:
        r = session.get(f"{RC_URL}/v1/tokens/{mint}/report", timeout=TIMEOUT)
    except Exception as e:  # requests.Timeout / ConnectionError / anything odd in the stack
        raise _Transient(f"rugcheck: {type(e).__name__}")
    if r.status_code == 429:
        _rc_paused_until = time.time() + max(5.0, _f(r.headers.get("Retry-After"), 30) or 30)
        raise _Transient("rugcheck 429")
    if r.status_code >= 500:
        raise _Transient(f"rugcheck {r.status_code}")
    if r.status_code != 200:
        try:
            msg = r.json().get("error") or r.text[:80]
        except Exception:
            msg = r.text[:80]
        return {"_error": f"rugcheck {r.status_code}: {msg}"}
    try:
        d = r.json()
    except Exception:
        raise _Transient("rugcheck: bad JSON")
    return d if isinstance(d, dict) else {"_error": "rugcheck: unexpected payload"}


def _lower_risk(name):
    """'Large Amount of LP Unlocked' -> 'large amount of LP unlocked' (keeps acronyms)."""
    return " ".join(w if (w.isupper() and len(w) > 1) else w.lower() for w in str(name).split())


def _addr_set(v, *keys):
    """True when an extension value names an authority / program: a non-system address string, or a dict where
    one of `keys` holds one."""
    def ok(x):
        return isinstance(x, str) and x.strip() not in ("", SYSTEM_PROGRAM)
    if ok(v):
        return True
    return isinstance(v, dict) and any(ok(v.get(k)) for k in keys)


def _creator(d, known):
    """The deployer wallet from a RugCheck report: `creator`, else the knownAccounts entry typed CREATOR."""
    c = d.get("creator")
    if _plausible(c) and c != SYSTEM_PROGRAM:
        return c
    for addr, ka in known.items():
        if isinstance(ka, dict) and ka.get("type") == "CREATOR" and _plausible(addr):
            return addr
    return None


def _extensions(d, risk_names, rc_fee_pct=None):
    """(fee percent from transferFeeConfig or None, [dangerous extension names]) from a RugCheck report."""
    ext = d.get("token_extensions")
    found, fee_pct = [], None
    if isinstance(ext, dict):
        if _addr_set(ext.get("permanentDelegate"), "delegate"):
            found.append("permanent delegate")
        if _addr_set(ext.get("transferHook"), "programId", "program_id", "authority"):
            found.append("transfer hook")
        nt = ext.get("nonTransferable")
        if nt is True or (isinstance(nt, dict) and nt.get("enabled", True) not in (False, None)):
            found.append("non-transferable")
        das = ext.get("defaultAccountState")
        if das is not None:
            state = das.get("accountState", das.get("state")) if isinstance(das, dict) else das
            if state == 2 or "frozen" in str(state if state is not None else das).lower():
                found.append("default frozen")
        pc = ext.get("pausableConfig")
        if pc is True or (isinstance(pc, dict) and (pc.get("paused") is True or _addr_set(pc, "authority"))):
            found.append("pausable")
        tf = ext.get("transferFeeConfig")
        if isinstance(tf, dict):
            bps = [_f((tf.get(k) or {}).get("transferFeeBasisPoints")) for k in ("olderTransferFee", "newerTransferFee")
                   if isinstance(tf.get(k), dict)]
            bps = [b for b in bps if b is not None]
            if bps:
                fee_pct = round(max(bps) / 100.0, 4)
    fee = max([x for x in (fee_pct, rc_fee_pct) if x is not None], default=None)
    if fee is not None and fee >= FEE_HARD:
        found.append(f"transfer fee {fee:g}%")
    for label, pat in _DANGER_RISKS:
        if label not in found and any(pat.search(str(n)) for n in risk_names):
            found.append(label)
    return fee_pct, found


def _parse_rugcheck(d, info):
    """Fill `info` from a RugCheck report dict."""
    token = d.get("token") or {}
    supply = _f(token.get("supply"))
    known = d.get("knownAccounts") or {}
    markets = d.get("markets") or []
    lockers = d.get("lockers") or {}
    risks = [r for r in (d.get("risks") or []) if isinstance(r, dict)]

    levels = {str(r.get("level", "")).lower() for r in risks}
    score_n = _f(d.get("score_normalised"))
    if "danger" in levels or (score_n is not None and score_n >= RC_DANGER_SCORE):
        level = "danger"
    elif "warn" in levels or (score_n is not None and score_n >= RC_WARN_SCORE):
        level = "warn"
    else:
        level = "good"
    info.update(
        rugcheck_score=int(score_n) if score_n is not None else None,
        rugcheck_raw_score=int(_f(d.get("score"), 0) or 0),
        rugcheck_level=level,
        rugcheck_risks=[str(r.get("name")) for r in risks if r.get("name")],
        rugcheck_risk_levels={str(r.get("name")): str(r.get("level", "")).lower() for r in risks if r.get("name")},
        rugged=bool(d.get("rugged")) if d.get("rugged") is not None else None,
        total_holders=d.get("totalHolders"),
        lp_providers=d.get("totalLPProviders"),
        total_liquidity_usd=_f(d.get("totalMarketLiquidity")),
        metadata_mutable=(d.get("tokenMeta") or {}).get("mutable"),
        transfer_fee_pct=_f((d.get("transferFee") or {}).get("pct")),
        launchpad=((d.get("launchpad") or {}).get("platform") or None),
        markets_count=len(markets),
        rugcheck_url=f"https://rugcheck.xyz/tokens/{info['mint']}",
    )
    info["creator_rugged_history"] = any("rugged" in n.lower() for n in info["rugcheck_risks"])
    info["creator"] = _creator(d, known)
    info["transfer_fee_ext_pct"], info["dangerous_extensions"] = _extensions(d, info["rugcheck_risks"],
                                                                             info.get("transfer_fee_pct"))

    # Creator holdings.
    cb = _f(d.get("creatorBalance"))
    if cb is not None and supply:
        info["creator_pct"] = _pct(cb / supply * 100)

    # Insider networks (wallets funded by the deployer / each other).
    n_ins = d.get("graphInsidersDetected")
    nets = d.get("insiderNetworks") or []
    if n_ins is not None:
        info["insiders_detected"] = bool(n_ins) and n_ins > 0
        info["insider_count"] = int(n_ins)
        held = sum(_f(n.get("currentHolding"), 0) or 0 for n in nets if isinstance(n, dict))
        if supply and 0 <= held / supply <= 1:
            info["insider_pct"] = _pct(held / supply * 100)
        # else: RugCheck's network total exceeds the supply for big old tokens (WIF: 299%) - unreliable,
        # insider_pct is filled from the top-holder insider markers below instead.

    # LP lock: liquidity-weighted over markets that have LP tokens.
    weighted, weight, best = 0.0, 0.0, None
    for m in markets:
        lp = m.get("lp") or {}
        liq = (_f(lp.get("quoteUSD"), 0) or 0) + (_f(lp.get("baseUSD"), 0) or 0)
        if (_f(lp.get("lpTotalSupply"), 0) or 0) > 0 and liq > 0:
            pct = _f(lp.get("lpLockedPct"), 0) or 0
            weighted += pct * liq
            weight += liq
            if best is None or liq > best[0]:
                best = (liq, pct, m.get("marketType"))
    if weight > 0:
        info["lp_locked_pct"] = _pct(weighted / weight)
        info["lp_locked_main_pct"] = _pct(best[1])
        info["main_market_type"] = best[2]
    elif markets:
        deep = max(markets, key=lambda m: (_f((m.get("lp") or {}).get("quoteUSD"), 0) or 0))
        info["main_market_type"] = deep.get("marketType")
        info["holders_note_lp"] = "no LP tokens (concentrated-liquidity pools), lock % not applicable"

    # Holder concentration from the top-20 token accounts, excluding pools / lockers / burn.
    vaults = set()
    for m in markets:
        vaults.update(x for x in (m.get("liquidityA"), m.get("liquidityB"), m.get("pubkey")) if x)
    locker_accounts = {v.get("tokenAccount") for v in lockers.values() if isinstance(v, dict)} | set(lockers)
    holders, excluded, kinds = [], 0.0, {}
    for h in d.get("topHolders") or []:
        pct, addr, owner = _f(h.get("pct")), h.get("address"), h.get("owner")
        if pct is None:
            continue
        label = None
        ka = known.get(owner) or known.get(addr) or {}
        if ka.get("type") == "AMM" or addr in vaults or owner in vaults or owner in AMM_OWNERS:
            label = "pool"
        elif ka.get("type") == "LOCKER" or addr in locker_accounts or owner in locker_accounts:
            label = "locker"
        elif owner == BURN or addr == BURN:
            label = "burn"
        if label:
            excluded += pct
            kinds[label] = kinds.get(label, 0) + 1
        else:
            holders.append({"pct": _pct(pct), "owner": owner, "insider": bool(h.get("insider")),
                            "creator": ka.get("type") == "CREATOR"})
    if d.get("topHolders"):
        holders.sort(key=lambda x: -x["pct"])
        info["top1_pct"] = holders[0]["pct"] if holders else 0.0
        info["top10_pct"] = _pct(sum(x["pct"] for x in holders[:10]))
        info["top_holders"] = holders[:10]
        info["insider_top_pct"] = _pct(sum(x["pct"] for x in holders if x["insider"]))
        if info.get("insider_pct") is None and info.get("insiders_detected"):
            info["insider_pct"] = info["insider_top_pct"]
        parts = [f"{n} {k} account{'s' if n > 1 else ''}" for k, n in kinds.items()]
        info["holders_note"] = (f"RugCheck top-20 token accounts; excluded {', '.join(parts)} holding "
                                f"{excluded:.1f}% of supply" if parts else
                                "RugCheck top-20 token accounts; no pool/locker accounts recognised among them")


# ----------------------------------------------------------------------------------------------- Solana RPC
def _rpc(session, body, cost, timeout=None):
    global _rpc_paused_until
    cost["requests"] += 1
    try:
        r = session.post(RPC_URL, json=body, timeout=min(TIMEOUT, timeout or TIMEOUT))
    except Exception as e:
        raise _Transient(f"rpc: {type(e).__name__}")
    if r.status_code == 429 or r.status_code >= 500:
        if r.headers.get("x-ratelimit-method-limit") == "0":
            _rpc_paused_until = time.time() + RPC_PAUSE_SECS  # method disabled on this endpoint
        raise _Transient(f"rpc {r.status_code}")
    try:
        j = r.json()
    except Exception:
        raise _Transient("rpc: bad JSON")
    items = j if isinstance(j, list) else [j]
    for it in items:
        err = it.get("error") if isinstance(it, dict) else None
        if err and err.get("code") == 429:
            _rpc_paused_until = time.time() + RPC_PAUSE_SECS
            raise _Transient("rpc method 429")
    return items


def _rpc_holders(session, mint, info, cost):
    """Top-20 token accounts from the chain; 3 requests. Overwrites top1/top10 in `info` on success."""
    if time.time() < _rpc_paused_until:
        return
    items = _rpc(session, [{"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [mint]},
                           {"jsonrpc": "2.0", "id": 2, "method": "getTokenLargestAccounts", "params": [mint]}], cost)
    by_id = {it.get("id"): it for it in items if isinstance(it, dict)}
    try:
        supply = int(by_id[1]["result"]["value"]["amount"])
        largest = by_id[2]["result"]["value"]
    except (KeyError, TypeError, ValueError):
        info["rpc_error"] = str((by_id.get(2) or by_id.get(1) or {}).get("error") or "rpc: unexpected payload")[:120]
        return
    if supply <= 0 or not largest:
        return
    addrs = [x["address"] for x in largest]
    accts = _rpc(session, {"jsonrpc": "2.0", "id": 3, "method": "getMultipleAccounts",
                           "params": [addrs, {"encoding": "jsonParsed"}]}, cost)[0]
    values = ((accts.get("result") or {}).get("value")) or [None] * len(addrs)
    owners = []
    for v in values:
        try:
            owners.append(v["data"]["parsed"]["info"]["owner"])
        except (KeyError, TypeError):
            owners.append(None)
    distinct = [o for o in dict.fromkeys(o for o in owners if o)]
    pda, sol = set(), {}
    if distinct:
        own = _rpc(session, {"jsonrpc": "2.0", "id": 4, "method": "getMultipleAccounts",
                             "params": [distinct, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}}]},
                   cost)[0]
        for o, v in zip(distinct, ((own.get("result") or {}).get("value")) or []):
            sol[o] = _sol(v)
            if v and v.get("owner") not in (None, SYSTEM_PROGRAM):
                pda.add(o)  # owned by a program: pool vault, locker, escrow - not a person's wallet
    known_pool_owners = {h.get("owner") for h in info.get("_rc_pool_owners", ())}
    holders, excluded, n_ex = [], 0.0, 0
    for x, owner in zip(largest, owners):
        pct = int(x["amount"]) / supply * 100
        if owner in pda or owner in AMM_OWNERS or owner in known_pool_owners or owner == BURN or owner is None:
            excluded += pct
            n_ex += 1
        else:
            holders.append({"pct": _pct(pct), "owner": owner, **({"sol": sol[owner]} if owner in sol else {})})
    holders.sort(key=lambda h: -h["pct"])
    info.update(top1_pct=holders[0]["pct"] if holders else 0.0,
                top10_pct=_pct(sum(h["pct"] for h in holders[:10])),
                top_holders=holders[:10],
                holders_note=(f"RPC top-20 token accounts; excluded {n_ex} program-owned/pool/burn account"
                              f"{'s' if n_ex != 1 else ''} holding {excluded:.1f}% of supply"))
    info["checked_sources"].append("rpc")


def _sol(v):
    """SOL balance of one getMultipleAccounts value (None = no such account = 0 SOL)."""
    try:
        return round(int((v or {}).get("lamports") or 0) / LAMPORTS, 4)
    except (TypeError, ValueError, AttributeError):
        return None


def _holder_balances(session, info, cost):
    """Record each top holder's owner-wallet SOL balance (`sol`) and `top5_sol` (module docstring). Never raises."""
    global _sol_paused_until
    holders = [h for h in info.get("top_holders") or () if isinstance(h, dict)]
    need = [o for o in dict.fromkeys(h.get("owner") for h in holders if "sol" not in h) if o]
    if need and time.time() >= _sol_paused_until:
        try:
            res = _rpc(session, {"jsonrpc": "2.0", "id": 5, "method": "getMultipleAccounts",
                                 "params": [need, {"encoding": "base64", "dataSlice": {"offset": 0, "length": 0}}]},
                       cost, timeout=SOL_TIMEOUT)[0]
            values = (res.get("result") or {}).get("value")
            if isinstance(values, list) and len(values) == len(need):
                bal, prog = {}, set()
                for o, v in zip(need, values):
                    if isinstance(v, dict) and v.get("owner") not in (None, SYSTEM_PROGRAM):
                        prog.add(o)  # a program-owned account (PDA, vault): rent-exempt minimum, not a funded wallet
                    else:
                        bal[o] = _sol(v)  # a System-owned wallet, or no account at all (0 SOL)
                for h in holders:
                    if h.get("owner") in prog:
                        h["program_owned"] = True
                    elif h.get("owner") in bal and bal[h["owner"]] is not None:
                        h["sol"] = bal[h["owner"]]
            else:
                _sol_paused_until = time.time() + SOL_PAUSE_SECS
        except Exception:  # _Transient or a malformed answer: balances stay unknown
            _sol_paused_until = time.time() + SOL_PAUSE_SECS
    if holders:
        creator = info.get("creator")
        rest = [h for h in holders if not h.get("creator") and not h.get("program_owned")
                and not (creator and h.get("owner") == creator)]
        top5 = [h.get("sol") for h in rest[:5]]
        info["top5_sol"] = top5 if any(s is not None for s in top5) else None
        info["sol_skipped"] = sum(1 for h in holders if h.get("program_owned"))


# ----------------------------------------------------------------------------------------------- public API
def assess(session, mint, decimals=None):
    """Collect rug data for `mint`. None = transient failure (retry later); dict otherwise (see module doc)."""
    t0 = time.time()
    cost = {"requests": 0}
    info = {"mint": mint, "top1_pct": None, "top10_pct": None, "holders_note": None, "lp_locked_pct": None,
            "creator_pct": None, "rugcheck_score": None, "rugcheck_level": None, "rugcheck_risks": [],
            "insiders_detected": None, "insider_pct": None, "checked_sources": [], "error": None,
            "checked": t0, "creator": None, "dangerous_extensions": None}
    if not _plausible(mint):
        info["error"] = "not a plausible Solana mint address"
        last_cost.update(requests=0, seconds=0.0, note=info["error"])
        return info
    try:
        rc = _rugcheck(session, mint, cost)
        if rc is not None:
            if rc.get("_error"):
                info["error"] = rc["_error"]
            else:
                _parse_rugcheck(rc, info)
                info["checked_sources"].append("rugcheck")
        want_rpc = RPC_HOLDERS == "always" or (RPC_HOLDERS == "auto" and RPC_URL != PUBLIC_RPC
                                               and info.get("top10_pct") is None)
        if want_rpc and RPC_HOLDERS != "off" and not info["error"]:
            if rc and not rc.get("_error"):
                info["_rc_pool_owners"] = [{"owner": k} for k, v in (rc.get("knownAccounts") or {}).items()
                                           if isinstance(v, dict) and v.get("type") in ("AMM", "LOCKER")]
            _rpc_holders(session, mint, info, cost)
            info.pop("_rc_pool_owners", None)
        if HOLDER_SOL and info.get("top_holders") and not info["error"]:
            _holder_balances(session, info, cost)
    except _Transient as e:
        last_cost.update(requests=cost["requests"], seconds=round(time.time() - t0, 2), note=str(e))
        return None
    if not info["checked_sources"] and not info["error"]:
        info["error"] = "no source available (RugCheck disabled or paused)"
        if not RC_ON and RPC_HOLDERS == "off":
            return info
        last_cost.update(requests=cost["requests"], seconds=round(time.time() - t0, 2), note=info["error"])
        return None  # paused: retry later
    info["holders_note"] = info.get("holders_note") or info.pop("holders_note_lp", None) or info["holders_note"]
    info.pop("holders_note_lp", None)
    last_cost.update(requests=cost["requests"], seconds=round(time.time() - t0, 2), note="ok")
    return info


def flags(info):
    """[(text, hard)] for the arena's risk list. Specific numbers, sentence case, no duplicates of market.py."""
    if not info:
        return []
    out = []

    def add(text, hard):
        out.append((text, bool(hard)))

    if info.get("rugged"):
        add("RugCheck marks this token as rugged", True)
    t10, t1 = info.get("top10_pct"), info.get("top1_pct")
    mature = (info.get("total_holders") or 0) >= MATURE_HOLDERS  # top wallets are exchanges: soft flags skipped
    if t1 is not None and t1 >= TOP1_SOFT and (t1 >= TOP1_HARD or not mature):
        add(f"single wallet holds {t1:.0f}% of supply (pool vaults excluded)", t1 >= TOP1_HARD)
    if t10 is not None and t10 >= TOP10_SOFT and (t10 >= TOP10_HARD or not mature):
        add(f"top 10 holders own {t10:.0f}% of supply (pool vaults excluded)", t10 >= TOP10_HARD)
    cp = info.get("creator_pct")
    if cp is not None and cp >= CREATOR_SOFT:
        add(f"creator still holds {cp:.0f}% of supply", cp >= CREATOR_HARD)
    ip = info.get("insider_pct")
    if ip is not None and ip >= INSIDER_SOFT:
        n = info.get("insider_count") or 0
        add(f"insider network of {n} wallets holds {ip:.0f}% of supply", ip >= INSIDER_HARD)
    lp = info.get("lp_locked_pct")
    liq = info.get("total_liquidity_usd") or 0
    if lp is not None and lp < LP_SOFT and liq < LP_SKIP_LIQ:
        add("liquidity not locked or burned" if lp <= 0 else f"only {lp:.0f}% of liquidity locked or burned", False)
    fee = info.get("transfer_fee_pct")
    if fee is not None and fee >= FEE_SOFT:
        add(f"{fee:g}% transfer fee on every trade", fee >= 10)

    risks = info.get("rugcheck_risks") or []
    levels = info.get("rugcheck_risk_levels") or {}
    have = {"holders": t10 is not None, "lp": lp is not None, "creator": cp is not None}
    hard_names, soft_names = [], []
    for name in risks:
        if _SKIP_RISKS.search(name) or any(have[k] and p.search(name) for k, p in _DUP_RISKS.items()):
            continue
        lvl = levels.get(name, "")
        if lvl == "danger" and name.lower() not in SOFT_RISKS:
            hard_names.append(_lower_risk(name))
        elif lvl in ("danger", "warn"):
            soft_names.append(_lower_risk(name))
    score = info.get("rugcheck_score")
    tail = f", score {score}/100" if score is not None else ""
    if hard_names:
        add(f"RugCheck: high risk ({', '.join(hard_names)}{tail})", True)
    elif soft_names:
        add(f"RugCheck: warning ({', '.join(soft_names)}{tail})", False)
    elif info.get("rugcheck_level") == "danger":
        add(f"RugCheck: high risk score {score}/100", True)
    elif info.get("rugcheck_level") == "warn":
        add(f"RugCheck: elevated risk score {score}/100", False)
    return out
