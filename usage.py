"""Claude usage tracking and controls.

Cost figures are Claude Code's own API-price estimate for each call. On a Claude plan you aren't charged
that amount; it's the best available measure of how much of your plan each agent uses relative to the others.

Controls (saved in the database, so they survive restarts):
  mode   normal | slow | paused, for all Claude agents
  agents per-agent override of the same modes
  cap    daily spend (API-price dollars, all Claude agents together) after which everyone runs in slow mode
"""
import time
from datetime import datetime

MODES = ("normal", "slow", "paused")
STATE_KEY = "__llm_control__"


class UsageControl:
    slow_minutes = 30

    def __init__(self, db):
        self.db = db
        saved = db.load_state(STATE_KEY) or {}
        self.mode = saved.get("mode", "normal")
        self.cap = saved.get("cap")            # None = no cap
        self.agents = saved.get("agents", {})  # name -> mode override
        self._spent = (0.0, 0.0)               # (checked_at, spent_today), refreshed every 15s

    def _save(self):
        self.db.save_state(STATE_KEY, {"mode": self.mode, "cap": self.cap, "agents": self.agents})

    @staticmethod
    def _midnight():
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def spent_today(self):
        checked, spent = self._spent
        if time.time() - checked > 15:
            spent = self.db.spent_since(self._midnight())
            self._spent = (time.time(), spent)
        return spent

    def capped(self):
        return self.cap is not None and self.spent_today() >= self.cap

    def mode_for(self, name):
        override = self.agents.get(name, "normal")
        if "paused" in (self.mode, override):
            return "paused"
        if "slow" in (self.mode, override) or self.capped():
            return "slow"
        return "normal"

    def update(self, mode=None, agent=None, cap="keep"):
        """Change the global mode, one agent's mode, and/or the cap (None removes it). Raises ValueError."""
        if mode is not None and mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        if mode is not None:
            if agent:
                if mode == "normal":
                    self.agents.pop(agent, None)
                else:
                    self.agents[agent] = mode
            else:
                self.mode = mode
        if cap != "keep":
            if cap is not None:
                cap = float(cap)
                if cap < 0:
                    raise ValueError("cap can't be negative")
            self.cap = cap
        self._spent = (0.0, 0.0)
        self._save()

    def plan(self):
        """Your Claude plan's 5-hour and weekly limits, as Claude Code reported them on the arena's latest call,
        with a burn rate over the last few hours and when each would hit 100% at that pace. The burn rate
        includes everything on your account (your own chats too), not only the arena."""
        latest = self.db.latest_plan_reading()
        if not latest:
            return {"as_of": None, "status": None, "windows": []}
        now = time.time()
        readings = self.db.plan_readings(now - 3 * 3600)
        windows = []
        for kind, label, col in (("five_hour", "5-hour limit", "plan_5h"), ("seven_day", "Weekly limit", "plan_7d")):
            pct, reset = latest.get(col), latest.get(col + "_reset")
            if pct is None:
                continue
            same = [r for r in readings if r[col] is not None and abs((r[col + "_reset"] or 0) - (reset or 0)) < 120]
            rate = full_at = None
            if same and latest["ts"] - same[0]["ts"] >= 1800:  # need half an hour of readings in this window
                rate = round((pct - same[0][col]) / ((latest["ts"] - same[0]["ts"]) / 3600), 2)
                if rate > 0:
                    eta = latest["ts"] + (100 - pct) / rate * 3600
                    full_at = eta if not reset or eta < reset else None
            windows.append({"kind": kind, "label": label, "pct": pct, "resets_at": reset,
                            "burn_per_hour": rate, "full_at": full_at})
        return {"as_of": latest["ts"], "status": latest.get("plan_status"), "windows": windows}

    def summary(self, llm_agents):
        """Everything the usage window and the dashboard need, in one JSON-friendly dict."""
        now = time.time()
        total = self.db.usage_by_agent(0)
        day = self.db.usage_by_agent(now - 86400)
        hour = self.db.usage_by_agent(now - 3600)
        first = self.db.first_decision_ts()
        blank = {"calls": 0, "in_tok": 0, "out_tok": 0, "cache_read": 0, "cache_write": 0, "think_tok": 0,
                 "cost": 0.0, "secs": 0.0, "errors": 0}
        rows = []
        for a in llm_agents:
            t, d, h = total.get(a.name, blank), day.get(a.name, blank), hour.get(a.name, blank)
            st = a.status()
            rows.append({
                "name": a.name, "model": a.backend.model, "persona": a.persona, "avatar": a.avatar,
                "mode": st["mode"], "override": self.agents.get(a.name, "normal"),
                "thinking_since": st["thinking_since"], "next_run": st["next_run"], "error": st["error"],
                "calls": t["calls"], "errors": t["errors"], "calls_1h": h["calls"],
                "tokens_in": t["in_tok"] + t["cache_read"] + t["cache_write"], "tokens_out": t["out_tok"],
                "cache_read": t["cache_read"], "think_tok": t["think_tok"],
                "cost_total": round(t["cost"], 4), "cost_24h": round(d["cost"], 4), "cost_1h": round(h["cost"], 4),
                "avg_cost": round(t["cost"] / t["calls"], 4) if t["calls"] else None,
                "avg_secs": round(t["secs"] / t["calls"], 1) if t["calls"] else None,
                "avg_tokens": round((t["in_tok"] + t["cache_read"] + t["cache_write"] + t["out_tok"]) / t["calls"])
                              if t["calls"] else None,
            })
        spent_total = sum(r["cost_total"] for r in rows)
        spent_24h = sum(r["cost_24h"] for r in rows)
        plan = self.plan()
        weekly = next((w for w in plan["windows"] if w["kind"] == "seven_day"), None)
        for r in rows:  # each agent's rough slice of the weekly limit, by its share of the arena's spend
            share = r["cost_24h"] / spent_24h if spent_24h else 0
            r["share_24h"] = round(share, 4)
            r["est_weekly_pct_per_day"] = (round(share * weekly["burn_per_hour"] * 24, 2)
                                           if weekly and weekly["burn_per_hour"] is not None else None)
        # Project a week from the last 24h (or since the first call, if that's shorter but at least 15 minutes)
        window = min(86400, now - first) if first else 0
        projected = round(spent_24h / window * 7 * 86400, 2) if window >= 900 else None
        return {"now": now, "mode": self.mode, "cap": self.cap, "capped": self.capped(),
                "slow_minutes": self.slow_minutes, "spent_today": round(self.spent_today(), 4),
                "spent_24h": round(spent_24h, 4), "spent_total": round(spent_total, 4),
                "projected_week": projected, "plan": plan, "agents": rows,
                "note": "Costs are Claude Code's API-price estimates, a relative measure of plan usage."}
