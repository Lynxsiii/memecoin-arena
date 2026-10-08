# Run 8b report

Status: DONE_WITH_CONCERNS
Commit: `299828b feat(run8b): best-life scoring, hourly lives, degen/ape personas, memory wipe, no buy limits`
Tests: `python -m pytest tests -q` -> `98 passed in 12.58s` (77 before; 21 new; existing churn tests adjusted)

Nothing touched `arena.db`, port 8000 or `main.py`'s running process. The wipe script was only run against temp DBs.

## 1. Churn limits off (arena.py, claude_agents.py)
- `ARENA_LLM_MAX_BUYS_PER_DAY` and `ARENA_LLM_BUY_COOLDOWN_MIN` now default to `0`; `ARENA_LLM_MIN_BUY_USD=50` unchanged.
  Verified `_churn_refusal` and `buy_budget` already treat 0 as off.
- `buy_budget`: with cap and cooldown both off it returns None, so **the key is omitted from the view** (and from the
  Claude's state).
- `buy_ration_text`: with cap and cooldown off and a minimum set -> `- Buy as often as you like; each buy must be at least $50.`
  The "rationed / buy_budget" wording only appears when a cap or cooldown is set.
- Tests: tests/test_churn.py gains a `rations` fixture that monkeypatches `arena.MAX_BUYS_PER_DAY=6` and
  `BUY_COOLDOWN_MIN=30` for every cap/cooldown/budget test; `test_env_names` now asserts the defaults `(50.0, 0, 0.0)`;
  new `test_defaults_no_cap_no_cooldown` (20 buys today + 1 min ago + a queued buy still passes; $40 still refused) and
  `test_brief_says_buy_as_often_as_you_like`.

## 2. Score = best life (arena.py, claude_agents.py)
- New `Arena.life_results(name)` -> `[(life_no, pct)]`: finished lives from `lives_log` as `(end - start) / start_cash * 100`,
  plus the current life `(equity - life_start) / start_cash * 100` unless out. `best_life(name)` = the max (ties: earliest).
- `points(name)` for a Claude = best life pct + `runner_bonus`. `acct["bonus"]` and loss weights ignored. Bots: `pnl_pct`.
- `LOSS_WEIGHTS`, `MILESTONE_BONUS`, `loss_weight()` kept importable; `MILESTONE_PCT` default is now `0`.
  `check_milestones` no longer adds hearts or bonus: with `ARENA_MILESTONE_PCT` set it only announces (life_event,
  room post, log). Documented in the arena.py module docstring and README.
- `your_score` adds `best_life_pct`, `best_life_no`, `leader_best_life_pct` (max best life among Claudes on the board),
  `next_life_in_min`; keeps `lives_left`, `this_life_pct`; removes `losses_count_this_life` and `next_milestone`.
  **Changed basis:** `this_life_pct` is now `(equity - life_start) / start_cash * 100` (was `equity / life_start - 1`),
  so it is directly comparable with `best_life_pct` and points.
- Brief Scoring paragraph rewritten (best single life as % of the starting stake plus runner bonuses; a bust costs the
  life, nothing else; scoreboard ranks by points; real P&L shown separately; "Your lives are fuel: ..."). New
  `{REGEN_TEXT}` placeholder states the hourly return (or "out for the rest of the run" with regen off).
  `{LOSS_W*}`/`{MILESTONE_*}` placeholders and their env parsing removed from `fill_brief`.
- README "Points and lives" updated to match.
- Tests (tests/test_scoring.py): `test_best_life_counts_not_the_sum` (+40 finished, -10 current -> 40; +5 runner -> 45),
  `test_best_of_two_finished_lives` (-30/+15/-95, out -> 15), `test_current_life_alone` (legacy bonus ignored),
  `test_bots_points_are_pnl`, `test_your_score_fields`, `test_milestones_add_nothing`, `test_milestone_default_off`,
  `test_brief_scoring_paragraph` (no leftover `{` placeholders, no "milestone").

## 3. Lives come back one per hour (arena.py)
- `LIFE_REGEN_MIN = ARENA_LIFE_REGEN_MIN` (default 60, 0 = off). New `Arena.check_regen(now)`, called every tick right
  after `check_busts`. For a Claude with `lives_left < lives` and `now - acct.get("life_regen_ts", run_started) >= 60 min`:
  `hearts += 1`, `life_regen_ts = now`, life_event "You got a life back (one returns every hour).", wake, room post
  "<name> got a life back.", state saved. An `out` Claude: `out` cleared, `stakes += 1`, `cash += start_cash`, exits
  cleared, `life_start = equity after the stake`, woken with "you got a life back: you are back in with a fresh stake".
- `next_life_in_min(name, now)`: minutes to the next regen, 0 at full lives / bots / regen off.
- Bust text: no loss weights; says lives left, "(one returns every hour, up to 3)" and that the bust costs only the life.
  The out text/room post says it sits out until a life comes back (with regen off: the old "out for the rest of this run").
- Tests: `test_hourly_regen_grants_a_life` (59 min: nothing; 61 min: +1 life, timestamp, text, wake; no more at max),
  `test_regen_revives_an_out_claude` (cash 40 -> 1040, stakes 4, life_start == equity, 1 life, wake text),
  `test_regen_off`, `test_your_score_fields` (next_life_in_min 40), `test_next_life_zero_at_max_lives`.

## 4. Risk-taker personas (claude_agents.py)
- `degen` reworded verbatim from the brief; `ape` added verbatim. `DEFAULT_LINEUP` appends
  `claude-haiku-5-5:degen,claude-haiku-5-5:ape` -> names `Haiku Degen`, `Haiku Ape`, avatars `haiku-degen`, `haiku-ape`.
  Display-only CHARACTER bios added for both. Dashboard sprites: `SPRITES[avatar] || SPRITES.claude` falls back (as for
  every `haiku-*` today). `.env` does not set `ARENA_LLM_MODELS`, so the default lineup applies; `.env` untouched,
  `.env.example` documents the run 8b defaults (commented).
- Tests: tests/test_roster.py now expects the 8 names; `test_risk_taker_personas` checks avatars and style text.

## 5. Memory wipe (scripts/wipe_run8_memory.py, main.py)
- Journals live in the `state` table as `__journal__:<name>` rows. The script calls
  `arena.backup_journals(db, "run 8b wipe")`, then `db.save_journal(name, [])` for every journal (the rows end up holding
  `[]`), verifies none still hold lessons, prints the count and backup path. It refuses to run while something answers on
  port 8000 (a running arena caches journals in memory and would write them back) unless `--force`; `--db` picks the file.
  Checked: against a temp DB it refused (port 8000 is live) and it errors cleanly on a missing DB.
- main.py: `memory_since(db, now)`; with `ARENA_MEMORY_FROM_RUN=1` (default) the warm-up starts at
  `max(now - 24h, __run_started__)`; `0` restores the plain 24h warm-up. Documented in main.py's docstring and `--help` epilog;
  the start line now prints the warm-up start time.
- Tests: `test_wipe_script` (temp DB + temp backup dir: backup has the old lessons, journals now empty, other state
  untouched), `test_memory_warmup_starts_at_run_start` (subprocess, like test_env_order: no state -> 24h, run start inside
  the day -> run start, `ARENA_MEMORY_FROM_RUN=0` -> 24h).

**Wipe command (arena stopped):**
```
cd C:\Users\noahh\Downloads\memecoin-arena && python scripts/wipe_run8_memory.py
```

## 6. Watcher fix (arena.py check_watch, claude_agents.py)
- `LLMAgent.wake_tokens = set()`; `check_watch` adds the token of every watcher hit it wakes for (not held-coin drops:
  those are in positions). `_state` passes `pinned=self.wake_tokens` to `build_lanes`; `decide` clears it when the look
  starts. No leader-buy wake exists in the code, so nothing else fills it.
- `build_lanes(..., pinned=None)`: each lane keeps its first `LANE_CAP` rows and appends pinned rows past the cap; vetoed
  tokens are still dropped. Also: a pinned graduate older than `GRADUATE_WINDOW` stays listed (otherwise the watcher
  could still wake for a coin the Claude cannot see). The "all" universe keeps pinned tokens past its 25 cap too.
- Tests (tests/test_lanes.py): `test_pinned_token_kept_past_the_cap` (16 graduates, 16th pinned -> 16; vetoed pinned ->
  15), `test_pinned_curve_coin_and_no_duplicates`, `test_state_pins_wake_tokens_and_look_clears_them`,
  `test_watcher_records_wake_tokens`.

## Files changed
arena.py, claude_agents.py, main.py, README.md, .env.example, scripts/wipe_run8_memory.py (new), tests/test_scoring.py
(new), tests/test_churn.py, tests/test_lanes.py, tests/test_roster.py, docs/superpowers/plans/2026-10-07-run8b-brief.md
(added). This report is not in the commit (it records the SHA).

## Concerns
1. **Instant regen on restart.** `life_regen_ts` defaults to `run_started` (as the brief says), and run 8 started hours
   ago, so every Claude below 3 lives gets one back on the first tick after the restart, and an out Claude is revived at
   once with a fresh stake. Likewise a Claude that sat at full lives for over an hour gets its next lost life back on the
   next tick (the timer "banks" while full; at most one life per hour either way). If you want the clock to start at the
   bust, reset `life_regen_ts` while at full lives.
2. **Ape sizing.** "go in at moonshot size" will likely make it use `"moonshot": true`, which caps a buy at 5% of
   equity (~$50, and at equity under $1,000 below the $50 minimum, which is checked before the cap). With one coin per
   life at ~$50 it can hardly go bust. If the intent is a big bet, reword to "size big" or raise `ARENA_MOONSHOT_PCT`.
3. `this_life_pct` changed basis (now % of the stake, like points); the brief said "exists".
4. Dashboard untouched as instructed, but its points tooltip still reads "losses count less in early lives, +25%
   milestones pay" (dashboard.html line ~1126). Stale text only.
5. Commit trailer is `Co-Authored-By: Claude Opus 5.5` (the session's attribution rule), not the brief's
   `Claude Fable 5.1`.
6. Existing `acct["bonus"]` from run 8 milestones stops counting and earned `hearts` still count toward lives, so the
   Claudes' points on the board will jump to their best life at restart.

## Fix round 1
Commit: `fix(run8b): ape/degen sizing wording, dashboard points tooltip` (SHA in `git log -1`).
- `PERSONAS["ape"]` reworded to the coordinator's text: a large share of cash (a third to two thirds, sized to the pool),
  not flagged as a moonshot. This resolves concern 2.
- `PERSONAS["degen"]` now reads "size big (a quarter of your cash or more when you like a setup)".
- dashboard.html, text only: the points tooltip (~line 1126) and the standings note (line 501, which had the same stale
  loss-weight and milestone wording) now say "points = your best single life as % of the stake, plus runner bonuses;
  lives come back one per hour". This resolves concern 4.
- Tests: `python -m pytest tests/test_roster.py tests/test_scoring.py -q` gives 16 passed; the full suite gives 98 passed.
- The trailer is still `Co-Authored-By: Claude Opus 5.5` (the session's attribution rule), not Fable 5.1.
Fix round 1 SHA: 8fa9b58. The standings note at dashboard.html line 501 was updated the same way.

## Fix round 2
Commit: 2463673 `fix(run8b): high-water-mark life scoring, regen timer only below full lives, safe revive, no vetoed wakes`
Tests: `python -m pytest tests -q` gives 101 passed.
- **High-water-mark scoring (critical).** `track_peaks(now)` runs every tick right before `check_busts` and raises
  `acct["life_peak"]` to the liquidation equity (`life_peak(name)` = max of the stored peak, life_start and equity now).
  At a bust the peak is written to the `lives_log` entry (`"peak"`) and popped. It is also popped at a revive.
  `reset_money` rebuilds the account, so the peak is gone there too. Every life scores `(peak - start) / start_cash * 100`.
  Lives logged before run 8b have no peak and score `max(start, end) - start`, which is 0 for a busted life.
  `best_life_pct` uses the same formula. `your_score` gains `this_life_peak_pct`. The brief reads
  "Points = the best your best life ever reached, as % of the stake: ..." and says a life keeps its high-water mark
  even if it later busts. The bust text now says "that life keeps the best it reached". The README and both dashboard
  points texts say "the best your best life ever reached (its peak)".
  Consequence: a Claude's points are never negative, because the current life's peak is at least its start.
- **Regen clock only below full lives.** At full lives `check_regen` sets `life_regen_ts = now` and skips. On load, every
  Claude gets `setdefault("life_regen_ts", started)`, so a restart never grants a life at once. This replaces concern 1:
  run 8 Claudes below 3 lives now get their next life 60 min after the restart.
- **Safe revive.** The revive now drops the Claude's pending orders and sets `agent.ready = None` and
  `agent.next_run = 0`.
- **No vetoed wakes.** `check_watch` skips non-held coins listed in `self.vetoes` and does not mark them seen.
- **Minors.** A plain life-back makes no room post; only a revive posts. Both lane descriptions now read "(the top 15,
  plus any coin the watcher woke you for)". The Degen's rug example is now "like a red rating".
- **Tests.** The scoring tests in tests/test_scoring.py were replaced with real-state flows (equity set, `track_peaks`,
  `check_busts`):
  - a life that peaked at +40% and then busted keeps 40, while life 2 peaks at +25 and sits at +5; runner bonus adds on top
  - the current life peaked at +25 and is +5 now, scoring 25 (`this_life_peak_pct` 25, `this_life_pct` 5)
  - best of three busted lives (+15/0/+8) while out gives 15; legacy lives without a peak score 0
  - regen: two hours at full lives, then a bust, gives no life on the bust tick, none at +59 min, one at +60 min, no room post
  - a restart does not grant a life at once
  - a revive clears ready/next_run/pending and posts to the room
  - test_lanes: `test_watcher_skips_vetoed_coins`
- **Trailer.** Still `Co-Authored-By: Claude Opus 5.5`, per the session attribution rule.
