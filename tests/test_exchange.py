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
