"""Ctrl+C-proof watchdog for the arena.

Starts `python -u main.py <args>` and restarts it when it exits. Arguments given to this script (e.g.
--reset-money --wipe-journals) apply to the FIRST start only; restarts get none. Pressing Ctrl+C in the console
does nothing: the watchdog ignores SIGINT/SIGBREAK and the child runs in its own process group, so the console's
Ctrl+C event never reaches it. To stop the arena, create a file called stop.flag in this folder.

Test/debug override: ARENA_WATCHDOG_CHILD is a JSON list used instead of [python, -u, main.py] (args still appended).
"""
import datetime
import json
import os
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
RESTART_WAIT = 15.0   # seconds between a child exiting and the next start
POLL = 5.0            # seconds between stop.flag checks while the child runs
TERM_WAIT = 10.0      # seconds a terminated child gets before kill()
CTRL_C_MSG = "Ctrl+C ignored: create stop.flag to stop the arena"


def child_base_command():
    override = os.environ.get("ARENA_WATCHDOG_CHILD")
    if override:
        return list(json.loads(override))
    return [sys.executable, "-u", os.path.join(ROOT, "main.py")]


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log_path(root):
    logs = os.path.join(root, "logs")
    os.makedirs(logs, exist_ok=True)
    # Date re-evaluated at every child start, so a long-running watchdog rolls over to the next day's file.
    return os.path.join(logs, "arena-%s.log" % datetime.date.today().isoformat())


def _log_line(path, text):
    line = "[%s] %s" % (_now(), text)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def _stop_child(child, log, wait=TERM_WAIT):
    child.terminate()
    try:
        child.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
    _log_line(log, "stop.flag found: stopped")


def run(args=(), root=ROOT, restart_wait=None, poll=None, term_wait=None, popen=subprocess.Popen,
        base_cmd=None, max_starts=None):
    """Watchdog loop. Returns 0 when stop.flag stops it (or after max_starts starts, used by tests)."""
    restart_wait = RESTART_WAIT if restart_wait is None else restart_wait
    poll = POLL if poll is None else poll
    term_wait = TERM_WAIT if term_wait is None else term_wait
    flag = os.path.join(root, "stop.flag")
    first_args = list(args)
    starts = 0
    while True:
        if os.path.exists(flag):
            print("stop.flag found, not restarting", flush=True)
            return 0
        if max_starts is not None and starts >= max_starts:
            return 0
        cmd = list(base_cmd if base_cmd is not None else child_base_command()) + first_args
        first_args = []   # restarts after a crash get no arguments
        log = _log_path(root)
        _log_line(log, "starting " + " ".join(cmd))
        starts += 1
        with open(log, "ab") as out:
            child = popen(cmd, cwd=root, stdout=out, stderr=subprocess.STDOUT,
                          creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            while True:
                try:
                    if os.path.exists(flag):
                        _stop_child(child, log, term_wait)
                        return 0
                    try:
                        child.wait(timeout=poll)
                    except subprocess.TimeoutExpired:
                        continue
                    break
                except KeyboardInterrupt:
                    print(CTRL_C_MSG, flush=True)
        _log_line(log, "exited with %s, restarting in %ds" % (child.returncode, int(restart_wait)))
        slept = 0.0
        while slept < restart_wait and not os.path.exists(flag):
            try:
                step = min(1.0, restart_wait - slept)
                time.sleep(step)
                slept += step
            except KeyboardInterrupt:
                print(CTRL_C_MSG, flush=True)


def main(argv=None):
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except KeyboardInterrupt:
        print(CTRL_C_MSG, flush=True)
        return main(argv)


if __name__ == "__main__":
    sys.exit(main())
