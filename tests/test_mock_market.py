"""MockMarket spawns pump.fun, graduated and organic tokens so the lanes are non-empty offline."""
import market


def test_mock_market_covers_all_three_sources():
    m = market.MockMarket(n=30, seed=3)
    toks = m.candidates()
    sources = {t.get("source") for t in toks}
    assert {"pumpfun", "graduated", "organic"} <= sources
    pf = [t for t in toks if t.get("source") == "pumpfun"]
    assert pf and all(t["dex"] == "pumpfun" and 5 <= t["pump"]["curve_pct"] <= 100 and t["pump"].get("launched") for t in pf)
    gr = [t for t in toks if t.get("source") == "graduated"]
    assert gr and all(t["dex"] == "pumpswap" and t["pump"].get("graduated") and t["pump"]["curve_pct"] == 100.0 for t in gr)


def test_mock_refresh_keeps_curve_pct_and_track_still_spawns():
    m = market.MockMarket(n=12, seed=5)
    m.refresh(set())
    assert all("curve_pct" in t["pump"] for t in m.candidates() if t.get("source") == "pumpfun")
    t = m.track("Zz9trackedMint", source="copy")
    assert t["address"] == "Zz9trackedMint" and t["source"] == "copy" and "Zz9trackedMint" in m.tokens
    assert not t.get("pump")  # tracking spawns a plain token, not a curve one
