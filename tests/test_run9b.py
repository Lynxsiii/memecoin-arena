"""Run 9b: ramp window (45-75% of the true graduation cap since 2026-10-09), 500 tracked slots with ramp-zone promotion and protection, $100 graduate buy cap,
slow-tick print."""
import arena as arena_mod
import market
import signals
from claude_agents import LLM_SYSTEM, PERSONAS, fill_brief
from market import LiveMarket
from signals import structural_view

_NOW = 1_790_000_000.0
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


# helpers as in test_market_pumpfun.py / test_run9.py
def _mint(tag):
    body = "".join(c if c in _B58 else "z" for c in tag.removesuffix("pump"))
    return body + "1" * (40 - len(body)) + "pump"


def _launch(mint, mcap_sol, ts=_NOW - 120):
    return {"mint": mint, "name": "Test " + mint[:4], "symbol": mint[:4].upper(), "creator": "Creator1111",
            "initial_buy_sol": 1.0, "mcap_sol": mcap_sol, "ts": ts, "curve": "Curve1111", "mayhem": False}


def _pair(addr, mcap, vol_h1, txns):
    return {"chainId": "solana", "dexId": "pumpfun", "pairAddress": "curve-" + addr[:8],
            "baseToken": {"address": addr, "symbol": addr[:4].upper(), "name": "Test " + addr[:4]},
            "priceUsd": f"{mcap / 1e9:.12f}", "marketCap": mcap, "fdv": mcap,
            "volume": {"h1": vol_h1, "h24": vol_h1}, "txns": {"h1": {"buys": txns - txns // 2, "sells": txns // 2}},
            "priceChange": {"m5": 0, "h1": 0, "h24": 0}, "liquidity": {"usd": 0}}


class _FakeFeed:
    def __init__(self, launches=()):
        self.launches = list(launches)

    def new_tokens(self, since=0):
        return [dict(e) for e in self.launches if e["ts"] > since]

    def graduations(self, since=0):
        return []


def _market(monkeypatch, universe, launches=(), pairs=None):
    monkeypatch.setattr(market, "UNIVERSE", universe)
    if universe == "pumpfun":
        monkeypatch.setattr(market, "PUMPFUN_SHARE", 1.0)
    pairs = pairs or {}

    def fake_get(self, url):
        if "/tokens/v1/solana/" in url:
            return [pairs[a] for a in url.rsplit("/", 1)[1].split(",") if a in pairs]
        return None

    monkeypatch.setattr(LiveMarket, "_get", fake_get)
    m = LiveMarket()
    m.pump = _FakeFeed(launches)
    return m


def _curve(pct, **kw):
    t = dict(address="RAMPpump", symbol="FROG", name="Frog", dex="pumpfun", source="pumpfun", liquidity=20_000.0,
             buys_h1=40, sells_h1=20, age_min=30, pump={"curve_pct": pct, "launched": _NOW - 1800})
    t.update(kw)
    return t


def _flow(net_share=0.3, buyers=15):
    return {"buy_usd": 3000.0, "sell_usd": 1500.0, "gross_usd": 4500.0, "net_usd": 1500.0, "net_share": net_share,
            "buyers": buyers, "sellers": 8, "trades": 40, "round_trip_share": 0.05, "top_buyer_share": 0.1,
            "bot_share": 0.1, "last_trade_min_ago": 2.0, "quality": "organic"}


def _view(t, flow=None):
    return structural_view(t, flow, None, None, None, now=_NOW)


# ------------------------------------------------------------------ 1. ramp window
def test_ramp_window_bounds():
    assert signals.RAMP_MIN_PCT == 35.0 and signals.RAMP_MAX_PCT == 55.0
    assert "ramp_setup" not in _view(_curve(34.0), _flow())
    assert _view(_curve(35.0), _flow())["ramp_setup"] is True
    assert _view(_curve(55.0), _flow())["ramp_setup"] is True
    assert "ramp_setup" not in _view(_curve(56.0), _flow())
    assert [signals.ramp_stage(p) for p in (34.9, 35.0, 55.0, 55.1)] == ["early", "ramp", "ramp", "late"]


def test_brief_and_personas_use_new_window(monkeypatch):
    monkeypatch.setattr(market, "UNIVERSE", "pumpfun")
    b = fill_brief(LLM_SYSTEM, 1, 60)
    assert '"ramp" 35-55%, "late" past 55%' in b and "under 35% filled" in b
    assert "ramp is now\n  35-55% filled" in b
    assert "ramp_setup coins first (35-55% filled with net buying; most filled first)" in b
    assert "averaged +4.5% (+6.2% with a -20% stop), buying at 45-65% averaged -5.7%" in b
    for old in ("69% and 46%", "40-52%", "+46% entering at 60%", "1.4x"):
        assert old not in b  # no old-scale figures left in the brief
    ramp = fill_brief(LLM_SYSTEM + "\n\n" + PERSONAS["ramp"][1], 1, 60)
    assert "while their fill is 35-55% (ramp_setup)" in ramp and "already past 55%" in ramp
    assert ('Set "stop_loss_pct": -20 on every ramp buy: on the replay a -20% stop beat -30% on the curve, because a '
            "ramp that stalls rarely recovers.") in ramp
    assert "an entry near 35% filled needs to keep filling" in ramp
    runner = fill_brief(PERSONAS["runner"][1], 1, 60)
    assert "never buy past 55% of the curve" in runner
    for text in [b, ramp, runner] + [p[1] for p in PERSONAS.values()]:
        assert "40-80" not in text and "40-60" not in text and "past 80" not in text
    assert "{RAMP_" not in b and "{RAMP_" not in ramp


# ------------------------------------------------------------------ 2. tracking capacity
def test_max_tracked_defaults_and_env(monkeypatch):
    monkeypatch.delenv("ARENA_MAX_TRACKED", raising=False)
    assert _market(monkeypatch, universe="pumpfun").max_tracked == 500
    assert _market(monkeypatch, universe="all").max_tracked == 60
    monkeypatch.setenv("ARENA_MAX_TRACKED", "250")
    assert _market(monkeypatch, universe="pumpfun").max_tracked == 250
    assert market.PROBATION_MIN == 60


def test_probation_promotes_ramp_zone_without_volume(monkeypatch):
    hot, warm = _mint("H1pump"), _mint("W1pump")
    m = _market(monkeypatch, universe="pumpfun", launches=[_launch(hot, mcap_sol=31), _launch(warm, mcap_sol=31)],
                pairs={hot: _pair(hot, mcap=21_250, vol_h1=0, txns=0), warm: _pair(warm, mcap=12_000, vol_h1=0, txns=0)})
    monkeypatch.setattr(market, "TRACK_MCAP_USD", 50_000)  # only the ramp rule can promote these two
    assert market.TRACK_RAMP_MCAP_USD is None  # unset: the floor is RAMP_MIN_PCT % of the live cap
    m.sol = {"price": 100.0}  # cap 425 SOL x $100 = $42,500; floor 35% = $14,875
    assert m.graduation_cap_usd() == 42_500
    assert m._probation_poll(now=_NOW) == {hot: "pumpfun"}
    assert warm in m.probation
    assert m.probation_stats["promoted_ramp"] == 1
    t = m._new_token(hot, "pumpfun", _NOW)
    assert t["pump"]["curve_pct"] == 50.0  # from DexScreener's market cap, before the first price refresh
    m.max_tracked = 1
    m.tokens = {"OLDpump": {"address": "OLDpump", "price": 1, "high": 1, "source": "pumpfun", "first_seen": 1}, hot: t}
    t["first_seen"] = 0  # even as the oldest launch it stays: the ramp zone protects it
    m._evict(held=set(), now=_NOW)
    assert set(m.tokens) == {hot}


def test_ramp_promotion_env_zero_disables(monkeypatch):
    hot = _mint("H2pump")
    m = _market(monkeypatch, universe="pumpfun", launches=[_launch(hot, mcap_sol=31)],
                pairs={hot: _pair(hot, mcap=40_000, vol_h1=0, txns=0)})
    monkeypatch.setattr(market, "TRACK_MCAP_USD", 50_000)
    monkeypatch.setattr(market, "TRACK_RAMP_MCAP_USD", 0.0)
    assert m._probation_poll(now=_NOW) == {}


def test_eviction_protects_ramp_zone_curve_coin(monkeypatch):
    m = _market(monkeypatch, universe="pumpfun")
    m.max_tracked = 2
    m.tokens = {
        "R60pump": {"address": "R60pump", "price": 5, "high": 5, "source": "pumpfun", "dex": "pumpfun",
                    "first_seen": 1, "pump": {"curve_pct": 60.0}},
        "R40pump": {"address": "R40pump", "price": 5, "high": 5, "source": "pumpfun", "dex": "pumpfun",
                    "first_seen": 2, "pump": {"curve_pct": 30.0}},
        "GRADpump": {"address": "GRADpump", "price": 5, "high": 5, "source": "graduated", "dex": "pumpswap",
                     "first_seen": 3, "pump": {"curve_pct": 100.0, "graduated": 1}},
        "NEWpump": {"address": "NEWpump", "price": 5, "high": 5, "source": "pumpfun", "dex": "pumpfun",
                    "first_seen": 4, "pump": {"curve_pct": 10.0}},
    }
    m._evict(held=set(), now=_NOW)
    assert "R60pump" in m.tokens  # the oldest launch, but in the ramp zone
    assert m.tokens["R60pump"]["protect_until"] == _NOW + 1800
    assert "R40pump" not in m.tokens and "NEWpump" not in m.tokens
    assert "protect_until" not in m.tokens["GRADpump"]  # a graduate is not a curve coin
    # the protection is refreshed while the coin stays in the zone, and lapses 30 minutes after it leaves
    m._evict(held=set(), now=_NOW + 600)
    assert m.tokens["R60pump"]["protect_until"] == _NOW + 2400
    m.tokens["R60pump"]["pump"]["curve_pct"] = 30.0
    m._evict(held=set(), now=_NOW + 1200)
    assert m.tokens["R60pump"]["protect_until"] == _NOW + 2400


def test_refresh_bounds_unchanged():
    m = LiveMarket.__new__(LiveMarket)
    LiveMarket.__init__(m)
    assert m.risk_checks == 12 and market.RUG_CHECKS <= 4 and market.PROBATION_PER_CYCLE == 120


# ------------------------------------------------------------------ 3. graduate buy cap
def _graduate(t):
    t.update(dex="pumpswap", source="graduated", pump={"graduated": 1, "curve_pct": 100.0})


def test_graduate_buy_capped(arena_llm):
    a, name, view = arena_llm()
    _graduate(a.market.get("T1pump"))
    o = {"action": "buy", "token": "T1pump", "usd": 400, "reason": "fresh graduate"}
    ok = a.validate(a.agents[name], o, view)
    assert ok["usd"] == 100 and ok["capped_to"] == 100
    assert ok["reason"] == "fresh graduate [capped at $100: graduate]"
    small = a.validate(a.agents[name], {"action": "buy", "token": "T1pump", "usd": 80, "reason": "x"}, view)
    assert small["usd"] == 80 and "capped_to" not in small


def test_graduate_cap_by_dex_only(arena_llm):
    a, name, view = arena_llm()
    a.market.get("T1pump").update(dex="pumpswap", pump={})
    ok = a.validate(a.agents[name], {"action": "buy", "token": "T1pump", "usd": 400, "reason": "x"}, view)
    assert ok["usd"] == 100 and ok["capped_to"] == 100


def test_curve_buy_not_capped(arena_llm):
    a, name, view = arena_llm()
    a.market.get("T1pump").update(dex="pumpfun", source="pumpfun", pump={"curve_pct": 60.0})
    ok = a.validate(a.agents[name], {"action": "buy", "token": "T1pump", "usd": 400, "reason": "ramp",
                                     "sell_at_graduation": True}, view)
    assert ok["usd"] == 400 and "capped_to" not in ok and "capped" not in ok["reason"]


def test_graduate_cap_off_and_bots_exempt(arena_llm, monkeypatch):
    a, name, view = arena_llm(bot=True)
    _graduate(a.market.get("T1pump"))
    ok = a.validate(a.agents[name], {"action": "buy", "token": "T1pump", "usd": 400, "reason": "x"}, view)
    assert ok["usd"] == 400  # bots size themselves
    monkeypatch.setattr(arena_mod, "LLM_GRADUATE_MAX_USD", 0.0)
    a, name, view = arena_llm()
    _graduate(a.market.get("T1pump"))
    ok = a.validate(a.agents[name], {"action": "buy", "token": "T1pump", "usd": 400, "reason": "x"}, view)
    assert ok["usd"] == 400 and "capped_to" not in ok


def test_brief_names_graduate_cap(monkeypatch):
    b = fill_brief(LLM_SYSTEM, 1, 60)
    assert "- Buys on graduated coins are capped at $100 each (graduates were 38 buys for -$809 on 2026-10-08" in b
    assert "Curve buys are not capped." in b and "{GRAD_CAP_TEXT}" not in b
    monkeypatch.setattr(arena_mod, "LLM_GRADUATE_MAX_USD", 0.0)
    assert "capped at" not in fill_brief(LLM_SYSTEM, 1, 60)


# ------------------------------------------------------------------ 4. slow tick
def test_slow_tick_print_throttled(arena_llm, monkeypatch, capsys):
    a, _, _ = arena_llm()
    clock = [1000.0]
    monkeypatch.setattr(arena_mod.time, "time", lambda: clock[0])
    a._note_tick_time(10.0)
    assert capsys.readouterr().out == ""
    a._note_tick_time(25.0)
    assert f"[arena] slow tick: 25.0s (tracked {len(a.market.tokens)})" in capsys.readouterr().out
    clock[0] += 120
    a._note_tick_time(40.0)
    assert capsys.readouterr().out == ""  # under 5 minutes since the last print
    clock[0] += 200
    a._note_tick_time(21.5)
    assert "slow tick: 21.5s" in capsys.readouterr().out


def test_step_reports_its_wall_time(arena_llm, monkeypatch):
    a, _, _ = arena_llm()
    seen = []
    monkeypatch.setattr(a, "_note_tick_time", seen.append)
    monkeypatch.setattr(a, "_step", lambda: None)
    a.step()
    assert len(seen) == 1 and seen[0] >= 0

    def boom():
        raise RuntimeError("tick failed")
    monkeypatch.setattr(a, "_step", boom)
    try:
        a.step()
    except RuntimeError:
        pass
    assert len(seen) == 2  # a failed tick still reports its time (run_forever prints the error)


# ------------------------------------------------------------------ 5. pool-poll priority (traders.py)
class _PoolMarket:
    def __init__(self, toks, held):
        self.toks, self.last_held = toks, set(held)

    def candidates(self):
        return list(self.toks)


def test_poll_priority_held_then_ramp_then_rest(monkeypatch):
    import traders
    toks = [{"address": "PLAINpump", "pair": "poolPlain", "dex": "pumpfun", "pump": {"curve_pct": 20.0}},
            {"address": "HELDpump", "pair": "poolHeld", "dex": "pumpswap", "pump": {"graduated": 1}},
            {"address": "RAMPpump", "pair": "poolRamp", "dex": "pumpfun", "pump": {"curve_pct": 62.0}},
            {"address": "GRADpump", "pair": "poolGrad", "dex": "pumpswap",
             "pump": {"graduated": 1, "curve_pct": 100.0}}]
    tr = traders.Tracker.__new__(traders.Tracker)
    tr.market, tr.pools, tr.pool_of = _PoolMarket(toks, held={"HELDpump"}), {}, {}
    tr.priority_mints = {"held": set(), "ramp": set()}
    monkeypatch.setattr(tr, "_remember_symbol", lambda *a: None, raising=False)
    tr._sync_pools()
    assert tr.priority_mints == {"held": {"HELDpump"}, "ramp": {"RAMPpump"}}
    now = 1000.0
    for i, pool in enumerate(("poolPlain", "poolGrad", "poolRamp", "poolHeld")):
        tr.pools[pool]["due"] = now - 100 + i  # the plain pool is the most overdue
    polled = []
    for _ in range(4):
        pool = tr._next_pool(now)
        polled.append(pool)
        tr.pools[pool]["due"] = now + 60  # what _poll_pool does
    assert polled == ["poolHeld", "poolRamp", "poolPlain", "poolGrad"]
    assert tr._next_pool(now) is None


# ------------------------------------------------------------------ 2026-10-09: graduation cap in SOL
def test_graduation_cap_uses_live_sol_and_falls_back(monkeypatch):
    import exchange
    monkeypatch.setattr(market, "GRADUATION_CAP_SOL", 425.0)
    monkeypatch.setattr(market, "_last_sol_usd", 0.0)
    monkeypatch.setattr(exchange, "SOL_USD", 150.0)
    assert market.graduation_cap_usd() == 425 * 150  # no live price yet: ARENA_SOL_USD
    assert market.graduation_cap_usd(116.0) == 425 * 116
    m = _market(monkeypatch, universe="pumpfun")
    assert m.graduation_cap_usd() == 425 * 150  # LiveMarket before its first SOL price
    m.sol = {"price": 110.0}
    assert m.graduation_cap_usd() == 425 * 110
    market._note_sol_price(112.0)  # what LiveMarket.refresh does once DexScreener prices SOL
    assert market.live_sol_usd() == 112.0 and market.graduation_cap_usd() == 425 * 112


def test_annotate_uses_the_market_cap_passed():
    t = {"price": 1e-6, "liquidity": 5000, "mcap": 25_000, "source": "pumpfun", "dex": "pumpfun", "pump": {}}
    market._annotate(t, cap_usd=50_000)
    assert t["pump"]["curve_pct"] == 50.0
    g = {"price": 1e-6, "mcap": 99_000, "source": "graduated", "dex": "pumpswap", "pump": {"graduated": 1}}
    market._annotate(g, cap_usd=50_000)
    assert g["pump"]["curve_pct"] == 100.0


def test_promotion_floor_follows_live_cap(monkeypatch):
    coin = _mint("F1pump")
    pairs = {coin: _pair(coin, mcap=16_000, vol_h1=0, txns=0)}
    monkeypatch.setattr(market, "TRACK_MCAP_USD", 50_000)
    cheap = _market(monkeypatch, universe="pumpfun", launches=[_launch(coin, mcap_sol=31)], pairs=pairs)
    cheap.sol = {"price": 100.0}  # floor 35% of $42,500 = $14,875: $16k promotes
    assert cheap._probation_poll(now=_NOW) == {coin: "pumpfun"}
    dear = _market(monkeypatch, universe="pumpfun", launches=[_launch(coin, mcap_sol=31)], pairs=pairs)
    dear.sol = {"price": 160.0}  # floor 35% of $68,000 = $23,800: $16k stays on probation
    assert dear._probation_poll(now=_NOW) == {} and coin in dear.probation
    override = _market(monkeypatch, universe="pumpfun", launches=[_launch(coin, mcap_sol=31)], pairs=pairs)
    override.sol = {"price": 100.0}
    monkeypatch.setattr(market, "TRACK_RAMP_MCAP_USD", 20_000.0)  # ARENA_PUMPFUN_TRACK_RAMP_MCAP_USD: absolute dollars
    assert override._probation_poll(now=_NOW) == {}


def test_mock_market_curve_pct_on_live_cap():
    m = market.MockMarket(n=9, seed=3)
    cap = m.graduation_cap_usd()
    assert cap == market.GRADUATION_CAP_SOL * m.sol["price"]
    curve = [t for t in m.tokens.values() if t.get("dex") == "pumpfun"]
    assert curve and all(abs(t["pump"]["curve_pct"] - min(100.0, t["mcap"] / cap * 100)) < 0.06 for t in curve)
    m.refresh(held=())
    assert market.live_sol_usd() == m.sol["price"]


def test_brief_explains_curve_pct_with_live_cap(monkeypatch):
    import claude_agents
    monkeypatch.setattr(market, "_last_sol_usd", 0.0)
    b = fill_brief(LLM_SYSTEM, 1, 60)
    assert "share of the graduation cap" in b
    assert ("curve_pct is the coin's market cap as a share of the graduation cap (about 425 SOL, about $47k at the "
            "current SOL price); from 35% a coin that graduates has about +190% of price left to migration, from 55% "
            "about +82%, before your costs.") in b
    assert "{CURVE_CAP_TEXT}" not in b

    class _Backend:
        model, label = "claude-sonnet-4-6", "test"

    agent = claude_agents.LLMAgent(_Backend())
    assert "about 425 SOL, about $47k at the current SOL price" in agent.system
    monkeypatch.setattr(market, "_last_sol_usd", 116.0)  # 425 x 116 = $49,300 -> "roughly $50,000"
    agent._refresh_cap_text()
    assert "about 425 SOL, roughly $50,000 at the current SOL price" in agent.system
    monkeypatch.setattr(market, "_last_sol_usd", 120.0)  # $51,000: same $5,000 bucket, brief unchanged
    before = agent.system
    agent._refresh_cap_text()
    assert agent.system == before
    assert "about $47k" not in agent.system
