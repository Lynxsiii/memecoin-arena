from backtest_copy import forward_return, price_at


def _px():
    # one snapshot every 30 s for two hours: price 1.0 until t=1000, then 2.0
    series = [(t, 1.0 if t < 1000 else 2.0) for t in range(0, 7200, 30)]
    return {"m": series, "gap": [(0, 1.0), (60, 1.0), (5000, 3.0)]}


def test_price_at_nearest_within_tolerance():
    s = _px()["gap"]
    assert price_at(s, 70) == 1.0
    assert price_at(s, 4500) == 3.0      # 500 s away: still "at"
    assert price_at(s, 2000) is None     # nothing within 600 s
    assert price_at([], 10) is None


def test_entry_is_buy_plus_60s_and_cost_is_subtracted():
    px = _px()
    # buy at 900: entry at 960 is still 1.0; exit at 900 + 3600 is 2.0 -> +100% - 5 points
    assert forward_return(px, "m", 900, 3600) == 95.0
    # buy at 950: entry at 1010 is already 2.0 -> flat, minus cost
    assert forward_return(px, "m", 950, 3600) == -5.0
    assert forward_return(px, "m", 900, 3600, cost_pct=0.0) == 100.0


def test_missing_price_returns_none():
    px = _px()
    assert forward_return(px, "nope", 900, 3600) is None
    # entry at 660 has a snapshot at 60 (600 s away) -> ok; exit at 2700 has nothing within 600 s
    assert forward_return(px, "gap", 600, 2100) is None
    # entry at 1860 has nothing within 600 s
    assert forward_return(px, "gap", 1800, 3600) is None
    # exit beyond the end of the recording
    assert forward_return(px, "m", 7000, 3600) is None
