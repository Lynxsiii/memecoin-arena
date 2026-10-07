"""Run 8b one-off: wipe every Claude journal (the market changed; the user's choice, 2026-10-07).

Run it while the arena is STOPPED: a running arena keeps each journal in memory and would write it straight back.

    python scripts/wipe_run8_memory.py              # arena.db next to main.py
    python scripts/wipe_run8_memory.py --db other.db

Every journal is backed up to journal_backups/<date>_<time>.json first (arena.backup_journals), then each one is saved
empty (db.save_journal(name, [])); the journals live in the state table as __journal__:<name> rows, so those rows end
up holding []. Money, trades, lives and everything else are left alone. The script refuses to run while something
answers on the dashboard port (8000 by default) unless --force is given.
"""
import argparse
import os
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import arena  # noqa: E402
from db import DB  # noqa: E402


def wipe(db_path):
    """Back up, then empty, every journal in db_path. Returns the backup file path (None when there were none)."""
    db = DB(db_path)
    try:
        journals = db.journals()
        backup = arena.backup_journals(db, "run 8b wipe")
        for name in journals:
            db.save_journal(name, [])
        left = {n: j for n, j in db.journals().items() if j}
        if left:
            raise RuntimeError(f"journals still hold lessons after the wipe: {sorted(left)}")
        print(f"[wipe] {len(journals)} journal(s) wiped ({sum(len(j) for j in journals.values())} lessons); backup: {backup}")
        return backup
    finally:
        db.conn.close()


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    ap = argparse.ArgumentParser(description="Back up and wipe every Claude journal (run 8b). Stop the arena first.")
    ap.add_argument("--db", default=os.path.join(ROOT, "arena.db"), help="database file (default: arena.db)")
    ap.add_argument("--port", type=int, default=8000, help="dashboard port to check the arena is stopped (default 8000)")
    ap.add_argument("--force", action="store_true", help="wipe even though something answers on the port")
    args = ap.parse_args()
    if not os.path.exists(args.db):
        sys.exit(f"[wipe] no database at {args.db}")
    if port_in_use(args.port) and not args.force:
        sys.exit(f"[wipe] something answers on port {args.port}: stop the arena first (a running arena would write "
                 f"its journals straight back), or pass --force")
    wipe(args.db)


if __name__ == "__main__":
    main()
