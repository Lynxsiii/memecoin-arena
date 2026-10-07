"""The roster: Team Claude (claude_agents.py) against Team Bots (bots.py).

Every agent sees the same view and returns a list of orders:

  {"action": "buy",  "token": "<address>", "usd": 50, "reason": "..."}
  {"action": "sell", "token": "<address>", "fraction": 1.0, "reason": "..."}

The arena enforces the rules (max size, max positions, cash) and fills orders on the NEXT tick.
To add your own agent: subclass Agent (agent_base.py), implement decide(), and add it in build_agents().
"""
from agent_base import Agent  # noqa: F401  (re-exported for older imports)
from bots import (DipBuyerAgent, GraduatesAgent, GreenRandomAgent, HoldSolAgent, IndexAgent, MomentumAgent,  # noqa: F401
                  RandomAgent,
                  RulesAgent, SniperAgent)
from copy_agents import CopyBot, build_copy_bots  # noqa: F401
from claude_agents import (LLM_SYSTEM, PERSONAS, ApiBackend, ClaudeCodeBackend, LLMAgent,  # noqa: F401
                           build_llm_agents, model_label)


def build_bots():
    # Only the two yardsticks stay (run 6): Hold SOL is the market, Random the no-skill control. Every other bot class
    # (Rules, Green Random, Sniper, Dip Buyer, Momentum, Index) and the copy bots stay importable for replays.
    return [RandomAgent(), HoldSolAgent(), GraduatesAgent()]


def build_agents():
    return build_llm_agents() + build_bots()
