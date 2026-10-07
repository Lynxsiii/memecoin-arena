# Economics and Lifecycle of Solana Memecoins on pump.fun (2024–2026)

Scope note: Solana / pump.fun focus. "Today" = October 2026. Older data is dated inline. Where a number came only from a search-engine summary of a page I could not fetch, it is marked "(search summary, unverified)".

## KQ1. How do pump.fun's bonding curve, fees and graduation/migration work today?

### Takeaway
A pump.fun coin is free to create, trades on a constant-product bonding curve with a 1.25% fee (0.95% protocol + 0.30% creator) until roughly 85 SOL of net buying (~$69k market cap, ~412–420 SOL) fills the curve, then migrates for 0.015 SOL to pump.fun's own AMM, PumpSwap (which replaced Raydium in March 2025), where fees are market-cap-tiered from 1.25% (tiny coins) down to 0.30% (≥98,240 SOL mcap) with the creator taking up to 0.95%. 2025–2026 brought Project Ascend dynamic creator fees (Sept 2025), Mayhem Mode (Nov 2025), multi-wallet creator fee sharing (Jan 2026), USDC pairs (May 2026), BOOST post-migration auto-buys (July 2026), and Holder Rewards replacing Cashback coins (Sept 2026).

### Cited Findings
- Official fee schedule: token creation "0 SOL / 0 USDC"; graduation to PumpSwap "0.015 SOL"; bonding curve "Creator fee 0.300%, Protocol fee 0.95%, LP fee 0%, Total fee 1.25%" — [pump.fun docs: fees](https://pump.fun/docs/fees)
- PumpSwap canonical-pool fees are tiered by market cap (SOL-denominated): 0–420 SOL mcap: 1.25% total (creator 0.30%, protocol 0.93%, LP 0.02%); 420–1,470 SOL: 1.20% (creator 0.95%, protocol 0.05%, LP 0.20%); ≥98,240 SOL: 0.30% (creator 0.05%, protocol 0.05%, LP 0.20%). USDC-denominated tiers parallel these (0–59k USDC: 1.25%; 59k–100k: 1.20%; ≥$20M: 0.30%). Non-canonical PumpSwap pools: 0.30% (0% creator, 0.05% protocol, 0.25% LP). USDC token option effective May 21, 2026 — [pump.fun docs: fees](https://pump.fun/docs/fees)
- Full intermediate tier ladder (Project Ascend, "Dynamic Fees V1", liquidity fees live from Sept 2, 2025): creator 0.95% at 420–1,470 SOL; 0.90% at 1,470–2,460; 0.85% at 2,460–3,440; 0.80% at 3,440–4,420; 0.75% at 4,420–9,820; 0.70% at 9,820–14,740 … down to 0.05% above 98,240 SOL; before Ascend, creators earned only 0.05% per trade — [Smithii: Project Ascend](https://smithii.io/en/project-ascend-update/)
- Graduation threshold: "approximately 85 SOL raised and a market capitalization of about $69,000" — [Marino, Naviglio, Tarantelli, Lillo (arXiv 2602.14860, Feb 2026)](https://arxiv.org/html/2602.14860)
- The curve is constant-product; the issuance function is strictly increasing and concave, so the price path along the curve is deterministic, increasing and convex in cumulative net SOL deposited ("late entry is mechanically penalized") — [arXiv search summary of 2602.14860 / related papers](https://arxiv.org/abs/2602.14860)
- Migration venue: "Migration has been instant and free since PumpSwap replaced Raydium as the graduation venue in March 2025"; PumpSwap turns pump.fun into a full-stack venue controlling the whole token lifecycle — [Froglabs fee explainer](https://froglabs.io/blog/pump-fun-fees-explained) (search summary, unverified); [Madeonsol: What is PumpSwap](https://madeonsol.com/blog/what-is-pumpswap) (search summary)
- Conflicting secondary source: a May 2026 Madeonsol page still states a flat "1% fee on every buy and sell" on the curve going "entirely to the pump.fun protocol" and "0.25% fee" on PumpSwap — [Madeonsol fee page](https://madeonsol.com/blog/pumpfun-revenue-sharing-pumpswap-fees-creators). This contradicts the official docs and Smithii and appears stale (pre-Sept-2025 structure).
- Project Ascend results: first day under the new structure creators received $2 million (vs $198,000 the day before); individual claims up to $80,000; TROLL creator rewards $223,150; tier range 0.05%–0.95% with the top tier for tokens valued ~$88k–$300k — [CoinMarketCap Academy](https://coinmarketcap.com/academy/article/pumpfun-creators-earn-dollar2m-in-first-day-under-new-fee-structure)
- Jan 2026 creator-fee revamp (announced by co-founder Alon Cohen, Jan 16, 2026): teams can split fees across up to 10 wallets, transfer coin ownership, revoke update authority; Cohen said Dynamic Fees V1 "did not sufficiently influence average token deployer behavior"; launches that day neared 30,000 (highest since September 2025) — [crypto.news](https://crypto.news/pump-fun-revamps-creator-fees-as-solana-memecoin-launches-near-30000-daily/)
- Mayhem Mode (Nov 2025): opt-in; an autonomous AI agent may buy/sell a new coin in its first 24h; 1B extra tokens minted for the agent, unused burned after 24h; agent pays no protocol fees; launches went from 17,300/day to 17,800/day (+2.9%, "insignificant") and daily revenue declined — [The Block, Nov 18, 2025](https://www.theblock.co/post/379285/pump-funs-new-mayhem-mode-fails-boost-token-launches-revenue)
- BOOST (late July 2026): ~20% of migration capital that was previously "dead liquidity" locked in PumpSwap is now deployed as "automatic market buys during the first five minutes after migration, with every token acquired burned afterwards"; graduation threshold unchanged; graduation rate jumped from ~0.84% (June avg) / 2.5% (week before) to 6.7% on one day and 4.7% over four days — [The Block, July 29, 2026](https://www.theblock.co/amp/post/409815/pump-fun-token-graduation-rate-jumps-boost-changes-launch-incentives)
- Cashback Coins (early 2026): creators could permanently redirect all creator fees to traders instead of themselves — [crypto.news](https://crypto.news/pump-fun-flips-creator-fees-launches-trader-cashback/) (search summary)
- Holder Rewards (announced Sept 12, 2026) replaces Cashback for new launches: platform fees route to a dedicated wallet and are paid pro-rata to holders several times per hour in the pair's quote token; holders need ≥$20 of the token; switching is permanent — [Incrypted, Sept 14, 2026](https://incrypted.com/en/pump-fun-launches-holder-rewards-and-cancels-cashback/)
- April 2026 graduation mix by token type: standard 3,953 graduated; cashback tokens 1,811 (0.65% rate); Mayhem mode 746 (0.37% rate) — [PumpFunData, April 2026](https://pumpfundata.com/blog/pumpfun-graduation-rate-analysis)
- Buybacks: 50% of revenue to PUMP buybacks/burns via a one-year locked contract, 50% to operations; $370M of PUMP burned (36% of circulating supply) at the time of the change (~May 2026) — [CoinMarketCap Academy](https://coinmarketcap.com/academy/article/pumpfun-burns-dollar370m-in-pump-commits-50percent-of-revenue-to-buybacks)

### Inferences
- Because the first PumpSwap tier (0–420 SOL mcap) sits just below the graduation mcap (~412–420 SOL), any post-migration dump drops the coin into the highest-fee tier (1.25%). The fee burden is therefore maximal exactly where most volume happens (tiny coins), and lowest only for the rare coins that reach ~$20M.
- Using the well-known program constants (30 SOL virtual SOL reserve, 1.073B virtual token reserve, 1B supply; not independently sourced here), the starting mcap is ~28 SOL and the graduation mcap ~412 SOL, so a coin that graduates has risen ~14–15x along the curve from its first trade. This is the "ride" that is mechanically guaranteed for graduates and only for graduates.
- BOOST materially changes the post-graduation price path (five minutes of guaranteed buy pressure plus supply burn), which likely explains the 3–8x jump in graduation rates in late July–Sept 2026 and makes "snipe the migration" a more attractive bot strategy. Any paper-trading simulator calibrated on pre-July-2026 data will understate early post-migration upside.

### Gaps
- I could not fetch pump.fun's own changelog for the Raydium→PumpSwap date or the historical 6 SOL Raydium migration fee; the March 2025 date comes from secondary explainers.
- The exact BOOST mechanics (which 20%, whether it applies to all token types) are only described at the level of The Block's summary.

## KQ2. What share of launches graduate; how many launches per day; what share of graduates are alive after 1h / 1d / 1w?

### Takeaway
Launches ran ~17k–34k per day through 2025–2026 (record 71,735 on Jan 23, 2025; 18.67M lifetime by June 2026). Graduation rates oscillated between ~0.5% and ~2% (2.1% peak June 2024; 0.63% Sept 2025; 0.84% April 2026) until BOOST pushed them to ~3.5–6.7% from late July 2026. Roughly 69% of all tokens never trade again after launch day and only 4.55% trade past 90 days; among graduates, ~60% fall below 20% of their migration price within 20 minutes, and ~91% sit at ≤20% of migration price within 60 days.

### Cited Findings
Launch volume
- Lifetime: 18.67M tokens launched Jan 14, 2024–June 18, 2026 (~29 months), "21,000+ new tokens per day" — [CoinGecko study via Crypto Briefing, June 25, 2026](https://cryptobriefing.com/pump-fun-token-survival-rate-study/)
- Record day: 71,735 launches on Jan 23, 2025; 25,385 on Feb 26, 2025; 24,008 graduations in January 2025 and 11,532 in February 2025 — [The Block, Feb 26, 2025 (TradingView mirror)](https://ru.tradingview.com/news/the_block%3Af76fef498094b%3A0-pump-fun-sees-rapid-decline-in-graduating-tokens-as-memecoin-frenzy-fizzles-out)
- Q4 2024: peak 69,046 tokens minted in one day; pump.fun = up to 71.1% of all Solana token mints; ~7 new tokens/minute by Nov 2024; 2–4M daily transactions; 260k daily active users at Nov 2024 peak — [Mancino, arXiv 2512.11850 (Dec 2025)](https://arxiv.org/html/2512.11850v3)
- Sept 1–Oct 1, 2025: 655,770 tokens by 243,123 creator addresses (~21.9k/day); 2,600,790 distinct trader addresses — [Marino et al. (arXiv 2602.14860)](https://arxiv.org/html/2602.14860)
- Nov 2025: 17,300/day before Mayhem, 17,800/day after — [The Block](https://www.theblock.co/post/379285/pump-funs-new-mayhem-mode-fails-boost-token-launches-revenue)
- Jan 2026: nearly 30,000 in one day — [crypto.news](https://crypto.news/pump-fun-revamps-creator-fees-as-solana-memecoin-launches-near-30000-daily/)
- April 2026: 763,350 launches (~25,000/day) — [PumpFunData](https://pumpfundata.com/blog/pumpfun-graduation-rate-analysis)
- May 8–June 10, 2026: 832,941 launches in 34 days (~24.5k/day) — [Kamat, arXiv 2607.02823v3](https://arxiv.org/html/2607.02823v3)
- June 10, 2026: ~42,000 tokens launched on Solana in 24h; pump.fun 71–83% of Solana mints on high-volume days; 11.9M lifetime launches at that point (different counting basis than CoinGecko) — [Solana Compass](https://solanacompass.com/news/pumpfun-launched-42000-tokens-in-one-day-fewer-than-2-will-ever-reach-a-dex)
- Sept 22, 2026: 32,325+ launches, 7-day average 33,676/day; 1,081–1,181 graduations/day Sept 14–22 (MemeFees data) — [Memecoinist](https://memecoinist.com/pump-fun-token-graduation-rate-solana-traders/)

Graduation rate time series
- Peak 2.1% (June 2024); 1.6% (Jan 2025); 0.7% (early Feb 2025, "near all-time lows") — [The Block, Feb 2025](https://ru.tradingview.com/news/the_block%3Af76fef498094b%3A0-pump-fun-sees-rapid-decline-in-graduating-tokens-as-memecoin-frenzy-fizzles-out)
- Historical Dune rate ~1.4%; Solidus: 97,000 of ~7M tokens (1.4%) kept ≥$1,000 liquidity (Jan 2024–Mar 2025) — [CoinDesk, May 2025](https://www.coindesk.com/business/2025/05/07/98-of-tokens-on-pump-fun-have-been-rug-pulls-or-an-act-of-fraud-new-report-says)
- Two-year baseline (Jan 2024–Jan 2026, 15.25M coins): "1.02% of coins graduate" — [Szwajcok et al., "Meme Coin Factories", arXiv 2609.10246 (Sept 2026)](https://arxiv.org/html/2609.10246)
- Sept 2025: 0.63% (4,338 of 655,770) — [Marino et al.](https://arxiv.org/html/2602.14860)
- Late 2025 low: ~0.5% (~80 graduations/day); Feb 2026: 1.15%, 300+/day, a 7-month high — [Cryptopolitan, Feb 19, 2026](https://www.cryptopolitan.com/pump-fun-graduating-tokens-break-to-1-15-of-new-launches/)
- April 2026: 0.84% (6,379 of 763,350; daily range 0.7–1.4%) — [PumpFunData](https://pumpfundata.com/blog/pumpfun-graduation-rate-analysis)
- May–June 2026: 0.198–0.207% but only within a ~6-minute observation window (collector artifact; a lower bound) — [Kamat](https://arxiv.org/html/2607.02823v3)
- Late July 2026 post-BOOST: 6.7% (one day), 4.7% (4-day avg) vs ~0.84% June — [The Block](https://www.theblock.co/amp/post/409815/pump-fun-token-graduation-rate-jumps-boost-changes-launch-incentives)
- "1.71% across 693,331 launches (June–July 2026)" — [ScorpLabs blog](https://trader.scorplabs.online/blog/pump-fun-graduation-rate-dev-signal-12-percent) (low-authority source, unverified)

Time to graduate and who graduates
- Median time-to-graduation 4.4 minutes; median 457 swaps to graduate (Sept 2025) — [Marino et al.](https://arxiv.org/html/2602.14860)
- April 2026: median 9.8 min; 62% within 10 min; 85% within 1 hour; 182 tokens took >1 day (max 24.5 days); median buy volume to graduate 281 SOL (IQR 163–461) vs median sell volume 199 SOL — [PumpFunData](https://pumpfundata.com/blog/pumpfun-graduation-rate-analysis)
- ~24% of April 2026 graduations (1,513 of 6,379) were bot graduations: bonded in <60 s with a median of 6 unique buyers and 8 trades, vs median 312 buyers / 853 trades for organic graduates — [PumpFunData](https://pumpfundata.com/blog/pumpfun-graduation-rate-analysis)
- Telegram link present: 1.485% graduation vs 0.166% without (8.94x lift; Cox HR 5.40) within the fast window; top-quartile initial mcap (>30 SOL): 0.634% — [Kamat](https://arxiv.org/html/2607.02823v3)
- Original coins graduate at 9.20% vs copycats 0.86%; wash-traded coins 2.0% vs 0.90%; top 0.1% of community groups reach 14% graduation — [Meme Coin Factories](https://arxiv.org/html/2609.10246)
- 34 "elite deployers" with 71% bonding rates vs 1–2% overall — [CoinStats/MadeOnSol KOL data](https://coinstats.app/news/07f38ebd47e8d820af3eb96b00c42a84b9b856c602626e3e4a71afbbd79014d6_KOL-Wallet-Tracking-on-Solana-What-the-Data-Actually-Shows-After-16-Million-Trades/)

Survival / death
- 68.67% (~12.8M) of all tokens recorded their final trade on the calendar day they were created; only 4.55% (~850k) remained active beyond 90 days — [CoinGecko via Crypto Briefing](https://cryptobriefing.com/pump-fun-token-survival-rate-study/)
- Older (2024, ~970k tokens, 3 months): 10,417 launched vs 9,912 defunct per day; 15% dead within day 1; 31% within a week; 98% within 3 months; average lifespan 12 days (defunct = 24h volume <10% of ATH 24h volume) — [ChainPlay](https://chainplay.gg/blog/lifespan-pump-fun-memecoins-analysis/)
- Post-migration (41,470 tokens, Dec 1, 2024–Mar 1, 2025): within 20 minutes after migration, 60.26% fell below 20% of migration price, a further 12.70% to 20–40%; "more than 73% of memecoins experience a price drop to below 40% of their migration price"; 84.13% labelled high-risk, 11.34% medium, 4.53% low-risk (min price ratio ≥0.7) — [Hu et al., MemeTrans, arXiv 2602.13480 (Feb 2026)](https://arxiv.org/html/2602.13480v1)
- 2,891 migrations over 60 days (2026): only 6.2% above migration price at latest reading; 91% at ≤20% of migration price (Belphor dataset) — [Memecoinist](https://memecoinist.com/pump-fun-token-graduation-rate-solana-traders/)
- "95%+ of pump.fun tokens that graduate are dead within 30 days"; "most lose 80% of their value within 72 hours of graduation" — [StakePoint, Oct 2026](https://stakepoint.app/blog/what-to-do-after-pump-fun-token-graduates-checklist) (unsourced marketing blog)
- "Four out of five graduated tokens are effectively dead within 24 hours"; "only 19.7% of all graduates still had $5k of liquidity 24 hours later" — Blofin academy page (search summary; page returned 403, unverified)
- Cryptopolitan: "very few trade for more than a month," many conclude trading "within a day" — [Cryptopolitan](https://www.cryptopolitan.com/pump-fun-graduating-tokens-break-to-1-15-of-new-launches/)
- Solidus Labs: 98.6% of ~7M tokens classed as rug/pump-and-dump (criterion: failed to keep ≥$1k liquidity); 93% of 388k Raydium pools (361k) showed soft-rug patterns; median rug $2,832, largest $1.9M; pump.fun called the report a misunderstanding of memecoins — [CoinDesk](https://www.coindesk.com/business/2025/05/07/98-of-tokens-on-pump-fun-have-been-rug-pulls-or-an-act-of-fraud-new-report-says)

### Inferences
- Derived Sept 2026 graduation rate: ~1,100–1,200 graduations/day on ~32–34k launches ≈ 3.3–3.7%, consistent with a sustained post-BOOST uplift vs the ~1% two-year baseline.
- A clean "alive at 1h / 1d / 1w after graduation" series does not exist in the sources. Triangulating: MemeTrans's 20-minute window (60% below 0.2x migration price) plus Belphor's 60-day reading (91% ≤0.2x, 6.2% above migration) implies the share of graduates still "tradably alive" is on the order of 25–40% at 1 hour, ~10–20% at 1 day (if the unverified Blofin 19.7%-liquidity figure is right), and single digits at 1 week.
- Because 24% of April 2026 graduations were bot-only (6 buyers), roughly a quarter of "graduations" are not organic events a paper-trader can expect to find real counterparties in.
- The "98.6% rug" headline and the "~1.4% graduation" statistic are the same fact seen two ways (liquidity retention), not independent evidence of fraud.

### Gaps
- No source gives a time-resolved survival curve for graduated tokens at exactly 1h / 24h / 7d; the Blofin figures could not be verified.
- Dune dashboards (@adam_tehc, Hashed, @jhackworth) are cited by media but I could not read them directly.

## KQ3. Shape of the typical price path; is "every coin goes to 0 but most ride first" right?

### Takeaway
The data support "almost every coin goes to zero" but reject "most ride for some time first": ~69% of launches never trade again after day one, ~99% never complete the curve, and among graduates the typical ride is minutes long (median 4–10 minutes to graduate; 60% below 0.2x migration price within 20 minutes; median holder hold time ~100 seconds). A tradable run-up exists mainly for the ~1–5% that graduate and the small subset that attracts organic buyers; for those, early entrants capture a median +62% while chasers lose −18% at 24h and the median retrace is 60% within 72h.

### Cited Findings
- Median hold time of a Solana memecoin position ≈100 seconds, down from ≈300 seconds a year earlier (Galaxy Research, 2025) — [Cointelegraph via TradingView](https://www.tradingview.com/news/cointelegraph:fbf71a3df094b:0-memecoins-attract-users-but-platforms-reap-the-profits-report)
- Bonding-curve stage: 92.22% of tokens with ≥30 trades exhibit at least one "dump event"; most tokens accumulate minimal liquidity with exponential drop-off at higher SOL thresholds — [Marino et al.](https://arxiv.org/html/2602.14860)
- Median buy volume to graduate 281 SOL against ~85 SOL net required (median sell volume 199 SOL) — [PumpFunData](https://pumpfundata.com/blog/pumpfun-graduation-rate-analysis)
- Post-migration: 60.26% of tokens hit <0.2x migration price within 20 minutes; only 4.53% keep ≥0.7x; high-risk tokens have first-10-buyer supply shares 17 pp higher and first-20-buyer shares 19 pp higher than low-risk ones; high-risk tokens have shorter curve durations and much larger per-buy sizes — [MemeTrans](https://arxiv.org/html/2602.13480v1)
- 60-day outcome: 6.2% of 2,891 migrations above migration price; 91% at ≤20% — [Belphor via Memecoinist](https://memecoinist.com/pump-fun-token-graduation-rate-solana-traders/)
- Pump anatomy (265 pump events with a ≥+100% day and ≥$150k volume, measured July 31, 2026): median time to peak 22 hours from pump-day start, 63% peak inside the pump day; median retrace from peak 60% by +72h; 15% fully reversed in 3 days; early followers (≤1h after smart-wallet entry) +62% median at 24h, +79.1% at 7d; pump chasers (buy at close) −18.2% at 24h, −28.9% at 72h; 65% of early entries profitable after 4% round-trip cost; 37% of pumped tokens had another +100% day within 30 days (median gap 3 days) — [Unhosted Research, Aug 7, 2026](https://www.unhosted.ai/research/memecoin-pump-anatomy)
- Sniper exit speed: 55%+ of snipes fully exited in <1 minute, 85% within 5 minutes, 11%+ within 15 seconds; 90%+ of sniper wallets sell in one or two swaps — [Pine Analytics via Gate Learn, Mar 2026](https://www.gate.com/learn/articles/exit-liquidity-machines/8739)
- Coordinated dumps: 4,402 conservative dump instances with median 7 sender addresses (max 312), ~33,393 SOL dumped — [Meme Coin Factories](https://arxiv.org/html/2609.10246)
- Non-launchpad memecoins (CoinMetrics, 2025): median ATH 17.2 days after first trade, a quarter within 1.6 days; median 370 days from peak to "death" (−95%); 81% of sampled memecoins fell ≥90% from peak; the analysis explicitly discounts launchpad tokens, so it overstates lifespans for pump.fun coins — [CoinMetrics State of the Network #384](https://coinmetrics.substack.com/p/state-of-the-network-issue-384) (search summary); [TokenPost](https://tokenpost.com/news/investing/27042) (search summary)
- Scale of the tail (Aug 2024, 1.8M tokens): 96 tokens ever exceeded $1M mcap (~5 per 100k), 18 exceeded $10M (~1 per 100k) — [Bitget / Dune data, Aug 19, 2024](https://www.bitget.com/news/detail/12560604161427)
- Pump.fun tokens' total FDV ≈ $4.8B across ~13M launches (Galaxy, 2025) — [Cointelegraph via TradingView](https://www.tradingview.com/news/cointelegraph:fbf71a3df094b:0-memecoins-attract-users-but-platforms-reap-the-profits-report)

### Inferences
- Typical path by cohort (synthesis): (a) ~69% of launches: 0–few trades, dead same day, no ride. (b) ~30%: some curve activity, stalls well below 85 SOL, dumps; 92% of anything with ≥30 trades gets dumped. (c) ~1–4% graduate: deterministic ~14x climb along the curve over a median 4–10 minutes (heavily churned: ~3x gross buys per net SOL), then a 20-minute post-migration window in which 60% lose ≥80%. (d) ~5–10% of graduates (≈0.05–0.4% of launches) hold above 0.2x for weeks; 6% end above migration price; a few per 100k reach $1M+.
- "Tradable run-up" share: roughly 1–5% of launches have a run-up you could in principle trade (the graduates), but the window is minutes and is contested by same-block snipers; the Unhosted figures (+62% early vs −18% chasing) show that run-ups are tradable only with early entry, and the median 60% retrace within 72h means holding beyond the pump day is usually wrong.
- The hypothesis is best restated as: "every coin eventually goes to ~0; a small minority ride at all, and for those the ride is measured in minutes to hours, with a long right tail (37% repeat pumps among already-pumped tokens) that justifies trailing-stop rather than time-based exits."

### Gaps
- No source reports a distribution of peak-multiple-after-graduation (e.g., median ATH/migration price) for an unselected cohort; MemeTrans reports only the minimum within 20 minutes and Unhosted conditions on tokens that already pumped.
- No source quantifies median time-to-ATH for graduates specifically (the 22-hour figure is for a selected pump cohort, not launchpad graduates in general).

## KQ4. Who reliably profits: platform, creators, snipers, bundlers, MEV, KOLs, bot apps?

### Takeaway
Reliable profit sits with fee collectors and fastest executors: pump.fun (~$1.22B cumulative revenue by Aug 2026), trading terminals (Axiom ~$740–760M cumulative fees by Aug–Oct 2026; Photon >$400M and BullX ~$200M by mid-2025), sandwich bots ($370–500M extracted over 16 months to May 2025; one bot netted $13.4M in 30 days), same-block/deployer-funded snipers (87% win rate, 15,000+ SOL/month), creators (~$87M cumulative fees, concentrated), and serial "factory" deployers. KOLs show 57–63% median win rates on tracked wallets with a small-buy/large-sell pattern; no reliable aggregate KOL PnL exists.

### Cited Findings
Platform (pump.fun)
- Cumulative revenue $1.222B; weekly $9.23M (week to Aug 4, 2026); 30-day $31.44M; annualized $455.5M; Q1 2026 $294.47M, Q2 $212.16M, Q3-to-date $90.08M (DefiLlama) — [CryptoTimes, Aug 4, 2026](https://www.cryptotimes.io/2026/08/04/pump-fun-hits-highest-weekly-revenue-since-march/)
- 2025 gross protocol revenue ~$971M; 2026 annualizing ~$320M — DefiLlama figures as reported in [search summary](https://defillama.com/protocol/pump.fun) (unverified; page returned 403)
- Peak daily revenue $15.4M (Jan 25, 2025); $1.1M/day by late Feb 2025; >3M SOL earned lifetime by Feb 2025; 2,433,286 SOL deposited to Kraken — [The Block, Feb 2025](https://ru.tradingview.com/news/the_block%3Af76fef498094b%3A0-pump-fun-sees-rapid-decline-in-graduating-tokens-as-memecoin-frenzy-fizzles-out)
- Peak revenue $4–6M/day in H2 Jan 2025; PUMP public sale raised $600M in July 2025 (sold out in 12 minutes) — [The Block, Aug 18, 2025](https://www.theblock.co/post/367266/solana-memecoin-launchpad-war-flips-again-as-pump-takes-top-spot-amid-letsbonk-collapse); Galaxy says $500M in under 12 minutes — [Cointelegraph/TradingView](https://www.tradingview.com/news/cointelegraph:fbf71a3df094b:0-memecoins-attract-users-but-platforms-reap-the-profits-report); Solana Compass says "approximately $1.3 billion at a $4 billion valuation" — [Solana Compass](https://solanacompass.com/news/pumpfun-launched-42000-tokens-in-one-day-fewer-than-2-will-ever-reach-a-dex) (conflicting; $500–600M is the widely reported sale size)
- ARR ≈ $390M; ~32.7% of revenue from non-launchpad products (PumpSwap, Padre); buybacks repurchased 27% of circulating supply in 8 months; PUMP down ~80% from ATH ($0.086 → ~$0.0019) — [IOSG via PANews](https://panews.io/articles/019d3ede-8458-772b-b3ea-c4c0649f90a0)
- >$664M combined revenue across bonding curve, PumpSwap and Padre at the time of the $370M burn; ~$150M YTD 2026 then — [CoinMarketCap Academy](https://coinmarketcap.com/academy/article/pumpfun-burns-dollar370m-in-pump-commits-50percent-of-revenue-to-buybacks)
- Launchpad competition: LetsBonk reached ~64% of launches (July 2025) with pump.fun at 24% (from >90%) — [The Block](https://www.theblock.co/post/363647/letsbonks-market-share-of-solana-meme-token-launchpad-grows-to-64) (search summary); by Aug 17, 2025 pump.fun was back at 90% of graduations and LetsBonk at 3% after "top 10 deployers (mostly bots)" moved back — [The Block](https://www.theblock.co/post/367266/solana-memecoin-launchpad-war-flips-again-as-pump-takes-top-spot-amid-letsbonk-collapse); 2026 Jupiter-dashboard snapshot: pump.fun 51%, LetsBonk 26.6%, BAGS 17.6% — [Bitget](https://www.bitget.com/news/detail/12560604901769)

Creators / deployers
- Cumulative creator fees ≈ $86.7M; Q1 2026 $25.85M, Q2 $10.86M, Q3 $19.97M, Q4-to-date $1.9M (DefiLlama income statement) — [search summary](https://defillama.com/protocol/pump.fun) (unverified)
- $2M paid to creators in the first 24h of Project Ascend vs $198k the day before — [CoinMarketCap Academy](https://coinmarketcap.com/academy/article/pumpfun-creators-earn-dollar2m-in-first-day-under-new-fee-structure)
- Creator concentration: top creator issued >2,000 tokens in one month; prolific creators' graduation ratios 0.023–0.084 — [Marino et al.](https://arxiv.org/html/2602.14860)
- Factories: 322,620 multi-address creator clusters; top 1% of clusters account for 52.99% of all coins; largest cluster 10,531 addresses; 23.5% of coins (3.57M) created right after social posts; 31 posts had extractable value ≥$1M, max $113.6M for one post; wash trading in 8.26% of coins (1.32% of volume) but 50.31% of volume for coins with >10k transactions; 14 GitHub repos advertise pump.fun comment bots; four "market-manipulation-as-a-service" sites — [Meme Coin Factories](https://arxiv.org/html/2609.10246)
- Top memecoin deployers launch "one new token every 3 minutes" (Conor Grogan) — [The Block](https://www.theblock.co/post/367266/solana-memecoin-launchpad-war-flips-again-as-pump-takes-top-spot-amid-letsbonk-collapse)
- Median rug extraction ≈$2,800 per token (Solidus) — [CoinDesk](https://www.coindesk.com/business/2025/05/07/98-of-tokens-on-pump-fun-have-been-rug-pulls-or-an-act-of-fraud-new-report-says)

Snipers / bundlers
- Deployer-funded same-block sniping (one month to Mar 2026): 15,000+ tokens (~1.75% of launches), 4,600+ sniper wallets, 10,400+ deployers, 15,000+ SOL realized net profit, 87% of snipes profitable, typical 1–100 SOL per wallet (outliers >500 SOL); >50% of tokens sniped in the creation block; activity concentrated 14:00–23:00 UTC — [Pine Analytics via Gate Learn](https://www.gate.com/learn/articles/exit-liquidity-machines/8739)
- Bundled accounts hold 36.5% of total supply across 41k tokens; Jito-bundle-identified bundlers = 10.39% of holders / 15.96% of holdings; fund-flow-linked bundlers 22.57% / 28.22%; bundling raises median top-10 concentration by +24 pp for high-risk tokens — [MemeTrans](https://arxiv.org/html/2602.13480v1)
- 24% of April 2026 graduations were bot-only — [PumpFunData](https://pumpfundata.com/blog/pumpfun-graduation-rate-analysis)

MEV / sandwich bots
- One sandwich program (Vpe/DeezNode): 1.55M sandwiches in 30 days (Dec 7, 2024–Jan 5, 2025), 88.9% success, 65,880 SOL ($13.43M) profit, ~$8.67 per attack, 22,760 SOL ($4.63M) in Jito tips; ~half of all Solana sandwiches; 16 of the top-20 sandwiched tokens were pump.fun tokens; 2024 Jito tips 3.75M SOL; 2024 arbitrage profits $142.8M across 90.4M trades — [Helius Solana MEV Report](https://www.helius.dev/blog/solana-mev-report)
- Sandwich extraction "$370 million to $500 million" over 16 months (to May 2025); sandwich bots tip validators only 15–20% (arb bots 50–60%); blind sandwiching rose from ~1% to 30% of attacks; some validators sandwich 30–60% of eligible trades — [Ghostlogs at Accelerate 2025 via Solana Compass](https://solanacompass.com/learn/accelerate-25/scale-or-die-at-accelerate-2025-the-state-of-solana-mev)
- 600–800 SOL/day extracted from pump.fun bonding-curve swaps; sandwiching dominated by ~6 bots (Jan 2025) — [Chris Chang on X](https://x.com/chrischang43/status/1880354695186653531) (search summary, unverified)
- B91 bot: 7,800 SOL gross / 6,900 SOL net in 30 days; 4,925 sandwiches on Apr 21, 2025 — [Medium case study](https://medium.com/@joel_28760/breaking-down-mev-sandwich-attacks-on-solana-the-b91-bot-case-study-3e1c1ba35556) (search summary)

Trading terminals / bot apps
- Axiom: $150M fees by July 7, 2025 ($1.75M that day), 72% of Solana bot volume, ~650k wallets, fee 0.75–1%; Photon >$400M lifetime (since Jan 2024) and BullX ~$200M (since Apr 2024) with volumes "dropped significantly from the highs" — [DL News, July 7, 2025](https://www.dlnews.com/articles/defi/solana-bot-axiom-takes-over-cursor-with-150m-revenue/)
- Axiom: $100M in 129 days, $200M in 202 days (Aug 4, 2025); daily revenue $740k–$4.2M; $238+ revenue per user; share 4.41% (Feb 2025) → 57.33% (July 2025); Photon $96.1M over the same 202 days with share falling from 30.7% to <10% — [Step Data, Aug 8, 2025](https://stepdata.substack.com/p/solana-trading-bot-axiom-becomes)
- Axiom cumulative fees $736.7M (Aug 14, 2026), ~$761M latest; >$1B monthly swaps — [DefiLlama Axiom](https://defillama.com/protocol/axiom) (search summary, unverified)
- Terminal fees on a $500 swap (Aug 2026): Axiom 1.00% (0.75% best), Photon 1.00% (0.90%), GMGN 1.00% (0.70%), Bloom 0.90%, Trojan 1.00% tiered, fomo wallet 0.50%; BullX "ceased trading June 2026"; plus PumpSwap 0.30–1.25%, priority fee + Jito tip (~0.001 SOL baseline), and unbounded slippage that "can exceed every other cost combined" on thin pools — [Axiompedia fee index](https://axiompedia.com/guides/fees/solana-terminal-fee-index)
- A claim that "Photon rebranded to Axiom in late 2025" appears in [MemeGateway](https://memegateway.com/bot/photon/) (search summary) but contradicts DL News and Step Data, which treat them as competitors; treat as unreliable.

KOLs
- 1,058 tracked KOL wallets, 1.6M trades (30 days, ~mid-2026): median win rate 57.1%, average 63.3%, top performers 70–75%; 495,720 buys vs 337,124 sells; avg buy 1.52 SOL vs avg sell 2.24 SOL; 9,404 coordination events (multiple KOLs buying the same token in a short window) — [CoinStats / MadeOnSol](https://coinstats.app/news/07f38ebd47e8d820af3eb96b00c42a84b9b856c602626e3e4a71afbbd79014d6_KOL-Wallet-Tracking-on-Solana-What-the-Data-Actually-Shows-After-16-Million-Trades/)
- KOL wallets ">80% win rate" vs ~55% for "smart money" — [Phemex](https://phemex.com/news/article/kol-wallets-outperform-smart-money-in-solana-meme-coin-market-22202) (search summary; sample undefined)
- KOL promotion pricing "hundreds to five figures" per promo (qualitative) — [Hoge.gg](https://hoge.gg/rug-pull-economy-2026-who-gets-paid/) (unsourced)

### Inferences
- Order-of-magnitude fee take 2024–mid-2026 (from the figures above): pump.fun ~$1.2B + Axiom ~$0.75B + Photon ~$0.4B + BullX ~$0.2B + other terminals + sandwich bots ~$0.4–0.5B (to May 2025) + Jito tips (3.75M SOL in 2024 alone) ≈ $3B+ extracted from memecoin order flow, before priority fees and slippage. This is the "house edge" a paper-trading agent must beat.
- The KOL buy/sell asymmetry (many small buys, fewer larger sells, 1.5:1) is consistent with a strategy of spraying entries and selling only winners, i.e., realized win rates overstate expectancy; the unsold losers are the hidden cost.
- Reliable edges in the data are structural, not predictive: fee collection, being in the creation block (deployer-funded), bundling supply before retail arrives, and sandwiching high-slippage retail. Everything else is a thin-margin race.

### Gaps
- No credible aggregate PnL for KOLs as a class (promo income + trading); tracked-wallet dashboards are self-selected.
- No 2026 update for sandwich-bot totals after Jito's blacklist (epoch 789) and "don't front" sentinel.
- Creator fee cumulative ($86.7M) and Axiom cumulative fees come from search summaries of DefiLlama; I could not open DefiLlama directly.

## KQ5. Who loses, and is the game zero-sum or negative-sum?

### Takeaway
Retail traders lose: in a 90-day window to Aug 2026, 93.75% of 304,161 active Solana memecoin wallets lost money (median loss $120, aggregate net −$1.26B); in Aug 2024 only 3.06% of 2.43M pump.fun users had ever netted >$1,000. The game is strongly negative-sum for traders: every round trip pays ~2.5% to pump.fun on the curve (0.6–2.5% on PumpSwap), ~1.5–2% to a terminal, plus priority/Jito tips and slippage, and the counterparties with structural advantages (deployers, snipers, bundlers, sandwichers) skim the rest.

### Cited Findings
- 304,161 active wallets, 90 days to Aug 20, 2026: 6.25% (19,003) profitable; median loss $120; aggregate loss ≈$1.26B; among winners 88% made <$100 and only 25 wallets made >$10,000 (on-chain/Fomo data) — [Cointribune, Aug 20, 2026](https://www.cointribune.com/en/crypto-solana-memecoins-trap-nearly-94-of-traders)
- Aug 2024 (Dune: Hashed, @evelyn233, @jhackworth; Lookonchain): 2.43M users; >$1,000 profit: 3.061% (76,587); >$10k: 0.477% (11,936); >$100k: 0.037% (924); >$1M: 0.0028% (70); >$10M: 6 users; 50–70k daily active users — [Bitget, Aug 19, 2024](https://www.bitget.com/news/detail/12560604161427)
- Pump.fun recovery research (May 2026): ~2.05M wallets (65.1% of the profitable group) earned $1–$500 in April 2026 and 87,000 (2.8%) earned $500–$1,000 — [Crowdfund Insider](https://www.crowdfundinsider.com/2026/05/277755-solana-based-meme-coins-trading-platform-pump-fun-makes-recovery-research/) (search summary; page returned 403)
- Manipulation victims (Oct 2024–Jan 2025, multi-chain, 4,140 pump.fun tokens identified): pump-and-dump realized losses $3.27M across 5,783 addresses; rug-pull losses $6.04M across 11,368 addresses; 82.8% of tokens with >100% returns showed artificial-growth strategies — [Mongardini & Mei, arXiv 2507.01963v2](https://arxiv.org/html/2507.01963v2)
- Merkle Science: ~$500M memecoin-related losses in 2024 — [CoinDesk](https://www.coindesk.com/business/2025/05/07/98-of-tokens-on-pump-fun-have-been-rug-pulls-or-an-act-of-fraud-new-report-says)
- Chainalysis: ~$17B stolen in scams/fraud in 2025, >$2.8B attributable to rug pulls (not Solana-specific) — [DeepStrike summary](https://deepstrike.io/blog/rug-pull-statistics) (search summary)
- Galaxy: "infrastructure providers such as launchpads, decentralized exchanges and trading bots capture millions in revenue" while most traders lose in a market with ~100-second median holds — [Cointelegraph via TradingView](https://www.tradingview.com/news/cointelegraph:fbf71a3df094b:0-memecoins-attract-users-but-platforms-reap-the-profits-report)
- Fee stack per trade: pump.fun 1.25% on curve; PumpSwap 0.30–1.25%; terminal 0.5–1%; priority + Jito tip; slippage — [pump.fun docs](https://pump.fun/docs/fees); [Axiompedia](https://axiompedia.com/guides/fees/solana-terminal-fee-index)
- Unhosted assumed a 4% round-trip cost and still found 65% of early entries profitable but chasers at −18% — [Unhosted](https://www.unhosted.ai/research/memecoin-pump-anatomy)
- Sandwich victims are "memecoin traders using high slippage tolerances," mostly on Raydium-era pools; 16/20 most-sandwiched tokens were pump.fun coins — [Helius](https://www.helius.dev/blog/solana-mev-report)
- Early-buyer advantage in high-risk tokens: first 10 buyers hold 17 pp more supply than in low-risk tokens — [MemeTrans](https://arxiv.org/html/2602.13480v1)

### Inferences
- Round-trip cost model for a paper-trading agent (bonding curve, via a terminal): 2 × (1.25% + ~1.0%) ≈ 4.5% + tips (0.001–0.01 SOL/trade) + slippage (often several % on sub-$20k pools). On PumpSwap for a coin that has dumped below ~420 SOL mcap the AMM leg is still 1.25%, so ~4.5% again; only for coins above ~$20M does it fall to ~2.6%. With median holds of ~100 seconds and tiny moves, fee drag alone explains most of the 94% loser rate.
- Zero-sum vs negative-sum: trader-vs-trader PnL is zero-sum before costs; after the ~$3B+ in fees/MEV documented above and creator/deployer extraction, the trader pool is clearly negative-sum. The aggregate −$1.26B over 90 days (304k wallets) vs pump.fun's ~$31M/30d revenue and Axiom-scale terminal fees indicates most trader losses are transfers to other traders (deployers/snipers/bundlers) rather than to fee collectors alone.
- Implication for the arena: an agent that is not in the creation block, cannot bundle, and pays terminal fees is structurally in the losing cohort unless it (a) trades only the small subset of organic graduates with real holder counts, (b) enters within the first minutes of a move rather than chasing closes, and (c) exits on retrace rather than time, consistent with the Unhosted early-vs-chaser split.

### Gaps
- The "94% lose" dataset's methodology (wallet selection, PnL definition, whether unrealized positions count) is not published; the 304k-wallet universe likely excludes pure bots.
- No source decomposes trader losses into fees vs transfers to insiders vs sandwich extraction for the same period; the split above is inferred.
- No dedicated academic treatment of zero-/negative-sum accounting for pump.fun found; the arXiv papers measure manipulation prevalence, not aggregate welfare.
