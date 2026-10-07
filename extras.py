"""Optional extra endpoints: /api/health and CSV exports. Loaded by main.create_app via extras.register(app, arena, db)."""
import csv
import io
import json
import os
import time

from flask import Response, jsonify


def _csv_response(header, rows, filename):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _db_size_mb(db):
    try:
        with db.lock:
            row = db.conn.execute("PRAGMA database_list").fetchone()
        path = row[2] if row else ""
        if path and os.path.exists(path):
            return round(os.path.getsize(path) / 1048576, 2)
        with db.lock:
            pc = db.conn.execute("PRAGMA page_count").fetchone()[0]
            ps = db.conn.execute("PRAGMA page_size").fetchone()[0]
        return round(pc * ps / 1048576, 2)
    except Exception:
        return None


def register(app, arena, db):
    def fail(e):
        return jsonify({"error": str(e)[:300]}), 500

    @app.route("/api/health")
    def health():
        try:
            now = time.time()
            with db.lock:
                row = db.conn.execute("SELECT MAX(ts) FROM equity").fetchone()
            last_ts = row[0] if row else None
            last_tick_age = round(now - last_ts, 1) if last_ts else None
            claude = []
            for name, agent in arena.agents.items():
                if getattr(agent, "kind", "") != "llm":
                    continue
                try:
                    st = agent.status() or {}
                except Exception as e:
                    st = {"error": str(e)[:300]}
                claude.append({"name": name, "model": st.get("model"), "thinking_since": st.get("thinking_since"),
                               "next_run": st.get("next_run"), "error": st.get("error")})
            try:
                tracked = len(arena.market.candidates())
            except Exception:
                tracked = None
            return jsonify({
                "now": now, "last_tick_age": last_tick_age, "tick": arena.tick, "ticks": arena.ticks,
                "started": arena.started, "tracked": tracked,
                "mock": "mock" in type(arena.market).__name__.lower(),
                "claude": claude, "db_size_mb": _db_size_mb(db),
            })
        except Exception as e:
            return fail(e)

    @app.route("/api/export/trades.csv")
    def export_trades():
        try:
            cols = ["id", "ts", "agent", "side", "token", "symbol", "usd", "qty", "spot", "fill", "pnl", "reason"]
            with db.lock:
                rows = db.conn.execute(f"SELECT {', '.join(cols)} FROM trades ORDER BY id").fetchall()
            return _csv_response(cols, ([r[c] for c in cols] for r in rows), "trades.csv")
        except Exception as e:
            return fail(e)

    @app.route("/api/export/decisions.csv")
    def export_decisions():
        try:
            cols = ["id", "ts", "agent", "secs", "note", "orders", "next_min", "error"]
            with db.lock:
                rows = db.conn.execute(f"SELECT {', '.join(cols)} FROM decisions ORDER BY id").fetchall()

            def flat(r):
                out = [r[c] for c in cols]
                o = r["orders"]
                try:  # normalise to a compact JSON string
                    out[cols.index("orders")] = json.dumps(json.loads(o or "[]"), separators=(",", ":"))
                except Exception:
                    out[cols.index("orders")] = o or "[]"
                return out
            return _csv_response(cols, (flat(r) for r in rows), "decisions.csv")
        except Exception as e:
            return fail(e)

    @app.route("/api/export/equity.csv")
    def export_equity():
        try:
            with db.lock:
                rows = db.conn.execute("SELECT ts, agent, equity FROM equity ORDER BY ts, agent").fetchall()
            return _csv_response(["ts", "agent", "equity"], ([r["ts"], r["agent"], r["equity"]] for r in rows),
                                 "equity.csv")
        except Exception as e:
            return fail(e)
