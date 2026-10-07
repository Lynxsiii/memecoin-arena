# Run 8: pump.fun-only long run — design

Date: 2026-10-07. Status: draft for review.

## Goal

A multi-day unattended run in which Claude agents trade ONLY pump.fun coins (bonding curve and PumpSwap graduates)
under pump.fun's own cost model, so that what the arena measures is what the same agents would do live on pump.fun.
Success is not "a Claude doubles": it is a pre-registered verdict per agent, reached after enough trades, that says
whether that agent beats the no-skill yardsticks on this universe.

Decisions already taken by the user: roster Haiku 5.5 x4 + Sonnet 5.5 x2; fresh run 8 (everyone back to $1000);
no automatic usage pacing (run flat out); universe = pump.fun only.

## What the diagnosis found (why this design)

Over seasons 1-6 the Claudes bought coins from trending feeds that fell ~45% over the next six hours; no exit rule
rescued those entries, and ~5% friction per round trip on 836 round trips ate most of the money. The fixes are
therefore: a different universe (pump.fun, seen from minute zero), far fewer trades, a leaderboard that ranks by
realized profit, and a verdict rule fixed before the run starts.

## Components

### 1. Market: pump.fun-only universe (market.py, pumpfun.py)

- New setting `ARENA_UNIVERSE=pumpfun` (default stays `all` so older runs replay unchanged). In pumpfun mode the
  DexScreener promotions and GeckoTerminal trending feeds are not used for discovery; every tracked token comes from
  PumpPortal (launch or migration) or from `track()` (a followed wallet bought it, and only if it is a pump.fun mint).
- `max_tracked` rises to 150 in pumpfun mode; `ARENA_PUMPFUN_SHARE` is forced to 1.0.
- Graduates: every migration is tracked at once (as now) and carries `pump.graduated` (unix time).
- Launches: instead of "the 2 biggest creator buys per 2 minutes", a probation poll. Every discover cycle the
  launches of the last `ARENA_PUMPFUN_PROBATION_MIN` (default 20) minutes with a creator buy >= the floor are priced
  in DexScreener batches of 30 (about 10 requests a minute, under its 300/min limit). A launch is promoted to tracked
  when it shows traction: market cap >= `ARENA_PUMPFUN_TRACK_MCAP_USD` (default 12,000, roughly a fifth of the curve)
  OR 1h volume >= `ARENA_PUMPFUN_TRACK_VOL_USD` (default 8,000) with at least 40 transactions. Launches that never
  pass are forgotten. Each tracked launch carries `pump.curve_pct` (progress toward graduation, from market cap over
  the ~$69k graduation cap) and `pump.launched`.
- Eviction: untouched tokens are dropped first, then the oldest dead launches (price down > 90% from its high or no
  DexScreener price for 10 minutes). Held tokens are never evicted (as now).

### 2. What the Claudes see: two lanes, no trending (claude_agents.py `_state`)

- `candidates` is replaced by two lists:
  - `graduates`: tokens with `pump.graduated` within the last 6 hours, newest first, up to 15, each with
    `minutes_since_graduation`, the existing flow/structure signals, holders and vetoes.
  - `curve`: bonding-curve tokens, up to 15, sorted by curve progress momentum (change in `curve_pct` over the last
    10 minutes, then `curve_pct`), each with `curve_pct`, `age_min`, `initial_buy_sol`, mayhem flag and flow.
- The top-25-by-1h-volume sort is removed. Vetoed tokens stay hidden (as now).
- The system brief gets a short pump.fun section: how the curve works, that graduation is the only mechanical ramp,
  that most graduates lose most of their value within 20 minutes of migrating, and the fee schedule of the route.

### 3. Exchange: `pumpfun` route (exchange.py)

- New `ARENA_ROUTE=pumpfun`: no app fee, pool fee by venue (1.25% on the curve, PumpSwap tiers by market cap, both
  already implemented), `$0.25` network/priority fee per transaction including failed ones, MEV slippage model kept
  (pump.fun's site has no sandwich protection). `.env` switches to this route for run 8; `fomo` stays available.
- `fee_text()` describes the pumpfun route so the Claudes read the right cost.

### 4. Leaderboard and copy trading (traders.py, copy_agents.py, arena.py)

- New ranking rule `ARENA_TRADERS_RANK=realized`: wallets are ranked by `realized_usd` only (unrealized ignored),
  eligible only with >= 5 round trips, win rate >= 50%, >= 3 tokens bought, and the existing bot/flipper exclusions.
  The old rule stays as `pnl` (default) for replays.
- Offline backtest BEFORE the run (`backtest_copy.py`, kept in the repo): over the 611k stored wallet trades and the
  recorded prices, rank wallets with each rule at each hour, then measure the forward 1h and 6h return (minus 5%
  cost) of copying every leader buy within 60 seconds. Output: a table per rule and leader count (top 5/10/20).
  The run uses whichever rule and leader count scored best; if none beats zero, Shadow still runs and the report
  says that no copy edge was measurable.
- Shadow follows a leader SET: `your_leaders` = the top `ARENA_SHADOW_LEADERS` (default 10) wallets with their last
  30 minutes of buys and sells (same skip reasons as now). The arena's "sell when the copied leader sells" rule keys
  on the wallet actually copied (stored per position, as the mechanical bots already do).
- New yardstick bot `Copy Top 10`: `CopyBot("Copy Top 10", 1, 10, "copy-a")` under the realized ranking, copying
  within 60 seconds, 10% of equity per buy, existing safety stop and 6-hour limit.

### 5. Churn control (arena.py `validate`)

For LLM agents only (bots size themselves):
- `ARENA_LLM_MAX_BUYS_PER_DAY=6` (rolling 24h), `ARENA_LLM_MIN_BUY_USD=50`, `ARENA_LLM_BUY_COOLDOWN_MIN=30`.
- A refused buy is recorded in the agent's `recent_failures` with the rule that refused it, so the agent sees why.
- Moonshot slots, the exit ladder, stops and lives are unchanged (the replay showed the current exits were the least
  bad of eight tested; the entries were the problem).

### 6. Roster and cadence (claude_agents.py, agents.py)

- `DEFAULT_LINEUP` = `claude-haiku-5-5:graduate, claude-haiku-5-5:runner, claude-haiku-5-5:skeptic,
  claude-haiku-5-5:shadow, claude-sonnet-5-5:graduate, claude-sonnet-5-5:shadow`.
- Cadence is the agents' own choice (user's decision: a violent market, let them be up whenever they want). No
  per-model limits: `ARENA_LLM_MIN_CHECK` defaults to 1 minute and `ARENA_LLM_MAX_CHECK` to 60, each agent returns
  its own `next_check_min` inside that range, and the watcher wakes it early whenever a watch rule or an alarm
  fires. The brief tells them plainly that they may look every minute if they want. Consequence accepted by the
  user: Sonnet at this pace will probably reach the weekly plan limit before the Oct 12 reset; when it does, the
  Sonnet agents stop deciding until the reset while the Haiku agents and bots keep running.
  Agent names: "Haiku Graduate", "Sonnet Graduate", etc.;
  `model_label` learns `claude-haiku-5-5` -> "Haiku 5.5". The CLI's "unrecognized_model" log line is harmless
  (verified today: the call completes on the user's plan).
- Personas reworded for the pump.fun universe: Graduate (unchanged in spirit), Runner (bonding-curve coins whose
  progress is accelerating from many wallets, never past 80% of the curve), Skeptic (graduates only, holders and LP
  checks, small size), Shadow (leader set, copies within its own checks).
- Bots: Hold SOL, Random (now draws from the pump.fun universe), Graduates (unchanged), Copy Top 10.

### 7. Pre-registered verdict (analytics.py, dashboard.html, strategy room)

- The existing `readiness` checklist is the verdict: >= N days, >= 100 closed trades, beats Random and Graduates
  after the luck check, >= 80% bootstrap confidence, drawdown and profit-factor limits, reliability.
- At run start the arena posts the verdict rule and roster to the strategy room and the Discord digest, and the
  dashboard's per-agent card shows "verdict: pending (x of 7)" until it lands. Nobody changes the roster before then.

### 8. Long-run hygiene

- Launcher `start_arena.cmd` (moved into the project as `start_arena.cmd`): restart loop (wait 15 s and relaunch
  when the process exits, unless a `stop.flag` file exists), log to `logs/arena-YYYY-MM-DD.log`.
- `--reset-money --keep-journals` at the first launch of run 8.
- Database: `VACUUM` after the reset; copy trades already pruned to 7 days; recordings already rotate daily.

## Data flow (one tick)

PumpPortal feed -> market discover (graduations + probation poll) -> DexScreener prices -> signals/vetoes ->
arena view (two lanes) -> LLM agent (Claude Code CLI) returns orders -> validate (churn rules) -> exchange fill
(pumpfun route) -> trades/equity tables -> dashboard, digest, verdict.

## Error handling

- PumpPortal down: no new launches/graduations; held tokens keep pricing; the dashboard already shows feed status.
- DexScreener rate limit: probation poll backs off for one cycle; tracked-token refresh keeps priority.
- Claude CLI failures/limits: existing retry and `recent_failures`; a model at its weekly limit simply stops
  deciding (no pacing, per the user's choice) while bots keep running.

## Testing

- Unit tests (pytest, new `tests/`): `validate` churn rules; `pumpfun` route fees on curve and PumpSwap tiers;
  lane builder (graduates vs curve, sorting, caps); realized ranking eligibility; probation promotion rule.
- `python main.py --mock` smoke run for five minutes with the new lineup (mock market gains fake pump.fun metadata).
- Backtest script run end to end on the real database before launch; its table goes in `reports/`.

## Out of scope

Live trading, Opus/Fable agents, the Council, usage pacing, changes to stops/ladder/lives/points.
