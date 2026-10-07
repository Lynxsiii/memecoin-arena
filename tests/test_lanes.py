from collections import deque

import market
from claude_agents import LLMAgent, build_lanes, fill_brief, LLM_SYSTEM, model_label


def _tok(addr, **extra):
    t = {"address": addr, "symbol": addr[:4], "price": 0.001, "liquidity": 20000.0, "mcap": 60000.0,
         "vol_h1": 10000.0, "buys_h1": 50, "sells_h1": 40, "chg_m5": 1.0, "chg_h1": 2.0, "chg_h24": 3.0,
         "age_min": 30, "rating": "green", "flags": [], "source": "pumpfun"}
    t.update(extra)
    return t


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
    assert lanes["curve"][0]["curve_pct"] == 40.0 and lanes["curve"][0]["curve_pct_chg_10m"] == 15.0


def test_lanes_cap_and_hide_vetoed():
    now = 1_000_000
    toks = [_tok(f"G{i}pump", pump={"graduated": now - i * 60}) for i in range(20)]
    lanes = build_lanes(toks, vetoed={"G0pump": ["rug"]}, chg_since={}, now=now)
    assert len(lanes["graduates"]) == 15 and lanes["graduates"][0]["token"] == "G1pump"


def test_lanes_tolerate_missing_optional_keys():
    now = 1_000_000
    t = _tok("C3pump", dex="pumpfun", pump={"curve_pct": 10.0})
    for k in ("chg_h24", "age_min", "flags", "rating"):
        del t[k]
    lanes = build_lanes([t], vetoed={}, chg_since={}, now=now)
    assert lanes["curve"][0]["token"] == "C3pump" and lanes["curve"][0]["curve_pct_chg_10m"] is None


def test_model_label_haiku_55():
    assert model_label("claude-haiku-5-5") == "Haiku 5.5"


class _Backend:
    model = "claude-haiku-5-5"
    label = ""


def _view(positions, candidates):
    return {"cash": 100.0, "equity": 150.0, "positions": positions, "candidates": candidates, "vetoes": {},
            "now": 1_000_000, "chg_since": {}}


def test_held_token_outside_lanes_still_in_positions(monkeypatch):
    # an LLMAgent._state with a 7h-old graduate held: positions keep it, lanes don't list it
    monkeypatch.setattr(market, "UNIVERSE", "pumpfun")
    agent = LLMAgent(_Backend())
    now = 1_000_000
    pos = {"token": "HELDpump", "symbol": "HELD", "value": 50.0, "cost": 40.0, "pnl_pct": 25.0, "price_chg_pct": 25.0,
           "held_min": 420, "rating": "green", "flags": [], "exits": {}}
    other = _tok("G9pump", pump={"graduated": now - 7 * 3600})
    state = agent._state(_view([pos], [other]))
    assert [p["token"] for p in state["positions"]] == ["HELDpump"]
    assert state["graduates"] == [] and state["curve"] == []
    assert "candidates" not in state


def test_all_mode_state_keeps_candidates(monkeypatch):
    monkeypatch.setattr(market, "UNIVERSE", "all")
    agent = LLMAgent(_Backend())
    state = agent._state(_view([], [_tok("A1pump")]))
    assert [t["token"] for t in state["candidates"]] == ["A1pump"]
    assert "graduates" not in state and "curve" not in state


def test_brief_universe_text(monkeypatch):
    monkeypatch.setattr(market, "UNIVERSE", "pumpfun")
    pf = fill_brief(LLM_SYSTEM, 1, 60)
    assert "graduates" in pf and "curve_pct" in pf and "$69k" in pf
    assert "look every minute if the market calls for it" in pf and "from 1 to 60 minutes" in pf
    assert "{" + "UNIVERSE_TEXT}" not in pf
    monkeypatch.setattr(market, "UNIVERSE", "all")
    al = fill_brief(LLM_SYSTEM, 1, 60)
    assert "candidates: the busiest tokens" in al and "$69k" not in al


def test_chg_since_reports_curve_pct_10m():
    import arena
    a = arena.Arena.__new__(arena.Arena)
    now = 10_000
    a.history = {"C1pump": deque([(now - 30 * i, 1.0) for i in range(25, -1, -1)], maxlen=130)}
    a.curve_history = {"C1pump": deque([(now - 30 * i, 50.0 - i) for i in range(25, -1, -1)], maxlen=130)}
    out = a.chg_since("C1pump", now)
    assert out["curve_pct_10m"] == 30.0  # 20 points of 30s back = 10 minutes ago
    assert out["curve_pct_10m_secs"] == 600


def test_fresh_curve_coin_gets_paced_momentum():
    """A coin tracked for 4 minutes that went 20 -> 30 fills at a 25-point 10-minute pace and outranks +5 over 10 min."""
    import arena
    a = arena.Arena.__new__(arena.Arena)
    now = 10_000
    a.history = {}
    a.curve_history = {
        "NEWpump": deque([(now - 30 * i, 30.0 - 10.0 * i / 8) for i in range(8, -1, -1)], maxlen=130),
        "OLDpump": deque([(now - 30 * i, 55.0 - 5.0 * i / 20) for i in range(25, -1, -1)], maxlen=130),
    }
    chg = {addr: a.chg_since(addr, now) for addr in a.curve_history}
    assert chg["NEWpump"] == {"curve_pct_10m": 20.0, "curve_pct_10m_secs": 240}
    assert chg["OLDpump"]["curve_pct_10m_secs"] == 600
    toks = [_tok("OLDpump", dex="pumpfun", pump={"curve_pct": 55.0}), _tok("NEWpump", dex="pumpfun", pump={"curve_pct": 30.0})]
    lanes = build_lanes(toks, vetoed={}, chg_since=chg, now=now)
    assert [t["token"] for t in lanes["curve"]] == ["NEWpump", "OLDpump"]
    assert lanes["curve"][0]["curve_pct_chg_10m"] == 25.0 and lanes["curve"][1]["curve_pct_chg_10m"] == 5.0
    assert "curve_pct_10m" not in lanes["curve"][0]["chg_since"] and "curve_pct_10m_secs" not in lanes["curve"][0]["chg_since"]


def test_curve_coin_under_two_minutes_has_no_momentum():
    import arena
    a = arena.Arena.__new__(arena.Arena)
    now = 10_000
    a.history = {}
    a.curve_history = {"NEWpump": deque([(now - 90, 10.0), (now - 60, 12.0), (now, 15.0)], maxlen=130)}
    assert a.chg_since("NEWpump", now) == {}


def test_brief_source_text_by_universe(monkeypatch):
    monkeypatch.setattr(market, "UNIVERSE", "pumpfun")
    pf = fill_brief(LLM_SYSTEM, 1, 60)
    assert '"promoted"' not in pf and '"organic"' not in pf
    assert '"graduated" (moved to PumpSwap)' in pf and "{" + "SOURCE_TEXT}" not in pf
    assert "scaled to a 10-minute pace" in pf
    monkeypatch.setattr(market, "UNIVERSE", "all")
    al = fill_brief(LLM_SYSTEM, 1, 60)
    assert '"promoted" (its team paid DexScreener' in al


def test_brief_states_buy_rations(monkeypatch):
    import arena
    monkeypatch.setattr(arena, "MAX_BUYS_PER_DAY", 6)
    monkeypatch.setattr(arena, "MIN_BUY_USD", 50.0)
    monkeypatch.setattr(arena, "BUY_COOLDOWN_MIN", 30.0)
    b = fill_brief(LLM_SYSTEM, 1, 60)
    assert "at most 6 buys per rolling 24 hours, at least $50 each, and 30 minutes between buys" in b


def test_state_passes_buy_budget(monkeypatch):
    monkeypatch.setattr(market, "UNIVERSE", "all")
    agent = LLMAgent(_Backend())
    v = {**_view([], []), "buy_budget": {"buys_left_24h": 2, "next_buy_in_min": 18}}
    assert agent._state(v)["buy_budget"] == {"buys_left_24h": 2, "next_buy_in_min": 18}
