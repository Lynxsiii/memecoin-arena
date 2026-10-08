"""Run 8b: points = a Claude's best single life, lives come back one per hour, journal wipe."""
import importlib.util
import json
import os

import arena as arena_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _claude(arena_llm):
    a, name, view = arena_llm()
    woke = []
    a.agents[name].wake = woke.append
    return a, name, view["now"], woke


def _board(a, name):
    return [{"name": name, "points": a.points(name)}]


def _bust(a, name, now):
    """Drive the Claude under the bust line and run the tick's peak tracking and bust check."""
    a.accounts[name]["cash"] = 50.0
    a.track_peaks(now)
    a.check_busts(now)


def _set_equity(a, name, usd, now):
    a.accounts[name]["cash"] = usd
    a.track_peaks(now)


def test_life_that_peaked_then_busted_keeps_its_peak(arena_llm):
    a, name, now, _ = _claude(arena_llm)
    _set_equity(a, name, 1400.0, now)            # +40% at the top
    _bust(a, name, now + 30)                     # ...then it busts
    acct = a.accounts[name]
    assert acct["lives_log"][0]["peak"] == 1400.0 and "life_peak" not in acct
    assert round(a.points(name), 6) == 40.0       # the busted life keeps its +40
    _set_equity(a, name, acct["life_start"] + 250, now + 60)   # life 2 peaks at +25
    _set_equity(a, name, acct["life_start"] + 50, now + 90)    # and is +5 now
    assert round(a.points(name), 6) == 40.0 and a.best_life(name)[0] == 1
    acct["runner_bonus"] = 5.0
    assert round(a.points(name), 6) == 45.0


def test_current_life_scores_its_peak(arena_llm):
    a, name, now, _ = _claude(arena_llm)
    _set_equity(a, name, 1250.0, now)            # peak +25
    _set_equity(a, name, 1050.0, now + 30)       # now +5
    assert round(a.points(name), 6) == 25.0
    s = a.your_score(name, _board(a, name), now + 30)
    assert s["this_life_peak_pct"] == 25.0 and s["this_life_pct"] == 5.0
    assert s["best_life_pct"] == 25.0 and s["best_life_no"] == 1 and s["leader_best_life_pct"] == 25.0
    a.accounts[name]["bonus"] = 30.0             # legacy milestone bonus no longer counts
    assert round(a.points(name), 6) == 25.0


def test_best_of_finished_lives_and_out(arena_llm):
    a, name, now, _ = _claude(arena_llm)
    _set_equity(a, name, 1150.0, now)            # life 1 peaks +15
    _bust(a, name, now + 30)
    _bust(a, name, now + 60)                     # life 2 never got above its start
    acct = a.accounts[name]
    _set_equity(a, name, acct["life_start"] + 80, now + 90)    # life 3 peaks +8
    _bust(a, name, now + 120)
    assert acct.get("out") and [round(l["peak"] - l["start"], 2) for l in acct["lives_log"]] == [150.0, 0.0, 80.0]
    assert round(a.points(name), 6) == 15.0 and a.best_life(name)[0] == 1


def test_legacy_lives_without_peak(arena_llm):
    a, name, now, _ = _claude(arena_llm)
    a.accounts[name].update(busts=[{"ts": now, "equity": 60}], stakes=2, life_start=1060.0, cash=1060.0,
                            lives_log=[{"life": 1, "start": 1000.0, "end": 60.0, "result": -940.0}])
    assert a.life_results(name) == [(1, 0.0), (2, 0.0)]


def test_bots_points_are_pnl(arena_llm):
    a, name, view = arena_llm(bot=True)
    a.accounts[name]["cash"] = 1100.0
    assert a.points(name) == a.pnl_pct(name)


def test_your_score_fields(arena_llm, monkeypatch):
    monkeypatch.setattr(arena_mod, "LIFE_REGEN_MIN", 60.0)
    a, name, now, _ = _claude(arena_llm)
    a.check_regen(now)                            # full lives: the clock waits at now
    _bust(a, name, now + 30)
    s = a.your_score(name, _board(a, name), now + 20 * 60)
    assert s["lives_left"] == 2 and s["next_life_in_min"] == 40
    assert "losses_count_this_life" not in s and "next_milestone" not in s


def test_next_life_zero_at_max_lives(arena_llm):
    a, name, now, _ = _claude(arena_llm)
    s = a.your_score(name, _board(a, name), now)
    assert s["lives_left"] == 3 and s["next_life_in_min"] == 0


def test_regen_clock_only_runs_below_full_lives(arena_llm, monkeypatch):
    monkeypatch.setattr(arena_mod, "LIFE_REGEN_MIN", 60.0)
    a, name, now, woke = _claude(arena_llm)
    acct = a.accounts[name]
    a.check_regen(now)
    a.check_regen(now + 7200)                     # two hours at full lives
    t = now + 7230
    _bust(a, name, t)
    a.check_regen(t)                              # same tick as the bust: no refund
    assert a.lives_info(name)["lives_left"] == 2
    a.check_regen(t + 3540)
    assert a.lives_info(name)["lives_left"] == 2
    woke.clear()
    a.check_regen(t + 3600)                       # an hour after the bust
    assert a.lives_info(name)["lives_left"] == 3 and acct["hearts"] == 1
    assert "You got a life back" in acct["life_event"]["text"] and woke
    assert not any("got a life back" in p["text"] for p in a.db.room_posts())  # not room news
    a.check_regen(t + 3600 + 7200)                # at full lives: nothing more
    assert acct["hearts"] == 1


def test_restart_does_not_grant_a_life_at_once(arena_llm, monkeypatch):
    monkeypatch.setattr(arena_mod, "LIFE_REGEN_MIN", 60.0)
    a, name, now, _ = _claude(arena_llm)
    acct = a.accounts[name]
    acct.update(busts=[{"ts": now - 86400, "equity": 50}], stakes=2, life_start=1050.0, cash=1050.0)
    acct.pop("life_regen_ts", None)               # saved before run 8b: no clock yet
    a.db.save_state(name, acct)
    b = arena_mod.Arena(a.market, a.db, list(a.agents.values()), start_cash=1000, tick=30)
    b.check_regen(b.started + 30)
    assert b.lives_info(name)["lives_left"] == 2
    b.check_regen(b.started + 3600)
    assert b.lives_info(name)["lives_left"] == 3


def test_regen_revives_an_out_claude(arena_llm, monkeypatch):
    monkeypatch.setattr(arena_mod, "LIFE_REGEN_MIN", 60.0)
    a, name, now, woke = _claude(arena_llm)
    agent, acct = a.agents[name], a.accounts[name]
    for i in range(3):
        _bust(a, name, now + i)
    assert acct.get("out") and a.lives_info(name)["lives_left"] == 0
    agent.ready, agent.next_run = (["stale order"], {}), now + 9999
    a.pending.append((name, {"action": "buy", "token": "T1pump", "usd": 60}))
    cash = acct["cash"]
    a.check_regen(now + 3)                        # the clock started at the first bust: not yet
    assert acct.get("out")
    a.check_regen(now + 3600)
    assert not acct.get("out") and acct["stakes"] == 4 and acct["cash"] == cash + 1000
    assert acct["life_start"] == a.equity(name) and "life_peak" not in acct
    assert a.lives_info(name)["lives_left"] == 1
    assert agent.ready is None and agent.next_run == 0 and not any(n == name for n, _ in a.pending)
    assert any("back in with a fresh stake" in w for w in woke)
    assert any("back in with a fresh stake" in p["text"] for p in a.db.room_posts())


def test_regen_off(arena_llm, monkeypatch):
    monkeypatch.setattr(arena_mod, "LIFE_REGEN_MIN", 0.0)
    a, name, now, _ = _claude(arena_llm)
    a.accounts[name].update(busts=[{"ts": now, "equity": 50}], life_regen_ts=now - 99999)
    a.check_regen(now)
    assert a.lives_info(name)["lives_left"] == 2
    assert a.your_score(name, _board(a, name), now)["next_life_in_min"] == 0


def test_milestones_add_nothing(arena_llm, monkeypatch):
    monkeypatch.setattr(arena_mod, "MILESTONE_PCT", 25.0)
    a, name, now, _ = _claude(arena_llm)
    acct = a.accounts[name]
    acct.update(busts=[{"ts": now, "equity": 50}], life_start=1000.0, cash=1600.0)
    a.check_milestones(now)
    assert acct.get("hearts", 0) == 0 and acct.get("bonus", 0.0) == 0.0


def test_milestone_default_off():
    assert arena_mod.MILESTONE_PCT == 0


def test_brief_scoring_paragraph():
    from claude_agents import LLM_SYSTEM, fill_brief
    b = fill_brief(LLM_SYSTEM, 1, 60)
    assert "Points = the best your best life ever reached, as % of the stake" in b and "Your lives are fuel" in b
    assert "high-water mark" in b and "this_life_peak_pct" in b
    assert "{" not in b.split("Scoring:")[1].split('"room_post"')[0]
    assert "milestone" not in b.lower()


def test_wipe_script(tmp_path, monkeypatch):
    import db as dbmod
    monkeypatch.setattr(arena_mod, "JOURNAL_DIR", str(tmp_path / "backups"))
    d = dbmod.DB(tmp_path / "w.db")
    d.save_journal("Haiku Runner", ["lesson a", "lesson b"])
    d.save_journal("Sonnet Shadow", ["lesson c"])
    d.save_state("Haiku Runner", {"cash": 5})
    d.conn.close()
    spec = importlib.util.spec_from_file_location("wipe_run8_memory", os.path.join(ROOT, "scripts", "wipe_run8_memory.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    backup = mod.wipe(str(tmp_path / "w.db"))
    assert backup and json.load(open(backup, encoding="utf-8"))["agents"]["Haiku Runner"]["journal"] == ["lesson a", "lesson b"]
    d = dbmod.DB(tmp_path / "w.db")
    assert d.journals() == {"Haiku Runner": [], "Sonnet Shadow": []}
    assert d.load_state("Haiku Runner") == {"cash": 5}


def test_memory_warmup_starts_at_run_start(tmp_path):
    """main.memory_since: this run's start (if within the last day) with ARENA_MEMORY_FROM_RUN=1, else 24 hours back."""
    import shutil
    import subprocess
    import sys
    shutil.copy(os.path.join(ROOT, "main.py"), tmp_path / "main.py")
    (tmp_path / ".env").write_text("", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "ARENA_MEMORY_FROM_RUN"}
    env.update(PYTHONPATH=ROOT, ARENA_PUMPFUN="0")
    code = ("import os, main, db; d = db.DB('m.db'); print(main.memory_since(d, 100000.0)); "
            "d.save_state('__run_started__', 50000.0); print(main.memory_since(d, 100000.0)); "
            "os.environ['ARENA_MEMORY_FROM_RUN'] = '0'; print(main.memory_since(d, 100000.0))")
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-3:] == ["13600.0", "50000.0", "13600.0"]
