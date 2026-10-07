import pytest

import arena
import db
import market
from claude_agents import LLMAgent

_NOW = 1_800_000_000


class _Backend:
    model = "claude-haiku-5-5"
    label = ""


class _Tracker:
    def __init__(self, top):
        self._top = top

    def top(self):
        return [dict(t) for t in self._top]

    def signals(self, since):
        return []


def _leader(rank, last_trade):
    """A leaderboard row that passes the shadow's checks (profitable, 3+ tokens, no flipping, 6-150 trades)."""
    return {"wallet": f"W{rank}" + "x" * 40 + f"END{rank}", "rank": rank, "pnl_usd": 1000.0 - rank, "roi_pct": 50.0,
            "win_rate": 0.6, "trades": 20, "tokens": 5, "volume_usd": 10000.0, "flips": 0, "last_trade_ts": last_trade}


@pytest.fixture
def arena_with_stub_tracker(tmp_path):
    def make(top):
        m = market.MockMarket(n=3, seed=1)
        a = arena.Arena(m, db.DB(tmp_path / "t.db"), [LLMAgent(_Backend(), persona="shadow")], start_cash=1000, tick=30)
        a.tracker = _Tracker(top)
        return a
    return make


def test_leader_set_empty_note(arena_with_stub_tracker):
    a = arena_with_stub_tracker(top=[])
    assert a.leader_view("Haiku Shadow", now=_NOW)["note"].startswith("No leaders yet")


def test_leader_set_takes_top_n_fresh(arena_with_stub_tracker, monkeypatch):
    monkeypatch.setattr("arena.SHADOW_LEADERS", 3)
    top = [_leader(i, last_trade=_NOW - 60) for i in range(1, 6)] + [_leader(9, last_trade=_NOW - 9 * 3600)]
    a = arena_with_stub_tracker(top=top)
    assert [l["rank"] for l in a.shadow_leaders("Haiku Shadow", _NOW)] == [1, 2, 3]


def _hold(a, token, **extra):
    """Give the shadow agent a position in `token` (added to the mock market) opened 10 minutes ago."""
    a.market.tokens[token] = {"address": token, "symbol": "M1", "price": 0.001, "liquidity": 20000.0, "mcap": 60000.0,
                              "rating": "green", "flags": []}
    a.accounts["Haiku Shadow"]["positions"][token] = {
        "symbol": "M1", "qty": 10000.0, "cost": 10.0, "opened": _NOW - 600, "entry_spot": 0.001,
        "liq_entry": 20000.0, "peak_price": 0.001, "peak_ts": _NOW - 600, **extra}


def test_sell_when_copied_wallet_sells(arena_with_stub_tracker, monkeypatch):
    sells = {"W1": [{"ts": _NOW - 60, "side": "sell", "token": "M1pump", "symbol": "M1", "usd": 50.0, "source": "helius"}]}
    monkeypatch.setattr(arena.Arena, "_leader_trades", lambda self, wallet, since: list(sells.get(wallet, [])))

    a = arena_with_stub_tracker(top=[_leader(1, last_trade=_NOW - 60)])
    _hold(a, "M1pump", copied_wallet="W1")
    a.check_managed(_NOW)
    queued = [o for n, o in a.pending if n == "Haiku Shadow" and o["token"] == "M1pump"]
    assert len(queued) == 1 and queued[0]["action"] == "sell" and queued[0]["fraction"] == 1.0
    assert queued[0]["reason"].startswith("leader sold")

    b = arena_with_stub_tracker(top=[_leader(1, last_trade=_NOW - 60)])
    _hold(b, "M1pump")  # no copied_wallet: the leader-sell rule leaves it alone
    b.check_managed(_NOW)
    assert not [o for n, o in b.pending if o["token"] == "M1pump"]


def test_buy_following_stores_copied_wallet(arena_with_stub_tracker, monkeypatch):
    monkeypatch.setattr("arena.SHADOW_LEADERS", 3)
    top = [_leader(i, last_trade=_NOW - 60) for i in range(1, 4)]
    a = arena_with_stub_tracker(top=top)
    a.clock = lambda: _NOW
    a.rng.random = lambda: 0.99  # no failed transactions
    agent = a.agents["Haiku Shadow"]
    tok = next(iter(a.market.tokens))
    w2 = top[1]["wallet"]
    for following, expect in ((f"{w2[:4]}…{w2[-4:]}", w2), ("nobody", None)):
        a.accounts["Haiku Shadow"]["positions"].clear()
        v = a.view("Haiku Shadow", _NOW)
        o = a.validate(agent, {"action": "buy", "token": tok, "usd": 20, "reason": "copy", "following": following}, v)
        assert o is not None
        a.execute("Haiku Shadow", o, _NOW)
        assert a.accounts["Haiku Shadow"]["positions"][tok].get("copied_wallet") == expect
