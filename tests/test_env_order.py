import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_dotenv_loaded_before_project_modules(tmp_path):
    """main.py must load .env before importing market/exchange (they read os.environ once, at import)."""
    shutil.copy(os.path.join(ROOT, "main.py"), tmp_path / "main.py")
    (tmp_path / ".env").write_text("ARENA_UNIVERSE=pumpfun\nARENA_ROUTE=pumpfun\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ("ARENA_UNIVERSE", "ARENA_ROUTE")}
    env.update(PYTHONPATH=ROOT, ARENA_PUMPFUN="0")
    out = subprocess.run([sys.executable, "-c", "import main, market, exchange; print(market.UNIVERSE, exchange.ROUTE)"],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "pumpfun pumpfun"
