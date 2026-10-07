"""GeckoTerminal price fallback: when DexScreener's /tokens/v1 answers [] for every token (the 2026-10-07 outage),
_fetch_pairs prices the missing mints through GeckoTerminal's tokens/multi + pools/multi endpoints."""
import pytest

import market
from market import SOL_MINT, LiveMarket

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
MINT_A = "AAAA" + "1" * 36 + "pump"
MINT_B = "BBBB" + "1" * 36 + "pump"
POOL_A = "PoolA" + "1" * 39
POOL_B = "PoolB" + "1" * 39


def _mint(i):
    """A distinct plausible 44-character base58 mint for index i."""
    s, n = "", i
    for _ in range(6):
        s += _B58[n % 58]
        n //= 58
    return s + "1" * 34 + "pump"


def _gecko_token(mint, pool, symbol="TOK"):
    """One entry of GET /networks/solana/tokens/multi/..."""
    return {"id": f"solana_{mint}", "type": "token",
            "attributes": {"address": mint, "name": f"Token {symbol}", "symbol": symbol, "decimals": 6,
                           "price_usd": "0.00002", "fdv_usd": "20000.0", "total_reserve_in_usd": "0",
                           "volume_usd": {"h24": "5000"}},
            "relationships": {"top_pools": {"data": [{"id": f"solana_{pool}", "type": "pool"}] if pool else []}}}


def _gecko_pool(pool, base, quote, dex, reserve="12345.6", mcap="20000", base_price="0.00002",
                quote_price="150.0", name="TOK / SOL"):
    """One entry of GET /networks/solana/pools/multi/..."""
    tx = {"buys": 40, "sells": 25, "buyers": 30, "sellers": 20}
    return {"id": f"solana_{pool}", "type": "pool",
            "attributes": {"base_token_price_usd": base_price, "quote_token_price_usd": quote_price,
                           "address": pool, "name": name, "pool_created_at": "2026-10-07T10:00:00Z",
                           "fdv_usd": mcap, "market_cap_usd": None,
                           "price_change_percentage": {"m5": "1.5", "m15": "2", "m30": "3", "h1": "-4.25",
                                                       "h6": "5", "h24": "12.5"},
                           "transactions": {"m5": tx, "m15": tx, "m30": tx, "h1": tx, "h24": tx},
                           "volume_usd": {"m5": "100", "m15": "200", "m30": "300", "h1": "2500.5", "h6": "4000",
                                          "h24": "9000"},
                           "reserve_in_usd": reserve},
            "relationships": {"base_token": {"data": {"id": f"solana_{base}", "type": "token"}},
                              "quote_token": {"data": {"id": f"solana_{quote}", "type": "token"}},
                              "dex": {"data": {"id": dex, "type": "dex"}}}}


def _dex_pair(addr, price="0.5"):
    """A DexScreener /tokens/v1 pair."""
    return {"chainId": "solana", "dexId": "raydium", "pairAddress": "pair-" + addr[:8],
            "baseToken": {"address": addr, "symbol": addr[:4], "name": "Dex " + addr[:4]},
            "priceUsd": price, "marketCap": 500000, "fdv": 500000,
            "volume": {"h1": 1000, "h24": 20000}, "txns": {"h1": {"buys": 10, "sells": 8}},
            "priceChange": {"m5": 0, "h1": 0, "h24": 0}, "liquidity": {"usd": 80000},
            "pairCreatedAt": 1_700_000_000_000, "url": "https://dexscreener.com/solana/x"}


def _market(monkeypatch, tokens=None, pools=None, dex_pairs=None, gecko_raises=False):
    """LiveMarket whose DexScreener is down (or serves `dex_pairs`) and whose GeckoTerminal serves `tokens` (mint ->
    tokens/multi entry) and `pools` (pool -> pools/multi entry). Returns (market, list of gecko paths called)."""
    monkeypatch.setattr(market, "GECKO_FALLBACK", True)
    tokens, pools, dex_pairs = tokens or {}, pools or {}, dex_pairs or {}
    calls = []

    def fake_get(self, url):
        if "/tokens/v1/solana/" in url:
            return [dex_pairs[a] for a in url.rsplit("/", 1)[1].split(",") if a in dex_pairs]
        return None

    def fake_gecko_get(self, path):
        calls.append(path)
        if gecko_raises:
            raise RuntimeError("boom")
        ids = path.rsplit("/", 1)[1].split(",")
        if path.startswith("/networks/solana/tokens/multi/"):
            return {"data": [tokens[m] for m in ids if m in tokens]}
        if path.startswith("/networks/solana/pools/multi/"):
            return {"data": [pools[p] for p in ids if p in pools]}
        return None

    monkeypatch.setattr(LiveMarket, "_get", fake_get)
    monkeypatch.setattr(LiveMarket, "_gecko_get", fake_gecko_get)
    m = LiveMarket()
    m.sol = {"price": 150.0}
    return m, calls


def _two_mint_feed():
    tokens = {MINT_A: _gecko_token(MINT_A, POOL_A, "AAA"), MINT_B: _gecko_token(MINT_B, POOL_B, "BBB")}
    # real GeckoTerminal dex ids (/networks/solana/dexes): "pumpswap" = the AMM, "pump-fun" = the bonding curve
    pools = {POOL_A: _gecko_pool(POOL_A, MINT_A, SOL_MINT, "pumpswap", name="AAA / SOL"),
             POOL_B: _gecko_pool(POOL_B, MINT_B, SOL_MINT, "pump-fun", reserve="0", mcap="20000",
                                 name="BBB / SOL")}
    return tokens, pools


def test_fallback_prices_when_dexscreener_empty(monkeypatch):
    tokens, pools = _two_mint_feed()
    m, calls = _market(monkeypatch, tokens, pools)
    best = m._fetch_pairs([MINT_A, MINT_B])
    assert set(best) == {MINT_A, MINT_B}
    for a in (MINT_A, MINT_B):
        t = best[a]
        assert set(t) == set(market.parse_pair({})) | {"price_source"}
        assert t["address"] == a
        assert t["price"] > 0
        assert t["price_source"] == "gecko"
        assert t["dex"] in ("pumpswap", "pumpfun")
        assert t["buys_h1"] == 40 and t["sells_h1"] == 25
        assert t["chg_m5"] == 1.5 and t["chg_h1"] == -4.25 and t["chg_h24"] == 12.5
        assert t["vol_h1"] == 2500.5 and t["vol_h24"] == 9000
        assert t["age_min"] is not None and t["age_min"] > 0
    assert best[MINT_A]["dex"] == "pumpswap"
    assert best[MINT_A]["symbol"] == "AAA" and best[MINT_A]["name"] == "Token AAA"
    assert best[MINT_A]["liquidity"] == pytest.approx(12345.6)
    assert best[MINT_A]["pair"] == POOL_A
    assert best[MINT_A]["url"] == f"https://www.geckoterminal.com/solana/pools/{POOL_A}"
    # a "pump-fun" pool must come out as dex "pumpfun" (graduation detection, signals.PUMP_DEXES, pool_fee)
    assert best[MINT_B]["dex"] == "pumpfun"
    assert best[MINT_B]["mcap"] == 20000
    assert best[MINT_B]["liquidity"] == pytest.approx(market.curve_liquidity_usd(20000, 150.0))
    assert best[MINT_B]["liquidity"] > 0
    assert m.pool_of == {MINT_A: POOL_A, MINT_B: POOL_B}
    assert m.gecko_fallback_stats["priced"] == 2
    assert m.gecko_fallback_stats["calls"] == len(calls) == 2


def test_fallback_not_called_when_dexscreener_prices(monkeypatch):
    tokens, pools = _two_mint_feed()
    m, calls = _market(monkeypatch, tokens, pools,
                       dex_pairs={MINT_A: _dex_pair(MINT_A), MINT_B: _dex_pair(MINT_B)})
    best = m._fetch_pairs([MINT_A, MINT_B])
    assert set(best) == {MINT_A, MINT_B}
    assert calls == []
    assert all("price_source" not in t for t in best.values())


def test_pool_cache_skips_token_lookup(monkeypatch):
    tokens, pools = _two_mint_feed()
    m, calls = _market(monkeypatch, tokens, pools)
    m._fetch_pairs([MINT_A, MINT_B])
    calls.clear()
    best = m._fetch_pairs([MINT_A, MINT_B])
    assert set(best) == {MINT_A, MINT_B}
    assert calls and all(p.startswith("/networks/solana/pools/multi/") for p in calls)


def test_fallback_call_cap(monkeypatch):
    mints = [_mint(i) for i in range(400)]
    assert len(set(mints)) == 400
    pool = {a: "Pool" + a[:6] + "1" * 34 for a in mints}
    tokens = {a: _gecko_token(a, pool[a]) for a in mints}
    pools = {pool[a]: _gecko_pool(pool[a], a, SOL_MINT, "pumpswap") for a in mints}
    m, calls = _market(monkeypatch, tokens, pools)
    best = m._fetch_pairs(mints)
    assert 0 < len(calls) <= market.GECKO_FALLBACK_MAX_CALLS
    assert best  # the budget still prices some of them
    assert all(t["price_source"] == "gecko" for t in best.values())


def test_fallback_respects_backoff(monkeypatch):
    tokens, pools = _two_mint_feed()
    m, calls = _market(monkeypatch, tokens, pools, dex_pairs={MINT_A: _dex_pair(MINT_A)})
    m.gecko_backoff_until = market.time.time() + 300
    best = m._fetch_pairs([MINT_A, MINT_B])
    assert calls == []
    assert set(best) == {MINT_A}
    assert "price_source" not in best[MINT_A]


def test_parse_gecko_pool_quote_orientation():
    pool = _gecko_pool(POOL_A, SOL_MINT, MINT_A, "raydium", base_price="150.0", quote_price="0.0042",
                       name="SOL / AAA")
    t = market.parse_gecko_pool(pool, {"address": MINT_A})
    assert t["address"] == MINT_A
    assert t["price"] == pytest.approx(0.0042)
    assert t["symbol"] == "AAA"
    assert t["dex"] == "raydium"
    assert t["price_source"] == "gecko"


def test_fallback_never_raises(monkeypatch):
    m, calls = _market(monkeypatch, dex_pairs={MINT_A: _dex_pair(MINT_A)}, gecko_raises=True)
    errors = m.gecko_stats["errors"]
    best = m._fetch_pairs([MINT_A, MINT_B])
    assert calls  # the fallback was attempted
    assert set(best) == {MINT_A}
    assert "price_source" not in best[MINT_A]
    assert m.gecko_stats["errors"] == errors + 1


def test_gecko_dex_ids_map_to_dexscreener_spelling():
    for gecko_id, dex in (("pump-fun", "pumpfun"), ("pumpswap", "pumpswap"), ("pump-swap", "pumpswap"),
                          ("raydium", "raydium")):
        t = market.parse_gecko_pool(_gecko_pool(POOL_A, MINT_A, SOL_MINT, gecko_id), {"address": MINT_A})
        assert t["dex"] == dex


def test_fresh_gecko_price_reused_within_20s(monkeypatch):
    tokens, pools = _two_mint_feed()
    m, calls = _market(monkeypatch, tokens, pools)
    now = market.time.time()
    for a, t in m._fetch_pairs([MINT_A, MINT_B]).items():
        m._merge_pair(a, t, now)
    assert calls
    calls.clear()
    best = m._fetch_pairs([MINT_A, MINT_B])  # e.g. the fast exit check 10 s later
    assert calls == []
    assert set(best) == {MINT_A, MINT_B}
    assert all(t["price_source"] == "gecko" and t["price"] > 0 for t in best.values())
    assert m.gecko_fallback_stats["reused"] == 2
    for a in (MINT_A, MINT_B):  # older than 20 s: fetched again
        m.tokens[a]["updated"] = now - 25
    m._fetch_pairs([MINT_A, MINT_B])
    assert calls and all(p.startswith("/networks/solana/pools/multi/") for p in calls)


def test_fallback_minute_budget(monkeypatch):
    monkeypatch.setattr(market, "GECKO_FALLBACK_PER_MIN", 3)
    mints = [_mint(i) for i in range(100)]
    pool = {a: "Pool" + a[:6] + "1" * 34 for a in mints}
    tokens = {a: _gecko_token(a, pool[a]) for a in mints}
    pools = {pool[a]: _gecko_pool(pool[a], a, SOL_MINT, "pumpswap") for a in mints}
    m, calls = _market(monkeypatch, tokens, pools)
    first = m._fetch_pairs(mints)
    assert len(calls) == 3
    assert first  # the last request the minute allows is a pools request, so something gets priced
    skipped = m.gecko_fallback_stats["skipped"]
    calls.clear()
    assert m._fetch_pairs(mints) == {}  # same minute: budget spent, no request at all
    assert calls == []
    assert m.gecko_fallback_stats["skipped"] > skipped


def test_fallback_prices_sol_and_held_first(monkeypatch):
    monkeypatch.setattr(market, "GECKO_FALLBACK_MAX_CALLS", 2)
    mints = [_mint(i) for i in range(100)]
    held = mints[90]
    sol_pool = "SolPool" + "1" * 37
    pool = {a: "Pool" + a[:6] + "1" * 34 for a in mints}
    tokens = {a: _gecko_token(a, pool[a]) for a in mints}
    tokens[SOL_MINT] = _gecko_token(SOL_MINT, sol_pool, "SOL")
    pools = {pool[a]: _gecko_pool(pool[a], a, SOL_MINT, "pumpswap") for a in mints}
    pools[sol_pool] = _gecko_pool(sol_pool, SOL_MINT, market.USDC_MINT, "orca", base_price="150", name="SOL / USDC")
    m, calls = _market(monkeypatch, tokens, pools)
    m.last_held = {held}
    best = m._fetch_pairs(mints + [SOL_MINT])
    assert len(calls) == 2  # one token lookup of 30, one pools request
    assert SOL_MINT in best and held in best
    assert best[SOL_MINT]["price"] == 150


def test_fallback_log_line_throttled(monkeypatch, capsys):
    tokens, pools = _two_mint_feed()
    m, calls = _market(monkeypatch, tokens, pools)
    for _ in range(3):
        assert len(m._fetch_pairs([MINT_A, MINT_B])) == 2
    out = capsys.readouterr().out
    assert out.count("via GeckoTerminal") == 1
    assert m.gecko_fallback_stats["priced"] == 6
