"""SQLite storage so the arena survives restarts."""
import json
import sqlite3
import threading

USAGE_COLUMNS = [("model", "TEXT"), ("in_tok", "INTEGER"), ("out_tok", "INTEGER"), ("cache_read", "INTEGER"),
                 ("cache_write", "INTEGER"), ("think_tok", "INTEGER"), ("cost", "REAL"), ("exits", "TEXT"),
                 ("plan_5h", "REAL"), ("plan_5h_reset", "REAL"), ("plan_7d", "REAL"), ("plan_7d_reset", "REAL"),
                 ("plan_status", "TEXT"), ("watch", "TEXT"), ("woke", "TEXT"), ("journal", "TEXT")]
JSON_COLUMNS = ("exits", "watch", "journal")  # decision columns stored JSON-encoded
JOURNAL_KEY = "__journal__:"                  # state-table key prefix for a Claude's trading journal


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            c = self.conn
            c.execute("""CREATE TABLE IF NOT EXISTS trades(
                id INTEGER PRIMARY KEY, ts REAL, agent TEXT, side TEXT, token TEXT, symbol TEXT,
                usd REAL, qty REAL, spot REAL, fill REAL, pnl REAL, reason TEXT)""")
            c.execute("CREATE TABLE IF NOT EXISTS equity(ts REAL, agent TEXT, equity REAL)")
            c.execute("CREATE INDEX IF NOT EXISTS eq_idx ON equity(agent, ts)")
            c.execute("CREATE TABLE IF NOT EXISTS state(agent TEXT PRIMARY KEY, data TEXT)")
            c.execute("""CREATE TABLE IF NOT EXISTS decisions(
                id INTEGER PRIMARY KEY, ts REAL, agent TEXT, secs REAL, note TEXT, orders TEXT, next_min REAL, error TEXT)""")
            have = {r[1] for r in c.execute("PRAGMA table_info(decisions)")}
            for col, typ in USAGE_COLUMNS:  # older databases get the usage columns added in place
                if col not in have:
                    c.execute(f"ALTER TABLE decisions ADD COLUMN {col} {typ}")
            c.execute("CREATE INDEX IF NOT EXISTS dec_idx ON decisions(ts)")
            c.commit()

    def reset_money(self):
        """Archive every trade and equity point under a new season number, then start empty tables. Trade ids keep
        counting up (the dashboard and phone alerts rely on that). Decisions, usage, journals and caches are untouched.
        Returns the archived season number."""
        with self.lock:
            c = self.conn
            cols = [r[1] for r in c.execute("PRAGMA table_info(trades)")]
            c.execute(f"CREATE TABLE IF NOT EXISTS trades_archive(season INTEGER, {', '.join(cols)})")
            c.execute("CREATE TABLE IF NOT EXISTS equity_archive(season INTEGER, ts REAL, agent TEXT, equity REAL)")
            season = 1 + max(c.execute("SELECT COALESCE(MAX(season), 0) FROM trades_archive").fetchone()[0],
                             c.execute("SELECT COALESCE(MAX(season), 0) FROM equity_archive").fetchone()[0])
            c.execute(f"INSERT INTO trades_archive SELECT ?, {', '.join(cols)} FROM trades", (season,))
            c.execute("INSERT INTO equity_archive SELECT ?, ts, agent, equity FROM equity", (season,))
            last_id = c.execute("SELECT COALESCE(MAX(id), 0) FROM trades").fetchone()[0]
            seq = c.execute("SELECT name FROM sqlite_master WHERE name='sqlite_sequence'").fetchone()
            if seq:
                last_id = max(last_id, c.execute("SELECT COALESCE(MAX(seq), 0) FROM sqlite_sequence WHERE name='trades'").fetchone()[0])
            c.execute("DROP TABLE trades")
            c.execute("""CREATE TABLE trades(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, agent TEXT, side TEXT, token TEXT, symbol TEXT,
                usd REAL, qty REAL, spot REAL, fill REAL, pnl REAL, reason TEXT)""")
            c.execute("DELETE FROM sqlite_sequence WHERE name='trades'")
            c.execute("INSERT INTO sqlite_sequence(name, seq) VALUES('trades', ?)", (last_id,))
            c.execute("DELETE FROM equity")
            c.commit()
        return season

    def add_council_message(self, ts, meeting, author, role, kind, text, orders):
        with self.lock:
            self.conn.execute("""CREATE TABLE IF NOT EXISTS council_board(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
                                 meeting INTEGER, author TEXT, role TEXT, kind TEXT, text TEXT, orders TEXT)""")
            self.conn.execute("INSERT INTO council_board(ts, meeting, author, role, kind, text, orders) VALUES(?,?,?,?,?,?,?)",
                              (ts, meeting, author, role, kind, text, json.dumps(orders)))
            self.conn.commit()

    def council_board(self, limit=100):
        """Council board messages, newest first."""
        with self.lock:
            if not self.conn.execute("SELECT name FROM sqlite_master WHERE name='council_board'").fetchone():
                return []
            rows = self.conn.execute("SELECT * FROM council_board ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r, orders=json.loads(r["orders"] or "[]")) for r in rows]

    def council_meetings(self):
        with self.lock:
            if not self.conn.execute("SELECT name FROM sqlite_master WHERE name='council_board'").fetchone():
                return 0
            return self.conn.execute("SELECT COALESCE(MAX(meeting), 0) FROM council_board").fetchone()[0]

    # ---------- strategy room (strategy_room.py): the Claudes' shared chat about getting better ----------
    def add_room_post(self, ts, author, text, status="ok", reason=None):
        with self.lock:
            self.conn.execute("""CREATE TABLE IF NOT EXISTS room_posts(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
                                 author TEXT, text TEXT, status TEXT, reason TEXT)""")
            cur = self.conn.execute("INSERT INTO room_posts(ts, author, text, status, reason) VALUES(?,?,?,?,?)",
                                    (ts, author, text, status, reason))
            self.conn.commit()
            return cur.lastrowid

    def room_posts(self, limit=200, include_blocked=True):
        """Strategy room posts, newest first."""
        with self.lock:
            if not self.conn.execute("SELECT name FROM sqlite_master WHERE name='room_posts'").fetchone():
                return []
            where = "" if include_blocked else "WHERE status='ok'"
            rows = self.conn.execute(f"SELECT * FROM room_posts {where} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def journals(self):
        """Every saved Claude journal: {agent: [lessons]}."""
        with self.lock:
            rows = self.conn.execute("SELECT agent, data FROM state WHERE agent LIKE '__journal__:%'").fetchall()
        return {r["agent"].split(":", 1)[1]: json.loads(r["data"]) or [] for r in rows}

    def add_trade(self, ts, agent, side, token, symbol, usd, qty, spot, fill, pnl, reason):
        with self.lock:
            self.conn.execute(
                "INSERT INTO trades(ts,agent,side,token,symbol,usd,qty,spot,fill,pnl,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ts, agent, side, token, symbol, usd, qty, spot, fill, pnl, reason))
            self.conn.commit()

    def add_equity(self, ts, agent, equity):
        with self.lock:
            self.conn.execute("INSERT INTO equity VALUES(?,?,?)", (ts, agent, equity))
            self.conn.commit()

    def save_state(self, agent, data):
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (agent, json.dumps(data)))
            self.conn.commit()

    def load_state(self, agent):
        with self.lock:
            row = self.conn.execute("SELECT data FROM state WHERE agent=?", (agent,)).fetchone()
        return json.loads(row["data"]) if row else None

    def add_decision(self, agent, d, orders):
        """d is a decision record from an LLM agent; orders are its orders after the arena checked them."""
        cols = ["ts", "secs", "note", "next_min", "error"] + [c for c, _ in USAGE_COLUMNS]
        with self.lock:
            self.conn.execute(
                f"INSERT INTO decisions(agent,orders,{','.join(cols)}) VALUES({','.join('?' * (len(cols) + 2))})",
                [agent, json.dumps(orders)] + [json.dumps(d.get(c)) if c in JSON_COLUMNS else d.get(c) for c in cols])
            self.conn.commit()

    def save_journal(self, agent, lessons):
        """A Claude's trading journal: a short list of lessons it keeps between looks and across restarts."""
        self.save_state(JOURNAL_KEY + agent, list(lessons))

    def load_journal(self, agent):
        j = self.load_state(JOURNAL_KEY + agent)
        return [str(x) for x in j] if isinstance(j, list) else []

    def usage_by_agent(self, since):
        with self.lock:
            rows = self.conn.execute(
                """SELECT agent, COUNT(*) calls, SUM(error IS NOT NULL) errors, TOTAL(in_tok) in_tok, TOTAL(out_tok) out_tok,
                          TOTAL(cache_read) cache_read, TOTAL(cache_write) cache_write, TOTAL(think_tok) think_tok,
                          TOTAL(cost) cost, TOTAL(secs) secs
                   FROM decisions WHERE ts >= ? GROUP BY agent""", (since,)).fetchall()
        return {r["agent"]: {k: (int(r[k]) if k not in ("cost", "secs") else r[k]) for k in r.keys() if k != "agent"}
                for r in rows}

    def spent_since(self, since):
        with self.lock:
            return self.conn.execute("SELECT TOTAL(cost) FROM decisions WHERE ts >= ?", (since,)).fetchone()[0]

    def plan_readings(self, since):
        """Plan-limit readings Claude Code reported with each Claude call, oldest first."""
        with self.lock:
            rows = self.conn.execute(
                """SELECT ts, plan_5h, plan_5h_reset, plan_7d, plan_7d_reset, plan_status FROM decisions
                   WHERE ts >= ? AND (plan_5h IS NOT NULL OR plan_7d IS NOT NULL) ORDER BY ts""", (since,)).fetchall()
        return [dict(r) for r in rows]

    def latest_plan_reading(self):
        with self.lock:
            row = self.conn.execute(
                """SELECT ts, plan_5h, plan_5h_reset, plan_7d, plan_7d_reset, plan_status FROM decisions
                   WHERE plan_5h IS NOT NULL OR plan_7d IS NOT NULL ORDER BY ts DESC LIMIT 1""").fetchone()
        return dict(row) if row else None

    def first_decision_ts(self):
        with self.lock:
            return self.conn.execute("SELECT MIN(ts) FROM decisions").fetchone()[0]

    def decisions(self, limit=60):
        with self.lock:
            rows = self.conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r, orders=json.loads(r["orders"] or "[]"), exits=json.loads(r["exits"] or "null") or [],
                     watch=json.loads(r["watch"] or "null"), journal=json.loads(r["journal"] or "null")) for r in rows]

    def measured_round_trip(self, since, min_buys=20, agents=None):
        """What trading really cost lately: (entry costs + exit costs) / dollars bought, in %, over the fills since
        `since` (fees, price impact, sandwich slippage, network fees) of `agents` (all when None). None with too few."""
        with self.lock:
            q, args = "SELECT side, usd, qty, spot FROM trades WHERE ts>=? AND spot>0", [since]
            if agents is not None:
                q += f" AND agent IN ({','.join('?' * len(agents))})"
                args += list(agents)
            rows = self.conn.execute(q, args).fetchall()
        # A rugged pool returns ~nothing against a nonsense "price": that's a rug loss, not a trading cost, and one
        # such fill once pushed this figure to 7,700%. Fills that lost more than half their value are left out.
        rows = [r for r in rows if r["usd"] > 0 and abs(r["usd"] - r["qty"] * r["spot"]) <= 0.5 * max(r["usd"], r["qty"] * r["spot"])]
        buys = [r for r in rows if r["side"] == "buy"]
        if len(buys) < min_buys:
            return None
        cost = sum(r["usd"] - r["qty"] * r["spot"] for r in buys)
        cost += sum(max(0.0, r["qty"] * r["spot"] - r["usd"]) for r in rows if r["side"] == "sell")
        bought = sum(r["usd"] for r in buys)
        return round(cost / bought * 100, 1) if bought else None

    FORCED_EXITS = ("stop loss", "trailing stop", "bust", "creator sold", "liquidity", "time stop", "leader sold")

    def typical_round_trip(self, since, agents=None, min_buys=10, min_sells=5):
        """What a normal trade costs (median buy cost % + median sell cost % vs the price on screen), from the fills
        of `agents` since `since`. Forced exits (stops, busts, crash exits) are left out: in a crash the fill gaps far
        below the screen price, which is a loss on the trade, not the cost of trading. None with too few fills."""
        import statistics
        with self.lock:
            q, args = "SELECT side, usd, qty, spot, reason FROM trades WHERE ts>=? AND spot>0", [since]
            if agents is not None:
                q += f" AND agent IN ({','.join('?' * len(agents))})"
                args += list(agents)
            rows = self.conn.execute(q, args).fetchall()
        rows = [r for r in rows if r["usd"] > 0 and abs(r["usd"] - r["qty"] * r["spot"]) <= 0.5 * max(r["usd"], r["qty"] * r["spot"])]
        buys = [(r["usd"] - r["qty"] * r["spot"]) / r["usd"] * 100 for r in rows if r["side"] == "buy"]
        sells = [(r["qty"] * r["spot"] - r["usd"]) / (r["qty"] * r["spot"]) * 100 for r in rows if r["side"] == "sell"
                 and not (r["reason"] or "").lower().startswith(self.FORCED_EXITS)]
        if len(buys) < min_buys or len(sells) < min_sells:
            return None
        return round(statistics.median(buys) + statistics.median(sells), 1)

    def token_history(self, agent, since):
        """Per token: how many times this agent traded it since `since`, its net P&L there, and how the last exit went."""
        with self.lock:
            rows = self.conn.execute("SELECT token, side, pnl, reason FROM trades WHERE agent=? AND ts>=? ORDER BY id",
                                     (agent, since)).fetchall()
        out = {}
        for r in rows:
            h = out.setdefault(r["token"], {"buys": 0, "sells": 0, "pnl_usd": 0.0, "last_exit": None})
            if r["side"] == "buy":
                h["buys"] += 1
            else:
                h["sells"] += 1
                h["pnl_usd"] = round(h["pnl_usd"] + (r["pnl"] or 0), 2)
                h["last_exit"] = (r["reason"] or "")[:80]
        return out

    def recent_sells(self, agent, n=8):
        """An agent's last closed trades, newest first, with the P&L of each."""
        with self.lock:
            rows = self.conn.execute("SELECT ts, symbol, usd, pnl, reason FROM trades WHERE agent=? AND side='sell' "
                                     "ORDER BY id DESC LIMIT ?", (agent, n)).fetchall()
        return [{"symbol": r["symbol"], "pnl_usd": round(r["pnl"] or 0, 2),
                 "pnl_pct": round((r["pnl"] or 0) / (r["usd"] - (r["pnl"] or 0)) * 100, 1) if r["usd"] - (r["pnl"] or 0) else None,
                 "ts": r["ts"], "reason": (r["reason"] or "")[:100]} for r in rows]

    def last_note(self, agent):
        with self.lock:
            row = self.conn.execute("SELECT note FROM decisions WHERE agent=? AND error IS NULL ORDER BY id DESC LIMIT 1",
                                    (agent,)).fetchone()
        return row["note"] if row else None

    def trades(self, limit=200):
        with self.lock:
            rows = self.conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def sell_stats(self, agent):
        with self.lock:
            row = self.conn.execute(
                "SELECT COUNT(*) n, SUM(pnl > 0) wins FROM trades WHERE agent=? AND side='sell'", (agent,)).fetchone()
            total = self.conn.execute("SELECT COUNT(*) FROM trades WHERE agent=?", (agent,)).fetchone()[0]
        return {"trades": total, "closed": row["n"] or 0, "wins": row["wins"] or 0}

    def equity_series(self, agent):
        with self.lock:
            rows = self.conn.execute("SELECT ts, equity FROM equity WHERE agent=? ORDER BY ts", (agent,)).fetchall()
        return [(r["ts"], r["equity"]) for r in rows]
