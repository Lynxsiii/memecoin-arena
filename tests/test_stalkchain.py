"""StalkChain integration (stalkchain.py): the credit-budgeted client, the summaries, the pre-buy check in validate()
and the smart-money entries. Every response is canned; nothing touches the network."""
import requests

import main
import signals
import stalkchain
from claude_agents import LLM_SYSTEM, fill_brief

MINT = "T1pump"
NEW_MINT = "Smart111111111111111111111111111111111pump"
DEPLOYER = "Dep1oyer11111111111111111111111111111111"


class _Resp:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class _Session:
    """Answers GET /tools/{name} from `answers` ({name: (status, body) | Exception}) and records every call."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def get(self, url, params=None, headers=None, timeout=None):
        name = url.rsplit("/", 1)[1]
        self.calls.append((name, dict(params or {}), dict(headers or {}), timeout))
        a = self.answers[name]
        if isinstance(a, Exception):
            raise a
        return _Resp(*a)


def _credits(cost, balance=374_000):
    return {"cost": cost, "balance": balance, "endpoints": ["x"]}


DEPLOYER_RAW = {"data": {"deployer": DEPLOYER, "graduatedCount": 1, "launches": [
    {"mint": MINT, "symbol": "THIS", "marketCap": 30000, "liquidity": 9000},          # the coin itself: left out
    {"mint": "A" * 40, "symbol": "A", "marketCap": 3100, "liquidity": 0, "graduated": False},
    {"mint": "B" * 40, "symbol": "B", "marketCap": 2500, "graduated": False},
    {"mint": "C" * 40, "symbol": "C", "status": "rugged"},
    {"mint": "D" * 40, "symbol": "D", "marketCap": 900000, "liquidity": 120000, "graduated": True},
]}, "credits": _credits(500)}
EARLY_RAW = {"data": {"buyers": [
    {"wallet": "w1", "isSniper": True, "supplyPct": 20, "sold": True},
    {"wallet": "w2", "isSniper": True, "supplyPct": 25, "sold": True},
    {"wallet": "w3", "isSniper": False, "supplyPct": 3, "sold": False},
    {"wallet": "w4", "isSniper": False, "supplyPct": 2, "sold": True},
], "bundles": {"count": 2, "supplyPct": 18}}, "credits": _credits(500)}
CLEAN_EARLY_RAW = {"data": {"buyers": [{"wallet": "w1", "isSniper": False, "sold": False}], "bundled": False},
                   "credits": _credits(500)}
QUALITY_RAW = {"data": {"isVerified": False, "organicScore": 12.5, "audit": {"devMints": 7},
                        "stats24h": {"buyVolume": 60000, "sellVolume": 40000, "buyOrganicVolume": 9000,
                                     "sellOrganicVolume": 6000}}, "credits": _credits(250)}
ENTRIES_RAW = {"data": {"tokens": [
    {"token": NEW_MINT, "symbol": "SMRT", "chain": "solana", "traders": [{"userId": 1}, {"userId": 2}, {"userId": 3}],
     "firstEntry": "2026-10-09T10:00:00Z", "lastEntry": "2026-10-09T10:20:00Z"},
    {"token": "0xabc", "symbol": "BASE", "chain": "base", "traderCount": 5},
    {"token": MINT, "symbol": "OLD", "chain": "solana", "traderCount": 4,
     "firstEntry": 1_791_540_000_000, "lastEntry": 1_791_540_600},
]}, "credits": _credits(125)}


def _client(answers, clock=None, **kw):
    s = _Session(answers)
    c = stalkchain.Client("sc_test", session=s, clock=clock or (lambda: 1_000_000.0), **kw)
    return c, s


# ------------------------------------------------------------------ client
def test_success_parses_credits_block_and_updates_stats():
    c, s = _client({"stalkchain_token_deployer": (200, DEPLOYER_RAW)})
    assert c.deployer(MINT) == DEPLOYER_RAW
    name, params, headers, timeout = s.calls[0]
    assert name == "stalkchain_token_deployer" and params == {"token": MINT}
    assert headers["Authorization"] == "Bearer sc_test" and timeout == 4.0
    assert c.stats["calls"] == 1 and c.stats["credits"] == 500 and c.stats["balance"] == 374_000
    assert c.stats["errors"] == 0 and c.stats["credits_24h"] == 500


def test_missing_cost_falls_back_to_the_documented_price():
    c, _ = _client({"stalkchain_token_quality": (200, {"data": {}, "credits": {"balance": 10}})})
    c.quality(MINT)
    assert c.stats["credits"] == 250 and c.stats["balance"] == 10


def test_402_sets_paywalled_and_returns_none(capsys):
    c, s = _client({"stalkchain_token_deployer": (402, {"error": "This tool needs a plan: https://data.stalkchain.com/#plans"}),
                    "stalkchain_account": (200, {"data": {"balance": 0}, "credits": _credits(0, 0)})})
    assert c.deployer(MINT) is None
    assert c.paywalled and c.stats["paywalled"] and c.stats["errors"] == 1
    assert c.deployer("X" * 40) is None          # skipped without a call while paywalled
    assert len(s.calls) == 1 and c.stats["skipped"] == 1
    assert c.account() is not None               # free tools still answer
    assert capsys.readouterr().out.count("no paid plan") == 1


def test_plan_error_in_a_200_body_also_paywalls():
    c, _ = _client({"stalkchain_token_deployer": (200, {"error": {"message": "Out of credits: pick a plan"}})})
    assert c.deployer(MINT) is None and c.paywalled


def test_401_turns_the_client_off():
    c, s = _client({"stalkchain_token_deployer": (401, {"error": "bad key"}), "stalkchain_health": (200, {"data": {}})})
    assert c.deployer(MINT) is None and c.unauthorized
    assert c.health() is None and len(s.calls) == 1


def test_timeout_returns_none_and_backs_off():
    clock = [1_000_000.0]
    c, s = _client({"stalkchain_token_deployer": requests.Timeout("slow"),
                    "stalkchain_token_quality": (200, QUALITY_RAW)}, clock=lambda: clock[0])
    assert c.deployer(MINT) is None
    assert c.stats["errors"] == 1 and c.stats["credits"] == 0
    assert c.quality(MINT) is None and c.stats["skipped"] == 1   # backing off for a minute
    clock[0] += stalkchain.ERROR_BACKOFF_SECS + 1
    assert c.quality(MINT) is not None


def test_bad_json_and_5xx_return_none():
    c, _ = _client({"stalkchain_token_deployer": (502, ValueError("not json"))})
    assert c.deployer(MINT) is None and c.stats["errors"] == 1


def test_cache_hit_does_not_call_again():
    clock = [1_000_000.0]
    c, s = _client({"stalkchain_token_deployer": (200, DEPLOYER_RAW)}, clock=lambda: clock[0], cache_h=6)
    c.deployer(MINT)
    clock[0] += 3600
    assert c.deployer(MINT) == DEPLOYER_RAW
    assert len(s.calls) == 1 and c.stats["cached"] == 1 and c.stats["credits"] == 500
    clock[0] += 6 * 3600     # expired
    c.deployer(MINT)
    assert len(s.calls) == 2


def test_entries_are_never_cached():
    c, s = _client({"stalkchain_fomo_multi_trader_entries": (200, ENTRIES_RAW)})
    c.multi_trader_entries()
    c.multi_trader_entries()
    assert len(s.calls) == 2
    assert s.calls[0][1] == {"windowMinutes": 60, "minTraders": 3, "side": "buy", "chain": "solana", "limit": 20}


def test_daily_budget_stops_calls_and_frees_up_after_24h(capsys):
    clock = [1_000_000.0]
    c, s = _client({"stalkchain_token_deployer": (200, DEPLOYER_RAW)}, clock=lambda: clock[0], daily_credits=1000)
    c.deployer("A" * 40)
    c.deployer("B" * 40)
    assert c.deployer("C" * 40) is None
    assert len(s.calls) == 2 and c.stats["skipped"] == 1 and c.stats["credits_24h"] == 1000
    assert "daily credit budget" in capsys.readouterr().out
    clock[0] += 86400
    assert c.deployer("C" * 40) is not None and len(s.calls) == 3


def test_call_never_raises():
    class Boom:
        def get(self, *a, **k):
            raise RuntimeError("kaput")
    c = stalkchain.Client("sc_test", session=Boom())
    assert c.deployer(MINT) is None and c.stats["errors"] == 1


def test_shared_is_none_without_a_key(monkeypatch):
    monkeypatch.setattr(stalkchain, "_SHARED", None)
    monkeypatch.setattr(stalkchain, "KEY", "")
    assert stalkchain.shared() is None
    monkeypatch.setattr(stalkchain, "KEY", "sc_x")
    assert isinstance(stalkchain.shared(), stalkchain.Client) and stalkchain.shared() is stalkchain.shared()


# ------------------------------------------------------------------ summaries
def test_summarize_deployer():
    d = stalkchain.summarize_deployer(DEPLOYER_RAW, MINT)
    assert d == {"deployer": DEPLOYER, "launched": 4, "rugged": 3, "graduated": 1, "rug_rate": 0.75}


def test_summarize_deployer_from_totals_only():
    d = stalkchain.summarize_deployer({"data": {"creator": DEPLOYER, "launchCount": 11, "rugCount": 9}}, MINT)
    assert d["launched"] == 10 and d["rugged"] == 9 and d["rug_rate"] == 0.9


def test_summarize_early_buyers():
    e = stalkchain.summarize_early_buyers(EARLY_RAW)
    assert e["sniped_pct"] == 45.0 and e["bundled"] is True and e["bundle_pct"] == 18.0
    assert e["early_buyers_sold_pct"] == 75.0 and e["buyers"] == 4


def test_summarize_quality():
    q = stalkchain.summarize_quality(QUALITY_RAW)
    assert q == {"wash_pct": 85.0, "verified": False, "organic_score": 12.5, "dev_mints": 7}


def test_summaries_of_empty_input_keep_their_keys():
    for raw in ({}, None, {"data": None}, {"data": []}):
        assert stalkchain.summarize_deployer(raw) == {"deployer": None, "launched": None, "rugged": None,
                                                      "graduated": None, "rug_rate": None}
        assert stalkchain.summarize_early_buyers(raw) == {"sniped_pct": None, "bundled": None, "bundle_pct": None,
                                                          "early_buyers_sold_pct": None, "buyers": None}
        assert stalkchain.summarize_quality(raw) == {"wash_pct": None, "verified": None, "organic_score": None,
                                                     "dev_mints": None}
        assert stalkchain.summarize_entries(raw) == []


def test_summarize_entries_solana_only_newest_first():
    rows = stalkchain.summarize_entries(ENTRIES_RAW)
    assert [r["mint"] for r in rows] == [NEW_MINT, MINT]   # the base row is dropped; newest last entry first
    new, old = rows
    assert new["symbol"] == "SMRT" and new["traders"] == 3 and new["last_ts"] - new["first_ts"] == 1200
    assert old["traders"] == 4 and old["first_ts"] == 1_791_540_000 and old["last_ts"] == 1_791_540_600


def test_verdict_veto_and_flags():
    v = signals.stalkchain_verdict({"deployer": stalkchain.summarize_deployer(DEPLOYER_RAW, MINT),
                                    "early_buyers": stalkchain.summarize_early_buyers(EARLY_RAW)})
    assert v["veto"] == "the deployer rugged 3 of 4 earlier launches"
    assert "45% of supply sniped at launch" in v["flags"] and "bundled launch (18% of supply)" in v["flags"]
    assert v["view"]["deployer_rugged"] == 3 and v["view"]["veto"] == v["veto"]
    clean = signals.stalkchain_verdict({"deployer": {"launched": 3, "rugged": 1, "rug_rate": 0.33}})
    assert clean["veto"] is None and clean["flags"] == []
    half = signals.stalkchain_verdict({"deployer": {"launched": 2, "rugged": 1, "rug_rate": 0.5}})
    assert half["veto"] == "the deployer rugged 1 of 2 earlier launches"
    assert signals.stalkchain_verdict({})["veto"] is None


# ------------------------------------------------------------------ the pre-buy check in validate()
def _buy(usd=60):
    return {"action": "buy", "token": MINT, "usd": usd, "reason": "ramp"}


def test_validate_vetoes_a_rugger_deployer(arena_llm):
    a, name, view = arena_llm()
    a.stalkchain, s = _client({"stalkchain_token_deployer": (200, DEPLOYER_RAW),
                               "stalkchain_token_early_buyers": (200, CLEAN_EARLY_RAW)})
    o = _buy()
    assert a.validate(a.agents[name], o, view) is None
    sym = a.market.get(MINT)["symbol"]
    assert a.accounts[name]["recent_failures"][-1]["text"] == \
        f"your buy of {sym} ($60) was refused: StalkChain says the deployer rugged 3 of 4 earlier launches"
    assert a.vetoes[MINT] == ["StalkChain: the deployer rugged 3 of 4 earlier launches"]
    assert a.structure[MINT]["stalkchain"]["deployer_rugged"] == 3
    assert [c[0] for c in s.calls] == ["stalkchain_token_deployer", "stalkchain_token_early_buyers"]
    a.update_signals(view["now"], force=True)       # the 60 s signal refresh keeps the verdict
    assert "StalkChain: the deployer rugged 3 of 4 earlier launches" in a.vetoes[MINT]
    assert a.structure[MINT]["stalkchain"]["veto"]
    assert a.validate(a.agents[name], _buy(), view) is None
    assert len(s.calls) == 2                        # vetoed for good, no second lookup


def test_validate_allows_when_the_client_returns_none(arena_llm):
    a, name, view = arena_llm()
    a.stalkchain, s = _client({"stalkchain_token_deployer": requests.Timeout("slow"),
                               "stalkchain_token_early_buyers": requests.Timeout("slow")})
    ok = a.validate(a.agents[name], _buy(), view)
    assert ok is not None and ok["usd"] == 60
    assert MINT not in a.vetoes and MINT not in a.sc_verdicts


def test_flags_do_not_block_and_verdict_is_cached(arena_llm):
    a, name, view = arena_llm()
    a.stalkchain, s = _client({"stalkchain_token_deployer": (200, {"data": {"deployer": DEPLOYER, "launches": []},
                                                                    "credits": _credits(500)}),
                               "stalkchain_token_early_buyers": (200, EARLY_RAW)})
    assert a.validate(a.agents[name], _buy(), view) is not None
    sc = a.structure[MINT]["stalkchain"]
    assert sc["sniped_pct"] == 45.0 and sc["bundled"] is True and "veto" not in sc
    assert "45% of supply sniped at launch" in sc["flags"]
    assert MINT not in a.vetoes
    assert a.validate(a.agents[name], _buy(), view) is not None
    assert len(s.calls) == 2                        # the second buy reuses the verdict


def test_partial_verdict_retries_only_the_missing_lookup(arena_llm):
    a, name, view = arena_llm()
    clean_dep = {"data": {"deployer": DEPLOYER, "launches": []}, "credits": _credits(500)}
    a.stalkchain, s = _client({"stalkchain_token_deployer": (200, clean_dep),
                               "stalkchain_token_early_buyers": (502, {"error": "upstream"})})
    assert a.validate(a.agents[name], _buy(), view) is not None
    assert not a.sc_verdicts[MINT]["complete"]
    s.answers["stalkchain_token_early_buyers"] = (200, CLEAN_EARLY_RAW)
    a.stalkchain._backoff_until = 0
    assert a.validate(a.agents[name], _buy(), view) is not None
    assert [c[0] for c in s.calls].count("stalkchain_token_deployer") == 1   # the client cache served it
    assert a.sc_verdicts[MINT]["complete"]


def test_never_runs_for_bots(arena_llm):
    a, name, view = arena_llm(bot=True)
    a.stalkchain, s = _client({"stalkchain_token_deployer": (200, DEPLOYER_RAW),
                               "stalkchain_token_early_buyers": (200, EARLY_RAW)})
    assert a.validate(a.agents[name], _buy(), view) is not None
    assert s.calls == []


def test_refused_buys_spend_no_credits(arena_llm):
    a, name, view = arena_llm()
    a.stalkchain, s = _client({"stalkchain_token_deployer": (200, DEPLOYER_RAW),
                               "stalkchain_token_early_buyers": (200, EARLY_RAW)})
    assert a.validate(a.agents[name], _buy(usd=20), view) is None    # under the $50 minimum
    assert s.calls == []


def test_off_without_a_client(arena_llm):
    a, name, view = arena_llm()
    assert a.stalkchain is None
    assert a.validate(a.agents[name], _buy(), view) is not None
    assert "smart_entries" not in a.llm_context(name, view["now"])


# ------------------------------------------------------------------ smart-money entries
def test_smart_entries_land_in_the_view_and_track_new_mints(arena_llm):
    a, name, view = arena_llm()
    a.stalkchain, s = _client({"stalkchain_fomo_multi_trader_entries": (200, ENTRIES_RAW)})
    now = 1_791_541_200.0                            # 2026-10-09T10:20:00Z
    assert a.market.get(NEW_MINT) is None
    a.poll_smart_entries(now)
    t = a.market.get(NEW_MINT)
    assert t is not None and "copy" in t["sources"]
    ctx = a.llm_context(name, now)
    se = ctx["smart_entries"]
    assert [e["token"] for e in se] == [NEW_MINT, MINT]
    assert se[1]["last_entry_min_ago"] == 10.0 and se[1]["symbol"] == "OLD"
    assert se[0] == {"token": NEW_MINT, "symbol": "SMRT", "traders": 3, "first_entry_min_ago": 20.0,
                     "last_entry_min_ago": 0.0}
    a.poll_smart_entries(now + 60)                   # not due yet
    assert len(s.calls) == 1
    a.poll_smart_entries(now + stalkchain.ENTRIES_MIN * 60)
    assert len(s.calls) == 2


def test_smart_entries_reach_the_claude_state(arena_llm):
    import claude_agents
    a, name, view = arena_llm()
    agent = claude_agents.LLMAgent.__new__(claude_agents.LLMAgent)
    v = {**view, "smart_entries": [{"token": NEW_MINT, "symbol": "SMRT", "traders": 3}]}
    agent.note, agent.watch, agent.wake_reason, agent.wake_tokens = "", None, None, set()
    agent.get_journal = lambda: []
    agent.mode = lambda: "normal"
    assert claude_agents.LLMAgent._state(agent, v)["smart_entries"] == v["smart_entries"]
    assert "smart_entries" not in claude_agents.LLMAgent._state(agent, view)


def test_failed_entries_poll_keeps_the_last_list(arena_llm):
    a, name, view = arena_llm()
    a.stalkchain, s = _client({"stalkchain_fomo_multi_trader_entries": (200, ENTRIES_RAW)})
    a.poll_smart_entries(1_791_541_200.0)
    s.answers["stalkchain_fomo_multi_trader_entries"] = requests.Timeout("slow")
    a.poll_smart_entries(1_791_541_200.0 + 3600)
    assert len(a.smart_entries) == 2


# ------------------------------------------------------------------ brief and /api/summary
def test_brief_mentions_stalkchain_only_when_on(monkeypatch):
    off = fill_brief(LLM_SYSTEM, 1, 60)
    assert "smart_entries" not in off and "structure.stalkchain" not in off and "{STALKCHAIN" not in off
    monkeypatch.setattr(stalkchain, "_SHARED", stalkchain.Client("sc_x", session=_Session({})))
    on = fill_brief(LLM_SYSTEM, 1, 60)
    assert "- smart_entries: coins that 3 or more of StalkChain's tracked traders bought" in on
    assert "answer shows on later looks as structure.stalkchain" in on and "is a hard no" in on
    assert on.index("- smart_money:") < on.index("- smart_entries:") < on.index("- scoreboard:")


def test_summary_carries_stalkchain_stats(arena_llm):
    a, name, view = arena_llm()
    app = main.create_app(a, a.db, mock=True).test_client()
    assert "stalkchain" not in app.get("/api/summary").get_json()
    a.stalkchain, _ = _client({"stalkchain_token_deployer": (200, DEPLOYER_RAW)})
    a.stalkchain.deployer(MINT)
    st = app.get("/api/summary").get_json()["stalkchain"]
    assert st["calls"] == 1 and st["credits"] == 500 and st["balance"] == 374_000


def test_other_errors_do_not_paywall():
    c, _ = _client({"stalkchain_token_deployer": (400, {"error": "invalid arguments, see the explanation"})})
    assert c.deployer(MINT) is None and not c.paywalled and c.stats["errors"] == 1
