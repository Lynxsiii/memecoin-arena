"""pump.fun-only universe (ARENA_UNIVERSE=pumpfun): discovery, launch probation, curve_pct, track() guard, eviction."""
import market
from market import LiveMarket

_NOW = 1_790_000_000.0
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _mint(tag):
    """A plausible 44-character base58 mint ending in "pump" built from a short tag such as "A1pump" (the market
    ignores implausible mints, and "0" is not base58)."""
    body = "".join(c if c in _B58 else "z" for c in tag.removesuffix("pump"))
    return body + "1" * (40 - len(body)) + "pump"


def _launch(mint, mcap_sol, ts=_NOW - 120):
    """A PumpPortal launch event as pumpfun.PumpFeed.new_tokens() returns it."""
    return {"mint": mint, "name": "Test " + mint[:4], "symbol": mint[:4].upper(), "creator": "Creator1111",
            "initial_buy_sol": 1.0, "mcap_sol": mcap_sol, "ts": ts, "curve": "Curve1111", "mayhem": False}


def _pair(addr, mcap, vol_h1, txns):
    """A DexScreener /tokens/v1 pair for a token still on its bonding curve."""
    return {"chainId": "solana", "dexId": "pumpfun", "pairAddress": "curve-" + addr[:8],
            "baseToken": {"address": addr, "symbol": addr[:4].upper(), "name": "Test " + addr[:4]},
            "priceUsd": f"{mcap / 1e9:.12f}", "marketCap": mcap, "fdv": mcap,
            "volume": {"h1": vol_h1, "h24": vol_h1}, "txns": {"h1": {"buys": txns - txns // 2, "sells": txns // 2}},
            "priceChange": {"m5": 0, "h1": 0, "h24": 0}, "liquidity": {"usd": 0}}


class _FakeFeed:
    def __init__(self, launches=(), grads=()):
        self.launches, self.grads = list(launches), list(grads)

    def new_tokens(self, since=0):
        return [dict(e) for e in self.launches if e["ts"] > since]

    def graduations(self, since=0):
        return [dict(e) for e in self.grads if e["ts"] > since]


def _market(monkeypatch, universe, launches=(), pairs=None, on_get=None):
    monkeypatch.setattr(market, "UNIVERSE", universe)
    if universe == "pumpfun":
        monkeypatch.setattr(market, "PUMPFUN_SHARE", 1.0)
    pairs = pairs or {}

    def fake_get(self, url):
        if on_get is not None:
            on_get(url)
        if "/tokens/v1/solana/" in url:
            return [pairs[a] for a in url.rsplit("/", 1)[1].split(",") if a in pairs]
        return None

    monkeypatch.setattr(LiveMarket, "_get", fake_get)
    m = LiveMarket()
    m.pump = _FakeFeed(launches)
    return m


def test_pumpfun_mode_skips_other_feeds(monkeypatch):
    m = _market(monkeypatch, universe="pumpfun")
    m._discover_dexscreener = lambda: (_ for _ in ()).throw(AssertionError("called"))
    m._discover_gecko = lambda: (_ for _ in ()).throw(AssertionError("called"))
    assert m._discover() == {}  # feed empty, nothing else consulted
    assert m.max_tracked == 500  # run 9b (was 150)
    assert m.quota() == {"pumpfun": 500, "organic": 0, "promoted": 0}


def test_probation_promotes_on_mcap(monkeypatch):
    a = _mint("A1pump")
    m = _market(monkeypatch, universe="pumpfun", launches=[_launch(a, mcap_sol=31)],
                pairs={a: _pair(a, mcap=15000, vol_h1=100, txns=5)})
    found = m._probation_poll(now=_NOW)
    assert found == {a: "pumpfun"}
    assert a not in m.probation
    assert m._pump_meta[a]["initial_buy_sol"] == 1.0 and m._pump_meta[a]["launched"] == _NOW - 120
    assert m.probation_stats["promoted"] == 1
    t = m._new_token(a, "pumpfun", _NOW)  # what refresh() does with the promoted address
    assert t["pump"]["launched"] == _NOW - 120 and t["symbol"] == a[:4].upper()


def test_probation_promotes_on_volume(monkeypatch):
    b = _mint("B2pump")
    m = _market(monkeypatch, universe="pumpfun", launches=[_launch(b, mcap_sol=31)],
                pairs={b: _pair(b, mcap=4000, vol_h1=9000, txns=45)})
    assert m._probation_poll(now=_NOW) == {b: "pumpfun"}


def test_probation_ignores_quiet_and_old(monkeypatch):
    c, d = _mint("C3pump"), _mint("D4pump")
    old = _launch(c, mcap_sol=31, ts=_NOW - (market.PROBATION_MIN + 5) * 60)
    quiet = _launch(d, mcap_sol=31)
    m = _market(monkeypatch, universe="pumpfun", launches=[old, quiet],
                pairs={d: _pair(d, mcap=3000, vol_h1=500, txns=10)})
    assert m._probation_poll(now=_NOW) == {}
    assert c not in m.probation
    assert d in m.probation  # still on probation, priced again on a later cycle


def test_probation_poll_caps_requests(monkeypatch):
    calls = []
    m = _market(monkeypatch, universe="pumpfun",
                launches=[_launch(_mint(f"L{i:03d}pump"), mcap_sol=31) for i in range(200)],
                pairs={}, on_get=calls.append)
    m._probation_poll(now=_NOW)
    assert len(calls) <= 4  # 4 requests x 30 addresses per cycle at most
    assert m.probation_stats["polled"] == 120
    m._probation_poll(now=_NOW + 120)  # the next cycle prices the 80 not polled yet first
    assert all(p.get("polled_at") for p in m.probation.values())
    assert sum(1 for p in m.probation.values() if p["polled_at"] == _NOW + 120) == 120


def test_curve_pct_annotated():
    from market import _annotate
    t = {"price": 1e-6, "liquidity": 5000, "mcap": 25_000, "source": "pumpfun", "dex": "pumpfun",
         "pump": {"launched": 1}}
    _annotate(t, cap_usd=50_000)
    assert t["pump"]["curve_pct"] == 50.0
    _annotate(t, cap_usd=20_000)
    assert t["pump"]["curve_pct"] == 100.0  # capped at 100
    assert t["high"] == 1e-6
    g = {"price": 2e-6, "mcap": 30000, "source": "graduated", "dex": "pumpswap",
         "pump": {"launched": 1, "graduated": 2, "curve_pct": 43.5}}
    _annotate(g)
    assert g["pump"]["curve_pct"] == 100.0  # graduates never keep a stale curve value


def test_track_refuses_non_pump_mint_in_pumpfun_mode(monkeypatch):
    m = _market(monkeypatch, universe="pumpfun")
    assert m.track("So11111111111111111111111111111111111111113", source="copy") is None
    assert m.track(_mint("E5pump"), source="copy") is not None


def test_evict_drops_dead_launch_first(monkeypatch):
    m = _market(monkeypatch, universe="pumpfun")
    m.max_tracked = 2
    m.tokens = {"X1pump": {"address": "X1pump", "price": 1, "high": 100, "source": "pumpfun", "first_seen": 1},
                "X2pump": {"address": "X2pump", "price": 50, "high": 60, "source": "pumpfun", "first_seen": 2},
                "X3pump": {"address": "X3pump", "price": 5, "high": 5, "source": "graduated", "first_seen": 3}}
    m._evict(held=set(), now=_NOW)
    assert "X1pump" not in m.tokens  # down >90% from its high goes first


def test_evict_dead_launch_beats_older_live_launch(monkeypatch):
    m = _market(monkeypatch, universe="pumpfun")
    m.max_tracked = 2
    m.tokens = {"Y1pump": {"address": "Y1pump", "price": 50, "high": 60, "source": "pumpfun", "first_seen": 1},
                "Y2pump": {"address": "Y2pump", "price": 1, "high": 100, "source": "pumpfun", "first_seen": 2},
                "Y3pump": {"address": "Y3pump", "price": 5, "high": 5, "source": "graduated", "first_seen": 3}}
    m._evict(held=set(), now=_NOW)
    assert set(m.tokens) == {"Y1pump", "Y3pump"}  # the dead launch goes although an older launch exists


def test_all_mode_keeps_crashed_launch_under_quota(monkeypatch):
    m = _market(monkeypatch, universe="all")
    monkeypatch.setattr(market, "PUMPFUN_SHARE", 0.5)
    m.max_tracked = 4  # quota: pumpfun 2, organic 1, promoted 1
    m.tokens = {"P1": {"address": "P1", "price": 1, "high": 1, "source": "promoted", "first_seen": 1},
                "Z1pump": {"address": "Z1pump", "price": 1, "high": 100, "source": "pumpfun", "first_seen": 2},
                "P2": {"address": "P2", "price": 1, "high": 1, "source": "promoted", "first_seen": 3},
                "O1": {"address": "O1", "price": 1, "high": 1, "source": "organic", "first_seen": 4},
                "P3": {"address": "P3", "price": 1, "high": 1, "source": "promoted", "first_seen": 5}}
    m._evict(held=set(), now=_NOW)
    assert "Z1pump" in m.tokens  # old behaviour: pump.fun is under quota, so the crashed launch stays
    assert "P1" not in m.tokens  # the oldest token of the group furthest over its share goes instead


def test_all_mode_keeps_top_creator_buys(monkeypatch):
    calls = []
    big, small = _mint("G1pump"), _mint("G2pump")
    m = _market(monkeypatch, universe="all", launches=[_launch(small, mcap_sol=31), _launch(big, mcap_sol=40)],
                on_get=calls.append)
    monkeypatch.setattr(market, "PUMPFUN_NEW", 1)
    assert m.max_tracked == 60
    assert m._discover_pumpfun() == {big: "pumpfun"}  # old rule: largest initial market cap, no pricing call
    assert calls == [] and m.probation == {}
    assert m._pump_meta[big]["initial_mcap_sol"] == 40
