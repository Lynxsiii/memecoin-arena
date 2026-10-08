"""/api/summary headlines a Claude's current life; equity/pnl_pct stay the real-money view."""
import main


def _client(arena_llm, tmp_path):
    a, name, view = arena_llm()
    return a, name, view["now"], main.create_app(a, a.db, mock=True).test_client()


def _rows(client):
    return {r["name"]: r for r in client.get("/api/summary").get_json()["agents"]}


def test_llm_row_after_bust_shows_fresh_stake_and_real_loss(arena_llm, tmp_path):
    a, name, now, client = _client(arena_llm, tmp_path)
    a.agents[name].wake = lambda *_: None
    a.accounts[name]["cash"] = 50.0       # under the bust line
    a.track_peaks(now)
    a.check_busts(now)
    r = _rows(client)[name]
    assert r["stakes"] == 2
    assert abs(r["life_equity"] - a.accounts[name]["life_start"]) < 1 and r["life_equity"] > 1000 and r["life_equity"] == r["trading_equity"]
    assert abs(r["this_life_pct"]) < 0.1
    assert abs(r["pnl_pct"] - -95) < 1        # real money: $50 left of the first stake, the fresh $1000 does not count
    assert abs(r["equity"] - 50) < 1               # score equity stays the real-money number
    assert r["points"] >= 0
    assert r["best_life_no"] == 1 and r["this_life_peak_pct"] is not None
    assert r["next_life_in_min"] is not None


def test_bot_row_has_no_life_fields(arena_llm, tmp_path):
    a, name, view = arena_llm(bot=True)
    r = _rows(main.create_app(a, a.db, mock=True).test_client())[name]
    assert r["life_equity"] == r["equity"]
    assert r["this_life_pct"] is None and r["stakes"] is None and r["best_life_pct"] is None
