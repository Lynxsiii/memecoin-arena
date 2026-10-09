# Run 9b implementation report

Commit: `feat(run9b): ramp window 55-85, 500 tracked slots with ramp-zone protection, $100 graduate buy cap`
Tests: `python -m pytest tests -q` gives `160 passed`. That is the 146 existing tests, 5 of them updated for the new defaults, plus 14 new tests in `tests/test_run9b.py`.

The running arena only picks up these changes when it restarts.

## 1. Ramp window 55-85%
- `signals.py`: the defaults are now `ramp_min_pct=55` and `ramp_max_pct=85`. `ARENA_RAMP_MIN` and `ARENA_RAMP_MAX` are read once at import and take priority over `ARENA_VETO_RAMP_MIN_PCT` / `_MAX_PCT`. They are exported as `signals.RAMP_MIN_PCT` / `RAMP_MAX_PCT`. With the defaults, `ramp_stage` is early below 55, ramp from 55 to 85 and late above 85.
- `claude_agents.py`: the brief and personas no longer hard-code the window. They use `{RAMP_MIN}` / `{RAMP_MAX}` placeholders, which `fill_brief` fills from `signals`, so an env override changes the text too. This covers:
  - the structure line ("early" under 55%, "ramp" 55-85%, "late" past 85%);
  - the Playbook ramp bullet, which now gives the run 9 evidence and the replay averages;
  - the curve-lane description;
  - the Ramp persona, which includes the required sentence: "Prefer the most-filled setup on screen; an entry that is still 55-65% filled needs to keep filling, so stop at -30% and move on if it stalls.";
  - the retired Runner persona ("past 85%").
  
  `replay.apply_brief` already runs personas through `fill_brief`.

## 2. Tracking capacity
- `market.py`:
  - `max_tracked` now defaults to 500 in pumpfun mode and stays at 60 in all mode. `ARENA_MAX_TRACKED` overrides either.
  - The docstring states the request budget. A 500-token refresh makes 17 DexScreener requests (~34/min against the 300/min limit), plus 4 probation requests per 120 s cycle. The GeckoTerminal fallback keeps its own budget (10 requests per call, 18 per minute) and prices SOL and held tokens first. During a DexScreener outage, only part of the pool is re-priced each minute, and the newest-tracked tokens wait.
- `ARENA_PUMPFUN_PROBATION_MIN` now defaults to 60 (was 20). The probation poll is unchanged: at most 120 addresses per cycle, never-polled first, then oldest.
- Immediate promotion:
  - A probation launch whose DexScreener market cap is at or above `TRACK_RAMP_MCAP_USD` is promoted whatever its volume. The default is 55% of $69k = $37,950, and `ARENA_PUMPFUN_TRACK_RAMP_MCAP_USD` overrides it (0 disables).
  - The promoted coin's `pump.curve_pct` is seeded from that market cap. This lets it be protected on the same refresh that adds it.
  - These promotions are counted in `probation_stats["promoted_ramp"]`.
  - With the default `TRACK_MCAP_USD=12000`, such a coin was already promoted by the existing rule, so this mostly matters when that rule is raised.
- Ramp-zone protection: `LiveMarket._protect_ramp(now)` runs at the start of every `_evict` pass, which covers both refresh and `track()`. Every tracked curve coin that has not graduated, has dex or source "pumpfun", and has `curve_pct >= RAMP_MIN_PCT` gets `protect_until = max(existing, now + 30 min)`. This is refreshed on each pass while the coin stays in the zone and lapses 30 minutes after it leaves.
- `arena.py`:
  - `step()` now wraps the old body (renamed `_step`) and times it with `time.monotonic()`, even when the tick raises.
  - `_note_tick_time` prints `[arena] slow tick: {secs:.1f}s (tracked {n})` above 20 s, at most once per 5 minutes of wall time.
  - The per-tick bounds are unchanged: `risk_checks_per_refresh=12`, `RUG_CHECKS=4`, `SELL_CHECKS`, and a test pins them.
- Already fine, no change:
  - `candidates()` is a plain list comprehension.
  - The history deques are 500 x 130 points.
  - `update_signals` runs once a minute, and its `flow_signals` query is already chunked by 500.
  - The recorder will write roughly 3x more per snapshot.

## 3. Graduate buy cap
- `arena.py`: `LLM_GRADUATE_MAX_USD` (`ARENA_LLM_GRADUATE_MAX_USD=100`, 0 disables) and a new helper, `is_graduate(t)`, which is true when `pump.graduated` is set or the dex is `pumpswap`.
- In `validate()`, a Claude's buy on a graduate above the cap is clamped to the cap. The clamp comes after the veto, churn and moonshot checks and before the equity and cash clamp. The order gets `capped_to` and `" [capped at $100: graduate]"` appended to its reason. It is not a refusal.
- Curve buys, including moonshots, are not capped. Bots are exempt.
- The brief's Rules get the cap line (as given) when the cap is on.

## Tests (tests/test_run9b.py)
- Ramp: the window bounds (50 false, 55 true, 85 true, 86 false, and the stage edges). The brief, Ramp and Runner text show 55-85% and "past 85%", and no persona or brief text contains "40-80", "40-60" or "past 80".
- Tracking:
  - `max_tracked` is 500 in pumpfun mode, 60 in all mode, and the env override works; probation is 60.
  - A $38k launch with no volume is promoted, seeded with curve_pct 55.1, and survives eviction as the oldest launch. Env 0 disables the rule.
  - Over capacity, a 60%-filled curve coin is protected and its protection is refreshed and then lapses. A 40% coin and a graduate are not protected.
  - The per-tick bounds are unchanged.
- Graduate cap:
  - A $400 graduate buy is clamped to $100 with `capped_to`; this also works with only `dex == "pumpswap"`.
  - An $80 graduate buy is untouched, and so is a $400 curve buy.
  - Bots are exempt, and env 0 disables the cap.
  - The brief shows the line, and drops it when the cap is 0.
- Slow tick: the print is throttled (none at 10 s, printed at 25 s, silent 2 minutes later, printed again after 5 minutes). `step()` reports its time even when the tick raises.
- Updated existing tests:
  - `test_run9.py`: the ramp tests moved from 50% to 60%, and the bounds test now uses 55/85/86.
  - `test_market_pumpfun.py`: the default is 500, and the expired-probation launch is now `PROBATION_MIN + 5` minutes old.

## Concerns
- **Flow data gets staler.** The traders.py pool trade feed polls about 6 GeckoTerminal pools per minute across every tracked pool. With 500 tokens instead of 150, each pool's trades are polled about 3x less often, so `net_share` / `buyers_1h` (the flow side of `ramp_setup`) are older. Without flow data, `ramp_setup` falls back to the DexScreener tx counts.
- **Price coverage in an outage.** During a DexScreener outage most of the 500 tokens sit on stale prices; held tokens are still re-priced first.
- **Probation backlog.** With a 60-minute window the backlog can exceed what 120 polls per 2-minute cycle cover. Each launch is then re-priced every few minutes rather than every cycle, so a coin crossing $38k is promoted on its next poll rather than instantly.
- **Protection has no ceiling.** If many curve coins sit at 55%+ at once, the pool can stay above 500 until their protection lapses. In practice that should be a few dozen coins.
- **Slow ticks.** A 500-token refresh makes about 17 DexScreener requests in sequence, so a slow DexScreener could push ticks past 20 s. The new print will show it.
- **Stale wording.** The cap's brief line says "yesterday", as specified, and will read stale after a few days.
- **Brief text vs the env cap.** `fill_brief` substitutes the cap amount, but the evidence numbers in that line are fixed.
