from traders import rank_wallets


def _st(w, realized, unreal, rts, win, toks):
    return {"wallet": w, "pnl_usd": realized + unreal, "realized_usd": realized, "unrealized_usd": unreal,
            "roi_pct": 10, "trades": 20, "buys": 10, "sells": 10, "tokens": toks, "tokens_bought": toks, "held": 1,
            "win_rate": win, "volume_usd": 5000, "spent_usd": 2500, "first_trade_ts": 0, "last_trade_ts": 0,
            "flips": 0, "round_trips": rts, "same_block": 0}


def test_realized_rule_ignores_unrealized():
    stats = {"bag": _st("bag", 100, 20000, 6, 60, 4), "pro": _st("pro", 900, -50, 8, 70, 5)}
    assert [s["wallet"] for s in rank_wallets(stats, 10, rule="realized")] == ["pro", "bag"]
    assert [s["wallet"] for s in rank_wallets(stats, 10, rule="pnl")] == ["bag", "pro"]


def test_realized_rule_eligibility():
    stats = {"few": _st("few", 900, 0, 4, 80, 5), "lossy": _st("lossy", 900, 0, 9, 40, 5), "ok": _st("ok", 10, 0, 5, 50, 3)}
    assert [s["wallet"] for s in rank_wallets(stats, 10, rule="realized")] == ["ok"]


def test_realized_rule_no_win_rate_is_ineligible():
    stats = {"none": _st("none", 900, 0, 9, None, 5), "ok": _st("ok", 10, 0, 5, 50, 3)}
    assert [s["wallet"] for s in rank_wallets(stats, 10, rule="realized")] == ["ok"]


def test_default_rule_is_module_rank(monkeypatch):
    import traders
    stats = {"bag": _st("bag", 100, 20000, 6, 60, 4), "pro": _st("pro", 900, -50, 8, 70, 5)}
    monkeypatch.setattr(traders, "RANK", "realized")
    assert [s["wallet"] for s in rank_wallets(stats, 10)] == ["pro", "bag"]
    monkeypatch.setattr(traders, "RANK", "pnl")
    assert [s["wallet"] for s in rank_wallets(stats, 10)] == ["bag", "pro"]


def test_copy_top10_bot():
    from copy_agents import build_copy_top10
    b = build_copy_top10()
    assert (b.name, b.lo, b.hi, b.fraction, b.window_secs) == ("Copy Top 10", 1, 10, 0.10, 60)
    assert "ranked by realized profit over the last two days" in b.description


def test_old_copy_bots_keep_defaults():
    from copy_agents import build_copy_bots
    assert all((b.fraction, b.window_secs) == (0.05, 300) for b in build_copy_bots())


def test_build_bots_includes_copy_top10():
    from agents import build_bots
    assert [b.name for b in build_bots()][-1] == "Copy Top 10"


def test_realized_rule_losing_gate_reads_realized():
    stats = {"hurt": _st("hurt", 900, -1000, 6, 60, 4)}
    assert [s["wallet"] for s in rank_wallets(stats, 10, rule="realized")] == ["hurt"]
    assert rank_wallets(stats, 10, rule="pnl") == []
