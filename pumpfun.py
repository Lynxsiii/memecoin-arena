"""pump.fun launches and graduations from PumpPortal's free data websocket (wss://pumpportal.fun/api/data).

Only the two FREE, keyless subscriptions are used: {"method": "subscribeNewToken"} (every bonding-curve launch,
roughly 40 a minute) and {"method": "subscribeMigration"} (every token that graduates to a PumpSwap pool, a few
an hour). subscribeTokenTrade / subscribeAccountTrade are metered and need an API key: this module never sends
them. PumpPortal temporarily bans clients that open many connections, so the whole process shares ONE
connection: use shared() (LiveMarket does) rather than creating PumpFeed objects of your own.

Message formats, checked live on 2026-10-06:
  launch     {"signature", "mint", "traderPublicKey", "txType": "create", "initialBuy": <tokens the creator bought>,
              "solAmount": <SOL the creator spent>, "bondingCurveKey", "vTokensInBondingCurve", "vSolInBondingCurve",
              "marketCapSol", "name", "symbol", "uri", "is_mayhem_mode", "pool": "pump"}
  graduation {"signature", "mint", "txType": "migrate", "pool": "pump-amm"}
  ack        {"message": "Successfully subscribed to token creation events."} (ignored)
A launch with no creator buy has marketCapSol = 27.96 (the curve's 30 virtual SOL over 1.073 billion virtual
tokens); every SOL the creator spends lifts it, so marketCapSol / solAmount is the only "traction" a launch has
at second zero.

API (all methods are thread-safe and never raise):
  feed = PumpFeed(); feed.start()        background daemon thread, reconnects with backoff (5 s doubling to 5 min)
  feed.new_tokens(since=0)               launches received after unix time `since`, oldest first:
                                         {"mint", "name", "symbol", "creator", "initial_buy_sol", "initial_buy_tokens",
                                          "mcap_sol", "v_sol", "v_tokens", "curve", "uri", "mayhem", "pool",
                                          "signature", "ts"}
  feed.graduations(since=0)              migrations after `since`, oldest first: {"mint", "pool", "signature", "ts"}
  feed.status()                          connection and counter snapshot (connected, launches, graduations, errors,
                                         reconnects, last_message age, buffered)
  feed.stop()
  shared()                               the process-wide feed, started on first use (None when websocket-client
                                         is missing or the feed is disabled).
Buffers are bounded deques (ARENA_PUMPFUN_BUFFER launches, 500 graduations); names and symbols are capped and
stripped of control characters because they are untrusted text from the chain.

Settings (environment variables, read once at import):
  ARENA_PUMPFUN=1                0/off disables the feed (shared() returns None; LiveMarket then tracks no
                                 pump.fun tokens and gives their slots back to promoted / organic discovery).
  ARENA_PUMPFUN_WS               websocket URL, default wss://pumpportal.fun/api/data.
  ARENA_PUMPFUN_BUFFER=3000      launches kept in memory (about 75 minutes at 40 a minute).
"""
import json
import os
import re
import threading
import time
from collections import deque

try:
    import websocket  # websocket-client
except ImportError:  # pragma: no cover - the arena runs without the feed
    websocket = None

ENABLED = os.environ.get("ARENA_PUMPFUN", "1").strip().lower() not in ("0", "off", "false", "no")
WS_URL = os.environ.get("ARENA_PUMPFUN_WS", "wss://pumpportal.fun/api/data").strip() or "wss://pumpportal.fun/api/data"
BUFFER = max(100, int(float(os.environ.get("ARENA_PUMPFUN_BUFFER", "3000") or 3000)))
INITIAL_MCAP_SOL = 27.96   # a launch nobody has bought yet
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏ -‮⁦-⁩]")


def _f(x, default=None):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if v == v and abs(v) != float("inf") else default


def _clean(s, n):
    """Untrusted on-chain text: drop control / bidi characters, collapse whitespace, cap the length."""
    if not isinstance(s, str):
        return ""
    s = " ".join(_CTRL.sub("", s).split())
    return s[:n]


class PumpFeed:
    """One PumpPortal data connection in a daemon thread, with bounded buffers of what it heard."""

    def __init__(self, url=WS_URL, keep_new=BUFFER, keep_grad=500):
        self.url = url
        self._lock = threading.Lock()
        self._new = deque(maxlen=keep_new)
        self._grad = deque(maxlen=keep_grad)
        self._thread = None
        self._stop = threading.Event()
        self._warned = set()
        self.stats = {"connected": False, "connects": 0, "reconnects": 0, "messages": 0, "launches": 0,
                      "graduations": 0, "errors": 0, "last_message": 0.0, "last_error": None, "started": 0.0}

    # ---------- lifecycle ----------
    def start(self):
        """Start the background thread (idempotent). Returns self, or None when websocket-client is missing."""
        if websocket is None:
            self._warn("nolib", "[pumpfun] websocket-client is not installed (pip install websocket-client); "
                                "pump.fun feed off")
            return None
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            self._stop.clear()
            self.stats["started"] = time.time()
            self._thread = threading.Thread(target=self._run, name="pumpfun-feed", daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def running(self):
        return self._thread is not None and self._thread.is_alive()

    # ---------- reads ----------
    def new_tokens(self, since=0):
        """Launches heard after unix time `since` (oldest first). Copies, so callers may keep them."""
        with self._lock:
            return [dict(e) for e in self._new if e["ts"] > since]

    def graduations(self, since=0):
        with self._lock:
            return [dict(e) for e in self._grad if e["ts"] > since]

    def status(self):
        with self._lock:
            s = dict(self.stats)
            s["buffered"] = {"launches": len(self._new), "graduations": len(self._grad)}
        s["last_message_age"] = round(time.time() - s["last_message"]) if s["last_message"] else None
        s["running"] = self.running()
        return s

    # ---------- background thread ----------
    def _warn(self, key, msg):
        if key not in self._warned:
            self._warned.add(key)
            print(msg)

    def _run(self):
        backoff = 5.0
        while not self._stop.is_set():
            opened = time.time()
            ws = None
            try:
                ws = websocket.create_connection(self.url, timeout=20, suppress_origin=True)
                ws.send(json.dumps({"method": "subscribeNewToken"}))
                ws.send(json.dumps({"method": "subscribeMigration"}))
                with self._lock:
                    self.stats["connected"] = True
                    self.stats["connects"] += 1
                self._warned.discard("connect")
                self._loop(ws)
            except Exception as e:
                with self._lock:
                    self.stats["errors"] += 1
                    self.stats["last_error"] = f"{type(e).__name__}: {str(e)[:120]}"
                self._warn("connect", f"[pumpfun] PumpPortal connection problem ({type(e).__name__}: {str(e)[:100]}); "
                                      f"reconnecting with backoff, the arena keeps running")
            finally:
                with self._lock:
                    self.stats["connected"] = False
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass
            if self._stop.is_set():
                break
            # a connection that lived a while was healthy: start the backoff over
            backoff = 5.0 if time.time() - opened > 120 else min(300.0, backoff * 2)
            with self._lock:
                self.stats["reconnects"] += 1
            self._stop.wait(backoff)

    def _loop(self, ws):
        """Receive until the connection breaks or stop() is called. Idle connections are pinged; three silent
        minutes in a row mean the socket is dead, so it is dropped and reopened."""
        silent = 0
        while not self._stop.is_set():
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                silent += 1
                if silent >= 3:
                    raise ConnectionError("no messages for 60s, reconnecting")
                try:
                    ws.ping()
                except Exception:
                    raise ConnectionError("ping failed")
                continue
            silent = 0
            if not raw:
                continue
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8", "replace")
                except Exception:
                    continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if isinstance(d, dict):
                self._handle(d)

    def _handle(self, d):
        now = time.time()
        with self._lock:
            self.stats["messages"] += 1
            self.stats["last_message"] = now
        mint = d.get("mint")
        if not isinstance(mint, str) or not (32 <= len(mint) <= 44):
            return  # subscription acks and anything else without a token
        tx = str(d.get("txType") or "").lower()
        pool = str(d.get("pool") or "")
        if tx == "create":
            rec = {
                "mint": mint,
                "name": _clean(d.get("name"), 40),
                "symbol": _clean(d.get("symbol"), 12),
                "creator": d.get("traderPublicKey") if isinstance(d.get("traderPublicKey"), str) else None,
                "initial_buy_sol": _f(d.get("solAmount"), 0.0),
                "initial_buy_tokens": _f(d.get("initialBuy"), 0.0),
                "mcap_sol": _f(d.get("marketCapSol"), INITIAL_MCAP_SOL),
                "v_sol": _f(d.get("vSolInBondingCurve")),
                "v_tokens": _f(d.get("vTokensInBondingCurve")),
                "curve": d.get("bondingCurveKey") if isinstance(d.get("bondingCurveKey"), str) else None,
                "uri": d.get("uri") if isinstance(d.get("uri"), str) else None,
                "mayhem": bool(d.get("is_mayhem_mode")),
                "pool": pool,
                "signature": d.get("signature"),
                "ts": now,
            }
            with self._lock:
                self._new.append(rec)
                self.stats["launches"] += 1
        elif tx in ("migrate", "migration") or (pool == "pump-amm" and tx != "create"):
            rec = {"mint": mint, "pool": pool, "signature": d.get("signature"), "ts": now}
            with self._lock:
                self._grad.append(rec)
                self.stats["graduations"] += 1
        # trade events are never subscribed; anything else is ignored


_shared = None
_shared_lock = threading.Lock()


def shared():
    """The process-wide feed (one websocket per process), started on first call. None when disabled or when
    websocket-client is missing. Never raises."""
    global _shared
    if not ENABLED or websocket is None:
        return None
    with _shared_lock:
        if _shared is None:
            try:
                feed = PumpFeed()
                _shared = feed if feed.start() is not None else None
            except Exception as e:  # pragma: no cover
                print(f"[pumpfun] could not start the feed: {str(e)[:120]}")
                _shared = None
    return _shared


if __name__ == "__main__":  # quick manual check: python pumpfun.py
    f = PumpFeed()
    f.start()
    t0 = time.time()
    try:
        while time.time() - t0 < 90:
            time.sleep(15)
            s = f.status()
            print(f"{time.time() - t0:5.0f}s connected={s['connected']} launches={s['launches']} "
                  f"graduations={s['graduations']} errors={s['errors']}")
    finally:
        f.stop()
    top = sorted(f.new_tokens(), key=lambda e: -e["mcap_sol"])[:5]
    for e in top:
        print(f"  {e['symbol']:<10} {e['mint']} mcap {e['mcap_sol']:.1f} SOL, creator bought {e['initial_buy_sol']:.2f} SOL")
    for g in f.graduations():
        print(f"  graduated {g['mint']} -> {g['pool']}")
