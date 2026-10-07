def test_default_lineup_names(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_MODELS", raising=False)
    monkeypatch.setenv("ARENA_LLM", "claude-code")
    monkeypatch.setattr("claude_agents.shutil.which", lambda _: "claude")
    from claude_agents import build_llm_agents
    names = [a.name for a in build_llm_agents()]
    assert names == ["Haiku Graduate", "Haiku Runner", "Haiku Skeptic", "Haiku Shadow", "Sonnet Graduate", "Sonnet Shadow",
                     "Haiku Degen", "Haiku Ape"]


def test_risk_taker_personas(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_MODELS", raising=False)
    monkeypatch.setenv("ARENA_LLM", "claude-code")
    monkeypatch.setattr("claude_agents.shutil.which", lambda _: "claude")
    from claude_agents import build_llm_agents
    by_name = {a.name: a for a in build_llm_agents()}
    assert by_name["Haiku Degen"].avatar == "haiku-degen" and by_name["Haiku Ape"].avatar == "haiku-ape"
    assert "Your style: degen. You hunt fresh curve coins" in by_name["Haiku Degen"].system
    assert "Your style: ape. One conviction coin per life" in by_name["Haiku Ape"].system
