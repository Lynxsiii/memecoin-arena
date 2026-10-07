def test_default_lineup_names(monkeypatch):
    monkeypatch.delenv("ARENA_LLM_MODELS", raising=False)
    monkeypatch.setenv("ARENA_LLM", "claude-code")
    monkeypatch.setattr("claude_agents.shutil.which", lambda _: "claude")
    from claude_agents import build_llm_agents
    names = [a.name for a in build_llm_agents()]
    assert names == ["Haiku Graduate", "Haiku Runner", "Haiku Skeptic", "Haiku Shadow", "Sonnet Graduate", "Sonnet Shadow"]
