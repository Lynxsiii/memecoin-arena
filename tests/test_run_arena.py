"""Launcher watchdog tests: a fake child (sleep 0.2, exit 3) stands in for main.py; no real arena runs."""
import datetime
import glob
import json
import os
import subprocess
import sys
import threading
import time

import run_arena

FAKE = [sys.executable, "-c", "import time,sys; time.sleep(0.2); sys.exit(3)"]
SLOW = [sys.executable, "-c", "import time; time.sleep(30)"]


class RecordingPopen:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append((list(cmd), kw))
        return subprocess.Popen(cmd, **kw)


def _log_text(root):
    files = glob.glob(os.path.join(str(root), "logs", "arena-*.log"))
    assert len(files) == 1
    assert os.path.basename(files[0]) == "arena-%s.log" % datetime.date.today().isoformat()
    with open(files[0], encoding="utf-8") as f:
        return f.read()


def test_log_lines_args_first_start_only_and_process_group(tmp_path):
    rec = RecordingPopen()
    rc = run_arena.run(["--reset-money", "--wipe-journals"], root=str(tmp_path), restart_wait=0.1, poll=0.05,
                       popen=rec, base_cmd=FAKE, max_starts=2)
    assert rc == 0
    assert len(rec.calls) == 2
    first, second = rec.calls[0][0], rec.calls[1][0]
    assert first[-2:] == ["--reset-money", "--wipe-journals"]
    assert second == FAKE            # restart gets no arguments
    for _, kw in rec.calls:
        assert kw["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
        assert kw["stderr"] == subprocess.STDOUT
    text = _log_text(tmp_path)
    assert text.count("] starting ") == 2
    assert "--reset-money --wipe-journals" in text.splitlines()[0]
    assert text.count("exited with 3, restarting in 0s") == 2


def test_stop_flag_during_child_terminates_and_exits_0(tmp_path):
    flag = tmp_path / "stop.flag"
    threading.Timer(0.5, lambda: flag.write_text("x")).start()
    t0 = time.time()
    rec = RecordingPopen()
    rc = run_arena.run([], root=str(tmp_path), restart_wait=0.1, poll=0.1, term_wait=3, popen=rec, base_cmd=SLOW)
    assert rc == 0
    assert time.time() - t0 < 4
    assert len(rec.calls) == 1
    assert "stop.flag found: stopped" in _log_text(tmp_path)


def test_stop_flag_present_before_start_never_starts_child(tmp_path):
    (tmp_path / "stop.flag").write_text("x")
    rec = RecordingPopen()
    assert run_arena.run([], root=str(tmp_path), popen=rec, base_cmd=FAKE) == 0
    assert rec.calls == []


def test_env_override_of_child_command(monkeypatch):
    monkeypatch.setenv("ARENA_WATCHDOG_CHILD", json.dumps(FAKE))
    assert run_arena.child_base_command() == FAKE
    monkeypatch.delenv("ARENA_WATCHDOG_CHILD")
    cmd = run_arena.child_base_command()
    assert cmd[1] == "-u" and cmd[2].endswith("main.py")
