import os
import sys

import pytest

# Must be set before any project module (market -> pumpfun) is imported,
# so no test opens the pump.fun websocket.
os.environ.setdefault("ARENA_PUMPFUN", "0")
# ...and no LiveMarket test reaches the real GeckoTerminal through the price fallback when its fake DexScreener
# leaves tokens unpriced (test_gecko_fallback.py turns it on with fake GeckoTerminal answers).
os.environ.setdefault("ARENA_GECKO_FALLBACK", "0")
# ...and no test ever spends StalkChain credits, even after main.py's load_dotenv() reads a real key from .env
# (load_dotenv only fills unset variables; test_stalkchain.py injects fake clients).
os.environ["ARENA_STALKCHAIN_KEY"] = ""

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def arena_llm(tmp_path):
    """Builds an Arena on a MockMarket with one stub agent (a Claude, or a bot with bot=True) and a tradable token
    "T1pump". buys_today=N seeds N buy rows in the trades table within the last 24 hours; last_buy_min_ago=M seeds
    one buy M minutes ago. Returns (arena, agent name, view)."""
    import time

    import agent_base
    import db as dbmod
    import market as marketmod
    from arena import Arena

    def make(buys_today=0, last_buy_min_ago=None, bot=False):
        class Stub(agent_base.Agent):
            kind = "bot" if bot else "llm"
            name = "Bot Test" if bot else "Haiku Test"
            max_trade_frac = 1.0
            max_positions = 8
            persona = None

        m = marketmod.MockMarket(n=3, seed=1)
        m.track("T1pump")
        d = dbmod.DB(tmp_path / "t.db")
        a = Arena(m, d, [Stub()], start_cash=1000, tick=30)
        name = Stub.name
        now = time.time()
        for i in range(buys_today):
            d.add_trade(now - 3600 * (i + 1) / 2, name, "buy", "T1pump", "T1", 60, 1, 1, 1, 0, "seed")
        if last_buy_min_ago is not None:
            d.add_trade(now - last_buy_min_ago * 60, name, "buy", "T1pump", "T1", 60, 1, 1, 1, 0, "seed")
        return a, name, a.view(name, now)

    return make
