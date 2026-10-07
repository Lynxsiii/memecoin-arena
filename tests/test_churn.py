import pytest

import arena


@pytest.fixture
def rations(monkeypatch):
    """The run-8 churn rules (6 buys per rolling 24 hours, 30 minute cooldown); run 8b turned both off by default."""
    monkeypatch.setattr(arena, "MAX_BUYS_PER_DAY", 6)
    monkeypatch.setattr(arena, "BUY_COOLDOWN_MIN", 30.0)


def _buy(usd, **kw):
    return {"action": "buy", "token": "T1pump", "usd": usd, "reason": "x", **kw}


def _last(a, name):
    return a.accounts[name]["recent_failures"][-1]


def test_min_buy_refused_and_explained(arena_llm):
    a, name, view = arena_llm()
    assert a.validate(a.agents[name], _buy(40), view) is None
    f = _last(a, name)
    assert "under the $50 minimum" in f["text"]
    assert f["action"] == "buy" and f["token"] == "T1pump" and f["usd"] == 40 and f["ts"] == view["now"]
    assert f["text"].startswith("your buy of ") and "($40) was refused" in f["text"]


def test_daily_buy_cap(arena_llm, rations):
    a, name, view = arena_llm(buys_today=6)
    assert a.validate(a.agents[name], _buy(60), view) is None
    assert "6 buys in the last 24 hours (limit 6)" in _last(a, name)["text"]


def test_cooldown(arena_llm, rations):
    a, name, view = arena_llm(last_buy_min_ago=12)
    assert a.validate(a.agents[name], _buy(60), view) is None
    assert "12 minutes since your last buy (30 minute cooldown)" in _last(a, name)["text"]


def test_bots_exempt(arena_llm):
    a, name, view = arena_llm(buys_today=20, bot=True)
    assert a.validate(a.agents[name], _buy(10), view) is not None
    assert a.accounts[name]["recent_failures"] == []


def test_valid_llm_buy_passes(arena_llm, rations):
    a, name, view = arena_llm(buys_today=4, last_buy_min_ago=45)
    o = a.validate(a.agents[name], _buy(60), view)
    assert o is not None and o["usd"] == 60
    assert a.accounts[name]["recent_failures"] == []


def test_old_buys_do_not_count(arena_llm):
    a, name, view = arena_llm()
    for i in range(10):
        a.db.add_trade(view["now"] - 90000 - i, name, "buy", "T1pump", "T1", 60, 1, 1, 1, 0, "old")
    assert a.validate(a.agents[name], _buy(60), view) is not None


def test_pending_buys_count(arena_llm, rations):
    a, name, view = arena_llm(buys_today=5)
    a.pending.append((name, {"action": "buy", "token": "T1pump", "usd": 60}))
    assert a.validate(a.agents[name], _buy(60), view) is None
    assert "6 buys in the last 24 hours" in _last(a, name)["text"]


def test_sells_never_refused(arena_llm, rations):
    a, name, view = arena_llm(buys_today=6, last_buy_min_ago=1)
    view["positions"] = [{"token": "T1pump"}]
    o = a.validate(a.agents[name], {"action": "sell", "token": "T1pump", "fraction": 1.0}, view)
    assert o is not None and a.accounts[name]["recent_failures"] == []


def test_failures_trimmed_to_ten(arena_llm):
    a, name, view = arena_llm()
    for _ in range(12):
        a.validate(a.agents[name], _buy(10), view)
    assert len(a.accounts[name]["recent_failures"]) == 10


def test_queued_buy_trips_cooldown_with_clear_text(arena_llm, rations):
    a, name, view = arena_llm()
    a.pending.append((name, {"action": "buy", "token": "T1pump", "usd": 60}))
    assert a.validate(a.agents[name], _buy(60), view) is None
    assert "a buy is already queued (30 minute cooldown)" in _last(a, name)["text"]


def test_env_names(monkeypatch):
    import importlib

    monkeypatch.setenv("ARENA_LLM_MIN_BUY_USD", "75")
    monkeypatch.setenv("ARENA_LLM_MAX_BUYS_PER_DAY", "3")
    monkeypatch.setenv("ARENA_LLM_BUY_COOLDOWN_MIN", "10")
    try:
        importlib.reload(arena)
        assert (arena.MIN_BUY_USD, arena.MAX_BUYS_PER_DAY, arena.BUY_COOLDOWN_MIN) == (75.0, 3, 10.0)
    finally:
        monkeypatch.undo()
        importlib.reload(arena)
    assert (arena.MIN_BUY_USD, arena.MAX_BUYS_PER_DAY, arena.BUY_COOLDOWN_MIN) == (50.0, 0, 0.0)


def test_view_buy_budget_counts_buys(arena_llm, rations):
    _, _, view = arena_llm(buys_today=4)
    assert view["buy_budget"]["buys_left_24h"] == 2


def test_view_buy_budget_cooldown(arena_llm, rations):
    _, _, view = arena_llm(last_buy_min_ago=12)
    assert view["buy_budget"] == {"buys_left_24h": 5, "next_buy_in_min": 18}


def test_view_buy_budget_free_and_bots(arena_llm, rations):
    _, _, view = arena_llm()
    assert view["buy_budget"] == {"buys_left_24h": 6, "next_buy_in_min": 0}
    _, _, bot_view = arena_llm(bot=True)
    assert "buy_budget" not in bot_view


def test_defaults_no_cap_no_cooldown(arena_llm):
    a, name, view = arena_llm(buys_today=20, last_buy_min_ago=1)
    a.pending.append((name, {"action": "buy", "token": "T1pump", "usd": 60}))
    assert "buy_budget" not in view
    o = a.validate(a.agents[name], _buy(60), view)
    assert o is not None and a.accounts[name]["recent_failures"] == []
    assert a.validate(a.agents[name], _buy(40), view) is None  # the $50 minimum stays
    assert "under the $50 minimum" in _last(a, name)["text"]


def test_brief_says_buy_as_often_as_you_like():
    from claude_agents import LLM_SYSTEM, fill_brief
    b = fill_brief(LLM_SYSTEM, 1, 60)
    assert "- Buy as often as you like; each buy must be at least $50." in b
    assert "rationed" not in b and "buy_budget" not in b
