import importlib
import os

import pytest


def _reload(route):
    os.environ["ARENA_ROUTE"] = route
    import exchange
    return importlib.reload(exchange)


@pytest.fixture(autouse=True)
def _restore_default_route():
    yield
    os.environ.pop("ARENA_ROUTE", None)
    import exchange
    importlib.reload(exchange)


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


def _rug_token():
    return {"price": 1.0, "liquidity": 20000.0}


def test_sell_quote_far_below_spot_is_trusted(capsys):
    """A rugged pool: the router values the sell at 1% of spot. The fill must follow the router, not the stale spot."""
    ex = _reload("jupiter")
    ex._low_note_at = -1e9
    qty = 1000.0  # spot value $1000
    proceeds, avg = ex.sell_fill(_rug_token(), qty, quote=lambda q: 10.0)
    assert proceeds == pytest.approx(10.0 - ex.PRIORITY_FEE_USD)
    assert avg == pytest.approx(proceeds / qty)
    assert "pool drained" in capsys.readouterr().out


def test_sell_low_quote_note_is_rate_limited(capsys):
    ex = _reload("jupiter")
    ex._low_note_at = -1e9
    for _ in range(5):
        ex.sell_fill(_rug_token(), 1000.0, quote=lambda q: 10.0)
    assert capsys.readouterr().out.count("pool drained") == 1


def test_sell_quote_far_above_spot_still_rejected():
    ex = _reload("jupiter")
    t = _rug_token()
    with_quote = ex.sell_fill(t, 1000.0, quote=lambda q: 100_000.0)
    assert with_quote == ex.sell_fill(t, 1000.0)  # fell back to the AMM formula


def test_buy_quote_far_below_spot_still_rejected():
    ex = _reload("jupiter")
    t = _rug_token()
    # a buy quote giving 0.01x the tokens spot implies (implied price 100x spot) is distrusted
    bad = lambda s: (s / t["price"]) * 0.01
    assert ex.buy_fill(t, 100.0, quote=bad) == ex.buy_fill(t, 100.0)
