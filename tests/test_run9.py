"""Run 9: ramp signal and lane, sell-at-graduation, bundle balance veto, chart tell, hard stop, ramp/scalper personas."""
import json

import market
import rugdata
import signals
from claude_agents import LLM_SYSTEM, PERSONAS, build_lanes, fill_brief
from signals import chart_tell, structural_view, veto_report

_NOW = 1_790_000_000.0
_CHART_FLAG = "straight green run since launch, no pullback (bundle pattern)"


def _curve(pct, **kw):
    t = dict(address="RAMPpump", symbol="FROG", name="Frog", dex="pumpfun", source="pumpfun", liquidity=20_000.0,
             buys_h1=40, sells_h1=20, age_min=30, pump={"curve_pct": pct, "launched": _NOW - 1800})
    t.update(kw)
    return t


def _flow(net_share=0.3, buyers=15):
    return {"buy_usd": 3000.0, "sell_usd": 1500.0, "gross_usd": 4500.0, "net_usd": 1500.0, "net_share": net_share,
            "buyers": buyers, "sellers": 8, "trades": 40, "round_trip_share": 0.05, "top_buyer_share": 0.1,
            "bot_share": 0.1, "last_trade_min_ago": 2.0, "quality": "organic"}


def _view(t, flow=None, **kw):
    return structural_view(t, flow, None, None, None, now=_NOW, **kw)


# ------------------------------------------------------------------ 1. ramp signal and lane
def test_ramp_setup_true_in_window():
    s = _view(_curve(50.0), _flow(), chg={"curve_pct_10m": 42.0, "curve_pct_10m_secs": 600})
    assert s["curve_pct"] == 50.0 and s["curve_pct_chg_10m"] == 8.0
    assert s["ramp"] == "ramp" and s["ramp_setup"] is True
    assert "vetoes" not in s


def test_ramp_stages_and_bounds():
    # 2026-10-09 window: 35-55% of the true (~425 SOL) graduation cap (signals.RAMP_MIN_PCT / RAMP_MAX_PCT)
    assert _view(_curve(30.0), _flow())["ramp"] == "early"
    assert _view(_curve(56.0), _flow())["ramp"] == "late"
    for pct in (20.0, 30.0, 34.9, 56.0):
        assert "ramp_setup" not in _view(_curve(pct), _flow())
    assert _view(_curve(35.0), _flow())["ramp_setup"] is True
    assert _view(_curve(55.0), _flow())["ramp_setup"] is True


def test_ramp_setup_false_cases():
    assert "ramp_setup" not in _view(_curve(50.0), _flow(net_share=0.05))     # no net buying
    assert "ramp_setup" not in _view(_curve(50.0), _flow(buyers=5))           # too few wallets
    vetoed = _view(_curve(50.0, symbol="CHATGPT", name="ChatGPT"), _flow())  # brand veto
    assert vetoed.get("vetoes") and "ramp_setup" not in vetoed
    grad = _view(_curve(60.0, dex="pumpswap", source="graduated", pump={"graduated": _NOW - 600}), _flow())
    assert "ramp" not in grad and "ramp_setup" not in grad and "curve_pct" not in grad


def test_ramp_setup_without_flow_uses_tx_counts():
    assert _view(_curve(50.0, buys_h1=40, sells_h1=20))["ramp_setup"] is True
    assert "ramp_setup" not in _view(_curve(50.0, buys_h1=20, sells_h1=40))
    assert "ramp_setup" not in _view(_curve(50.0, buys_h1=6, sells_h1=2))   # under 10 buys


def test_ramp_setup_excludes_chart_tell():
    pts = [(_NOW - 30 * (9 - i), 1.0 + 0.15 * i) for i in range(10)]  # 1.0 -> 2.35, never down
    s = _view(_curve(50.0), _flow(), prices=pts)
    assert s["chart_tell"] == "straight run" and "ramp_setup" not in s
    assert s["flags"][0] == _CHART_FLAG


def _tok(addr, pct, **extra):
    t = {"address": addr, "symbol": addr[:4], "price": 0.001, "liquidity": 20000.0, "mcap": 60000.0,
         "vol_h1": 10000.0, "buys_h1": 50, "sells_h1": 40, "chg_m5": 1.0, "chg_h1": 2.0, "chg_h24": 3.0,
         "age_min": 30, "rating": "green", "flags": [], "source": "pumpfun", "dex": "pumpfun",
         "pump": {"curve_pct": pct}}
    t.update(extra)
    return t


def test_curve_lane_puts_ramp_setup_first():
    now = 1_000_000
    toks = [_tok("FASTpump", 20.0), _tok("R45pump", 45.0), _tok("SLOWpump", 70.0), _tok("R60pump", 60.0)]
    chg = {"FASTpump": {"curve_pct_10m": 5.0}, "SLOWpump": {"curve_pct_10m": 69.0},
           "R45pump": {"curve_pct_10m": 44.0}, "R60pump": {"curve_pct_10m": 59.0}}
    structure = {"R45pump": {"ramp_setup": True}, "R60pump": {"ramp_setup": True}, "SLOWpump": {"ramp": "ramp"}}
    lanes = build_lanes(toks, vetoed={}, chg_since=chg, now=now, structure=structure)
    assert [t["token"] for t in lanes["curve"]] == ["R60pump", "R45pump", "FASTpump", "SLOWpump"]


def test_curve_lane_cap_unchanged_with_ramps():
    now = 1_000_000
    toks = [_tok(f"C{i}pump", 41.0 + i) for i in range(20)]
    structure = {f"C{i}pump": {"ramp_setup": True} for i in range(20)}
    lanes = build_lanes(toks, vetoed={}, chg_since={}, now=now, structure=structure, pinned={"C0pump"})
    tokens = [t["token"] for t in lanes["curve"]]
    assert len(tokens) == 16 and tokens[0] == "C19pump" and tokens[-1] == "C0pump"


# ------------------------------------------------------------------ 1b. sell at graduation (arena)
class _NoFail:
    def random(self):
        return 1.0


def _curve_arena(arena_llm):
    a, name, view = arena_llm()
    a.rng = _NoFail()
    t = a.market.get("T1pump")
    t.update(dex="pumpfun", source="pumpfun", pump={"curve_pct": 50.0}, chg_m5=0.0)
    return a, name, view["now"], t


def _sells(a):
    return [(n, o) for n, o in a.pending if o.get("action") == "sell"]


def test_validate_keeps_sell_at_graduation(arena_llm):
    a, name, now, _ = _curve_arena(arena_llm)
    o = {"action": "buy", "token": "T1pump", "usd": 100, "reason": "ramp", "sell_at_graduation": True}
    ok = a.validate(a.agents[name], o, a.view(name, now))
    assert ok and ok["sell_at_graduation"] is True


def test_sell_at_graduation_fires_on_graduation_only(arena_llm):
    a, name, now, t = _curve_arena(arena_llm)
    a.execute(name, {"action": "buy", "token": "T1pump", "usd": 100, "reason": "ramp", "sell_at_graduation": True}, now)
    pos = a.accounts[name]["positions"]["T1pump"]
    assert pos["sell_at_graduation"] is True and pos["entry_dex"] == "pumpfun"
    a.check_managed(now + 30)
    assert _sells(a) == []                              # still on the curve: nothing
    t["pump"] = {"curve_pct": 100.0, "graduated": now + 60}
    t["dex"] = "pumpswap"
    a.check_managed(now + 60)
    sells = _sells(a)
    assert len(sells) == 1 and sells[0][1]["fraction"] == 1.0
    assert sells[0][1]["reason"] == "ramp: graduated, cashing the curve"


def test_no_same_tick_graduation_sell_on_a_graduated_fill(arena_llm):
    a, name, now, t = _curve_arena(arena_llm)
    t["pump"] = {"curve_pct": 100.0, "graduated": now - 5}   # migrated, dex not updated yet
    a.execute(name, {"action": "buy", "token": "T1pump", "usd": 100, "reason": "late", "sell_at_graduation": True}, now)
    assert a.accounts[name]["positions"]["T1pump"]["entry_dex"] is None
    a.check_managed(now)
    assert not any("graduated" in o["reason"] for _, o in _sells(a))


def test_no_graduation_sell_without_the_flag(arena_llm):
    a, name, now, t = _curve_arena(arena_llm)
    a.execute(name, {"action": "buy", "token": "T1pump", "usd": 100, "reason": "plain"}, now)
    assert not a.accounts[name]["positions"]["T1pump"].get("sell_at_graduation")
    t["pump"] = {"curve_pct": 100.0, "graduated": now + 60}
    t["dex"] = "pumpswap"
    a.check_managed(now + 60)
    assert not any("graduated" in o["reason"] for _, o in _sells(a))


# ------------------------------------------------------------------ 2. bundle balance check
def _rug(sols, creator_sol=None):
    holders = [{"pct": 3.0 - i * 0.1, "owner": f"W{i}", "insider": False, "creator": False,
                **({"sol": s} if s is not None else {})} for i, s in enumerate(sols)]
    if creator_sol is not None:
        holders.insert(0, {"pct": 4.0, "owner": "DEV", "insider": False, "creator": True, "sol": creator_sol})
    return {"top1_pct": 4.0, "top10_pct": 20.0, "top_holders": holders, "insider_pct": 0.0, "creator_pct": 1.0,
            "creator": "DEV", "checked": _NOW, "error": None}


def _bundle(rep):
    return [v for v in rep["vetoes"] if v.startswith("bundle: top holders")]


def test_bundle_balance_veto_on_identical_tiny_balances():
    rep = veto_report({"symbol": "FROG", "rug": _rug([0.1, 0.11, 0.1, 0.12, 0.1, 5.0])}, now=_NOW)
    assert _bundle(rep) == ["bundle: top holders all carry ~0.10 SOL (identical funding)"]


def test_bundle_balance_four_of_five_is_enough():
    rep = veto_report({"symbol": "FROG", "rug": _rug([0.1, 0.11, 9.0, 0.12, 0.1])}, now=_NOW)
    assert _bundle(rep)


def test_bundle_balance_no_veto_on_varied_or_missing():
    assert not _bundle(veto_report({"symbol": "FROG", "rug": _rug([0.1, 2.5, 7.0, 0.3, 15.0])}, now=_NOW))
    assert not _bundle(veto_report({"symbol": "FROG", "rug": _rug([None] * 5)}, now=_NOW))
    assert not _bundle(veto_report({"symbol": "FROG", "rug": _rug([0.1, 0.1, 0.1, 0.1, None])}, now=_NOW))
    # tiny but spread out: 0.01 .. 0.22, no four within 0.05 SOL
    assert not _bundle(veto_report({"symbol": "FROG", "rug": _rug([0.01, 0.07, 0.13, 0.22, 0.18])}, now=_NOW))


def test_bundle_balance_excludes_creator_and_flags_three():
    rep = veto_report({"symbol": "FROG", "rug": _rug([0.1, 0.1, 0.1, 4.0, 8.0], creator_sol=0.1)}, now=_NOW)
    assert not _bundle(rep)
    assert "3 of the top 5 holders carry ~0.10 SOL each (possible bundle)" in rep["flags"]


def test_bundle_balance_env_threshold(monkeypatch):
    monkeypatch.setitem(signals.THRESHOLDS, "bundle_sol_max", 0.05)
    assert not _bundle(veto_report({"symbol": "FROG", "rug": _rug([0.1, 0.11, 0.1, 0.12, 0.1])}, now=_NOW))


class _Resp:
    status_code = 200
    headers = {}

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _Session:
    def __init__(self, lamports, programs=()):
        self.lamports, self.calls, self.timeouts, self.programs = lamports, [], [], set(programs)

    def post(self, url, json=None, timeout=None):
        self.calls.append(json)
        self.timeouts.append(timeout)
        owners = json["params"][0]
        return _Resp({"jsonrpc": "2.0", "id": json.get("id"),
                      "result": {"value": [None if self.lamports.get(o) is None else
                                           {"lamports": self.lamports[o],
                                            "owner": "PDAprogram111" if o in self.programs else rugdata.SYSTEM_PROGRAM}
                                           for o in owners]}})


def test_rugdata_skips_program_owned_holders_and_still_vetoes(monkeypatch):
    monkeypatch.setattr(rugdata, "_sol_paused_until", 0.0)
    owners = ["PDA", "A", "B", "C", "D", "E"]
    info = {"creator": None, "top_holders": [{"pct": 6.0 - i, "owner": o, "insider": False, "creator": False}
                                             for i, o in enumerate(owners)]}
    s = _Session({"PDA": 2_039_280, "A": 100_000_000, "B": 110_000_000, "C": 100_000_000, "D": 120_000_000,
                  "E": 9_000_000_000}, programs={"PDA"})
    rugdata._holder_balances(s, info, {"requests": 0})
    assert s.timeouts == [2.0]
    pda = info["top_holders"][0]
    assert pda.get("program_owned") is True and "sol" not in pda and info["sol_skipped"] == 1
    assert info["top5_sol"] == [0.1, 0.11, 0.1, 0.12, 9.0]
    rep = veto_report({"symbol": "FROG", "rug": {**info, "top1_pct": 6.0, "top10_pct": 20.0, "checked": _NOW,
                                                "error": None}}, now=_NOW)
    assert _bundle(rep) == ["bundle: top holders all carry ~0.11 SOL (identical funding)"]
    # program-owned owners all carrying the same rent-exempt minimum are not a bundle
    rents = {"creator": None, "top_holders": [{"pct": 5.0 - i, "owner": f"P{i}", "insider": False, "creator": False}
                                              for i in range(5)]}
    rugdata._holder_balances(_Session({f"P{i}": 2_039_280 for i in range(5)}, programs={f"P{i}" for i in range(5)}),
                             rents, {"requests": 0})
    assert rents["sol_skipped"] == 5 and rents["top5_sol"] is None
    assert not _bundle(veto_report({"symbol": "FROG", "rug": {**rents, "checked": _NOW, "error": None}}, now=_NOW))


def test_rugdata_records_holder_sol(monkeypatch):
    monkeypatch.setattr(rugdata, "_sol_paused_until", 0.0)
    info = {"creator": "DEV", "top_holders": [
        {"pct": 5.0, "owner": "DEV", "insider": False, "creator": True},
        {"pct": 4.0, "owner": "A", "insider": False, "creator": False},
        {"pct": 3.0, "owner": "B", "insider": True, "creator": False},
        {"pct": 2.0, "owner": "C", "insider": False, "creator": False},
        {"pct": 1.0, "owner": "D", "insider": False, "creator": False},
        {"pct": 0.5, "owner": "E", "insider": False, "creator": False},
        {"pct": 0.4, "owner": "F", "insider": False, "creator": False}]}
    s = _Session({"DEV": 3_000_000_000, "A": 100_000_000, "B": 110_000_000, "C": 90_000_000, "D": 100_000_000,
                  "E": 2_000_000_000})
    rugdata._holder_balances(s, info, {"requests": 0})
    assert len(s.calls) == 1 and s.calls[0]["method"] == "getMultipleAccounts"
    by = {h["owner"]: h["sol"] for h in info["top_holders"]}
    assert by["A"] == 0.1 and by["DEV"] == 3.0 and by["F"] == 0.0   # no account = no lamports
    assert info["top5_sol"] == [0.1, 0.11, 0.09, 0.1, 2.0]          # creator left out, holder order


def test_rugdata_balance_failure_leaves_no_sol(monkeypatch):
    monkeypatch.setattr(rugdata, "_sol_paused_until", 0.0)

    class Boom:
        def post(self, *a, **k):
            raise TimeoutError("slow")
    info = {"creator": None, "top_holders": [{"pct": 4.0, "owner": "A", "insider": False, "creator": False}]}
    rugdata._holder_balances(Boom(), info, {"requests": 0})
    assert "sol" not in info["top_holders"][0] and info.get("top5_sol") is None
    assert rugdata._sol_paused_until > 0


# ------------------------------------------------------------------ 3. chart tell
def test_chart_tell_on_monotonic_double():
    pts = [(i * 30, 1.0 + 0.12 * i) for i in range(10)]   # 1.0 -> 2.08
    out = chart_tell(pts)
    assert out == {"green_run": 9, "chart_tell": "straight run"}
    wiggle = list(pts)
    wiggle[5] = (150, pts[4][1] * 0.995)                   # one -0.5% tick is allowed
    assert chart_tell(wiggle)["chart_tell"] == "straight run"


def test_chart_tell_not_on_pullback_short_or_small():
    pts = [(i * 30, 1.0 + 0.15 * i) for i in range(10)]
    pulled = list(pts)
    pulled[5] = (150, pts[4][1] * 0.9)                     # a real -10% red candle
    out = chart_tell(pulled)
    assert out["chart_tell"] is None and out["green_run"] == 4
    assert chart_tell(pts[:7])["chart_tell"] is None       # under 8 points
    assert chart_tell([(i * 30, 1.0 + 0.05 * i) for i in range(10)])["chart_tell"] is None  # only 1.45x
    two_wiggles = list(pts)
    two_wiggles[3] = (90, pts[2][1] * 0.995)
    two_wiggles[6] = (180, pts[5][1] * 0.995)
    assert chart_tell(two_wiggles)["chart_tell"] is None


def test_chart_tell_flag_not_a_veto():
    pts = [(i * 30, 1.0 + 0.2 * i) for i in range(10)]
    s = _view(_curve(20.0), _flow(), prices=pts)
    assert _CHART_FLAG in s["flags"] and "vetoes" not in s


def test_arena_structure_carries_ramp_and_chart(arena_llm):
    from collections import deque
    a, name, view = arena_llm()
    now = view["now"]
    t = a.market.get("T1pump")
    t.update(dex="pumpfun", source="pumpfun", pump={"curve_pct": 55.0}, buys_h1=40, sells_h1=10,
             risk={"mint_revoked": True, "freeze_revoked": True})
    a.history["T1pump"] = deque([(now - 30 * (9 - i), 1.0 + 0.2 * i) for i in range(10)], maxlen=130)
    a.update_signals(now, force=True)
    s = a.structure["T1pump"]
    assert s["curve_pct"] == 55.0 and s["ramp"] == "ramp" and s["chart_tell"] == "straight run"


# ------------------------------------------------------------------ 4. hard stop
def _held(arena_llm, moonshot=False, own_stop=None):
    a, name, view = arena_llm()
    now = view["now"]
    t = a.market.get("T1pump")
    t["price"] = 1.0
    pos = {"symbol": "T1", "qty": 100.0, "cost": 100.0, "opened": now, "entry_spot": 1.0, "liq_entry": t["liquidity"],
           "peak_ts": now, "cost_in": 100.0}
    if moonshot:
        pos["moonshot"] = True
    a.accounts[name]["positions"]["T1pump"] = pos
    if own_stop is not None:
        a.accounts[name]["exits"]["T1pump"] = {"stop_loss_pct": own_stop, "set_at": now}
    return a, name, now, t


def test_hard_stop_fires_at_minus_30(arena_llm):
    a, name, now, t = _held(arena_llm)
    t["price"] = 0.75
    a.check_managed(now + 30)
    assert _sells(a) == []
    t["price"] = 0.69
    a.check_managed(now + 60)
    sells = _sells(a)
    assert len(sells) == 1 and sells[0][1]["reason"] == "hard stop: -30% from entry" and sells[0][1]["fraction"] == 1.0


def test_hard_stop_spares_moonshots_until_their_floor(arena_llm):
    a, name, now, t = _held(arena_llm, moonshot=True)
    t["price"] = 0.65
    a.check_managed(now + 30)
    assert _sells(a) == []
    t["price"] = 0.45
    a.check_managed(now + 60)
    assert [o["reason"] for _, o in _sells(a)] == ["hard stop: -50% from entry (moonshot floor)"]


def test_hard_stop_defers_to_a_tighter_own_stop(arena_llm):
    a, name, now, t = _held(arena_llm, own_stop=-20.0)
    t["price"] = 0.65
    a.check_managed(now + 30)
    assert not any(o["reason"].startswith("hard stop") for _, o in _sells(a))
    a2, name2, now2, t2 = _held(arena_llm, own_stop=-45.0)   # a looser own stop does not loosen it
    t2["price"] = 0.65
    a2.check_managed(now2 + 30)
    assert [o["reason"] for _, o in _sells(a2)] == ["hard stop: -30% from entry"]


# ------------------------------------------------------------------ 5. personas, roster and brief
def test_run9_roster(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_MODELS", raising=False)
    monkeypatch.setenv("ARENA_LLM", "claude-code")
    monkeypatch.setattr("claude_agents.shutil.which", lambda _: "claude")
    from claude_agents import build_llm_agents
    agents = build_llm_agents()
    assert [a.name for a in agents] == ["Haiku Ramp", "Sonnet Ramp", "Haiku Graduate", "Sonnet Graduate",
                                        "Haiku Scalper", "Haiku Shadow", "Haiku Degen", "Haiku Ape"]
    by = {a.name: a for a in agents}
    assert '"sell_at_graduation": true' in by["Haiku Ramp"].system
    assert "Your style: scalper. You buy curve coins early, $5k-$20k market cap" in by["Haiku Scalper"].system


def test_run9_persona_texts():
    assert "ramp_setup" in PERSONAS["ramp"][1] and '"stop_loss_pct": -20 on every ramp buy' in PERSONAS["ramp"][1]
    assert "take profit at +30% to +50% every" in PERSONAS["scalper"][1]
    for key in ("degen", "ape"):
        assert "the best ramp_setup or fresh graduate with net buying" in PERSONAS[key][1]
        assert "fastest curve fill" not in PERSONAS[key][1]


def test_run9_brief(monkeypatch):
    monkeypatch.setattr(market, "UNIVERSE", "pumpfun")
    b = fill_brief(LLM_SYSTEM, 1, 60)
    assert "ramp_setup" in b and "hard -30% stop" in b and "(moonshots -50%)" in b
    assert b.index("- Ramp: curve_pct is the coin's market cap as a share of the graduation cap") < b.index("- Rugs that look strong")
    assert '"sell_at_graduation": true' in b and "Never average down" in b
    assert "{" + "HARD_STOP_TEXT}" not in b
