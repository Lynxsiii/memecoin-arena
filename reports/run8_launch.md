# Run 8 launch record

- Launched 2026-10-07 13:30 local via `start_arena_run8.cmd` (`--reset-money --keep-journals` on the first start only). Run 7 was already down (last equity point ~11:48 local).
- Mode line: universe=pumpfun route=pumpfun rank=realized max_tracked=150. Season 7 archived; journals kept.
- Roster: Haiku Graduate, Haiku Runner, Haiku Skeptic, Haiku Shadow, Sonnet Graduate, Sonnet Shadow; bots Random, Hold SOL, Graduates, Copy Top 10.
- Verdict rule posted to the strategy room at run start (7 days, 100 closed trades, beats Random/Hold SOL/Graduates after the luck check at 90% confidence, drawdown under 25%, profit factor over 1.2).
- `.env`: ARENA_ROUTE=pumpfun, ARENA_UNIVERSE=pumpfun, ARENA_TRADERS_RANK=realized, ARENA_SHADOW_LEADERS=10, ARENA_LLM_MIN_CHECK=1, ARENA_LLM_MAX_CHECK=60.
- Incident at launch: DexScreener's token endpoints returned an empty list for every token (verified for SOL and BONK, from this machine and via another IP). A GeckoTerminal price fallback (commits c33ae8d, 253a2a2) was added and the arena restarted onto it at 13:56 local; the first tokens were priced two ticks later.
- Copy backtest (reports/copy_backtest.md): no copy edge measurable; Shadow runs anyway per the spec.
