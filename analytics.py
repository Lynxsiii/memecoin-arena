"""Who's really winning: luck checks, confidence against the benchmark bots, risk- and cost-adjusted results,
and a readiness checklist per Claude. Served at GET /api/analytics, which the dashboard polls, so the result
is cached for 30 seconds. Add ?from=<epoch>&to=<epoch> for one day's standings, trades and usage (the recap page).

Everything here is descriptive statistics on the arena's own records. "Sharpe-like" is the mean of 15-minute
equity returns divided by their standard deviation, not annualised. Confidence figures come from a bootstrap:
the per-bucket return differences between an agent and a benchmark are resampled with replacement and the
figure is the share of resamples in which the agent came out ahead."""
import random
import statistics
import threading
import time

BUCKET = 900                    # equity returns are measured over 15-minute buckets
BOOTSTRAPS = 2000
MIN_CLOSED, MIN_HOURS = 20, 2   # below this a confidence figure is marked "not enough data"
BENCHMARKS = ("Random", "Hold SOL", "Graduates")  # Index was retired after run 2
CACHE_TTL = 30
READY = {"days": 7, "closed_trades": 100, "confidence": 0.9, "max_drawdown_pct": 25, "profit_factor": 1.2,
         "max_fail_rate": 0.3, "fail_window": 20}

_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()


def _rows(db, sql, args=()):
    with db.lock:
        return [dict(r) for r in db.conn.execute(sql, args).fetchall()]


def _one(db, sql, args=()):
    with db.lock:
        row = db.conn.execute(sql, args).fetchone()
    return dict(row) if row else None


def max_drawdown(series):
    peak = mdd = 0.0
    for _, eq in series:
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, (peak - eq) / peak)
    return mdd * 100


def bucket_returns(series):
    """Equity at the end of each 15-minute bucket -> {bucket: simple return since the previous sampled bucket}."""
    last = {}
    for ts, eq in series:
        last[int(ts // BUCKET)] = eq
    keys = sorted(last)
    return {b: last[b] / last[a] - 1 for a, b in zip(keys, keys[1:]) if last[a] > 0}


def bootstrap_beats(ra, rb, rng, n_boot=BOOTSTRAPS):
    """P(agent a's mean 15-minute return is above b's), from resampling the per-bucket differences.
    Returns (probability or None, number of shared buckets)."""
    common = sorted(set(ra) & set(rb))
    d = [ra[k] - rb[k] for k in common]
    n = len(d)
    if n < 2:
        return None, n
    if all(x == 0 for x in d):
        return 0.5, n
    score = 0.0
    for _ in range(n_boot):
        s = sum(rng.choices(d, k=n))
        score += 1 if s > 0 else 0.5 if s == 0 else 0
    return score / n_boot, n


def trade_stats(trades):
    """Closed-trade statistics for one agent's trades, oldest first. Hold time runs from the first buy that
    opened a position to each sell out of it."""
    sells = [t for t in trades if t["side"] == "sell" and t["pnl"] is not None]
    wins = [t["pnl"] for t in sells if t["pnl"] > 0]
    losses = [-t["pnl"] for t in sells if t["pnl"] < 0]
    opened, last_side, holds = {}, {}, []
    for t in trades:
        tok = t["token"]
        if t["side"] == "buy":
            if last_side.get(tok) != "buy":
                opened[tok] = t["ts"]
        elif tok in opened:
            holds.append(t["ts"] - opened[tok])
        last_side[tok] = t["side"]
    gw, gl = sum(wins), sum(losses)
    return {
        "trades": len(trades), "closed": len(sells), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(sells) * 100, 1) if sells else None,
        "gross_wins": round(gw, 2), "gross_losses": round(gl, 2),
        "profit_factor": round(gw / gl, 2) if gl else None,   # None with wins > 0 means no losing trade yet
        "avg_win": round(gw / len(wins), 2) if wins else None,
        "avg_loss": round(-gl / len(losses), 2) if losses else None,
        "avg_hold_min": round(sum(holds) / len(holds) / 60, 1) if holds else None,
        "realized": round(sum(t["pnl"] for t in sells), 2),
    }


def luck_check(sells, positions, pnl):
    """P&L with the single best closed trade removed, with the worst rug removed too, and with the best open
    position's unrealised gain removed. 'best_any' is whichever single trade, closed or open, made the most."""
    def tr(t, kind):
        return {"symbol": t["symbol"], "pnl": round(t["pnl"], 2), "kind": kind, "ts": t.get("ts")}
    best = max((t for t in sells if t["pnl"] > 0), key=lambda t: t["pnl"], default=None)
    worst = min((t for t in sells if t["pnl"] < 0), key=lambda t: t["pnl"], default=None)
    gains = [{"symbol": p["symbol"], "pnl": p["value"] - p["cost"], "ts": p.get("opened")} for p in positions
             if p["value"] - p["cost"] > 0]
    open_best = max(gains, key=lambda g: g["pnl"], default=None)
    b, w, o = (best or {}).get("pnl", 0.0), (worst or {}).get("pnl", 0.0), (open_best or {}).get("pnl", 0.0)
    any_best = max(b, o)
    return {
        "best_trade": tr(best, "closed") if best else None,
        "worst_trade": tr(worst, "closed") if worst else None,
        "best_open": tr(open_best, "open") if open_best else None,
        "pnl_ex_best": round(pnl - b, 2),
        "pnl_ex_best_and_worst": round(pnl - b - w, 2),
        "pnl_ex_best_open": round(pnl - o, 2),
        "pnl_ex_best_any": round(pnl - any_best, 2),
        "share_of_pnl_from_best_trade": round(any_best / pnl, 3) if pnl > 0 and any_best > 0 else None,
    }


def equity_at(series, ts):
    """Last equity reading at or before ts (None if the series starts later)."""
    eq = None
    for t, e in series:
        if t > ts:
            break
        eq = e
    return eq


def cost_adjusted(row, usage, series, now):
    """P&L per API-price dollar of usage, and (over the last day) per percent of the weekly plan limit."""
    if not usage:
        return {"cost_total": None, "pnl_per_usage_dollar": None, "pnl_per_weekly_pct": None, "note": "no usage recorded"}
    cost = usage.get("cost_total") or 0.0
    then = equity_at(series, now - 86400)
    pnl_24h = (series[-1][1] - then) if series and then is not None else row["pnl"]
    per_pct = usage.get("est_weekly_pct_per_day")
    return {
        "cost_total": round(cost, 4), "cost_24h": round(usage.get("cost_24h") or 0.0, 4),
        "calls": usage.get("calls", 0), "errors": usage.get("errors", 0),
        "pnl_per_usage_dollar": round(row["pnl"] / cost, 2) if cost > 0 else None,
        "pnl_24h": round(pnl_24h, 2),
        "weekly_pct_per_day": per_pct,
        "pnl_per_weekly_pct": round(pnl_24h / per_pct, 2) if per_pct else None,
        "note": None if per_pct else "plan burn rate not known yet",
    }


def worst_failure_stretch(calls, window):
    """Highest share of failed calls in any run of `window` consecutive calls (all of them if fewer, needs 5)."""
    if len(calls) < 5:
        return None
    w = min(window, len(calls))
    worst, at = -1.0, None
    for i in range(len(calls) - w + 1):
        chunk = calls[i:i + w]
        rate = sum(c["failed"] for c in chunk) / w
        if rate > worst:
            worst, at = rate, chunk[-1]["ts"]
    return {"rate": round(worst, 3), "window": w, "at": at}


def readiness(row, bench, calls):
    """The checklist a Claude has to clear before a small live test is worth considering."""
    checks, risk, luck, conf = [], row["risk"], row["luck"], row["confidence"]
    days = row["hours_of_history"] / 24

    def add(key, label, ok, reason):
        checks.append({"key": key, "label": label, "pass": bool(ok), "reason": reason})

    add("history", f"At least {READY['days']} days of history", days >= READY["days"],
        f"{days:.1f} days so far" + ("" if days >= READY["days"] else f", needs {READY['days']}"))
    add("trades", f"At least {READY['closed_trades']} closed trades", risk["closed"] >= READY["closed_trades"],
        f"{risk['closed']} closed" + ("" if risk["closed"] >= READY["closed_trades"] else f", needs {READY['closed_trades']}"))
    mine, parts, ok = luck["pnl_ex_best_any"], [], True
    for b, br in bench.items():
        if not br:
            parts.append(f"{b} isn't in the arena"); ok = False
            continue
        theirs = br["luck"]["pnl_ex_best_any"]
        ok = ok and mine > theirs
        parts.append(f"{'ahead of' if mine > theirs else 'behind'} {b} ({theirs:+.0f})")
    add("beats_benchmarks", f"Beats {' and '.join(BENCHMARKS)} after the luck check", ok,
        f"{mine:+.0f} with each one's best trade removed: " + ", ".join(parts))
    cparts, cok = [], True
    for b, c in conf.items():
        p = c.get("probability")
        if p is None or not c.get("enough"):
            cok = False; cparts.append(f"{b}: not enough data yet")
        else:
            cok = cok and p >= READY["confidence"]; cparts.append(f"{b}: {p * 100:.0f}%")
    add("confidence", f"At least {READY['confidence'] * 100:.0f}% likely better than both benchmarks", cok, ", ".join(cparts))
    dd = risk["max_drawdown_pct"]
    add("drawdown", f"Max drawdown under {READY['max_drawdown_pct']}%", dd < READY["max_drawdown_pct"], f"{dd:.1f}% so far")
    pf = risk["profit_factor"]
    if pf is None:
        pf_ok, pf_why = risk["wins"] > 0 and risk["closed"] >= 5, ("no losing trade yet" if risk["wins"] else "no closed trades yet")
    else:
        pf_ok, pf_why = pf > READY["profit_factor"], f"{pf:.2f} (gross wins {risk['gross_wins']:.0f} / gross losses {risk['gross_losses']:.0f})"
    add("profit_factor", f"Profit factor above {READY['profit_factor']}", pf_ok, pf_why)
    stretch = worst_failure_stretch(calls, READY["fail_window"])
    if stretch is None:
        add("reliability", f"No stretch with over {READY['max_fail_rate'] * 100:.0f}% of calls failing", len(calls) > 0,
            f"only {len(calls)} calls so far" if calls else "no calls yet")
    else:
        add("reliability", f"No stretch with over {READY['max_fail_rate'] * 100:.0f}% of calls failing",
            stretch["rate"] <= READY["max_fail_rate"],
            f"worst run: {stretch['rate'] * 100:.0f}% of {stretch['window']} calls failed" if stretch["rate"] > 0 else f"no failed calls in {len(calls)}")
    passed = sum(c["pass"] for c in checks)
    return {"checks": checks, "passed": passed, "total": len(checks), "ready": passed == len(checks),
            "verdict": "Ready for a small live test: yes" if passed == len(checks)
                       else f"Ready for a small live test: no ({passed} of {len(checks)} checks pass)"}


def _compute(arena, db, control, now):
    start = arena.start_cash
    by_agent = {}
    for t in _rows(db, "SELECT id, ts, agent, side, token, symbol, usd, pnl, reason FROM trades ORDER BY id"):
        by_agent.setdefault(t["agent"], []).append(t)
    calls = {}
    for r in _rows(db, "SELECT agent, ts, error IS NOT NULL AS failed FROM decisions ORDER BY ts"):
        calls.setdefault(r["agent"], []).append(r)
    llm = [a for a in arena.agents.values() if a.kind == "llm"]
    usage = {}
    if llm:
        try:
            usage = {r["name"]: r for r in control.summary(llm)["agents"]}
        except Exception as e:  # usage is a bonus; the rest of the page shouldn't die with it
            print(f"[analytics] usage summary failed: {e}")
    series = {name: db.equity_series(name) for name in arena.agents}
    returns = {name: bucket_returns(s) for name, s in series.items()}
    with arena.lock:
        views = {name: arena.view(name, now) for name in arena.agents}
    rng = random.Random(1234)  # a fixed seed so figures don't jitter from one poll to the next
    rows = {}
    for name, agent in arena.agents.items():
        v, s, tr = views[name], series[name], by_agent.get(name, [])
        equity = v.get("score_equity", v["equity"])  # lost lives count
        pnl = equity - start
        sells = [t for t in tr if t["side"] == "sell" and t["pnl"] is not None]
        hours = (s[-1][0] - s[0][0]) / 3600 if len(s) > 1 else 0.0
        rets = list(returns[name].values())
        mean = sum(rets) / len(rets) if rets else None
        std = statistics.pstdev(rets) if len(rets) > 1 else None
        rows[name] = {
            "name": name, "team": agent.team_name(), "kind": agent.kind, "avatar": agent.avatar,
            "model": getattr(getattr(agent, "backend", None), "model", None), "persona": getattr(agent, "persona", None),
            "equity": round(equity, 2), "pnl": round(pnl, 2), "pnl_pct": round(pnl / start * 100, 2) if start else None,
            "hours_of_history": round(hours, 2), "open_positions": len(v["positions"]),
            "luck": luck_check(sells, v["positions"], pnl),
            "risk": {"max_drawdown_pct": round(max_drawdown(s), 2), "buckets": len(rets),
                     "mean_15m_pct": round(mean * 100, 4) if mean is not None else None,
                     "volatility_15m_pct": round(std * 100, 4) if std is not None else None,
                     "sharpe_like": round(mean / std, 3) if std else None, **trade_stats(tr)},
        }
    # the report card the research asks for: fee drag, profit concentration, alpha against every yardstick
    from exchange import PRIORITY_FEE_USD, app_fee
    for name, r in rows.items():
        tr = by_agent.get(name, [])
        sells = [t for t in tr if t["side"] == "sell" and t["pnl"] is not None]
        fees = sum(app_fee(t["usd"] or 0) + PRIORITY_FEE_USD for t in tr)
        net = sum(t["pnl"] for t in sells)
        wins, losses = [t["pnl"] for t in sells if t["pnl"] > 0], [t["pnl"] for t in sells if t["pnl"] <= 0]
        r["extra"] = {
            "fees_usd": round(fees, 2), "fee_drag_pct": round(fees / start * 100, 2) if start else None,
            "top3_share": round(sum(sorted((t["pnl"] for t in sells), reverse=True)[:3]) / net, 2) if net > 0 else None,
            "alpha": {b: round(r["pnl_pct"] - rows[b]["pnl_pct"], 2) for b in BENCHMARKS
                      if b in rows and b != name and r["pnl_pct"] is not None and rows[b]["pnl_pct"] is not None},
            "closed": len(sells), "avg_win_usd": round(statistics.mean(wins), 2) if wins else None,
            "avg_loss_usd": round(statistics.mean(losses), 2) if losses else None,
        }
    bench = {b: rows.get(b) for b in BENCHMARKS}
    for name, agent in arena.agents.items():
        if agent.kind != "llm":
            continue
        r, conf = rows[name], {}
        for b in BENCHMARKS:
            if b not in rows:
                conf[b] = {"probability": None, "samples": 0, "enough": False, "note": f"{b} isn't in the arena"}
                continue
            p, n = bootstrap_beats(returns[name], returns[b], rng)
            enough = r["risk"]["closed"] >= MIN_CLOSED and n * BUCKET / 3600 >= MIN_HOURS and p is not None
            conf[b] = {"probability": None if p is None else round(p, 3), "samples": n, "enough": enough,
                       "note": None if enough else "not enough data yet"}
        r["confidence"] = conf
        r["cost"] = cost_adjusted(r, usage.get(name), series[name], now)
        r["readiness"] = readiness(r, bench, calls.get(name, []))
    return {
        "now": now, "computed_at": now, "cache_seconds": CACHE_TTL, "start_cash": start, "bucket_minutes": BUCKET // 60,
        "bootstraps": BOOTSTRAPS, "benchmarks": list(BENCHMARKS), "min_sample": {"closed_trades": MIN_CLOSED, "hours": MIN_HOURS},
        "thresholds": READY, "agents": sorted(rows.values(), key=lambda r: -r["equity"]),
        "note": "Sharpe-like is mean / standard deviation of 15-minute equity returns, not annualised. Confidence is a "
                "bootstrap over 15-minute return differences. Cost figures are Claude Code's API-price estimates.",
    }


def day_report(arena, db, frm, to, base):
    """One day's standings, per-agent P&L, trades, notable Claude decisions and usage, for the recap page.
    frm/to are epoch seconds (the recap page sends local midnight to midnight)."""
    start = arena.start_cash
    trades = _rows(db, "SELECT id, ts, agent, side, token, symbol, usd, pnl, reason FROM trades WHERE ts >= ? AND ts < ? ORDER BY id", (frm, to))
    agents = []
    for name, agent in arena.agents.items():
        before = _one(db, "SELECT equity FROM equity WHERE agent=? AND ts < ? ORDER BY ts DESC LIMIT 1", (name, frm))
        within = _one(db, "SELECT COUNT(*) n, MIN(ts) first FROM equity WHERE agent=? AND ts >= ? AND ts < ?", (name, frm, to))
        end = _one(db, "SELECT equity FROM equity WHERE agent=? AND ts < ? ORDER BY ts DESC LIMIT 1", (name, to))
        active = bool(within and within["n"])
        eq_start = before["equity"] if before else (start if active else None)
        eq_end = end["equity"] if end else None
        mine = [t for t in trades if t["agent"] == name]
        sells = [t for t in mine if t["side"] == "sell" and t["pnl"] is not None]
        pnl_day = (eq_end - eq_start) if eq_end is not None and eq_start is not None else None
        agents.append({
            "name": name, "team": agent.team_name(), "kind": agent.kind, "avatar": agent.avatar,
            "active": active, "equity_start": None if eq_start is None else round(eq_start, 2),
            "equity_end": None if eq_end is None else round(eq_end, 2),
            "pnl_day": None if pnl_day is None else round(pnl_day, 2),
            "pnl_day_pct": None if pnl_day is None or not eq_start else round(pnl_day / eq_start * 100, 2),
            "pnl_total": None if eq_end is None else round(eq_end - start, 2),
            "trades_day": len(mine), "closed_day": len(sells), "wins_day": sum(t["pnl"] > 0 for t in sells),
            "realized_day": round(sum(t["pnl"] for t in sells), 2),
        })
    agents.sort(key=lambda a: -(a["equity_end"] if a["equity_end"] is not None else -1e18))
    llm_names = {a["name"] for a in agents if a["kind"] == "llm"}
    notable = []
    for t in sorted((t for t in trades if t["agent"] in llm_names and t["side"] == "sell" and t["pnl"] is not None),
                    key=lambda t: -abs(t["pnl"]))[:8]:
        d = _one(db, "SELECT note, ts FROM decisions WHERE agent=? AND ts <= ? AND error IS NULL ORDER BY ts DESC LIMIT 1", (t["agent"], t["ts"]))
        notable.append({**t, "note": d["note"] if d else None, "note_ts": d["ts"] if d else None})
    usage = {r["agent"]: r for r in _rows(db, """SELECT agent, COUNT(*) calls, SUM(error IS NOT NULL) errors, TOTAL(cost) cost
                                                 FROM decisions WHERE ts >= ? AND ts < ? GROUP BY agent""", (frm, to))}
    readings = _rows(db, "SELECT ts, plan_7d, plan_7d_reset, plan_5h FROM decisions WHERE ts >= ? AND ts < ? AND plan_7d IS NOT NULL ORDER BY ts", (frm, to))
    plan_used = None
    if len(readings) > 1 and abs((readings[-1]["plan_7d_reset"] or 0) - (readings[0]["plan_7d_reset"] or 0)) < 120:
        plan_used = round(max(0.0, readings[-1]["plan_7d"] - readings[0]["plan_7d"]), 2)
    total_cost = sum(u["cost"] or 0 for u in usage.values())
    usage_rows = []
    for name in llm_names:
        u = usage.get(name, {"calls": 0, "errors": 0, "cost": 0.0})
        share = (u["cost"] or 0) / total_cost if total_cost else 0
        usage_rows.append({"name": name, "calls": u["calls"], "errors": u["errors"] or 0, "cost": round(u["cost"] or 0, 4),
                           "share": round(share, 4), "weekly_pct": round(share * plan_used, 2) if plan_used is not None else None})
    usage_rows.sort(key=lambda r: -r["cost"])
    return {
        "from": frm, "to": to, "trades": trades, "agents": agents, "notable": notable,
        "usage": {"agents": usage_rows, "cost": round(total_cost, 4), "calls": sum(u["calls"] for u in usage.values()),
                  "errors": sum(u["errors"] or 0 for u in usage.values()), "weekly_pct_used": plan_used,
                  "weekly_pct_at_end": readings[-1]["plan_7d"] if readings else None,
                  "readings": len(readings)},
    }


def compute(arena, db, control):
    """The JSON for /api/analytics: cached for CACHE_TTL seconds, plus an uncached 'day' section when the request
    carries ?from=&to= (epoch seconds)."""
    now = time.time()
    with _lock:
        if _cache["data"] is None or now - _cache["at"] > CACHE_TTL:
            _cache["data"], _cache["at"] = _compute(arena, db, control, now), now
        out = dict(_cache["data"])
    out["now"] = now
    frm = to = None
    try:
        from flask import request
        frm, to = request.args.get("from", type=float), request.args.get("to", type=float)
    except (ImportError, RuntimeError):  # outside a request (tests)
        pass
    if frm is not None and to is not None and to > frm:
        out["day"] = day_report(arena, db, frm, to, out)
    return out
