import os
import sys

# Must be set before any project module (market -> pumpfun) is imported,
# so no test opens the pump.fun websocket.
os.environ.setdefault("ARENA_PUMPFUN", "0")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
