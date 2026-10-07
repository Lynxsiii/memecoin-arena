"""Base class shared by the bots (bots.py) and the Claude agents (claude_agents.py)."""
from collections import deque


class Agent:
    name = "base"
    description = ""
    kind = "bot"           # "bot" or "llm", for the dashboard
    team = None            # "claude", "bots" or "copy"; None = by kind
    avatar = ""            # which mascot the dashboard draws
    interval = 0           # seconds between decisions (0 = every tick)
    max_trade_frac = 0.10  # max % of equity in a single buy
    max_positions = 8
    bio = ""               # display personality: one or two sentences shown on the dashboard
    catchphrase = ""       # a short line the stage and announcer can use

    def __init__(self):
        self.last_run = 0
        self.note = ""
        self.db = None      # the arena's database, once attach() has been called
        self.log = deque()  # decision records for the arena to save

    def attach(self, db):
        """Hands the agent the arena's database so it can load and save its own memory (a Claude's journal)."""
        self.db = db

    def due(self, now):
        return now - self.last_run >= self.interval

    def decide(self, view):
        return []

    def status(self):
        return {}

    def team_name(self):
        return self.team or ("claude" if self.kind == "llm" else "bots")

    def profile(self):
        """Display-only personality, shown on the dashboard. Never part of a Claude's trading instructions."""
        return {"bio": self.bio, "catchphrase": self.catchphrase}

    def wake(self, reason):
        """Called by the arena when one of the agent's alarms trips. Bots check every tick, so they ignore it."""
