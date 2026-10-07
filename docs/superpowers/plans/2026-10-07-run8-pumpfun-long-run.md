# Run 8: pump.fun-only long run — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the arena into a pump.fun-only paper-trading run (curve coins + PumpSwap graduates, pump.fun fees) with a Haiku 5.5 x4 + Sonnet 5.5 x2 roster, fewer trades per agent, a realized-profit leaderboard that Shadow and a Copy Top 10 bot follow, and a pre-registered verdict, then launch it unattended.

**Architecture:** Every change is a new mode behind an environment variable so replays of old runs still work. The market gains a `pumpfun` universe (PumpPortal discovery + a probation poll of fresh launches), the Claude view gains two candidate lanes, the exchange gains a `pumpfun` route, traders.py gains a `realized` ranking, the arena gains churn rules and a leader set, and the launcher gains a restart loop.

**Tech Stack:** Python 3.14, Flask, requests, sqlite3, pytest (to install), Claude Code CLI (`claude -p`), DexScreener + PumpPortal + Helius feeds.

**Spec:** `docs/superpowers/specs/2026-10-07-run8-pumpfun-long-run-design.md`

## Global Constraints

- Every new behaviour is opt-in via env vars with the old behaviour as default: `ARENA_UNIVERSE=pumpfun`, `ARENA_ROUTE=pumpfun`, `ARENA_TRADERS_RANK=realized`. Defaults stay `all`, `bot`, `pnl`.
- Env vars are read once at import like the rest of the code (`_env` helpers). Follow each file's existing style (docstring block at the top listing settings).
- Do not touch stops, the exit ladder, moonshots, lives or points.
- Agent names: `"<Family> <Persona label>"` (e.g. `Haiku Graduate`). Family comes from the model id; `claude-haiku-5-5` -> `Haiku 5.5`.
- Cadence: `ARENA_LLM_MIN_CHECK` default `1`, `ARENA_LLM_MAX_CHECK` default `60`. No per-model limits.
- Churn: `ARENA_LLM_MAX_BUYS_PER_DAY=6`, `ARENA_LLM_MIN_BUY_USD=50`, `ARENA_LLM_BUY_COOLDOWN_MIN=30`, LLM agents only.
- Pump.fun: `ARENA_PUMPFUN_PROBATION_MIN=20`, `ARENA_PUMPFUN_TRACK_MCAP_USD=12000`, `ARENA_PUMPFUN_TRACK_VOL_USD=8000` (with >= 40 1h transactions), graduation cap `69000` USD for `curve_pct`, `max_tracked=150` in pumpfun mode.
- Leaders: realized ranking requires `round_trips >= 5`, `win_rate >= 50`, `tokens_bought >= 3`; `ARENA_SHADOW_LEADERS=10`; Copy Top 10 bot copies within `60` s at `10%` of equity.
- The project is not a git repo today; Task 0 initialises one so each task can commit.

## Review Focus

1. A Claude sends `"usd": 40` (under the $50 minimum): the buy must be refused and the refusal text must appear in its next `recent_failures`, not vanish silently. (Task 7 test `test_min_buy_refused_and_explained`.)
2. PumpPortal reconnects after an outage and replays a burst of 200 launches at once: the probation poll must cap DexScreener requests per cycle instead of firing 7 requests of 30 at once on top of the normal refresh. (Task 2 test `test_probation_poll_caps_requests`.)
3. A graduate migrated 7 hours ago is still held by a Claude: it must stay priced and tradable even though it left the `graduates` lane. (Task 3 test `test_held_token_outside_lanes_still_in_positions`.)
4. The realized leaderboard is empty for the first hour of a fresh database: Shadow and Copy Top 10 must idle with a clear note, not crash on an empty leader set. (Task 6 test `test_leader_set_empty_note`.)
5. The `claude` CLI prints `[claude-code:unrecognized_model]` for Haiku 5.5 on stderr: the backend must ignore that line and still parse the `result` JSON. (Task 8 test `test_model_label_haiku_55` plus the manual CLI check in Task 11.)

---

### Task 0: Test harness and repository

**Files:**
- Create: `tests/conftest.py`, `tests/__init__.py`, `.gitignore`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `pytest` runnable from the project root with `python -m pytest tests -q`; modules importable as `import arena`, `import market` from tests.

- [ ] **Step 1: Install pytest and add it to requirements**

Run: `python -m pip install pytest` then append `pytest>=8` to `requirements.txt`.

- [ ] **Step 2: Write `tests/conftest.py`**

Add the project root to `sys.path` (parent of `tests/`) and set `os.environ.setdefault("ARENA_PUMPFUN", "0")` so no test opens the websocket. Create empty `tests/__init__.py`.

- [ ] **Step 3: Write a smoke test `tests/test_smoke.py`**

```python
def test_imports():
    import arena, market, exchange, claude_agents, bots, traders, copy_agents  # noqa: F401
```

- [ ] **Step 4: Run it**

Run: `python -m pytest tests -q`
Expected: `1 passed`

- [ ] **Step 5: Initialise git and commit**

Write `.gitignore` with `arena.db`, `arena_mock.db`, `*.db-journal`, `recordings/`, `journal_backups/`, `logs/`, `__pycache__/`, `.env`, `stop.flag`. Then:

```bash
git init && git add -A && git commit -m "chore: test harness, gitignore, baseline before run 8"
```

---

### Task 1: `pumpfun` exchange route

**Files:**
- Modify: `exchange.py:60-76` (ROUTES table, TIERED), `exchange.py:117-128` (`fee_text`)
- Test: `tests/test_exchange.py`

**Interfaces:**
- Produces: `ROUTES["pumpfun"] == (0.0, 0.0, 0.25, 3.0)`; `fee_text()` on that route returns a sentence containing `"pump.fun"` and `"$0.25"`; `pool_fee(token)` unchanged.

- [ ] **Step 1: Write the failing tests**

```python
import importlib, os

def _reload(route):
    os.environ["ARENA_ROUTE"] = route
    import exchange
    return importlib.reload(exchange)

def test_pumpfun_route_has_no_app_fee():
    ex = _reload("pumpfun")
    assert ex.FEE == 0.0 and ex.MIN_FEE_USD == 0.0 and ex.PRIORITY_FEE_USD == 0.25
    assert ex.app_fee(100) == 0.0

def test_pumpfun_curve_fee_is_125_bps():
    ex = _reload("pumpfun")
    assert ex.pool_fee({"source": "pumpfun"}) == 0.0125
    assert ex.pool_fee({"dex": "pumpswap", "mcap": 200 * 150}) == 0.0125

def test_pumpfun_fee_text_names_the_route():
    ex = _reload("pumpfun")
    s = ex.fee_text()
    assert "pump.fun" in s and "$0.25" in s
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_exchange.py -v`
Expected: the first and third FAIL (route falls back to `bot`: `FEE == 0.01`).

- [ ] **Step 3: Implement**

Add `"pumpfun": (0.0, 0.0, 0.25, 3.0)` to `ROUTES` and the `ARENA_ROUTE` docstring line: `pumpfun  pump.fun's own site: no app fee, the venue's pool fee (1.25% on the curve, PumpSwap tiers after), $0.25 network/priority fee, no sandwich protection`. In `fee_text()`, before the generic branch, return for `ROUTE == "pumpfun"`: `"pump.fun's own fees: 1.25% on the bonding curve and 0.30-1.25% on PumpSwap by market cap, plus a $0.25 network fee per transaction (no app fee)"`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_exchange.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add exchange.py tests/test_exchange.py && git commit -m "feat(exchange): pumpfun route"
```

---

### Task 2: pump.fun-only universe in the market

**Files:**
- Modify: `market.py:20-70` (settings docstring), `market.py:125-145` (constants), `market.py:306-335` (`LiveMarket.__init__`), `market.py:352-368` (`_discover`), `market.py:369-414` (`_discover_pumpfun`), `market.py:513-556` (`quota`, `_evict`), `market.py:560-575` (`track`), `market.py:232-236` (`_annotate`)
- Test: `tests/test_market_pumpfun.py`

**Interfaces:**
- Produces: module constants `UNIVERSE` (`"all"`|`"pumpfun"`), `PROBATION_MIN`, `TRACK_MCAP_USD`, `TRACK_VOL_USD`, `GRADUATION_CAP_USD = 69000`; `LiveMarket.__init__(..., max_tracked=None)` resolving to 150 in pumpfun mode; `LiveMarket._probation_poll(now) -> dict[addr, "pumpfun"]`; `LiveMarket.probation` (dict addr -> launch meta); every tracked curve token carries `t["pump"]["curve_pct"]` (float 0-100) after `_annotate`; `track()` returns `None` for non-pump mints in pumpfun mode (a mint is pump.fun if it ends in `"pump"` or has `pump` meta).

- [ ] **Step 1: Write the failing tests**

Use a `LiveMarket` built with `requests` patched: monkeypatch `LiveMarket._get` to return canned DexScreener pair lists, and set a fake `self.pump` object exposing `new_tokens(since)` and `graduations(since)`.

```python
def test_pumpfun_mode_skips_other_feeds(monkeypatch):
    m = _market(monkeypatch, universe="pumpfun")
    m._discover_dexscreener = lambda: (_ for _ in ()).throw(AssertionError("called"))
    m._discover_gecko = lambda: (_ for _ in ()).throw(AssertionError("called"))
    assert m._discover() == {}  # feed empty, nothing else consulted

def test_probation_promotes_on_mcap(monkeypatch):
    m = _market(monkeypatch, universe="pumpfun", launches=[_launch("A1pump", mcap_sol=31)],
                pairs={"A1pump": _pair("A1pump", mcap=15000, vol_h1=100, txns=5)})
    found = m._probation_poll(now=_NOW)
    assert found == {"A1pump": "pumpfun"}

def test_probation_promotes_on_volume(monkeypatch):
    m = _market(monkeypatch, universe="pumpfun", launches=[_launch("B2pump", mcap_sol=31)],
                pairs={"B2pump": _pair("B2pump", mcap=4000, vol_h1=9000, txns=45)})
    assert m._probation_poll(now=_NOW) == {"B2pump": "pumpfun"}

def test_probation_ignores_quiet_and_old(monkeypatch):
    old = _launch("C3pump", mcap_sol=31, ts=_NOW - 25 * 60)
    quiet = _launch("D4pump", mcap_sol=31)
    m = _market(monkeypatch, universe="pumpfun", launches=[old, quiet],
                pairs={"D4pump": _pair("D4pump", mcap=3000, vol_h1=500, txns=10)})
    assert m._probation_poll(now=_NOW) == {}
    assert "C3pump" not in m.probation

def test_probation_poll_caps_requests(monkeypatch):
    calls = []
    m = _market(monkeypatch, universe="pumpfun", launches=[_launch(f"L{i:03d}pump", mcap_sol=31) for i in range(200)],
                pairs={}, on_get=calls.append)
    m._probation_poll(now=_NOW)
    assert len(calls) <= 4  # 4 requests x 30 addresses per cycle at most

def test_curve_pct_annotated():
    from market import _annotate
    t = {"price": 1e-6, "liquidity": 5000, "mcap": 34500, "source": "pumpfun", "dex": "pumpfun", "pump": {"launched": 1}}
    _annotate(t)
    assert t["pump"]["curve_pct"] == 50.0

def test_track_refuses_non_pump_mint_in_pumpfun_mode(monkeypatch):
    m = _market(monkeypatch, universe="pumpfun")
    assert m.track("So11111111111111111111111111111111111111113", source="copy") is None
    assert m.track("E5pump", source="copy") is not None

def test_evict_drops_dead_launch_first(monkeypatch):
    m = _market(monkeypatch, universe="pumpfun")
    m.max_tracked = 2
    m.tokens = {"X1pump": {"address": "X1pump", "price": 1, "high": 100, "source": "pumpfun", "first_seen": 1},
                "X2pump": {"address": "X2pump", "price": 50, "high": 60, "source": "pumpfun", "first_seen": 2},
                "X3pump": {"address": "X3pump", "price": 5, "high": 5, "source": "graduated", "first_seen": 3}}
    m._evict(held=set(), now=_NOW)
    assert "X1pump" not in m.tokens  # down >90% from its high goes first
```

`_market(monkeypatch, universe, launches=(), pairs={}, on_get=None)` is a test helper in the same file: sets `market.UNIVERSE`, builds `LiveMarket()`, installs a fake `pump` with `new_tokens`/`graduations`, patches `_get` to serve `pairs` for `/tokens/v1/solana/...` URLs (calling `on_get(url)` when given). `_NOW` is a fixed epoch; `_launch(mint, mcap_sol, ts=_NOW-120)` returns a PumpPortal-shaped dict with `initial_buy_sol=1.0`; `_pair(addr, mcap, vol_h1, txns)` returns a DexScreener pair dict with `dexId="pumpfun"`.

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_market_pumpfun.py -v`
Expected: FAIL (`UNIVERSE`, `_probation_poll`, `probation` missing).

- [ ] **Step 3: Implement the constants and constructor**

Add `UNIVERSE = os.environ.get("ARENA_UNIVERSE", "all").strip().lower()` (anything but `pumpfun` -> `all`), `PROBATION_MIN`, `TRACK_MCAP_USD`, `TRACK_VOL_USD`, `GRADUATION_CAP_USD = 69000`. In pumpfun mode force `ORGANIC_SHARE`/promoted discovery off (`_discover` skips both feeds) and `PUMPFUN_SHARE = 1.0`. `LiveMarket.__init__(self, max_tracked=None, ...)`: `self.max_tracked = max_tracked or (150 if UNIVERSE == "pumpfun" else 60)`; add `self.probation = {}` (mint -> launch dict + `first_seen`) and `self.probation_stats = {"polled": 0, "promoted": 0, "expired": 0}`.

- [ ] **Step 4: Implement `_probation_poll(self, now) -> dict`**

Called from `_discover_pumpfun` in pumpfun mode instead of the `good[:PUMPFUN_NEW]` block (old block stays for `all`). Add every launch from `self.pump.new_tokens(...)` that passes the creator-buy floor to `self.probation`; drop entries older than `PROBATION_MIN` minutes. Price at most 120 addresses per cycle (4 `_fetch_pairs`-style requests), oldest-unpolled first, using the existing `_fetch_pairs` so curve liquidity is filled in. Promote when `mcap >= TRACK_MCAP_USD` or (`vol_h1 >= TRACK_VOL_USD` and `buys_h1 + sells_h1 >= 40`); promoted mints move their meta into `self._pump_meta` exactly as the old block did and leave probation. Count stats.

- [ ] **Step 5: Implement `curve_pct`, the pump-only `track()` guard and dead-launch eviction**

In `_annotate`, when `t.get("dex") == "pumpfun"` or `t.get("source") == "pumpfun"`, set `t.setdefault("pump", {})["curve_pct"] = round(min(100.0, (t.get("mcap") or 0) / GRADUATION_CAP_USD * 100), 1)`; also maintain `t["high"] = max(t.get("high") or 0, price)` for every priced token. In `track()`, return `None` in pumpfun mode unless `mint.endswith("pump")` or `mint in self._pump_meta` or the existing token has `pump` meta. In `_evict`, before the existing `dead` rule, collect free launches with `price <= 0.1 * high` into `dead` as well.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_market_pumpfun.py -v`
Expected: 8 passed.

- [ ] **Step 7: Update the settings docstring and commit**

Document `ARENA_UNIVERSE`, `ARENA_PUMPFUN_PROBATION_MIN`, `ARENA_PUMPFUN_TRACK_MCAP_USD`, `ARENA_PUMPFUN_TRACK_VOL_USD` in the `market.py` docstring in the existing format.

```bash
git add market.py tests/test_market_pumpfun.py && git commit -m "feat(market): pump.fun-only universe with launch probation"
```

---

### Task 3: Two candidate lanes and the pump.fun brief

**Files:**
- Modify: `claude_agents.py:495-515` (`_state` candidates), `claude_agents.py:36-160` (brief), `claude_agents.py:171-192` (`fill_brief`), `claude_agents.py:787-800` (`build_llm_agents` defaults), `claude_agents.py:274-278` (`model_label`)
- Test: `tests/test_lanes.py`

**Interfaces:**
- Consumes: `t["pump"]["graduated"]`, `t["pump"]["curve_pct"]` from Task 2; `v["chg_since"][addr]` (existing).
- Produces: `claude_agents.build_lanes(candidates, vetoed, chg_since, now) -> {"graduates": [...], "curve": [...]}` (pure function, each list already formatted like today's candidate dicts plus `minutes_since_graduation` / `curve_pct` / `curve_pct_chg_10m`); `_state` emits `graduates` and `curve` keys and no `candidates` key when `UNIVERSE == "pumpfun"`; `model_label("claude-haiku-5-5") == "Haiku 5.5"`.

- [ ] **Step 1: Write the failing tests**

```python
from claude_agents import build_lanes, model_label

def test_lanes_split_and_sort():
    now = 1_000_000
    g_new = _tok("G1pump", pump={"graduated": now - 600})
    g_old = _tok("G2pump", pump={"graduated": now - 7 * 3600})
    c_fast = _tok("C1pump", dex="pumpfun", pump={"curve_pct": 40.0})
    c_slow = _tok("C2pump", dex="pumpfun", pump={"curve_pct": 60.0})
    chg = {"C1pump": {"curve_pct_10m": 25.0}, "C2pump": {"curve_pct_10m": 58.0}}
    lanes = build_lanes([g_new, g_old, c_fast, c_slow], vetoed={}, chg_since=chg, now=now)
    assert [t["token"] for t in lanes["graduates"]] == ["G1pump"]
    assert lanes["graduates"][0]["minutes_since_graduation"] == 10
    assert [t["token"] for t in lanes["curve"]] == ["C1pump", "C2pump"]  # +15 momentum before +2

def test_lanes_cap_and_hide_vetoed():
    now = 1_000_000
    toks = [_tok(f"G{i}pump", pump={"graduated": now - i * 60}) for i in range(20)]
    lanes = build_lanes(toks, vetoed={"G0pump": ["rug"]}, chg_since={}, now=now)
    assert len(lanes["graduates"]) == 15 and lanes["graduates"][0]["token"] == "G1pump"

def test_model_label_haiku_55():
    assert model_label("claude-haiku-5-5") == "Haiku 5.5"

def test_held_token_outside_lanes_still_in_positions():
    # an LLMAgent._state with a 7h-old graduate held: positions keep it, lanes don't list it
    ...
```

`_tok(addr, **extra)` builds a minimal market token dict (price, liquidity, mcap, vol_h1, buys/sells, chg fields, rating "green", flags []). The last test constructs an `LLMAgent` with a stub backend (`model="claude-haiku-5-5"`, `label=""`) and calls `_state` with a view holding one position whose token is not in `candidates`.

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_lanes.py -v`
Expected: FAIL (`build_lanes` missing; `model_label` returns `"Haiku 5.5"` already, that one passes).

- [ ] **Step 3: Implement `build_lanes` and wire `_state`**

Move the per-candidate formatting of `_state` into `_format_candidate(t, v, structure)` and write `build_lanes` on top of it. Graduates: `pump.graduated` within 6h, newest first, cap 15, add `minutes_since_graduation` (int). Curve: `dex == "pumpfun"` or source `pumpfun` without `graduated`, cap 15, sorted by `(-(curve_pct - curve_pct_10m), -curve_pct)` with `curve_pct_chg_10m` added; `curve_pct_10m` comes from `chg_since[addr]` (Task 3 also adds it to `Arena.chg_since` in `arena.py`: store `curve_pct` alongside price in the 30-second history and report the value 10 minutes ago). In pumpfun mode `_state` sets `state["graduates"], state["curve"]` and omits `candidates`; otherwise unchanged.

- [ ] **Step 4: Brief and defaults**

In `LLM_SYSTEM` (pumpfun mode only, via a `{UNIVERSE_TEXT}` placeholder filled in `fill_brief`): replace the "candidates: the busiest tokens" paragraph with a `graduates` / `curve` description and add a pump.fun paragraph: the bonding curve fills at about $69k market cap and the coin migrates to PumpSwap; `curve_pct` is progress toward that; most graduates lose most of their value within 20 minutes of migrating and the first minute after launch or migration is the snipers' exit; fees come from `{FEE_TEXT}` as now. Change `next_check_min` wording to "from {MIN_CHECK} to {MAX_CHECK} minutes; look every minute if the market calls for it". In `build_llm_agents` change the defaults to `ARENA_LLM_MIN_CHECK=1`, `ARENA_LLM_MAX_CHECK=60`.

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add claude_agents.py arena.py tests/test_lanes.py && git commit -m "feat(claude): graduate and curve lanes, pump.fun brief, free cadence"
```

---

### Task 4: Realized leaderboard and the Copy Top 10 bot

**Files:**
- Modify: `traders.py:117-140` (constants), `traders.py:295-331` (`human_reason`, `rank_wallets`), `copy_agents.py:15-18` (constants), `copy_agents.py:86-87` (`build_copy_bots`), `agents.py:16-24` (`build_bots`)
- Test: `tests/test_ranking.py`

**Interfaces:**
- Produces: `traders.RANK` (`"pnl"`|`"realized"`); `rank_wallets(stats, top_n, banned=None, rule=None)` sorting by `realized_usd` under `realized` with eligibility `round_trips >= 5`, `win_rate >= 50`, `tokens_bought >= 3`; `copy_agents.CopyBot(name, lo, hi, avatar, fraction=COPY_FRACTION, window_secs=COPY_WINDOW_SECS)`; `copy_agents.build_copy_top10() -> CopyBot("Copy Top 10", 1, 10, "copy-a", fraction=0.10, window_secs=60)`; `agents.build_bots()` returns `[RandomAgent(), HoldSolAgent(), GraduatesAgent(), build_copy_top10()]`.

- [ ] **Step 1: Write the failing tests**

```python
from traders import rank_wallets

def _st(w, realized, unreal, rts, win, toks):
    return {"wallet": w, "pnl_usd": realized + unreal, "realized_usd": realized, "unrealized_usd": unreal,
            "roi_pct": 10, "trades": 20, "buys": 10, "sells": 10, "tokens": toks, "tokens_bought": toks, "held": 1,
            "win_rate": win, "volume_usd": 5000, "spent_usd": 2500, "first_trade_ts": 0, "last_trade_ts": 0,
            "flips": 0, "round_trips": rts, "same_block": 0}

def test_realized_rule_ignores_unrealized():
    stats = {"bag": _st("bag", 100, 20000, 6, 60, 4), "pro": _st("pro", 900, -50, 8, 70, 5)}
    assert [s["wallet"] for s in rank_wallets(stats, 10, rule="realized")] == ["pro", "bag"]
    assert [s["wallet"] for s in rank_wallets(stats, 10, rule="pnl")] == ["bag", "pro"]

def test_realized_rule_eligibility():
    stats = {"few": _st("few", 900, 0, 4, 80, 5), "lossy": _st("lossy", 900, 0, 9, 40, 5), "ok": _st("ok", 10, 0, 5, 50, 3)}
    assert [s["wallet"] for s in rank_wallets(stats, 10, rule="realized")] == ["ok"]

def test_copy_top10_bot():
    from copy_agents import build_copy_top10
    b = build_copy_top10()
    assert (b.name, b.lo, b.hi, b.fraction, b.window_secs) == ("Copy Top 10", 1, 10, 0.10, 60)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_ranking.py -v`
Expected: FAIL (`rule` kwarg unknown, `build_copy_top10` missing).

- [ ] **Step 3: Implement**

`RANK = os.environ.get("ARENA_TRADERS_RANK", "pnl")`. `rank_wallets(..., rule=None)`: `rule = rule or RANK`; under `realized`, filter with `human_reason` plus the three thresholds (new constants `REAL_MIN_ROUND_TRIPS=5`, `REAL_MIN_WIN=50`, `REAL_MIN_TOKENS=3`, env-overridable), sort by `(-realized_usd, -roi_pct, -volume_usd)`. `CopyBot.__init__` takes `fraction` and `window_secs` and uses them in `decide` instead of the module constants. Add `build_copy_top10()`. `agents.build_bots()` adds it. The `Copy Top 10` description must say "ranked by realized profit over the last two days".

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add traders.py copy_agents.py agents.py tests/test_ranking.py && git commit -m "feat(copy): realized leaderboard rule and Copy Top 10 yardstick"
```

---

### Task 5: Offline copy backtest

**Files:**
- Create: `backtest_copy.py`, `reports/copy_backtest.md` (output)

**Interfaces:**
- Consumes: `traders.score_wallets`, `traders.rank_wallets(rule=...)`; tables `copy_trades`, recordings in `recordings/*.jsonl.gz` (skip truncated files with `EOFError`, read with `encoding="utf-8"`).
- Produces: CLI `python backtest_copy.py [--db arena.db] [--hours 1 6] [--tops 5 10 20]` printing and writing a markdown table: rows = rule x top-N, columns = leader buys copied, mean/median forward return at each horizon after 5% cost, share positive; plus a one-line recommendation (best rule and N by 6h mean, or "no copy edge measurable" when every mean is <= 0).

- [ ] **Step 1: Write the script**

Algorithm: load trades (ts, wallet, mint, kind, usd, qty, price) and the price index from recordings (as in the diagnosis replay: `{mint: [(ts, price)]}`). For each hour `H` in the data span, rank wallets with `score_wallets(trades_before_H, now=H)` under each rule (window 48h), take the top N, and for every buy by one of them in `[H, H+1h)` compute the forward return from the recorded price at `buy_ts + 60s` to `buy_ts + horizon`, minus 5 points. Skip buys with no price within 10 minutes at either end. Aggregate per (rule, N, horizon).

- [ ] **Step 2: Run it on the real database**

Run: `python backtest_copy.py --db arena.db`
Expected: a table printed and `reports/copy_backtest.md` written; the run finishes in under ten minutes.

- [ ] **Step 3: Apply the result**

Set `ARENA_TRADERS_RANK` and `ARENA_SHADOW_LEADERS` in `.env` (Task 10) to the winning rule and N. If nothing beats zero, keep `realized` / 10 and put the sentence "No copy edge was measurable on 2 days of data" at the top of the report.

- [ ] **Step 4: Commit**

```bash
git add backtest_copy.py reports/copy_backtest.md && git commit -m "feat: offline copy-trading backtest"
```

---

### Task 6: Shadow follows a leader set

**Files:**
- Modify: `arena.py:511-537` (`shadow_leader` -> `shadow_leaders`), `arena.py:559-583` (`leader_view` -> `your_leaders`), `arena.py:490-510` (`_leader_trades`), the position-level "sell when the leader sells" check (grep `leader` in `arena.py` fast-exit section around lines 940-990), `claude_agents.py:215-233` (shadow persona text), `claude_agents.py` `_state` key `your_leaders`
- Test: `tests/test_shadow.py`

**Interfaces:**
- Produces: `Arena.shadow_leaders(name, now) -> list[dict]` (top `SHADOW_LEADERS` from `tracker.top()` that traded in the last 6h, persisted under `__leaders__:<name>` for 6h); `Arena.leader_view(name, now) -> {"leaders": [{wallet, rank, record_48h, latest_trades (last 30 min, with skip_reasons), seems_to_hold}], "note": ...}` or `{"note": "No leaders yet: ..."}`; positions opened by a shadow buy store `copied_wallet` (the leader whose buy the Claude cited via an optional order field `"following": "<wallet prefix>"`); the arena sells a shadow's position when THAT wallet sells.

- [ ] **Step 1: Write the failing tests**

```python
def test_leader_set_empty_note(arena_with_stub_tracker):
    a = arena_with_stub_tracker(top=[])
    assert a.leader_view("Haiku Shadow", now=_NOW)["note"].startswith("No leaders yet")

def test_leader_set_takes_top_n_fresh(arena_with_stub_tracker, monkeypatch):
    monkeypatch.setattr("arena.SHADOW_LEADERS", 3)
    top = [_leader(i, last_trade=_NOW - 60) for i in range(1, 6)] + [_leader(9, last_trade=_NOW - 9 * 3600)]
    a = arena_with_stub_tracker(top=top)
    assert [l["rank"] for l in a.shadow_leaders("Haiku Shadow", _NOW)] == [1, 2, 3]

def test_sell_when_copied_wallet_sells(arena_with_stub_tracker):
    ...  # position with copied_wallet="W1"; a signal {"wallet": "W1", "side": "sell", "mint": "M1pump"} queues a full sell
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_shadow.py -v`
Expected: FAIL (`shadow_leaders` missing).

- [ ] **Step 3: Implement**

Add `SHADOW_LEADERS = int(os.environ.get("ARENA_SHADOW_LEADERS", "10"))` in `arena.py`. `shadow_leaders` keeps the old eligibility (`pnl_usd > 0`, `tokens >= 3`, `flips <= 1`, `6 <= trades <= 150`, fresh) but returns the top N by rank; persist the wallet list. `leader_view` builds one entry per leader (reuse the existing per-wallet code in a helper `_leader_entry(w, lead, now)`, trades limited to the last 30 minutes, `seems_to_hold` capped at 5). Buy orders accept `"following"`: the arena matches it against the leader set and stores `copied_wallet` on the position; the leader-sell exit loops over positions with `copied_wallet` and the tracker's sell signals. Shadow persona text: "your_leaders lists the top wallets the arena picked ... when one of them buys a coin that passes your checks you may buy too, and name it with "following" so the arena sells when that wallet sells."

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add arena.py claude_agents.py tests/test_shadow.py && git commit -m "feat(shadow): follow a set of leaders"
```

---

### Task 7: Churn control for Claude agents

**Files:**
- Modify: `arena.py:716-752` (`validate`), `arena.py:119-150` (`__init__`: constants), `arena.py:1063-1070` (where `validate` is called: record refusals)
- Test: `tests/test_churn.py`

**Interfaces:**
- Produces: `arena.MAX_BUYS_PER_DAY`, `arena.MIN_BUY_USD`, `arena.BUY_COOLDOWN_MIN` from env; `Arena.validate` returns `None` for an LLM buy that breaks a rule and appends `{"ts", "action": "buy", "token", "symbol", "usd", "reason", "text"}` to `acct["recent_failures"]` with `text` of the form `"your buy of SYM ($40) was refused: under the $50 minimum"` / `"...: 6 buys in the last 24 hours (limit 6)"` / `"...: 12 minutes since your last buy (30 minute cooldown)"`. Bots are exempt. Sells and `exits` are never refused by these rules.

- [ ] **Step 1: Write the failing tests**

```python
def test_min_buy_refused_and_explained(arena_llm):
    a, name, view = arena_llm()
    assert a.validate(a.agents[name], {"action": "buy", "token": "T1pump", "usd": 40, "reason": "x"}, view) is None
    assert "under the $50 minimum" in a.accounts[name]["recent_failures"][-1]["text"]

def test_daily_buy_cap(arena_llm):
    a, name, view = arena_llm(buys_today=6)
    assert a.validate(a.agents[name], {"action": "buy", "token": "T1pump", "usd": 60}, view) is None
    assert "limit 6" in a.accounts[name]["recent_failures"][-1]["text"]

def test_cooldown(arena_llm):
    a, name, view = arena_llm(last_buy_min_ago=12)
    assert a.validate(a.agents[name], {"action": "buy", "token": "T1pump", "usd": 60}, view) is None
    assert "30 minute cooldown" in a.accounts[name]["recent_failures"][-1]["text"]

def test_bots_exempt(arena_llm):
    a, name, view = arena_llm(buys_today=20, bot=True)
    assert a.validate(a.agents[name], {"action": "buy", "token": "T1pump", "usd": 10}, view) is not None
```

`arena_llm` is a fixture building an `Arena` on `MockMarket` with one stub LLM agent (kind `"llm"`) and the `trades` table seeded through `db.add_trade` so the rolling-24h count and last-buy time come from the database.

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_churn.py -v`
Expected: FAIL (buys accepted).

- [ ] **Step 3: Implement**

Read the three env vars at module import. In `validate`, after the veto check and only for `agent.kind == "llm"`: count buys in `trades` for this agent since `now - 86400` plus pending buys; find the last buy ts; apply the three rules in the order minimum, cap, cooldown; on refusal call a new `self._refuse(name, o, text, now)` that appends to `recent_failures` (trim to 10) and returns `None`. Adding to a position you already hold still counts as a buy.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add arena.py tests/test_churn.py && git commit -m "feat(arena): daily buy cap, minimum size and cooldown for Claudes"
```

---

### Task 8: Roster, personas and names

**Files:**
- Modify: `claude_agents.py:201-233` (`PERSONAS`), `claude_agents.py:780-782` (`DEFAULT_LINEUP`), `claude_agents.py:248-250` (`CHARACTER["haiku"]` keep), `claude_agents.py:603-640` (`ClaudeCodeBackend.ask`: ignore stderr noise)
- Test: `tests/test_roster.py`

**Interfaces:**
- Produces: `DEFAULT_LINEUP == "claude-haiku-5-5:graduate,claude-haiku-5-5:runner,claude-haiku-5-5:skeptic,claude-haiku-5-5:shadow,claude-sonnet-5-5:graduate,claude-sonnet-5-5:shadow"`; agent names `Haiku Graduate`, `Haiku Runner`, `Haiku Skeptic`, `Haiku Shadow`, `Sonnet Graduate`, `Sonnet Shadow`; personas reworded per the spec (Runner: curve coins, never past 80% of the curve; Skeptic: graduates only; Shadow: leader set with `following`).

- [ ] **Step 1: Write the failing test**

```python
def test_default_lineup_names(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_MODELS", raising=False)
    monkeypatch.setenv("ARENA_LLM", "claude-code")
    monkeypatch.setattr("claude_agents.shutil.which", lambda _: "claude")
    from claude_agents import build_llm_agents
    names = [a.name for a in build_llm_agents()]
    assert names == ["Haiku Graduate", "Haiku Runner", "Haiku Skeptic", "Haiku Shadow", "Sonnet Graduate", "Sonnet Shadow"]
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_roster.py -v`
Expected: FAIL (five Sonnet names).

- [ ] **Step 3: Implement**

Change `DEFAULT_LINEUP`; rewrite the four persona strings; in `ClaudeCodeBackend.ask` nothing changes functionally (the result line is parsed from stdout already) but add a comment that `[claude-code:unrecognized_model]` on stderr is expected for new model ids. Update the run-history comment above `DEFAULT_LINEUP` with a "Run 8 (2026-10-07)" line.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add claude_agents.py tests/test_roster.py && git commit -m "feat(roster): Haiku 5.5 x4 + Sonnet 5.5 x2 for run 8"
```

---

### Task 9: Pre-registered verdict on the dashboard

**Files:**
- Modify: `arena.py:265-292` (`reset_money`: room post), `dashboard.html:1067-1088` (`renderTables`, Agents tab rows), `dashboard.html` polling (add a 60 s fetch of `/api/analytics`), `notifier.py` `_digest_text` (one verdict line per Claude)
- Test: `tests/test_verdict.py` (arena side only; the dashboard change is checked by eye in Task 11)

**Interfaces:**
- Consumes: `analytics.compute(...)["agents"][i]["readiness"]` = `{"checks", "passed", "total", "ready", "verdict"}` (existing).
- Produces: at `reset_money`, a room post by `"arena"`: `"Run {season+1} started: pump.fun only. Verdict per Claude after 7 days and 100 closed trades: beats Random, Hold SOL and Graduates after the luck check at 90% confidence, drawdown under 25%, profit factor over 1.2. Roster stays fixed until then."`; the Agents tab shows `verdict: pending (x of 7)` or `verdict: ready` under each Claude; the digest appends `Verdicts: Haiku Graduate 3/7, ...`.

- [ ] **Step 1: Write the failing test**

```python
def test_reset_posts_verdict_rule(arena_llm):
    a, name, _ = arena_llm()
    a.reset_money(keep_journals=True)
    posts = a.db.room_posts(limit=5)
    assert any("Verdict per Claude" in p["text"] for p in posts)
```

- [ ] **Step 2: Run it to see it fail**

Run: `python -m pytest tests/test_verdict.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Build the sentence from `analytics.READY` and `analytics.BENCHMARKS` so the numbers never drift. In `dashboard.html`, keep `analytics` in the page state (fetch every 60 s, ignore errors), and in the Agents table row for each `kind === "llm"` agent append a small `<div class="desc">verdict: …</div>`. In `_digest_text`, call `analytics.compute(self.arena, self.db, None)` inside a try/except and append the verdict line.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add arena.py dashboard.html notifier.py tests/test_verdict.py && git commit -m "feat: pre-registered verdict posted at run start and shown per Claude"
```

---

### Task 10: Launcher, env, mock market and smoke run

**Files:**
- Create: `start_arena.cmd`, `logs/.gitkeep`
- Modify: `.env`, `market.py:985-1000` (`MockMarket._spawn`: pump meta), `main.py:264` (pass nothing new; `LiveMarket()` already resolves `max_tracked`), `db.py:36-62` (`reset_money`: `VACUUM` after commit)

**Interfaces:**
- Produces: `start_arena.cmd` loops `python main.py %*` with a 15 s pause between exits until `stop.flag` exists, appending stdout/stderr to `logs\arena-YYYY-MM-DD.log`; `.env` gains `ARENA_ROUTE=pumpfun`, `ARENA_UNIVERSE=pumpfun`, `ARENA_TRADERS_RANK=<from Task 5>`, `ARENA_SHADOW_LEADERS=<from Task 5>`, `ARENA_LLM_MIN_CHECK=1`, `ARENA_LLM_MAX_CHECK=60`; `MockMarket` spawns a third of its tokens with `dex="pumpfun"` + `pump={"launched", "curve_pct"}` and a third with `source="graduated"` + `pump={"graduated"}` so the lanes are non-empty offline.

- [ ] **Step 1: Write the launcher**

```bat
@echo off
title Memecoin Arena
cd /d C:\Users\noahh\Downloads\memecoin-arena
if not exist logs mkdir logs
:loop
if exist stop.flag (echo stop.flag found, not restarting & goto end)
for /f "tokens=1-3 delims=/- " %%a in ("%date%") do set D=%%c-%%a-%%b
echo [%date% %time%] starting >> logs\arena-%D%.log
python main.py %* >> logs\arena-%D%.log 2>&1
echo [%date% %time%] exited with %errorlevel%, restarting in 15s >> logs\arena-%D%.log
timeout /t 15 /nobreak > nul
goto loop
:end
cmd /k
```

(The first run passes `--reset-money --keep-journals`; later restarts are started without arguments. A second file `start_arena_run8.cmd` calls `start_arena.cmd --reset-money --keep-journals` once.)

- [ ] **Step 2: Env, VACUUM and mock pump meta**

Edit `.env` as listed. In `db.reset_money`, after `c.commit()` run `c.execute("VACUUM")` (outside the lock is fine; it takes seconds on 380 MB). In `MockMarket._spawn`, cycle sources `pumpfun` / `graduated` / `organic`.

- [ ] **Step 3: Smoke run offline**

Run: `python main.py --mock --tick 5` for three minutes with `ARENA_LLM=off` in the environment, then open `http://localhost:8000`.
Expected: no tracebacks in the console; Graduates and Copy Top 10 appear on the Agents tab; the mock market shows `pumpfun` and `graduated` sources in `/api/state` (or the market panel).

- [ ] **Step 4: Full test run and commit**

Run: `python -m pytest tests -q`
Expected: all pass.

```bash
git add start_arena.cmd start_arena_run8.cmd .env.example market.py db.py && git commit -m "chore: run 8 launcher, env, mock pump.fun tokens"
```

(Commit `.env.example` with the same keys and placeholder secrets; `.env` itself stays ignored.)

---

### Task 11: Launch run 8 and verify the first hour

**Files:** none new.

- [ ] **Step 1: Verify Haiku 5.5 through the CLI once more**

Run: `claude -p --model claude-haiku-5-5 --tools "" --safe-mode --no-session-persistence --output-format json "Reply with exactly: ok"`
Expected: JSON with `"stop_reason":"end_turn"` (the `unrecognized_model` stderr line is fine).

- [ ] **Step 2: Stop the current arena and start run 8**

Close the running arena window (run 7 ends; its trades are archived by the reset). Double-click `start_arena_run8.cmd`.
Expected: the log shows `money reset: season 7 archived`, the room post with the verdict rule, `[market] discovered N graduated/pumpfun` within 5 minutes, and six Claude agents plus four bots on the dashboard.

- [ ] **Step 3: Check the first looks**

After 15 minutes, open the Decisions tab and `/api/analytics`.
Expected: each Haiku agent has made at least two looks; their `state` (visible in the decision record) contains `graduates` and `curve` lanes and no `candidates`; `measured_round_trip_cost_pct` reflects the pumpfun route; any refused buy shows up in `recent_failures` with the rule named.

- [ ] **Step 4: Check the Tailscale link on the phone and the digest time**

Open `https://desktop-4t0p72k.tail1b9781.ts.net`. Expected: the dashboard loads with the run 8 roster. Confirm `ARENA_ALERT_DIGEST_AT` is set to a time the user will see.

- [ ] **Step 5: Record the launch**

Append to `reports/copy_backtest.md` (or a new `reports/run8_launch.md`): launch time, roster, env values, and the verdict rule, and commit.

```bash
git add reports && git commit -m "docs: run 8 launched"
```
