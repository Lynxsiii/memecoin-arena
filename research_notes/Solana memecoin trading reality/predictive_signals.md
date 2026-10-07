# Predictive Signals for Solana Memecoin Returns (2024–2026)

Scope note: this covers published evidence (arXiv/IMC papers, analytics-firm reports, Dune-derived summaries) and practitioner write-ups on which measurable signals predict Solana memecoin outcomes, with an emphasis on pump.fun-launched tokens. Each finding is tagged by evidence type where it matters: **[measured]** (data + stated method), **[vendor]** (data claim from a company selling a related tool), **[anecdote]** (no method/sample given). Research date: 2026-10-06.

Base rates that everything below sits on top of:
- Graduation (bonding curve completes, token migrates to an AMM pool) is rare and has fallen over time: "fewer than 2%" in Q4 2024 — [Memecoin Phenomenon, arXiv 2512.11850](https://arxiv.org/html/2512.11850v3); 0.63% (4,338 of 655,770 launches, Sep 1–Oct 1 2025) — [Predicting the success of new crypto-tokens, arXiv 2602.14860](https://arxiv.org/html/2602.14860); 0.198% pooled (1,651 of 832,941 launches, May 8–Jun 10 2026, but with a ~6-minute collector visibility window so this is a lower bound) — [Graduation Regime Windows, arXiv 2607.02823v3](https://arxiv.org/html/2607.02823v3); 1.71% (11,877 of 693,331, Jun 23–Jul 19 2026) — [scorplabs](https://trader.scorplabs.online/blog/pump-fun-graduation-rate-dev-signal-12-percent) [vendor]. Weekly graduation fell below 1% for four consecutive weeks from Feb 17 2025 for the first time; best week was 1.67% in Nov 2024 — [Cointelegraph via TradingView](https://www.tradingview.com/news/cointelegraph:56f07a8fa094b:0-pump-fun-memecoins-are-dying-at-record-rates-less-than-1-survive/).
- Of 7M+ pump.fun tokens with ≥5 trades (Jan 2024–Mar 2025), only ~97,000 kept >$1,000 liquidity; 98.6% collapsed; ~93% of 388,000 Raydium pools showed soft-rug characteristics — [Solidus Labs](https://www.soliduslabs.com/reports/solana-rug-pulls-pump-dumps-crypto-compliance).
- Trader outcomes: as of Aug 2024 only ~3% of pump.fun wallets (76,587) had >$1,000 profit, 0.477% had >$10,000, 70 wallets had >$1M (Dune dashboards by @evelyn233, @jhackworth, @adam_tehc) — [ChainCatcher](https://www.chaincatcher.com/en/article/2139008). In March 2026, ~49–50.6% of pump.fun trading wallets lost money and ~45% made <$500, i.e. ~96% lost or made <$500 (Dune) — [CoinMarketCap](https://coinmarketcap.com/top-stories/69cac98635bc806ad6e55590/).

---

## KQ1. What do studies/backtests show for each candidate entry signal?

### Takeaway
The signals with the best *measured* support are structural/on-chain ones observable in the first minutes: few-swaps-to-reach-a-given-curve-level (trading intensity), low bot-trade share, early-holder concentration and bundle share (negative), creator history, and market cap/liquidity at entry. Social-link presence shows huge in-sample hazard ratios but failed a pre-registered two-week temporal holdout (AUROC 0.86 → 0.46), KOL mentions are on average a sell signal, time-of-day is not statistically supported, and "unique buyers" is contaminated by coordinated sniper rings. No study shows any entry signal pushing expected return above breakeven across the whole curve; the best-supported signals mostly help you *avoid* rugs rather than *find* runners.

### Cited Findings

**Holder distribution (top-10 share, dev holdings, bundled supply)**
- In 41,470 migrated memecoins (Dec 1 2024–Mar 1 2025; 218.5M transactions), the first 10 buyers of high-risk tokens held 17 percentage points more of supply than in low-risk tokens, the first 20 buyers held 19 pp more; 36.5% of token supply was held by bundled (multi-address coordinated) accounts; 98.7% of developers bought in the same transaction as minting. 84.13% of migrated tokens were labeled high-risk. Feature-ablation importance: market activity (tx count, participation) > bundle statistics > holding concentration > launch timing — [MemeTrans, arXiv 2602.13480](https://arxiv.org/html/2602.13480v1) [measured].
- Among 707 tokens (4 chains, Solana = 33.8% of the 31,811-token dataset) that returned >100% over three months, 54.46% showed concentrated holdings with top-10 holders controlling an average 77.85% (median 87.01%); bundle buys were present in 18.81%; 82.6% of the high-return tokens showed artificial-growth tactics. Only 17.4% of high performers had no manipulation indicator — [A Midsummer Meme's Dream, arXiv 2507.01963](https://arxiv.org/html/2507.01963v1) [measured]. Note: this is a Dexscreener-style cross-chain sample of older tokens, not a pump.fun launch sample.
- Solidus Labs' detection flags: concentrated holder distributions, unlocked liquidity, and a 90% liquidity-withdrawal threshold; median rug pull drained ~$2,832, 25% drained <$732, largest $1.9M — [Solidus Labs](https://www.soliduslabs.com/reports/solana-rug-pulls-pump-dumps-crypto-compliance) [measured].
- Practitioner heuristics (no sample/method): bundled launch where a wallet spends 10 SOL at block zero owns ~26.6% of supply; red flags are 15%+ in one or two wallets and clusters funded from one source buying simultaneously — [BloFin Academy](https://blofin.com/en/academy/education/pumpfun/pump-fun-bundling-explained) [anecdote]. Because the bonding curve is deterministic, bundled supply is computable before the first candle — [scorplabs bundle detection](https://trader.scorplabs.online/blog/pump-fun-bundle-detection) [vendor].

**Creator/dev history**
- A reverse-engineered leading sniper bot ("orcACR", mid-2024, buying ~20% of new launches and earning an estimated 100–200 SOL/day) *never* bought when: the creator had launched previous coins; the creator was funded by prior coin creators; or the creator's initial buy exceeded 4.0 SOL. It exited immediately if the creator sold and used ~20-second "copy-block" holds. The author backtested with a 14% slippage haircut but published only visual PnL output, no win-rate numbers — [mikem.codes Part 1](https://www.mikem.codes/if-you-aint-first-youre-last-2/), code at [github.com/1fge/pump-fun-blog-part-1](https://github.com/1fge/pump-fun-blog-part-1) [measured but unreported numbers].
- Tokens from the top-10 most prolific creators (50+ launches) showed conditional graduation probability that "even exceeds the economic breakeven curve" near the top of the curve, but the authors say statistical support is limited — [arXiv 2602.14860](https://arxiv.org/html/2602.14860) [measured].
- "Dev previously graduated a token AND has been quiet ≥7 days" → 98/816 = 12.01% graduation (95% CI 10.0–14.4%) vs 1.71% baseline (7x lift); a 77-position live probe hit 5/77 = 6.5%. The author says "dozens of features" (volume score, holders, socials, wallet clusters) were "noise". No code or data released — [scorplabs](https://trader.scorplabs.online/blog/pump-fun-graduation-rate-dev-signal-12-percent) [vendor].
- Serial deployers: "just 18% of unique creators were responsible for 82% of total liquidity drained" — reported in [Solidus Labs](https://www.soliduslabs.com/reports/solana-rug-pulls-pump-dumps-crypto-compliance) coverage, though the fetched report page itself did not show the percentage; treat as secondary.

**Liquidity and market cap at entry**
- Cox model on 832,941 launches: log market cap hazard ratio 4.51 (95% CI 4.29–4.73) for graduation; top initial-market-cap quartile graduated at 0.634% vs 0.198% pooled — [arXiv 2607.02823v3](https://arxiv.org/html/2607.02823v3) [measured, but see temporal-holdout failure below].
- The unconditional graduation probability as a function of virtual SOL in the curve lies *below* the naive buy-and-hold breakeven curve p(vSol) = vSol²/115² over most of the range: buying higher up the curve raises your graduation odds but not enough to pay for the worse price — [arXiv 2602.14860](https://arxiv.org/html/2602.14860) [measured].
- On a constant-product pool, price impact ≈ 2 × (trade size ÷ pool liquidity); most 2026 launches have pools "measured in thousands of dollars", so at that depth "your own order... determines your price" — [scorplabs slippage post](https://trader.scorplabs.online/blog/solana-memecoin-slippage-explained) [vendor; the formula is standard AMM math].

**Volume and buy/sell flow**
- Trading intensity was the strongest predictor of graduation: tokens that reached a given vSol level with <10 swaps had substantially higher graduation probability than those needing 100–1,000+ swaps. Bot-trade share also mattered: ≥70% non-bot trades (frontend vs direct contract calls) raised graduation probability; >70% bot share lowered it systematically beyond intermediate vSol. Identification was done on the first two weeks of September 2025 and tested on the second two weeks — [arXiv 2602.14860](https://arxiv.org/html/2602.14860) [measured, temporal OOS].
- A 23-feature set from the first 5 minutes (buy/sell counts and ratios, unique buyers/sellers, SOL in/out, price volatility, first-to-3-blocks price change, first-buy/sell timing) predicts rug-by-1-hour with XGBoost F1 0.78 / MCC 0.36 / AUC-PR 0.76 on pump.fun (rolling 3-month temporal CV; last window held out). Pump.fun tokens had a median of just 12 transactions in the first 5 minutes — [Catching the Rug, arXiv 2608.20271](https://arxiv.org/abs/2608.20271) [measured, temporal OOS].

**Number of unique buyers**
- Coordinated sniper cohorts: 1,012 persistent wallet rings (2–12 wallets each, 2,965 addresses) across 166,098 launches (Jun 11–25 2026). Propensity-matched on 5,419 launch pairs, coordinated wallets lifted first-30-minute *buyer counts* by +16.1% (95% CI +13.0 to +19.4%) but lifted *SOL inflow* by only +6.3% (CI −0.5 to +15.1%, not distinguishable from zero); naive comparison showed +130.9%. 7.0% of treated launches had zero non-cohort buyers in the first 30 minutes. **The paper carries a correction notice: "buyer records include sells and miss many buys; all numerical results... are withdrawn pending a corrected analysis."** Cohort catalogue and code released (RED-COHORT-2026-v1, CC-BY-4.0) — [arXiv 2607.02795](https://arxiv.org/abs/2607.02795) [measured; withdrawn].
- MemeTrans: high-risk tokens had "fewer transactions and buyers but larger per-buyer accumulations" pre-migration — [arXiv 2602.13480](https://arxiv.org/html/2602.13480v1) [measured].

**Token age**
- "A vast majority of these memecoins exhibit rug pull characteristics within one hour of launch" (6.4M tokens, Nov 2024–Jun 2025) — [arXiv 2608.20271](https://arxiv.org/abs/2608.20271) [measured].
- Median time from creation to graduation ≈ 4.4 minutes (Sep 2025) — [arXiv 2602.14860](https://arxiv.org/html/2602.14860); 1.66 minutes median, 90th pct 2.80 min, max 5.98 min in the 2026 sample, but that collector only saw ~6 minutes per token so this is an artifact of the window — [arXiv 2607.02823v3](https://arxiv.org/html/2607.02823v3).
- 60.26% of migrated memecoins fell below 20% of their migration price within 20 minutes; 73.44% fell below 40% — [MemeTrans](https://arxiv.org/html/2602.13480v1) [measured].
- "About 69% of memecoins launched on Solana-based Pump.fun stop trading on launch day" (18.67M tokens) — reported by [Cryptorank](https://cryptorank.io/news/feed/a4c19-pumpfun-memecoin-failure-rate-launch-day); the page could not be fetched (403), so the sample/author are unverified.
- For the ~150 memecoins large enough to list on a CEX (Solana era, Dec 2023+): median time to all-time high 17.2 days after first trade, 25% peaked within 1.6 days; 81% later fell ≥90% from ATH and only 5 of 151 (3.3%) ever regained it. Coin Metrics notes this universe "systemically overestimates the lifespan" of typical launchpad tokens — [Coin Metrics SOTN #384](https://coinmetrics.substack.com/p/state-of-the-network-issue-384) [measured].

**Graduation / migration from the bonding curve**
- Graduation requires the curve's total reserve to reach 115 SOL (~85 SOL real deposits + 30 SOL virtual); graduates are "on the order of 10x+" from birth price by construction — [arXiv 2602.14860](https://arxiv.org/html/2602.14860), [scorplabs](https://trader.scorplabs.online/blog/pump-fun-graduation-rate-dev-signal-12-percent).
- "Selling strictly before graduation is more profitable than selling immediately after graduation" because the curve's virtual liquidity is deeper than the fresh AMM pool, so pre-graduation dumps are incentivized; 92.22% of tokens with ≥30 swaps show at least one statistically significant negative price shock (4σ MAD rule) — [arXiv 2602.14860](https://arxiv.org/html/2602.14860) [measured].
- Graduation labels themselves are noisy: an off-chain collector's "TIMEOUT" label "does not establish platform-side non-graduation"; an attempted correction using high final market cap was withdrawn after API verification of 100 sampled tokens found none had graduated despite high virtual reserves — [arXiv 2607.02823v4 (audit)](https://arxiv.org/pdf/2607.02823), [v3](https://arxiv.org/html/2607.02823v3) [measured].

**Social signals (X/Telegram/website links, KOL attention)**
- In-sample (May–Jun 2026, n=832,941): Telegram link hazard ratio 5.40 (CI 4.73–6.17), Twitter 1.305, website 1.194; graduation 1.485% with Telegram vs 0.166% without (8.94x); all three socials 1.919% vs none 0.110% (17.4x); Harrell's C 0.858 — [arXiv 2607.02823v3](https://arxiv.org/html/2607.02823v3) [measured, in-sample].
- **The same author's pre-registered follow-up (v4 of the same arXiv ID) found the locked logistic model fit on a 15-day development cohort had AUROC 0.8594 in development but 0.4642 on the subsequent 14-day validation cohort (bootstrap 95% interval 0.4112–0.5196, containing 0.5); calibration slope collapsed to 0.013; 2 of 9 pre-registered stability gates passed, 6 failed. The author now states these associations "are not predictors of pump.fun graduation" and flags collider bias from the collector's top-50 feed** — [Auditing Collector-Generated Graduation Labels, arXiv 2607.02823v4](https://arxiv.org/pdf/2607.02823) [measured, temporal OOS; negative result].
- KOL promotions (CoinWire via Dune; 377 X influencers with 10k+ followers, 1,567 memecoins, 3 months): one week after promotion 80% of tokens were down 70%; one month 90% were down 80%; three months 86% were at ≤1/10 of promotion price; only 1–3% ever hit 10x. Larger accounts were worse: 200k+ follower promotions were −39% at one week and −89% at three months, while <50k-follower promotions averaged +25% at one week and +141% at three months (average, i.e. driven by outliers). Caveat: deleted posts may bias results — [BlockBeats](https://en.theblockbeats.news/news/55919) [measured, third-party].
- For non-meme altcoins (181 coins, 426,520 tweets) short-term returns were predictable from Twitter activity/sentiment — [Steinert & Herff, PLOS ONE 2018](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6279012/) [measured, but pre-memecoin era and not Solana].
- Social-media manipulation and "Market-Manipulation-as-a-Service" tooling are documented as one of five manipulation classes across 15M pump.fun coins — [Meme Coin Factories, arXiv 2609.10246](https://arxiv.org/abs/2609.10246) [measured; percentages not in abstract].

**Smart-money inflows / copy trading**
- Presence of "historically successful traders" (identified in the prior two weeks) had "at most a modest and non-monotonic effect" on graduation probability, with a "dual role": they accelerate early discovery but engage in rapid exits — [arXiv 2602.14860](https://arxiv.org/html/2602.14860) [measured, temporal OOS].
- The only rigorous wallet-persistence study found is on Hyperliquid perps (BTC/ETH/SOL, July 2026, 147,113 wallets): wallet informativeness persisted across 10-day windows (Spearman ρ = 0.52; 91.3% of top-decile wallets traded again), identity features raised 1-second out-of-sample R² from 10.88% to 12.31%, but the gain decayed from 18.7% at 200 ms to 3.0% at 30 s, and the authors say turning it into profit "would require a dynamic execution and market-making model accounting for latency, queue priority, fill probabilities, fees, and inventory" — [Public Trader Identity, arXiv 2608.04373](https://arxiv.org/html/2608.04373) [measured; not memecoins].
- Practitioner warnings: public wallet leaderboards "conflate transfers with trades, reward one lucky winner, ignore latency and liquidity, use future information... and report idealized prices that a follower could never receive"; big PnL screenshots are "survivorship bias dressed up as alpha" — [Medium (Baldwin)](https://medium.com/@nathan.baldwin_31153/copy-trading-on-solana-how-to-find-alpha-wallets-without-getting-faked-out-by-bots-0bc550f07290) [anecdote]. Claims like "0.5 SOL into 52 SOL in a night" are [anecdote] — [Medium (gemQueenx)](https://medium.com/@gemQueenx/best-solana-meme-coin-wallet-traders-for-copy-trading-insider-wallets-4353930b33b9).

**Time of day**
- 190 paper trades (Mar 29–Apr 12 2026): the three worst UTC entry hours (2, 13, 23; n=17) averaged −11.60% vs +1.82% for all other hours (n=173), but Mann-Whitney p = 0.5634 and the hours were selected on outcome from the same sample; the author labels it "directional and non-confirmatory" — [Hour-Aware Adaptive Risk Management, arXiv 2606.08232](https://arxiv.org/abs/2606.08232) [measured; not significant].
- Vendor claims that 14:00–22:00 UTC is the best launch window with "3–4x more active traders" — [solbundler](https://solbundler.app/blog/best-time-launch-pump-fun) [vendor; no data shown].

### Inferences
- The strongest measured entry signals are *negative* filters (bundle share, early-buyer concentration, bot share, serial creator, creator initial buy size, high swap count per curve level). They raise the chance you're in a token that won't rug in the next hour; none is shown to make the unconditional curve-buy positive-EV.
- "Unique buyers" and "early volume" are the two most manipulated observables (sniper rings add buyer count without adding SOL; wash trading; MMaaS). Prefer SOL-denominated inflow, swaps-per-curve-level, and non-bot share over raw buyer/trade counts.
- Social-link presence is the clearest case of "measured in-sample, failed out-of-sample": treat it as a weak prior that may flip sign as launch bots copy the pattern. KOL mentions should be modeled as a late-stage/exit signal, not an entry signal.
- Time-of-day is folklore until someone shows a significant effect on a pre-registered sample; the one paper that tested it could not reject the null.

### Gaps
- No study was found that measures *post-entry return* (rather than graduation or rug probability) conditional on top-10 holder share or dev holdings on pump.fun specifically; MemeTrans and Midsummer link concentration to risk labels, not to realized PnL for a trader entering at time t.
- No source quantified the price effect of a "dev sold" event (the orcACR bot exits on it, but no magnitude/timing statistics were published).
- No peer-reviewed evidence on copy-trading returns for Solana memecoins; the Hyperliquid persistence study is the closest analogue.

---

## KQ2. Momentum vs mean reversion at minute/hour horizons, by stage

### Takeaway
No published autocorrelation study of memecoin minute bars was found. What is measured is a strong *negative drift with heavy right tail*: most tokens die within the hour, most migrated tokens lose 60–80% within 20 minutes of migration, and a momentum-entry system won 40.5% of trades with a −3.58% median but +0.62% mean. The evidence points to mean-reversion-to-zero as the dominant process at minute/hour horizons, with the entire positive expectation coming from a small number of continuation runs — i.e., "momentum" only pays through tail capture, not through a reliable sign in the next bar.

### Cited Findings
- Momentum/liquidity-signal entry system, 190 trades: win rate 40.5%, mean per-trade +0.62%, median −3.58%, skewness −1.21, excess kurtosis 6.61, cumulative +117.7% but net SOL only +0.039; removing the top three trades (1.6% of sample) flips cumulative return negative; longest losing streak 12. Winners' median hold 3.60 min vs losers' 0.60 min — [arXiv 2606.08232](https://arxiv.org/abs/2606.08232) [measured; paper-traded, small n].
- Post-migration (first 20 minutes): 60.26% of tokens below 20% of migration price, 73.44% below 40%; sharp drops "shortly after migration" are "more likely to be driven by insiders unwinding their low-cost inventory" — [MemeTrans](https://arxiv.org/html/2602.13480v1) [measured].
- Pre-graduation: dumping *before* graduation is more profitable than after because the virtual curve is deeper than the new pool; 92.22% of tokens with ≥30 swaps show a significant negative shock — [arXiv 2602.14860](https://arxiv.org/html/2602.14860) [measured].
- Hours old: among tokens the Hour-Aware system *rejected*, 27 of 48 (56.25%) observed ≥6 hours reached a 50% drawdown from the rejection-time reference price; full-cohort censored lower bound 17.9% — [arXiv 2606.08232](https://arxiv.org/abs/2606.08232) [measured].
- Days/weeks old (CEX-listed survivors only): median ATH at 17.2 days, quartile at 1.6 days; "two-thirds of Solana-era memecoins never stage a failed rally at all — they peak once within days and never approach that level again" — [Coin Metrics](https://coinmetrics.substack.com/p/state-of-the-network-issue-384) [measured].
- Pump-and-dump structure in older tokens (91 operations, 54 on Solana): median pump +143.95%, median dump −55.82%; 59.34% lost ≥50% in the dump — [arXiv 2507.01963](https://arxiv.org/html/2507.01963v1) [measured].
- For large-cap crypto (not memecoins) intraday returns show both momentum (late-informed investors) and reversal (overreaction) — [Wen, Bouri, Xu, Zhao, NAJEF 2022](https://www.sciencedirect.com/science/article/abs/pii/S1062940822000833) [measured; different asset class].
- Unverified practitioner claims: "the first 6 hours... 37.32% moon rate (>100%) and 16.02% dump rate... after 6 hours this collapses to near 1:1" — [Medium (Therani)](https://medium.com/@rakesh.therani/the-memecoin-trading-encyclopedia-35-concepts-backed-byproduction-data-6745ab79d1c9) (page returned 403; numbers come from the search snippet only) [anecdote/unverified]. "The median coin peaks 8 minutes after migrating, halves 1 minute after the peak, and loses 90% within 4 minutes" — [GitHub PR, LPTravelAustralia/polymarket #7](https://github.com/LPTravelAustralia/polymarket/pull/7) (404 on fetch) [unverified].

### Inferences
- By stage: (a) pre-graduation on the curve — negative expectation for a buy-and-hold-to-graduation unless a filter lifts graduation probability above vSol²/115²; (b) minutes after migration — strongly negative drift dominated by insider unwinding, so "buy the graduation" is a reversal setup, not a momentum one; (c) hours old — still majority-drawdown (56% of rejected tokens halved within 6h), but this is where survivors' runs happen; (d) days old — the few that reach CEX listing peak at a median 17 days.
- A momentum rule in this market is really a tail-harvesting rule: it needs a loss-cutting mechanism that keeps the −3.6% median from compounding, and position counts large enough that the 1–2% of trades that make all the money are actually in the sample.

### Gaps
- No minute-level autocorrelation / variance-ratio study of pump.fun or PumpSwap price series was found. The hypothesis "momentum pre-graduation, reversal post-graduation" is consistent with the structural findings above but has not been directly tested.
- No source gave the full post-migration return distribution beyond the 20-minute window (e.g., 1h, 6h, 24h quantiles) for a broad migrated-token sample.

---

## KQ3. Exit timing — when runs end; trailing-stop vs time-based exits

### Takeaway
Measured evidence on *when* runs end is consistent: insider/bundle supply is sold around migration (most migrated tokens lose 60–80% within 20 minutes), pre-graduation dumps are structurally incentivized, and the only reverse-engineered profitable bot exited the instant the creator sold. No published backtest compares trailing stops with time stops on memecoin data; the one academic system that uses a take-profit/trailing/time-stop cascade keeps its parameters proprietary and found winners held ~6x longer than losers.

### Cited Findings
- Insider unwinding is the proximate cause of early post-migration collapses; 60.26% of migrated tokens fell below 20% of migration price within 20 minutes — [MemeTrans](https://arxiv.org/html/2602.13480v1) [measured].
- "Selling strictly before graduation is more profitable than selling immediately after graduation"; 92.22% of tokens with ≥30 swaps have at least one significant negative shock; successful traders "engage in rapid exits" — [arXiv 2602.14860](https://arxiv.org/html/2602.14860) [measured].
- Creator-sell as exit trigger: orcACR "exit[ed] immediately if creators sold" and otherwise used ~20-second copy-block holds — [mikem.codes](https://www.mikem.codes/if-you-aint-first-youre-last-2/) [measured behavior, unreported PnL].
- Exit cascade in a measured system: "Exits are managed by a tiered cascade (take-profit, trailing-stop, time-stop) and a circuit-breaker layer that halts trading under adverse-streak conditions"; thresholds are "the subject of pending intellectual-property protection". Winners' median hold 3.60 min, losers' 0.60 min — [arXiv 2606.08232](https://arxiv.org/abs/2606.08232) [measured].
- Rug definition used by the largest study: max drawdown below −99% or idle >80% of lifetime; majority rug within one hour; XGBoost from the first 5 minutes predicts the 1-hour outcome with F1 0.78 — [arXiv 2608.20271](https://arxiv.org/abs/2608.20271) [measured].
- Liquidity-removal flag at 90% withdrawal; median rug ~$2,832 — [Solidus Labs](https://www.soliduslabs.com/reports/solana-rug-pulls-pump-dumps-crypto-compliance) [measured].
- For survivors large enough for CEX data: median ATH→−95% took 370 days; "major" memecoins retain ≤7% of peak active addresses; active-address counts "mirror price patterns with few local tops" — [Coin Metrics](https://coinmetrics.substack.com/p/state-of-the-network-issue-384) [measured].
- Unverified: "a 10% trailing stop that shows +36% on minute data produces −36% to −55% on live trades, and still −31% with zero reaction time. The price jumps through the stop inside a single sell" — [GitHub PR #7](https://github.com/LPTravelAustralia/polymarket/pull/7) (404) [unverified]. Vendor guidance to trail 30% from the high after a 2x — [Odin.tools](https://odin.tools/blog/pump-fun-autosell-take-profit-stop-loss-2026) [vendor].

### Inferences
- The measurable exit triggers with support are event-based, not price-based: creator/bundle wallets selling, liquidity withdrawal, and the migration event itself (sell into it rather than after it). Price-based trailing stops will be gapped through on thin pools because a single insider sell moves price more than the stop width; a trailing stop needs to be paired with an on-chain "insider sold" watcher.
- Time stops are justified by the base rates: if a token hasn't run within minutes of entry, the hourly drawdown statistics (56% halve within 6h) dominate. The winners-held-6x-longer pattern suggests "cut fast, let the rare continuation run" rather than fixed take-profit targets.

### Gaps
- No published memecoin backtest of trailing-stop width vs time-stop length with realistic fills. The widely circulated live-vs-backtest gap figures could not be verified.
- No study quantified volume-exhaustion or holder-concentration *changes* as leading indicators of the top (as opposed to static concentration at launch).

---

## KQ4. The user's thesis: "every coin goes to 0 but most ride for some time first" — what helps catch the run-up and exit before collapse?

### Takeaway
The first half is well supported (81% of even CEX-listed memecoins fall ≥90% from ATH; 98.6% of pump.fun tokens collapse); the second half is only half-true. Most tokens do *not* ride: ~69% stop trading on launch day (unverified source), the majority rug within an hour, and 60% of migrated tokens lose 80% within 20 minutes. The "ride" is concentrated in a small minority, and among those the run-up is typically days (median ATH 17 days for survivors, 25% within 1.6 days). The measured levers for catching the ride are: pre-filters that remove rug-structured launches (bundles, serial creators, bot-dominated flow, high swaps-per-curve-level), entering where the few non-rug tokens are (post-filter, not post-KOL), and exiting on insider-sell/migration events rather than on price.

### Cited Findings
- 98.6% of 7M+ pump.fun tokens collapsed below $1,000 liquidity — [Solidus Labs](https://www.soliduslabs.com/reports/solana-rug-pulls-pump-dumps-crypto-compliance); 81% of 151 CEX-listed Solana-era memecoins fell ≥90% from ATH, 3.3% regained ATH, only 5 of 151 traded above day-one price — [Coin Metrics](https://coinmetrics.substack.com/p/state-of-the-network-issue-384) [measured].
- Among tokens that *did* run (>100% over three months), 82.6% showed artificial-growth tactics and only 17.4% were clean — [arXiv 2507.01963](https://arxiv.org/html/2507.01963v1) [measured].
- "Fewer than 1 in 100,000" pump.fun tokens reached $10M market cap, 1 in 20,000 reached $1M (Aug 2024) — [ChainCatcher/Dune](https://www.chaincatcher.com/en/article/2139008) [measured].
- Successful ("smart") traders accelerate discovery but exit rapidly — [arXiv 2602.14860](https://arxiv.org/html/2602.14860); KOL-promoted tokens were mostly already near their top (80% down 70% a week later) — [BlockBeats](https://en.theblockbeats.news/news/55919) [measured].
- Risk scores from first-minutes features "reduce investment losses by up to 56%" in MemeTrans' simulation (non-temporal split) — [MemeTrans](https://arxiv.org/html/2602.13480v1) [measured, optimistic split].

### Inferences
- "Most ride first" should be restated as "a filtered minority rides, and the ride is front-loaded": the realistic goal of an agent is not to predict which coin runs but to avoid the ~85% of launches that are structurally rug-shaped, then size small across many survivors so the heavy right tail is in-sample.
- Exit discipline matters more than entry selection in the measured data: the +0.62% mean / −3.58% median profile means an agent that cannot cut losers at the ~1-minute mark loses even if its entry filter is good.

### Gaps
- No source quantifies the *conditional* run-up distribution (e.g., given a token passes a bundle/creator filter, what fraction 2x within an hour and how long the median run lasts). This is the single most useful missing number for the arena.

---

## KQ5. How large are edges after realistic costs? Do they survive?

### Takeaway
No published Solana memecoin strategy shows a net-positive edge after realistic costs on an out-of-sample sample. The best academic result (190 paper trades, +0.62% mean/trade, +0.039 SOL net) excludes slippage, failed transactions, and MEV, and its profit comes entirely from 3 trades. Measured frictions: ~1.25% pump.fun fees, price impact of roughly 2 × (trade ÷ pool) on pools of a few thousand dollars, a median ~$5 sandwich loss when sandwiched (0.038% of Jito bundles, but memecoin pairs are the main target), plus any per-app minimum fee. Against a −3.6% median trade, a $1 minimum fee on small tickets is itself a double-digit-percent drag.

### Cited Findings
- Pump.fun fees ~1.25% total, treated as "negligible" by the authors; even so, graduation-probability curves stay below the breakeven vSol²/115² over most of the curve, i.e. negative EV before costs for unconditional curve buys — [arXiv 2602.14860](https://arxiv.org/html/2602.14860) [measured].
- Hour-Aware system: +117.7% cumulative on 190 trades equals net +0.039 SOL; "realised-execution frictions (slippage, failed transactions, MEV extraction...) are not measured here and are the principal caveat"; "the top 1.6 percent of trades generate 100 percent of cumulative profit" — [arXiv 2606.08232](https://arxiv.org/abs/2606.08232) [measured].
- Sandwiching on Jito (4+ months, early 2025): 521,903 sandwich instances, >$7.7M victim losses, attackers gained ~$9.68M; the median sandwiched transaction lost roughly $5 and some lost >$100; sandwiches were 0.038% of Jito bundles; users spent ~$2.4M on defensive bundling tips (avg $0.00286 per defensive bundle). Solana median tx fee $0.00064 — [Gerzon, Weintraub et al., IMC '25](https://ben-weintraub.com/files/solanamev.pdf) [measured].
- Single sandwich program "Vpe" (Dec 7 2024–Jan 5 2025): 1.55M sandwiches, 88.9% success, 65,880 SOL ($13.43M) extracted, average 0.0425 SOL ($8.67) per attack; 16 of the top 20 sandwiched tokens were pump.fun-created; memecoin traders are targeted because they "set high slippage tolerances" — [Helius MEV Report](https://www.helius.dev/blog/solana-mev-report) [measured].
- orcACR reverse-engineering assumed a 14% haircut vs the creator's buy/sell price to model slippage on fresh curves — [mikem.codes](https://www.mikem.codes/if-you-aint-first-youre-last-2/) [practitioner assumption].
- Arbitrage MEV averaged $1.58 per successful arb across 90.4M arbs in 2024 — [Helius](https://www.helius.dev/blog/solana-mev-report) [measured] (context for how thin per-trade edges are for the best-equipped players).
- Trader outcome distribution (Mar 2026): ~96% of wallets lost or made <$500 — [CoinMarketCap/Dune](https://coinmarketcap.com/top-stories/69cac98635bc806ad6e55590/) [measured].

### Inferences
- With a $1 minimum fee, a $20 ticket pays 5% round-trip before AMM fees and impact; a $5 ticket pays 20%. Given a −3.6% median trade and +0.6% mean, the arena's small-ticket agents are structurally negative-EV unless tickets are large enough that the fixed fee is <1% and the pool is deep enough that impact is <2%.
- The only cost-aware edge in the literature is on the *rejection* side: MemeTrans' "up to 56% loss reduction" and the 56%-halve-within-6h rejected cohort show that filters have measurable value as loss avoidance even when no positive edge is shown.
- Sandwich risk is manageable (use low slippage tolerance / Jito bundles) but failed-transaction cost and price impact on $2–5k pools are not; these should be modeled explicitly in the arena's fill simulator rather than as a flat percentage.

### Gaps
- No study reports a net-of-cost Sharpe or expectancy for any Solana memecoin strategy on a temporal holdout. The scorplabs 12% signal's "live probe" (5/77 graduated) gives no PnL.
- No measured distribution of failed-transaction rates or priority-fee spend for retail-size memecoin orders was found.

---

## KQ6. ML/quant papers and open-source projects — out-of-sample results

### Takeaway
Three academic efforts report temporal out-of-sample results, all for *rug/graduation classification* rather than returns: XGBoost from the first 5 minutes reaches MCC ~0.36–0.39 on pump.fun with rolling temporal CV but transfers near-zero across platforms; a non-parametric graduation model validated on a later two-week slice found only trading intensity and bot share robust; and a pre-registered logistic model on social/market-cap features went from AUROC 0.86 to 0.46 on a two-week holdout. Open-source bots (Dexter, TreeCityWes, 1fge) ship backtest scaffolding but publish no out-of-sample PnL.

### Cited Findings
- **Catching the Rug** (6.4M tokens, Nov 30 2024–Jun 30 2025): XGBoost on pump.fun F1 0.7810, MCC 0.3562, AUC-PR 0.7564; fused Raydium+pump.fun training → pump.fun MCC 0.3947, AUC-PR 0.8011; Raydium→pump.fun transfer MCC −0.0026 (fails); rolling time-series CV with 3-month windows and last window held out; "no smart contract code analysis or bundle-level features"; no economic backtest; authors say results are "not yet sufficient for real-world deployment" — [arXiv 2608.20271](https://arxiv.org/abs/2608.20271).
- **Predicting the success of new crypto-tokens** (655,770 tokens, Sep 2025): conditional probability curves; identification on first two weeks, test on second two; trading intensity and non-bot share robust; prolific-creator effect "limited" statistical support; successful-trader presence modest/non-monotonic; no AUC reported; no PnL after costs — [arXiv 2602.14860](https://arxiv.org/html/2602.14860).
- **Graduation survival + audit** (same arXiv ID, v3 vs v4): Cox C-index 0.858 in-sample; pre-registered logistic model dev AUROC 0.8594 → validation 0.4642 (95% PI 0.4112–0.5196); calibration slope 0.013; frozen inputs/code on Zenodo (DOI 10.5281/zenodo.20633486) — [v3](https://arxiv.org/html/2607.02823v3), [v4](https://arxiv.org/pdf/2607.02823).
- **MemeTrans** (41,470 migrated tokens): MLP AUPRC 0.5729, F1 0.6981 (P 69.5% / R 70.1%); 70/30 random split with 5-fold CV, *no temporal split*; "reduce investment losses by up to 56%" in simulation — [arXiv 2602.13480](https://arxiv.org/html/2602.13480v1).
- **Hour-Aware** (190 trades): CC-BY trade log and 4,874-sample rejection corpus plus an MIT `audit.py` that reproduces every headline number; signal set, gate thresholds, exit tiers and circuit-breaker rules withheld (patent applications 64/022,461 and 64/099,108) — [arXiv 2606.08232](https://arxiv.org/abs/2606.08232).
- **Sniper cohorts**: detection code, PSM script and cohort catalogue released (RED-COHORT-2026-v1, CC-BY-4.0) but all numbers withdrawn pending correction — [arXiv 2607.02795](https://arxiv.org/abs/2607.02795).
- **CoinCLIP**: CLIP-based multimodal (logo image, description text, comments/likes) viability classifier on pump.fun with a public "CoinVibe" dataset; the abstract gives no accuracy/AUC and no temporal evaluation — [arXiv 2412.07591](https://arxiv.org/abs/2412.07591).
- **Meme Coin Factories** (15M pump.fun coins): five manipulation classes (wash trading, creator-address obfuscation, coordinated sell, copycat coins, social-media manipulation) executed "in a highly automated and low-latency fashion"; MMaaS tooling — [arXiv 2609.10246](https://arxiv.org/abs/2609.10246).
- Open source: [FLOCK4H/Dexter](https://github.com/FLOCK4H/Dexter) (creator-tracking sniper with a `backtest` command and aggressive/balanced/conservative profiles; no published results); [TreeCityWes/Pump-Fun-Trading-Bot-Solana](https://github.com/TreeCityWes/Pump-Fun-Trading-Bot-Solana) (25% profit target, 10% stop, bonding-curve-progress exits; a forum user reported 2 wins at +20% and 1 loss at −20% on 3 coins [anecdote]); [1fge/pump-fun-blog-part-1](https://github.com/1fge/pump-fun-blog-part-1) (pump.fun API scraper + `backtest-strategy-db.py` for creator-behavior filters; author notes the API has since changed); [jcoulaud/pumpfun-sniping-bot](https://github.com/jcoulaud/pumpfun-sniping-bot) (creates tokens and sells into snipers — i.e., the counterparty to sniping strategies).
- Practitioner ML write-ups: a Medium "practical investment system" for predicting pump.fun prices — [thedeephub](https://medium.com/thedeephub/predicting-pump-fun-memecoin-prices-using-machine-learning-a-practical-investment-system-f3df24e8b83a) — and an "Analysis of Pump.Fun Predictive Model Collapse & Recovery" — [KeithTheDev69](https://medium.com/@KeithTheDev69/analysis-of-pump-fun-predictive-model-collapse-recovery-d0aca8819db6) — both returned 403 and could not be verified; the latter's title corroborates the non-stationarity theme but no numbers are available.

### Inferences
- Every result with a temporal holdout is a classifier for *bad outcomes*; none is a return predictor. For an AI agent, the actionable use is as a pre-trade veto (reject tokens with high rug probability), with the understanding that a ~0.36–0.39 MCC still passes many rugs.
- Feature drift is the dominant failure mode: the audit paper's 0.86→0.46 collapse and the cross-platform MCC ≈ 0 both say that any model must be retrained on a rolling window (weeks, not months) and evaluated only on later data.

### Gaps
- No open-source project publishes an out-of-sample, cost-inclusive PnL curve for a pump.fun strategy; all "results" found are forum anecdotes or proprietary.
- CoinCLIP's quantitative results and the MemeChain dataset paper ([arXiv 2601.22185](https://arxiv.org/html/2601.22185v1)) were not reviewed in full; they may contain additional predictor rankings.
