def test_reset_posts_verdict_rule(arena_llm):
    a, name, _ = arena_llm()
    a.reset_money(keep_journals=True)
    posts = a.db.room_posts(limit=5)
    texts = [p["text"] for p in posts if "Verdict per Claude" in p["text"]]
    assert texts
    assert texts[0] == ("Run 2 started: pump.fun only. Verdict per Claude after 7 days and 100 closed trades: "
                        "beats Random, Hold SOL and Graduates after the luck check at 90% confidence, "
                        "drawdown under 25%, profit factor over 1.2. Roster stays fixed until then.")


def test_reset_money_returns_season_number(tmp_path):
    import db as dbmod
    d = dbmod.DB(tmp_path / "s.db")
    d.add_trade(1.0, "A", "buy", "T", "T", 10, 1, 1, 1, 0, "x")
    assert d.reset_money() == 1
    d.add_trade(2.0, "A", "buy", "T", "T", 10, 1, 1, 1, 0, "x")
    assert d.reset_money() == 2
