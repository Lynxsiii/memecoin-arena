"""Market memory: which kinds of entries actually paid off lately, measured from the arena's own prices.

Every two minutes it samples each tracked token's features and price: 5-minute and 1-hour change, age, liquidity,
buy/sell flow, how far it sits below its 1-hour high, how violently it has been swinging, where it was discovered
(paid promotion or organic trending) and, once the rug check has run, holder concentration and RugCheck's score.
Once a sample is an hour old it knows what that token did over the next 15 and 60 minutes, and it summarizes those
outcomes by bucket over the last 24 hours. Every Claude agent sees the same table, so it learns from the market's
recent behaviour instead of from fixed rules.

ARENA_MARKET_MEMORY=0 turns it off.
"""
import bisect
import os
import statistics
from collections import defaultdict, deque

SAMPLE_SECS = 120
WINDOW_SECS = 24 * 3600
DEFAULT_ROUND_TRIP_PCT = 2.6  # used until the arena has measured its own fills
MIN_SAMPLES = 150             # below this the table would be noise
ENABLED = os.environ.get("ARENA_MARKET_MEMORY", "1").strip().lower() not in ("0", "off", "false", "no")

# (title, feature, [(label, low, high)]): numeric buckets hold low <= v < high (None = open-ended);
# a bucket whose low is a string matches that exact value.
BUCKETS = [
    ("5-minute change", "chg_m5", [("below -15%", None, -15), ("-15% to -5%", -15, -5), ("-5% to +5%", -5, 5),
                                   ("+5% to +20%", 5, 20), ("+20% to +50%", 20, 50), ("above +50%", 50, None)]),
    ("1-hour change", "chg_h1", [("below -30%", None, -30), ("-30% to 0%", -30, 0), ("0% to +50%", 0, 50),
                                 ("+50% to +200%", 50, 200), ("above +200%", 200, None)]),
    ("below its 1-hour high", "drawdown_60m", [("within 5% of the high", -5, None), ("5% to 15% below", -15, -5),
                                               ("15% to 30% below", -30, -15), ("over 30% below", None, -30)]),
    ("30-minute swings (std of 2-minute moves)", "volatility_30m", [("calm, under 2%", None, 2), ("2% to 5%", 2, 5),
                                                                     ("5% to 10%", 5, 10), ("wild, over 10%", 10, None)]),
    ("age", "age_min", [("under 30 min", None, 30), ("30 min to 2 h", 30, 120), ("2 h to 6 h", 120, 360),
                        ("6 h to 24 h", 360, 1440), ("over 1 day", 1440, None)]),
    ("liquidity", "liquidity", [("under $20k", None, 20e3), ("$20k to $50k", 20e3, 50e3),
                                ("$50k to $150k", 50e3, 150e3), ("over $150k", 150e3, None)]),
    ("1-hour buy/sell flow", "flow", [("more sells than buys", None, 1.0), ("buys 1-2x sells", 1.0, 2.0),
                                      ("buys over 2x sells", 2.0, None)]),
    ("where it was found", "source", [("paid promotion", "promoted", None), ("organic trending", "organic", None),
                                      ("both", "both", None), ("fresh pump.fun launch", "pumpfun", None),
                                      ("just graduated from pump.fun", "graduated", None),
                                      ("a top trader bought it", "copy", None)]),
    ("top 10 holders (pools excluded)", "top10_pct", [("under 20% of supply", None, 20), ("20% to 35%", 20, 35),
                                                       ("35% to 50%", 35, 50), ("over 50%", 50, None)]),
    ("RugCheck score", "rugcheck_score", [("0-10, clean", None, 10), ("10-40", 10, 40), ("over 40, risky", 40, None)]),
]


def _in(v, lo, hi):
    if isinstance(lo, str):
        return v == lo
    if not isinstance(v, (int, float)):
        return False
    return (lo is None or v >= lo) and (hi is None or v < hi)


class MarketMemory:
    def __init__(self):
        self.prices = defaultdict(list)   # token -> [(ts, price)], one point per sample
        self.samples = deque()            # (ts, token, features)
        self.last_sample = 0.0
        self._cache = (0.0, None, None)

    def _path_features(self, a, now):
        """How far below its 1-hour high the token is, and how hard it has swung over 30 minutes (from our samples)."""
        s = self.prices[a]
        i = bisect.bisect_left(s, (now - 3600, 0))
        hour = [p for _, p in s[i:]]
        out = {"drawdown_60m": None, "volatility_30m": None}
        if len(hour) >= 5:
            out["drawdown_60m"] = (hour[-1] / max(hour) - 1) * 100
        j = bisect.bisect_left(s, (now - 1800, 0))
        half = [p for _, p in s[j:]]
        if len(half) >= 6:
            moves = [(b / a_ - 1) * 100 for a_, b in zip(half, half[1:]) if a_ > 0]
            if len(moves) >= 5:
                out["volatility_30m"] = statistics.pstdev(moves)
        return out

    def observe(self, now, tokens):
        """Called every tick; keeps one sample every two minutes."""
        if now - self.last_sample < SAMPLE_SECS:
            return
        self.last_sample = now
        for t in tokens:
            a, p = t.get("address"), t.get("price") or 0
            if not a or p <= 0:
                continue
            self.prices[a].append((now, p))
            rug = t.get("rug") if isinstance(t.get("rug"), dict) and not t["rug"].get("error") else {}
            self.samples.append((now, a, {
                "chg_m5": t.get("chg_m5"), "chg_h1": t.get("chg_h1"), "age_min": t.get("age_min"),
                "liquidity": t.get("liquidity"),
                "flow": (t.get("buys_h1") or 0) / max(1, t.get("sells_h1") or 0),
                "source": t.get("source"), "top10_pct": rug.get("top10_pct"), "rugcheck_score": rug.get("rugcheck_score"),
                **self._path_features(a, now),
            }))
        while self.samples and now - self.samples[0][0] > WINDOW_SECS:
            self.samples.popleft()
        if len(self.prices) > 500 or int(now) % 3600 < SAMPLE_SECS:  # drop tokens unseen for over a day
            self.prices = defaultdict(list, {a: [x for x in s if now - x[0] <= WINDOW_SECS + 3600]
                                             for a, s in self.prices.items() if s and now - s[-1][0] <= WINDOW_SECS})

    def load(self, snapshots):
        """Warm up from recorded snapshots (anything with .ts and .tokens), e.g. today's recordings at startup."""
        for snap in snapshots:
            self.observe(snap.ts, snap.tokens)

    def _price_after(self, token, ts, mins):
        s = self.prices.get(token)
        if not s:
            return None
        target = ts + mins * 60
        i = bisect.bisect_left(s, (target, 0))
        return s[i][1] if i < len(s) and s[i][0] - target <= 300 else None

    def stats(self, now, round_trip_pct=None):
        """Outcome table by bucket, recomputed at most every 10 minutes. None until there is enough data.
        `round_trip_pct` is the arena's measured trading cost; "beat costs" is judged against it."""
        cost = round_trip_pct or DEFAULT_ROUND_TRIP_PCT
        at, cached, cached_cost = self._cache
        if cached is not None and now - at < 600 and cached_cost == cost:
            return cached
        done, first, last = [], None, None
        for ts, a, f in self.samples:
            if now - ts < 3600:
                break
            p0 = self._price_after(a, ts, 0)
            p15, p60 = self._price_after(a, ts, 15), self._price_after(a, ts, 60)
            if p0 and p15 and p60:
                done.append((f, max(-100.0, min((p15 / p0 - 1) * 100, 500.0)), max(-100.0, min((p60 / p0 - 1) * 100, 500.0))))
                first, last = first or ts, ts
        if len(done) < MIN_SAMPLES:
            self._cache = (now, None, cost)
            return None

        def summary(rows):
            r15, r60 = [r[1] for r in rows], [r[2] for r in rows]
            return {"n": len(rows), "avg_15m_pct": round(statistics.mean(r15), 1), "avg_60m_pct": round(statistics.mean(r60), 1),
                    "median_60m_pct": round(statistics.median(r60), 1),
                    "beat_costs_60m_pct": round(sum(x > cost for x in r60) / len(r60) * 100)}

        table = {}
        for title, key, buckets in BUCKETS:
            rows = []
            for label, lo, hi in buckets:
                hit = [r for r in done if _in(r[0].get(key), lo, hi)]
                if len(hit) >= 20:
                    rows.append({"bucket": label, **summary(hit)})
            if rows:
                table[title] = rows
        result = {"hours_of_data": round((last - first) / 3600 + 1, 1), "round_trip_cost_pct": cost,
                  "all_tokens": summary(done), "by": table}
        self._cache = (now, result, cost)
        return result
