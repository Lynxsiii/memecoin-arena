"""Brand-name impersonation and bundle-liquidity vetoes (signals.py), and the refresh() iteration race (market.py)."""
import importlib
import time

import signals
from signals import brand_match, veto_report

_NOW = 1_790_000_000.0


def _vetoes(**t):
    return veto_report(t, now=_NOW)["vetoes"]


def _brand_vetoed(**t):
    return any(v.startswith("brand-name impersonation") for v in _vetoes(**t))


def _bundle_vetoed(**t):
    return any("injected liquidity gets pulled" in v for v in _vetoes(**t))


def test_brand_positives():
    assert brand_match({"symbol": "ChatGPT"}) == "chatgpt"
    assert brand_match({"symbol": "$Apple"}) == "apple"
    assert brand_match({"symbol": "NIKE coin"}) == "nike"
    assert brand_match({"symbol": "tesla2"}) == "tesla"
    assert brand_match({"symbol": "TESLAAI"}) == "tesla"
    assert brand_match({"symbol": "BBC123"}) == "bbc"
    assert brand_match({"symbol": "XYZQ", "name": "NVIDIA"}) == "nvidia"  # innocent symbol, brand name
    v = _vetoes(symbol="CHATGPT", name="ChatGPT")
    assert "brand-name impersonation (ChatGPT): every such coin bought so far was rugged" in v


def test_brand_negatives():
    for word in ("metamorph", "solcat", "legoland", "pineapple", "CAT", "", None):
        assert brand_match({"symbol": word, "name": word}) is None, word
    assert not _brand_vetoed(symbol="WIF", name="dogwifhat")


def test_brand_extra_env(monkeypatch):
    monkeypatch.setenv("ARENA_VETO_BRAND_EXTRA", "Hooters, red bull")
    try:
        mod = importlib.reload(signals)
        assert mod.brand_match({"symbol": "HOOTERS"}) == "hooters"
        assert mod.brand_match({"name": "Red Bull"}) == "redbull"
        assert mod.brand_match({"symbol": "APPLE"}) == "apple"  # the seed list is kept
    finally:
        monkeypatch.delenv("ARENA_VETO_BRAND_EXTRA")
        importlib.reload(signals)


def _graduate(liq, mig_min, **kw):
    return dict(symbol="FROG", name="Frog", dex="pumpswap", liquidity=liq,
                pump={"graduated": _NOW - mig_min * 60}, **kw)


def test_bundle_liquidity_veto():
    v = _vetoes(**_graduate(80_000, 10))
    assert ("liquidity $80k on a 10-minute-old graduate: far above a normal migration (~$12k), "
            "injected liquidity gets pulled") in v
    assert not _bundle_vetoed(**_graduate(20_000, 10))
    assert not _bundle_vetoed(**_graduate(80_000, 240))           # 4 hours past migration
    assert not _bundle_vetoed(**_graduate(None, 10))              # missing liquidity is never a veto
    assert not _bundle_vetoed(symbol="FROG", dex="pumpfun", liquidity=80_000, age_min=10,
                              pump={"launched": _NOW - 600})      # still on its bonding curve


def test_bundle_liquidity_veto_falls_back_to_pair_age():
    t = dict(symbol="FROG", dex="pumpswap", liquidity=150_000, age_min=5)  # no migration stamp
    assert _bundle_vetoed(**t)
    assert not _bundle_vetoed(**dict(t, age_min=500))
    assert not _bundle_vetoed(symbol="FROG", dex="pumpswap", liquidity=150_000)  # age unknown


def test_bundle_liquidity_uses_migrated_min_ago_arg():
    t = _graduate(90_000, 400)
    assert any("injected" in v for v in veto_report(t, now=_NOW, migrated_min_ago=3)["vetoes"])


def test_refresh_survives_track_mid_loop(monkeypatch):
    """The wallet tracker calls track() from its own thread while refresh() iterates self.tokens: adding a token
    mid-loop must not raise "dictionary changed size during iteration"."""
    import market
    from market import LiveMarket

    monkeypatch.setattr(market, "UNIVERSE", "all")
    monkeypatch.setattr(market, "RUG_CHECKS", 0)
    monkeypatch.setattr(market, "SELL_CHECKS", 0)
    monkeypatch.setattr(market.time, "sleep", lambda s: None)
    mints = [c * 40 + "pump" for c in "ABCD"]

    def fake_get(self, url):
        if "/tokens/v1/solana/" in url:
            return [{"chainId": "solana", "dexId": "pumpswap", "pairAddress": "pool-" + a[:6],
                     "baseToken": {"address": a, "symbol": a[:3], "name": "T " + a[:3]},
                     "priceUsd": "0.0001", "marketCap": 100_000, "fdv": 100_000, "liquidity": {"usd": 20_000},
                     "volume": {"h1": 1000, "h24": 1000}, "txns": {"h1": {"buys": 5, "sells": 5}},
                     "priceChange": {"m5": 0, "h1": 0, "h24": 0}}
                    for a in url.rsplit("/", 1)[1].split(",") if a in mints]
        return None

    monkeypatch.setattr(LiveMarket, "_get", fake_get)
    m = LiveMarket()
    m.last_discover = time.time()
    for a in mints:
        m.track(a)
    added = []

    def fake_risk(self, addr):
        new = chr(ord("E") + len(added)) * 40 + "pump"
        added.append(new)
        self.track(new)  # what the tracker thread does concurrently
        return {"mint_revoked": True, "freeze_revoked": True}

    monkeypatch.setattr(LiveMarket, "_check_risk", fake_risk)
    m.refresh(set())
    assert added and all(a in m.tokens for a in added)
    assert all(m.tokens[a].get("risk") for a in mints)
