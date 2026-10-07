"""Day-by-day results, so one lucky or unlucky day doesn't decide anything.

For every recorded day it shows the market's mood (what the average tracked token did over the following hour,
from the recordings) next to each agent's P&L for that day (from arena.db), so you can see who wins in falling,
flat and rising markets.

  python days.py               every recorded day
  python days.py --last 7      the last week
"""
import argparse
import glob
import os
import sqlite3
import time
from collections import defaultdict

import market_memory
import replay

HERE = os.path.dirname(os.path.abspath(__file__))


def mood(paths):
    """The pool's average and median 1-hour change after each sample, for one day's recordings."""
    m = market_memory.MarketMemory()
    m.load(replay.iter_snapshots(paths, None, None))
    if not m.samples:
        return None
    s = m.stats(m.samples[-1][0] + 3601)
    return s and s["all_tokens"]


def label(avg60):
    return "falling" if avg60 <= -2 else "rising" if avg60 >= 2 else "flat"


def summary(db_path=os.path.join(HERE, "arena.db"), rec_dir=os.path.join(HERE, "recordings"), last=None):
    """[{day, mood, pool_avg_60m_pct, pool_median_60m_pct, agents: {name: {pnl, trades}}}] oldest first."""
    files = defaultdict(list)
    for p in glob.glob(os.path.join(rec_dir, "[0-9]*.jsonl.gz")):
        files[replay._segment_key(p)[0]].append(p)
    pnl = defaultdict(dict)  # day -> agent -> P&L, summed over money-reset seasons within the day
    trades = defaultdict(lambda: defaultdict(int))
    if os.path.exists(db_path):
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        eq_sql = "SELECT 0, agent, ts, equity FROM equity"
        tr_sql = "SELECT agent, ts FROM trades"
        if "equity_archive" in tables:  # seasons archived by a money reset
            eq_sql += " UNION ALL SELECT season, agent, ts, equity FROM equity_archive"
        if "trades_archive" in tables:
            tr_sql += " UNION ALL SELECT agent, ts FROM trades_archive"
        span = {}  # (day, agent, season) -> [first equity, last equity]
        for season, agent, ts, eq in c.execute(f"SELECT * FROM ({eq_sql}) ORDER BY ts"):
            key = (time.strftime("%Y-%m-%d", time.localtime(ts)), agent, season)
            span.setdefault(key, [eq, eq])[1] = eq
        for (day, agent, _), (eq_first, eq_last) in span.items():
            pnl[day][agent] = pnl[day].get(agent, 0.0) + eq_last - eq_first
        for agent, ts in c.execute(tr_sql):
            trades[time.strftime("%Y-%m-%d", time.localtime(ts))][agent] += 1
    days = sorted(set(files) | set(pnl))
    if last:
        days = days[-last:]
    out = []
    for day in days:
        m = mood(sorted(files[day], key=replay._segment_key)) if day in files else None
        out.append({"day": day, "mood": label(m["avg_60m_pct"]) if m else None,
                    "pool_avg_60m_pct": m and m["avg_60m_pct"], "pool_median_60m_pct": m and m["median_60m_pct"],
                    "agents": {a: {"pnl": round(v, 2), "trades": trades[day][a]} for a, v in pnl[day].items()}})
    return out


def main():
    ap = argparse.ArgumentParser(description="Day-by-day market mood and agent results")
    ap.add_argument("--last", type=int, help="only the last N days")
    args = ap.parse_args()
    rows = summary(last=args.last)
    if not rows:
        print("No recorded days yet.")
        return
    agents = sorted({a for r in rows for a in r["agents"]})
    width = max([len(a) for a in agents] + [5])
    print(f"{'day':12}{'market':>9}{'pool 1h':>9}  " + "  ".join(f"{a[:width]:>{width}}" for a in agents))
    for r in rows:
        mood_txt = r["mood"] or "-"
        pool = f"{r['pool_avg_60m_pct']:+.1f}%" if r["pool_avg_60m_pct"] is not None else "-"
        cells = [f"{r['agents'][a]['pnl']:+.0f}" if a in r["agents"] else "-" for a in agents]
        print(f"{r['day']:12}{mood_txt:>9}{pool:>9}  " + "  ".join(f"{c:>{width}}" for c in cells))
    totals = {a: sum(r["agents"].get(a, {}).get("pnl", 0) for r in rows) for a in agents}
    print(f"{'total':12}{'':>18}  " + "  ".join(f"{totals[a]:>+{width}.0f}" for a in agents))
    wins = defaultdict(int)
    for r in rows:
        if r["agents"]:
            wins[max(r["agents"], key=lambda a: r["agents"][a]["pnl"])] += 1
    print("\nBest agent per day: " + ", ".join(f"{a} {n}x" for a, n in sorted(wins.items(), key=lambda x: -x[1])))
    print("Pool 1h = what the average tracked token did over the following hour that day "
          "(falling below -2%, rising above +2%).")


if __name__ == "__main__":
    main()
