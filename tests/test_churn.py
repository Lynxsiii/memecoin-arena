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


def test_daily_buy_cap(arena_llm):
    a, name, view = arena_llm(buys_today=6)
    assert a.validate(a.agents[name], _buy(60), view) is None
    assert "6 buys in the last 24 hours (limit 6)" in _last(a, name)["text"]


def test_cooldown(arena_llm):
    a, name, view = arena_llm(last_buy_min_ago=12)
    assert a.validate(a.agents[name], _buy(60), view) is None
    assert "12 minutes since your last buy (30 minute cooldown)" in _last(a, name)["text"]


def test_bots_exempt(arena_llm):
    a, name, view = arena_llm(buys_today=20, bot=True)
    assert a.validate(a.agents[name], _buy(10), view) is not None
    assert a.accounts[name]["recent_failures"] == []


def test_valid_llm_buy_passes(arena_llm):
    a, name, view = arena_llm(buys_today=4, last_buy_min_ago=45)
    o = a.validate(a.agents[name], _buy(60), view)
    assert o is not None and o["usd"] == 60
    assert a.accounts[name]["recent_failures"] == []


def test_old_buys_do_not_count(arena_llm):
    a, name, view = arena_llm()
    for i in range(10):
        a.db.add_trade(view["now"] - 90000 - i, name, "buy", "T1pump", "T1", 60, 1, 1, 1, 0, "old")
    assert a.validate(a.agents[name], _buy(60), view) is not None


def test_pending_buys_count(arena_llm):
    a, name, view = arena_llm(buys_today=5)
    a.pending.append((name, {"action": "buy", "token": "T1pump", "usd": 60}))
    assert a.validate(a.agents[name], _buy(60), view) is None
    assert "6 buys in the last 24 hours" in _last(a, name)["text"]


def test_sells_never_refused(arena_llm):
    a, name, view = arena_llm(buys_today=6, last_buy_min_ago=1)
    view["positions"] = [{"token": "T1pump"}]
    o = a.validate(a.agents[name], {"action": "sell", "token": "T1pump", "fraction": 1.0}, view)
    assert o is not None and a.accounts[name]["recent_failures"] == []


def test_failures_trimmed_to_ten(arena_llm):
    a, name, view = arena_llm()
    for _ in range(12):
        a.validate(a.agents[name], _buy(10), view)
    assert len(a.accounts[name]["recent_failures"]) == 10
