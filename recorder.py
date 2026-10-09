"""Records every market snapshot the arena sees, so replay.py can re-run any agents on a past day.

main.py wraps the market:  market = recorder.wrap(market, "recordings", mock=args.mock)
The wrapper passes everything through to the real market and, after each refresh(), appends one line to

    recordings/YYYY-MM-DD.jsonl.gz          (local date; mock markets: mock-YYYY-MM-DD.jsonl.gz,
                                             and only when ARENA_RECORD_MOCK=1)

Each arena process writes its own file. A restart on the same day adds 2026-10-05.1.jsonl.gz, .2, ... so
every file is a single gzip stream that is complete except (after a crash) its last line; appending to a
gzip file whose trailer was never written would make everything after it unreadable. replay.py loads all
of a day's files together, so the split is invisible when replaying.

File format (version 1), gzip-compressed JSON lines:
    {"hdr": {"v": 1, "mock": false, "started": <unix>, ...}}           first line of every file
    {"ts": <unix>, "sol": {...} | null, "defs": {<addr>: {...}}, "tokens": [{"a": <addr>, ...}, ...]}
Per token, the fields that never change (symbol, name, url, decimals, first_seen) and the pair's creation
time ("born", unix seconds derived from age_min) go in "defs" once per file, and again (changed keys only)
if they change; replay recomputes age_min = (ts - born) / 60. Every other field
is written only when it differs from the previous line for that token (delta encoding); "-": [...] lists
fields that disappeared. Floats are rounded to 6 significant digits; keys starting with "_" (mock market
internals) and "updated" (the fetch time) are dropped. replay.iter_snapshots() turns this back into the
full token dicts the arena saw.

pump.curve_pct scale: recordings made before 2026-10-09 carry curve_pct = mcap / a fixed $69,000; from then on it
is mcap / the live graduation cap (425 SOL x the SOL price, market.graduation_cap_usd()), about 1.4x higher at
SOL ~ $115. To compare old files, recompute it from mcap and the snapshot's "sol" price.

Disk use: live data runs about 2-6 MB per day (60 tokens, one snapshot every 30 s); a mock market, where
every number changes every tick, is the worst case at roughly 10 MB per day.
"""
import atexit
import gzip
import json
import math
import os
import socket
import time
from datetime import datetime

FORMAT_VERSION = 1
SIG_DIGITS = 6
STATIC_KEYS = ("symbol", "name", "url", "decimals", "first_seen")  # written once per file in "defs"
DROP_KEYS = {"updated"}  # the fetch time, which replay sets to the snapshot time


def _round(v):
    """Round floats to SIG_DIGITS significant digits, recursively. Non-finite floats become null."""
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        return float(f"{v:.{SIG_DIGITS}g}")
    if isinstance(v, dict):
        return {str(k): _round(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_round(x) for x in v]
    return v


class RecordingMarket:
    """Proxy around a market object. Attribute reads and writes that aren't the recorder's own go to the
    real market, so new market attributes (risk_cache, risk_dirty, ...) keep working."""

    _OWN = frozenset(("_market", "_dir", "_mock", "_fh", "_path", "_date", "_defs", "_last", "_warned",
                      "_lines", "_bytes"))

    def __init__(self, market, directory, mock=False):
        for k, v in dict(_market=market, _dir=directory, _mock=mock, _fh=None, _path=None, _date=None,
                         _defs={}, _last={}, _warned=False, _lines=0, _bytes=0).items():
            object.__setattr__(self, k, v)

    def __getattr__(self, name):  # only called when normal lookup fails
        return getattr(object.__getattribute__(self, "_market"), name)

    def __setattr__(self, name, value):
        if name in RecordingMarket._OWN:
            object.__setattr__(self, name, value)
        else:
            setattr(self._market, name, value)

    def __repr__(self):
        return f"RecordingMarket({self._market!r} -> {self._path})"

    # ---------- market interface ----------
    def refresh(self, held):
        self._market.refresh(held)
        try:
            self._record()
        except Exception as e:  # recording must never break the arena
            if not self._warned:
                self._warned = True
                print(f"[recorder] could not write a snapshot ({e}); the arena keeps running, "
                      f"recording will keep retrying quietly")

    def get(self, addr):
        return self._market.get(addr)

    def candidates(self):
        return self._market.candidates()

    # ---------- recording ----------
    @property
    def recording_path(self):
        return self._path

    def stop_recording(self):
        """Close the current file (called automatically at exit)."""
        fh, self._fh = self._fh, None
        if fh is not None:
            try:
                fh.close()
            except Exception:
                pass

    def _open_file(self, now):
        self.stop_recording()
        os.makedirs(self._dir, exist_ok=True)
        date = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
        base = f"{'mock-' if self._mock else ''}{date}"
        path, n = os.path.join(self._dir, base + ".jsonl.gz"), 0
        while os.path.exists(path):  # another arena process already wrote this day: start a new segment
            n += 1
            path = os.path.join(self._dir, f"{base}.{n}.jsonl.gz")
        self._fh = gzip.open(path, "wb", compresslevel=6)
        self._path, self._date, self._defs, self._last = path, date, {}, {}
        self._write({"hdr": {"v": FORMAT_VERSION, "mock": self._mock, "started": round(now, 3),
                             "host": socket.gethostname(), "pid": os.getpid(),
                             "market": type(self._market).__name__}})
        print(f"[recorder] saving market snapshots to {path}")

    def _write(self, obj):
        data = (json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str) + "\n").encode("utf-8", "replace")
        self._fh.write(data)
        self._fh.flush()  # zlib sync flush: everything so far is on disk and readable even if we get killed
        self._lines += 1
        self._bytes += len(data)

    def _encode(self, t, now, defs):
        """One token as a delta against the last line, filling `defs` if its static fields changed."""
        a = t["address"]
        static = {k: _round(t[k]) for k in STATIC_KEYS if k in t}
        prev = self._defs.get(a)
        if t.get("age_min") is not None:
            try:  # a few seconds of jitter (the live feed's fetch time) isn't worth a new line
                born = round(now - float(t["age_min"]) * 60)
                old = (prev or {}).get("born")
                static["born"] = old if old is not None and abs(old - born) <= 15 else born
            except (TypeError, ValueError):
                pass
        if prev is None:
            self._defs[a] = defs[a] = static
        elif static != prev:  # only the changed static fields; replay merges them
            defs[a] = {k: v for k, v in static.items() if k not in prev or prev[k] != v}
            self._defs[a] = static
        dyn = {k: _round(v) for k, v in t.items()
               if k != "address" and k != "age_min" and k not in STATIC_KEYS and k not in DROP_KEYS
               and not str(k).startswith("_")}
        last = self._last.get(a, {})
        out = {"a": a}
        for k, v in dyn.items():
            if k not in last or last[k] != v:
                out[k] = v
        gone = [k for k in last if k not in dyn]
        if gone:
            out["-"] = gone
        self._last[a] = dyn
        return out

    def _record(self):
        now = time.time()
        if self._fh is None or datetime.fromtimestamp(now).strftime("%Y-%m-%d") != self._date:
            self._open_file(now)
        defs, tokens = {}, []
        for t in self._market.candidates():
            if isinstance(t, dict) and t.get("address"):
                tokens.append(self._encode(t, now, defs))
        sol = getattr(self._market, "sol", None)
        line = {"ts": round(now, 3), "sol": self._encode(sol, now, defs) if isinstance(sol, dict) and sol.get("address") else None}
        if defs:
            line["defs"] = defs
        line["tokens"] = tokens
        self._write(line)


def wrap(market, directory, mock=False):
    """Return `market` wrapped so every refresh() is recorded under `directory`. Mock markets are only
    recorded when ARENA_RECORD_MOCK=1 (into mock-YYYY-MM-DD.jsonl.gz, so they never mix with live data)."""
    if mock and os.environ.get("ARENA_RECORD_MOCK", "").strip() not in ("1", "true", "yes"):
        return market
    rec = RecordingMarket(market, directory, mock=mock)
    atexit.register(rec.stop_recording)
    return rec
