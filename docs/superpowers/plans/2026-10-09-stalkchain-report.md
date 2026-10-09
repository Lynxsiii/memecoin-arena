# StalkChain Data integration (2026-10-09)

StalkChain is now wired in but stays **off until you add a key**. With no `ARENA_STALKCHAIN_KEY`, nothing calls the network and the Claudes' brief is the same as before. The mock market and replays never call it, even with a key set.

## What it does
- **Pre-buy check.** The check runs inside `Arena.validate`, only for Claude buys, and only after every other rule has passed, so a refused buy costs no credits. The first time a Claude buys a coin, the arena looks up who deployed it (`stalkchain_token_deployer`, 500 credits) and who its early buyers were (`stalkchain_token_early_buyers`, 500 credits).
  - **Veto:** the buy is refused when the deployer has `rugged >= ARENA_STALKCHAIN_RUG_VETO` (default 2) earlier launches, or a rug rate of 50% or more across at least 2 launches. The Claude sees the refusal in `recent_failures`, for example "your buy of SYM ($60) was refused: StalkChain says the deployer rugged 3 of 4 earlier launches". The coin is also added to `arena.vetoes`, so it leaves the lanes.
  - **Flags (not vetoes):** 40% or more of supply sniped, a bundled launch, 80% or more of early buyers already sold, or 70% or more wash volume (only when `quality` is turned on).
  - **What the Claudes see:** the verdict appears as `structure[mint].stalkchain` on later looks, and it survives the 60-second signal refresh.
  - **Caching:** a verdict is reused for `ARENA_STALKCHAIN_CACHE_H` hours. A veto never expires.
  - **Failures never block a buy:** a timeout, an error, an exhausted budget or no paid plan all let the buy through.
  - **Tick time:** the lookups run synchronously with a 4-second timeout each, so a new coin can add up to about 8 seconds to a tick. After an error, paid calls back off for 60 seconds.
- **Smart-money entries.** Every `ARENA_STALKCHAIN_ENTRIES_MIN` minutes, the arena makes one `stalkchain_fomo_multi_trader_entries` call (windowMinutes=60, minTraders=3, side=buy, chain=solana, limit=20; 125 credits).
  - The results reach the Claudes as `smart_entries`: token, symbol, number of traders, and minutes since the first and last entry, newest first.
  - Coins the arena doesn't track yet are force-tracked with source `copy`. `track()` only accepts pump.fun mints.
- **Brief.** It gains a `smart_entries` bullet and a Playbook line on `structure.stalkchain` ("a deployer rug history is a hard no, sniping or bundling is a flag"). Both appear only when a key is set.
- **`/api/summary`.** It gains `stalkchain: {calls, credits, cached, skipped, errors, balance, credits_24h, paywalled}`.

## Lines to add to `.env`
Create a key in the StalkChain dashboard (https://data.stalkchain.com). Without a paid plan, paid calls return 402 and the arena logs it once, then carries on unchanged.

```
ARENA_STALKCHAIN_KEY=sc_your_key_here
ARENA_STALKCHAIN_CACHE_H=6
ARENA_STALKCHAIN_DAILY_CREDITS=12000
ARENA_STALKCHAIN_PREBUY=deployer,early_buyers
ARENA_STALKCHAIN_RUG_VETO=2
ARENA_STALKCHAIN_ENTRIES_MIN=30
```
Only the key is required; the other five lines are the defaults. After adding them, restart the arena. Startup prints `[main] StalkChain on: ...`.

## Credit math
- One new coin checked = deployer (500) + early_buyers (500) = **1,000 credits**. Adding `quality` makes it 1,250.
- Entries polled every 30 minutes = 48 × 125 = **6,000 credits a day**.
- **Starter:** 375,000 credits a month, about 12,500 a day, so the 12,000 budget fits.
  - With entries **off** (`ENTRIES_MIN=0`), the budget covers about **12 new coins a day**.
  - With entries every 30 minutes, about **6 new coins a day**.
  - With entries every 120 minutes (1,500 a day), about **10 new coins a day**.
- **Growth:** 1,250,000 credits a month, about 41,000 a day. Set `ARENA_STALKCHAIN_DAILY_CREDITS=40000`. That covers about 40 new coins a day with entries off, or about 34 with entries every 30 minutes.
- The budget is a rolling 24 hours. Once it runs out, lookups are skipped (counted in `skipped`) and buys go through unchecked.

## Caveats
- The OpenAPI spec doesn't describe the response fields (it only says `{ data, notes?, credits, meta }`), so the parsers guess field names from the tool descriptions and read them defensively.
  - **Deployer:** a prior launch counts as rugged when it is marked rugged/dead, or when it never graduated and sits under a $6k market cap or $1k liquidity.
  - **Quality:** wash share assumes Jupiter-style `stats24h` buy/sell (organic) volume fields.
  - **Check before trusting the vetoes:** after the first real calls, compare a few responses against `summarize_*`. If the real field names differ, the deployer summary may come back as None. That means no veto, not a false veto.
- Verdicts live in memory only, so a restart re-checks coins (the client cache is in memory too).
