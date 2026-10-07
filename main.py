"""Memecoin Agent Arena - paper trading only. Run:  python main.py   then open http://localhost:8000"""
import argparse
import os
import threading
import time

from flask import Flask, jsonify, request, send_file, send_from_directory

from agents import build_agents
from arena import Arena
from db import DB
from market import LiveMarket, MockMarket
from usage import UsageControl

HERE = os.path.dirname(os.path.abspath(__file__))


def load_dotenv():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def max_drawdown(series):
    peak, mdd = 0.0, 0.0
    for _, eq in series:
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, (peak - eq) / peak)
    return mdd * 100


def downsample(series, n=400):
    if len(series) <= n:
        return series
    step = len(series) / n
    out = [series[int(i * step)] for i in range(n)]
    out.append(series[-1])
    return out


def create_app(arena, db, mock):
    app = Flask(__name__)
    control = UsageControl(db)
    llm_agents = [a for a in arena.agents.values() if a.kind == "llm"]
    for a in llm_agents:
        a.control = control

    @app.route("/")
    def index():
        return send_file(os.path.join(HERE, "dashboard.html"))

    cache = {"at": 0, "series": {}, "dd": {}}

    def equity_history():
        """Equity series and drawdowns are the expensive part, so rebuild them at most every 20s."""
        if time.time() - cache["at"] > 20:
            series = {name: db.equity_series(name) for name in arena.agents}
            cache["series"] = {n: [[round(ts * 1000), round(eq, 2)] for ts, eq in downsample(s)] for n, s in series.items()}
            cache["dd"] = {n: round(max_drawdown(s), 1) for n, s in series.items()}
            cache["at"] = time.time()
        return cache

    @app.route("/api/summary")
    def summary():
        now = time.time()
        hist = equity_history()
        rows = []
        with arena.lock:
            for order, (name, agent) in enumerate(arena.agents.items()):
                v = arena.view(name, now)
                stats = db.sell_stats(name)
                rows.append({
                    "name": name, "order": order, "kind": agent.kind, "team": agent.team_name(), "avatar": agent.avatar,
                    "description": agent.description, "note": agent.note, **agent.status(), **agent.profile(),
                    # equity is the SCORE equity (every extra stake after a bust subtracted); trading_equity is what it holds
                    "equity": round(v["score_equity"], 2), "trading_equity": round(v["equity"], 2), "cash": round(v["cash"], 2),
                    "pnl_pct": round(v["pnl_pct"], 2), "points": round(v["points"], 2),
                    "life": (v["lives"] or {}).get("life"), "hearts_earned": (v["lives"] or {}).get("hearts_earned"),
                    "runner_bonus": (v["lives"] or {}).get("runner_bonus"),
                    "lives": (v["lives"] or {}).get("lives"), "lives_left": (v["lives"] or {}).get("lives_left"),
                    "out": bool((v["lives"] or {}).get("out")), "busts": (v["lives"] or {}).get("busts", []),
                    "trades": stats["trades"], "closed": stats["closed"],
                    "win_rate": round(stats["wins"] / stats["closed"] * 100, 1) if stats["closed"] else None,
                    "max_dd": hist["dd"].get(name, 0.0),
                    "positions": [{k: p[k] for k in ("token", "symbol", "cost", "value", "pnl_pct", "held_min", "rating",
                                                     "price_chg_pct", "exits", "moonshot")}
                                  for p in v["positions"]],
                })
        rows.sort(key=lambda r: r["equity"], reverse=True)
        # Near-ties shouldn't flip the leader every tick (it drives banners, sounds and the announcer)
        prev = next((r for r in rows if r["name"] == cache.get("leader")), None)
        if prev and rows[0] is not prev and rows[0]["equity"] - prev["equity"] < max(1.0, arena.start_cash * 0.001):
            rows.remove(prev)
            rows.insert(0, prev)
        cache["leader"] = rows[0]["name"] if rows else None
        return jsonify({
            "now": now, "mock": mock, "start_cash": arena.start_cash, "started": arena.started, "ticks": arena.ticks,
            "tracked": len(arena.market.candidates()), "agents": rows,
            "trades": db.trades(150), "decisions": db.decisions(60),
        })

    @app.route("/api/series")
    def series():
        return jsonify(equity_history()["series"])

    @app.route("/api/market")
    def market():
        with arena.lock:
            holders = {}
            for name, acct in arena.accounts.items():
                for addr in acct["positions"]:
                    holders.setdefault(addr, []).append(name)
            toks = [{k: t.get(k) for k in ("address", "symbol", "name", "price", "liquidity", "mcap", "vol_h1", "buys_h1",
                                           "sells_h1", "chg_m5", "chg_h1", "chg_h24", "age_min", "rating", "flags", "url")}
                    | {"held_by": holders.get(t["address"], [])} for t in arena.market.candidates()]
        return jsonify(sorted(toks, key=lambda t: t.get("vol_h1") or 0, reverse=True))

    @app.route("/api/usage")
    def usage():
        return jsonify(control.summary(llm_agents))

    @app.route("/api/llm/control", methods=["POST"])
    def llm_control():
        """JSON body: {"mode": "normal"|"slow"|"paused", "agent": optional name, "cap": dollars or null}.
        Requires a JSON content type, so other websites can't trigger it from your browser."""
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "send a JSON object"}), 400
        agent = body.get("agent")
        if agent and agent not in {a.name for a in llm_agents}:
            return jsonify({"error": f"no Claude agent called {agent!r}"}), 404
        try:
            control.update(mode=body.get("mode"), agent=agent, cap=body["cap"] if "cap" in body else "keep")
        except (TypeError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        return jsonify(control.summary(llm_agents))

    @app.route("/api/traders")
    def traders_api():
        tracker = arena.tracker
        if tracker is None:
            return jsonify({"error": "the top-trader tracker isn't running (mock market, ARENA_TRADERS=0 or traders.py missing)"}), 404
        top = tracker.top()
        following = {a.name: a.following(top) for a in arena.agents.values() if hasattr(a, "following")}
        return jsonify({"updated": time.time(), "status": tracker.status(), "top": top,
                        "signals": list(reversed(tracker.signals(time.time() - 86400)))[:150], "following": following})

    @app.route("/api/screens")
    def screens_api():
        """What each Claude is looking at: its focus tokens with the arena's price history and its trades in them."""
        with arena.lock:
            return jsonify(arena.screens(time.time()))

    @app.route("/api/room")
    def room_api():
        """The strategy room, newest first, blocked posts included (the Claudes only see that those were removed)."""
        import strategy_room
        if not strategy_room.ENABLED:
            return jsonify({"error": "the strategy room is off (ARENA_ROOM=0)"}), 404
        return jsonify({"posts": db.room_posts(200), "rules": "Strategies, lessons, risk rules and how to read the data. "
                        "Naming, hinting at or linking a coin is blocked."})

    @app.route("/api/council")
    def council_api():
        council = next((a for a in arena.agents.values() if hasattr(a, "members")), None)
        if council is None:
            return jsonify({"error": "no council in this arena (ARENA_COUNCIL=off?)"}), 404
        return jsonify({"name": council.name, "members": council.members(), "messages": db.council_board(100)})

    @app.route("/api/reset-money", methods=["POST"])
    def reset_money_api():
        """JSON body {"journals": "keep" | "wipe"} (required, no default). JSON-only, so other sites can't trigger it."""
        body = request.get_json(silent=True)
        choice = body.get("journals") if isinstance(body, dict) else None
        if choice not in ("keep", "wipe"):
            return jsonify({"error": 'send {"journals": "keep"} or {"journals": "wipe"}'}), 400
        result = arena.reset_money(choice == "keep")
        cache.update(at=0, leader=None)  # charts and drawdowns start over
        return jsonify(result)

    @app.route("/static/<path:p>")
    def static_files(p):
        return send_from_directory(os.path.join(HERE, "static"), p)

    @app.route("/recap")
    def recap_page():
        return send_file(os.path.join(HERE, "recap.html"))

    @app.route("/api/token/<addr>/history")
    def token_history(addr):
        """The arena's own 30-second price history for one token, plus every trade any agent made in it."""
        with arena.lock:
            points = [[round(ts * 1000), p] for ts, p in arena.history.get(addr, [])]
            t = arena.market.get(addr) or {}
        trades = [tr for tr in db.trades(2000) if tr["token"] == addr]
        return jsonify({"address": addr, "symbol": t.get("symbol"), "points": points, "trades": trades})

    @app.route("/api/analytics")
    def analytics_api():
        try:
            import analytics
        except ImportError:
            return jsonify({"error": "analytics.py not installed"}), 404
        return jsonify(analytics.compute(arena, db, control))

    try:  # optional extra endpoints live in extras.py
        import extras
        extras.register(app, arena, db)
    except ImportError:
        pass
    except Exception as e:
        print(f"[main] extras.py failed to load: {e}")

    try:  # optional phone alerts live in notifier.py (configured in .env)
        import notifier
        notifier.start(arena, db, control)
    except ImportError:
        pass
    except Exception as e:
        print(f"[main] notifier.py failed to start: {e}")

    return app


def ask_keep_journals():
    while True:
        a = input("Keep the Claudes' journals (the lessons they wrote)? They're backed up either way. [k]eep / [w]ipe: ")
        if a.strip().lower() in ("k", "keep", "y", "yes"):
            return True
        if a.strip().lower() in ("w", "wipe", "n", "no"):
            return False


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Memecoin Agent Arena (paper trading)")
    ap.add_argument("--mock", action="store_true", help="use a fake offline market instead of live data")
    ap.add_argument("--tick", type=int, default=30, help="seconds between ticks (default 30)")
    ap.add_argument("--cash", type=float, default=1000.0, help="starting fake cash per agent")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reset", action="store_true", help="wipe saved results and start fresh (journals are backed up first)")
    ap.add_argument("--reset-money", action="store_true",
                    help="everyone back to the starting cash; trades are archived, usage and recordings kept")
    ap.add_argument("--keep-journals", action="store_true", help="with --reset-money: keep the Claudes' journals")
    ap.add_argument("--wipe-journals", action="store_true", help="with --reset-money: clear the Claudes' journals")
    args = ap.parse_args()

    db_path = os.path.join(HERE, "arena_mock.db" if args.mock else "arena.db")
    if args.reset and os.path.exists(db_path):
        from arena import backup_journals
        old = DB(db_path)
        saved = backup_journals(old, "before full reset")
        old.conn.close()
        if saved:
            print(f"[main] journals backed up to {saved}")
        os.remove(db_path)
        print(f"[main] reset: deleted {os.path.basename(db_path)}")

    market = MockMarket(tick=args.tick) if args.mock else LiveMarket()
    try:  # recorder.py saves every market snapshot so replay.py can re-run a past day
        import recorder
        market = recorder.wrap(market, os.path.join(HERE, "recordings"), mock=args.mock)
    except ImportError:
        pass
    db = DB(db_path)
    arena = Arena(market, db, build_agents(), start_cash=args.cash, tick=args.tick)
    if arena.memory and not args.mock:  # warm up market memory from the last day of recordings
        try:
            import glob
            import replay
            files = sorted(glob.glob(os.path.join(HERE, "recordings", "[0-9]*.jsonl.gz")), key=replay._segment_key)[-12:]
            hour_ago = time.time() - 3900

            def snaps():  # market memory gets the last day; the screens' price charts get the last hour
                for snap in replay.iter_snapshots(files, time.time() - 86400, None):
                    if snap.ts >= hour_ago:
                        arena.warm_history(snap)
                    yield snap
            arena.memory.load(snaps())
            print(f"[main] market memory and price charts warmed up from {len(files)} recording file(s)")
        except Exception as e:
            print(f"[main] couldn't warm up market memory: {e}")
    if args.reset_money:
        keep = True if args.keep_journals else False if args.wipe_journals else ask_keep_journals()
        arena.reset_money(keep)
    if not args.mock and os.environ.get("ARENA_TRADERS", "1") != "0":
        try:  # the top-100 leaderboard and copy signals for Team Copy (traders.py)
            import traders
            arena.tracker = traders.Tracker(db, market, helius_key=os.environ.get("ARENA_HELIUS_KEY") or None)
            arena.tracker.start()
        except ImportError:
            pass
        except Exception as e:
            print(f"[main] the top-trader tracker didn't start: {e}")
    threading.Thread(target=arena.run_forever, daemon=True).start()

    print(f"\n  Dashboard: http://localhost:{args.port}\n  ({'MOCK market' if args.mock else 'LIVE prices, fake money'})\n")
    create_app(arena, db, args.mock).run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
