from claude_agents import LLM_SYSTEM, PERSONAS, fill_brief


def test_brief_incentives():
    b = fill_brief(LLM_SYSTEM, 1, 60)
    assert "scores 0 and sits at the bottom" in b
    assert "base rate, not a veto" in b
    assert "cash earns nothing" in b
    assert "injected liquidity" in b


def test_risk_personas_buy_when_flat():
    for key in ("degen", "ape"):
        assert "buy the best ramp_setup or fresh graduate with net buying" in PERSONAS[key][1]

    assert "never chase a coin that already ran" not in PERSONAS["runner"][1]
