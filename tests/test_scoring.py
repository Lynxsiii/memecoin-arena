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


def test_best_life_counts_not_the_sum(arena_llm):
    a, name, now, _ = _claude(arena_llm)
    acct = a.accounts[name]
    acct.update(busts=[{"ts": now, "equity": 1400}], stakes=2, life_start=1000.0, cash=900.0,
                lives_log=[{"life": 1, "start": 1000.0, "end": 1400.0, "result": 400.0}])
    assert round(a.points(name), 6) == 40.0          # life 1 at +40 beats the current life at -10
    acct["runner_bonus"] = 5.0
    assert round(a.points(name), 6) == 45.0          # runner bonus on top


def test_best_of_two_finished_lives(arena_llm):
    a, name, now, _ = _claude(arena_llm)
    acct = a.accounts[name]
    acct.update(out=True, busts=[{"ts": now, "equity": 0}] * 3, cash=0.0, life_start=0.0,
                lives_log=[{"life": 1, "start": 1000.0, "end": 700.0, "result": -300.0},
                           {"life": 2, "start": 1000.0, "end": 1150.0, "result": 150.0},
                           {"life": 3, "start": 1000.0, "end": 50.0, "result": -950.0}])
    assert round(a.points(name), 6) == 15.0


def test_current_life_alone(arena_llm):
    a, name, now, _ = _claude(arena_llm)
    a.accounts[name]["cash"] = 1200.0
    assert round(a.points(name), 6) == 20.0
    a.accounts[name]["bonus"] = 30.0                 # legacy milestone bonus no longer counts
    assert round(a.points(name), 6) == 20.0


def test_bots_points_are_pnl(arena_llm):
    a, name, view = arena_llm(bot=True)
    a.accounts[name]["cash"] = 1100.0
    assert a.points(name) == a.pnl_pct(name)


def test_your_score_fields(arena_llm):
    a, name, now, _ = _claude(arena_llm)
    acct = a.accounts[name]
    acct.update(busts=[{"ts": now, "equity": 50}], stakes=2, life_start=1050.0, cash=1050.0 + 105.0,
                lives_log=[{"life": 1, "start": 1000.0, "end": 50.0, "result": -950.0}], life_regen_ts=now - 20 * 60)
    s = a.your_score(name, _board(a, name), now)
    assert s["best_life_pct"] == 10.5 and s["best_life_no"] == 2 and s["leader_best_life_pct"] == 10.5
    assert s["this_life_pct"] == 10.5 and s["lives_left"] == 2   # same basis as points: % of the $1000 stake
    assert s["next_life_in_min"] == 40
    assert "losses_count_this_life" not in s and "next_milestone" not in s


def test_next_life_zero_at_max_lives(arena_llm):
    a, name, now, _ = _claude(arena_llm)
    s = a.your_score(name, _board(a, name), now)
    assert s["lives_left"] == 3 and s["next_life_in_min"] == 0


def test_hourly_regen_grants_a_life(arena_llm, monkeypatch):
    monkeypatch.setattr(arena_mod, "LIFE_REGEN_MIN", 60.0)
    a, name, now, woke = _claude(arena_llm)
    acct = a.accounts[name]
    acct.update(busts=[{"ts": now, "equity": 50}], stakes=2, life_start=1000.0, life_regen_ts=now - 59 * 60)
    a.check_regen(now)
    assert a.lives_info(name)["lives_left"] == 2 and not woke     # not an hour yet
    a.check_regen(now + 61)
    assert a.lives_info(name)["lives_left"] == 3 and acct["hearts"] == 1 and acct["life_regen_ts"] == now + 61
    assert "You got a life back" in acct["life_event"]["text"] and woke
    a.check_regen(now + 7200)                                     # at max lives: nothing more
    assert acct["hearts"] == 1


def test_regen_revives_an_out_claude(arena_llm, monkeypatch):
    monkeypatch.setattr(arena_mod, "LIFE_REGEN_MIN", 60.0)
    a, name, now, woke = _claude(arena_llm)
    acct = a.accounts[name]
    acct.update(out=True, busts=[{"ts": now, "equity": 40}] * 3, stakes=3, cash=40.0, life_start=40.0,
                lives_log=[{"life": i, "start": 1000.0, "end": 40.0, "result": -960.0} for i in (1, 2, 3)],
                life_regen_ts=now - 3700)
    assert a.lives_info(name)["lives_left"] == 0
    a.check_regen(now)
    assert not acct.get("out") and acct["stakes"] == 4 and acct["cash"] == 1040.0
    assert acct["life_start"] == a.equity(name) == 1040.0
    assert a.lives_info(name)["lives_left"] == 1
    assert any("back in with a fresh stake" in w for w in woke)


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
    assert "best single life" in b and "Your lives are fuel" in b
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
