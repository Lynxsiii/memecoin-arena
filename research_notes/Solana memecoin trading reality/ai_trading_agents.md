# AI/LLM Trading Agents for Crypto Memecoins and Their Data Infrastructure (2024-2026)

Scope note: research conducted 2026-10-06. Sources are 2024-2026 web pages, arXiv/SSRN preprints, vendor docs and crypto-media reporting. Several vendor pricing pages returned 404 during this session; where a figure comes only from a secondary review or a search snippet, that is flagged. Nothing below is investment advice.

## Key Question 1: Public results of LLM trading agents in crypto (Alpha Arena, ai16z/elizaOS, AIXBT, academic benchmarks) — what worked and what didn't

### Takeaway
Every public, real-money or live-paper test of general-purpose LLMs trading crypto in 2025-2026 shows the same pattern: a minority of models squeak out a small profit, most lose, fee drag from overtrading is a dominant cost, and none sustain alpha over a simple buy-and-hold benchmark. The headline "AI agent" tokens (ai16z, AIXBT, Virtuals ecosystem) were valued as narrative assets, never published audited trading track records, and have collapsed 90-97% from peak.

### Cited Findings

**Nof1 Alpha Arena Season 1 (live, real money, Hyperliquid perps, Oct 17 - Nov 3/4, 2025)**
- Six models each given $10,000 of real capital on Hyperliquid with identical prompts and data; final published snapshot: Qwen3 Max +22.31% ($12,231), DeepSeek V3.1 +4.89% ($10,489), Claude Sonnet 4.5 -42.01%, Gemini 2.5 Pro -45.55%, Grok 4 -57.92%, GPT-5 -58.74% — [iWeaver summary of Nof1 leaderboard](https://www.iweaver.ai/blog/alpha-arena-ai-trading-season-1-results/)
- Protos's end-of-contest figures differ for the losers: ChatGPT -$6,267 (63%), Gemini -$5,671, Grok -$4,531, Claude Sonnet -$3,081, DeepSeek +$489, Qwen3 Max +$2,232. Winner figures match iWeaver; loser figures do not (likely different snapshot times or open positions) — [Protos, Nov 2025](https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/); contradicted on loser magnitudes by [iWeaver](https://www.iweaver.ai/blog/alpha-arena-ai-trading-season-1-results/)
- Win rate across all models was only 25-30%. Gemini made 238 trades; Claude Sonnet made 38. Grok, ChatGPT and Gemini shorted more; Claude "rarely" shorted. Fees: Qwen3 Max paid $1,654 (the most, despite winning), Gemini $1,331 — [Protos](https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/)
- Peak was Oct 27, 2025: Qwen3 Max and DeepSeek had roughly doubled; Claude and Grok were briefly profitable; ChatGPT and Gemini were underwater throughout. Nof1's own stated finding: "PnL was dominated by trading costs in early runs as agents over-traded and took quick, tiny gains that fees erased." Nof1 also acknowledged LLMs struggle with numerical time-series data, limited context windows, and a constrained asset/action space — [Protos quoting Nof1](https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/)
- Season 1.5 (Nov-Dec 3, 2025) switched to tokenized US equities with 8 models (added Kimi K2 and a "mystery model" from a top lab); the mystery model won with +12.11% over two weeks. As of Aug 2026 no Season 2 roster or results were publicly visible — [BlockFlow on X](https://x.com/BlockFlow_News/status/1991387204099375354/photo/1); [TradeRank blog, 2026](https://www.traderank.ai/blog/alpha-arena-alternatives-2026)
- Note: a GitHub repo named "alpha-arena-nof1-ai/nof1ai-alpha-arena" claims to be an open-source "deep reinforcement learning" Nof1 bot; it is not an official Nof1 property as far as I could verify and reads like a lookalike/affiliate project — [GitHub](https://github.com/alpha-arena-nof1-ai/nof1ai-alpha-arena)

**AI-Trader benchmark (live, data-uncontaminated, Oct 1 - Nov 14, 2025; arXiv Dec 2025)**
- Six LLMs (DeepSeek-v3.1, MiniMax-M2, Claude-3.7-Sonnet, GPT-5, Qwen3-Max, Gemini-2.5-Flash) traded Nasdaq-100 hourly, SSE-50 daily and 10 major crypto pairs daily, given holdings, live prices and five tools (price check, web search, news, calculator, execution). In crypto, baseline CD5 index was -14.30%; DeepSeek-v3.1 at -12.18% was the only agent beating it, Gemini-2.5-Flash was worst at -18.63%; all agents lost — [AI-Trader, arXiv 2512.10971](https://arxiv.org/html/2512.10971v1)
- Failure modes catalogued: overtrading (Gemini accumulated 30+ positions before liquidation), information hallucination (DeepSeek adopted an unverified "structural slow bull" narrative), rigid allocation without liquidity awareness (GPT-5), passive "hold-to-die" news dependency (Gemini). Conclusion: "General LLM intelligence does not translate to trading proficiency"; "Risk management, not return maximization, determines cross-market success" — [AI-Trader](https://arxiv.org/html/2512.10971v1)

**"Can AI Make Money in Crypto? Measuring the Gap from Backtests to Real Markets" (Yu et al., arXiv Sept 2026)**
- 32 methods (24 ML, 2 RL, 3 LLM: DeepSeek/Qwen/FinGPT, 3 agents: FinMem/FinAgent/TradingAgents) evaluated in three stages: 2025 backtest, OKX paper trading Jun-Sep 2026, real-money live Aug-Sep 2026 — [arXiv 2609.34510](https://arxiv.org/html/2609.34510v1)
- All six non-ML methods (RL, LLM, agents) were unprofitable in the 2025 backtest; DeepSeek had the highest alpha (278%) but -43.3% cumulative return with extreme volatility. LLM execution latency was 186.9-522.9 seconds per decision vs 18.6 s for ML — [arXiv 2609.34510](https://arxiv.org/html/2609.34510v1)
- Rankings reversed in paper trading (LLM/agent median +13.2% vs -29.9% in backtest); in live trading only Qwen stayed profitable (+3.72%), all four deployed methods had negative alpha, and none beat Bitcoin buy-and-hold (+11.63%). Paper-to-live execution price discrepancy rose ~6x (0.31‰ to 1.86‰). Conclusion: "Current trading methods do not sustain market-beating performance under live deployment" — [arXiv 2609.34510](https://arxiv.org/html/2609.34510v1)

**DX Terminal Pro (real-capital LLM memecoin agents on Base, arXiv Apr 28, 2026)**
- 21-day live deployment: 3,505 user-funded vaults, 12 memecoin tokens in Uniswap V4 pools, 5,000+ ETH deployed, 2.3% fee per swap, Qwen3-235B, ~7.5M invocations / ~70B tokens. This is the closest published analogue to an LLM memecoin arena with real money; the paper reports operational metrics (99.9% settlement success) rather than aggregate PnL — [arXiv 2604.26091](https://arxiv.org/html/2604.26091)

**CryptoBench (analysis tasks, not trading; v5 May 2026)**
- 50 monthly expert-written tasks; 10 LLMs (GPT-5, Grok-4, Claude, DeepSeek R1, Qwen3-Max, Gemini 2.5 Pro) with and without SmolAgent. "Retrieval-prediction imbalance": Grok-4 (Web) 54.9% on simple retrieval but 28.6% on complex prediction; GPT-5 58.8% vs 5.9%. Agents "struggle with specialized on-chain analysis platforms and real-time DeFi data interfaces." Authors: current agents are "sophisticated search engines rather than true analysts" — [CryptoBench, arXiv 2512.00417](https://arxiv.org/html/2512.00417v5)

**ai16z / elizaOS**
- AI16Z launched on Solana Oct 2024 as "an autonomous, AI-run venture fund"; peak market cap $2.39B on Jan 2, 2025; the daos.fun vehicle held $22M+ of user tokens. Class action filed April 2025 (SDNY, Burwick Law) alleging the project was insider-controlled rather than AI-run and that holders were diluted in the AI16Z-to-ELIZAOS migration; the foundation settled by transferring its remaining treasury. On Aug 5, 2026 founder Shaw Walters wrote "The token is dead. Completely." ELIZAOS is ~$2.3M market cap, -97% from peak. No trading performance of the fund's AI agent was ever disclosed in this reporting — [CoinDesk, Aug 5, 2026](https://www.coindesk.com/markets/2026/08/05/ai-agent-token-once-worth-usd2-4-billion-ends-with-founder-calling-it-dead)
- The project rebranded from ai16z to ElizaOS (token fell 12.7% on the announcement) and Eliza Labs launched a no-code agent builder — [Coinspeaker](https://www.coinspeaker.com/ai16z-falls-12-7-platform-officially-rebrands-elizaos/); [The Defiant](https://thedefiant.io/news/nfts-and-web3/eliza-labs-ai16z-launches-ai-agent-platform)

**AIXBT / Virtuals**
- AIXBT was the most-followed "alpha" agent (400k X followers, ~$650M token cap at peak in Jan 2025) but it is a research/commentary agent, not a trader; it publishes "hit rates" with no audited track record and severe selection bias — [CoinDesk Indices, Jan 22, 2025](https://www.coindesk.com/coindesk-indices/2025/01/22/that-new-sports-betting-guy-you-like-may-be-an-ai-agent); [crawlux comparison](https://www.crawlux.com/compare/virtuals-vs-ai16z/)
- In March 2025 an attacker queued malicious X replies into AIXBT's autonomous response system and drained 55.5 ETH (~$105k) from its wallet; the token fell 20% to $0.097, ~90% off its Jan 16, 2025 ATH of $0.94 — [Decrypt](https://decrypt.co/310510/aixbt-ai-influencer-hacked-100k-ethereum); [CoinCentral](https://coincentral.com/aixbt-ai-agent-loses-55-5-eth-in-security-breach-token-falls-20/)
- New agent launches on Virtuals plummeted in Feb 2025; AI-agent token market cap fell from ~$17B in early Jan 2025 to under $5B — [Cointelegraph](https://cointelegraph.com/news/new-ai-agent-launches-virtuals-plummet-token-drawdowns)

### Inferences
- Across four independent 2025-2026 live tests (Alpha Arena, AI-Trader, Yu et al., DX Terminal), the models that lost least were the ones that traded least or held the most cash; the user's observation that Claudes "avoided rugs but rarely profited" matches Claude's low trade count and conservative profile in Alpha Arena (38 trades, rarely short) and is the expected outcome, not an anomaly.
- The Alpha Arena and Yu et al. results are consistent with noise: small-n (6 models, 2 weeks), 25-30% win rate, winners paid the highest fees, and the same model families rank differently in different studies (Qwen won Alpha Arena and the Yu et al. live stage; Qwen3-Max was among the worst in AI-Trader's US/A-share markets). No published study supports a stable "best model for trading."
- The "AI agent" token boom was priced on narrative; the agents' actual trading P&L was never the product. Treat any agent-token performance narrative as marketing until an audited, time-stamped trade log exists.

### Gaps
- Nof1's own technical post (nof1.ai/blog/TechPost1) returned 404; I could not read the exact prompt, data cadence or fee schedule first-hand. Figures come from Protos and secondary summaries.
- No published P&L for the ai16z "AI Marc" DAO trading agent or for the DX Terminal Pro vault population; neither source reports aggregate returns.
- No public study of LLM agents trading pump.fun-stage tokens specifically; DX Terminal (12 established Base memecoins) is the closest.

## Key Question 2: Known failure modes of LLM traders and design patterns that helped

### Takeaway
The documented failure modes are overtrading/fee drag, fabricated rules and numbers, anchoring on literal thresholds in the prompt, "cadence trading" (treating each polling tick as a signal), hallucinated narratives, look-ahead leakage via memory, prompt sensitivity, correlated herding across agents, and second-to-minute latency. The fixes that have evidence behind them are harness-level: structured/typed inputs and outputs, explicit fee modelling placed before market context, removing hard numeric thresholds, memory filters, pre-trade risk checks, and decoupling slow reasoning from fast execution.

### Cited Findings
- Pre-launch testing of DX Terminal's memecoin agents found: 57% of sell decisions cited invented constraints (e.g., "Hierarchy rule #2"); 32.5% of observations were blocked by "fee paralysis" because fee language appeared before market context; soft guidance like "observe floors" inverted a trading-activity slider; agents treated elapsed polling intervals as trading signals ("cadence trading"); and during a "reap" tokenomics event 4,938 sell orders executed in three hours despite holders being eligible for pro-rata compensation — [arXiv 2604.26091, Apr 2026](https://arxiv.org/html/2604.26091)
- Harness-only fixes (no retraining): remove law-like phrasing and state that prior decisions are context not precedent; move fee language to paragraph 1 and express fees relative to expected daily volatility; replace exact thresholds with comparative language tied to fresh signals; filter memory so repeated observations don't become a rhythm; insert tokenomics mechanics as structured domain context. Results: fabricated sell rules 57% -> 3%, fee-driven observations 32.5% -> <10%, capital deployment 42.9% -> 78.0% — [arXiv 2604.26091](https://arxiv.org/html/2604.26091)
- Alpha Arena: overtrading and "quick, tiny gains that fees erased" dominated early PnL; models differed radically in trade frequency (238 vs 38) and directional bias under identical prompts — [Protos](https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/)
- AI-Trader: overtrading, unverified narrative adoption, rigid target-weight allocation ignoring liquidity, passive news dependency, and failure to generalize across markets; "Agents lack systematic information verification mechanisms" — [arXiv 2512.10971](https://arxiv.org/html/2512.10971v1)
- Yu et al.: LLM decision latency 186.9-545 s vs 18.6 s for ML, causing slippage exposure; backtest-selected methods did not keep their edge prospectively; live price discrepancy ~6x paper — [arXiv 2609.34510](https://arxiv.org/html/2609.34510v1)
- "Agentic Trading: When LLM Agents Meet Financial Markets" survey (May 2026; 77 studies screened, 19 empirical): failure modes include look-ahead bias from news timestamps, "oracle fallacy" (memory retrieval leaking post-hoc outcomes, needing an "Outcome Embargo"), unfaithful reasoning traces (verify chain-of-thought against ground-truth snapshots), strategy crowding/alpha decay when multiple agents share objectives, conflating target weights with executable orders, and second-scale latency ("reflective reasoning must be decoupled from the critical path"). Recommended patterns: typed I/O contracts, versioned RAG with source tracking, pre-trade checks and explicit transaction-cost models, time-aware memory with decay, immutable decision logs, cascaded control that routes by market regime. Reproducibility audit: only 1/19 studies specified transaction costs, 1/19 documented survivorship handling, 15/19 at the lowest reproducibility tier — [arXiv 2605.19337](https://arxiv.org/html/2605.19337v1)
- CryptoBench failure modes: reliance on outdated sources, parsing failures on complex dashboards, inability to integrate multi-source data, unsupported predictions — [arXiv 2512.00417](https://arxiv.org/html/2512.00417v5)
- A behavioral study of 96 GPT-4-family agents exposed to attention shocks about meme stocks found the agents reduced buying propensity by 11.67 percentage points, i.e., they fail to replicate the attention-driven buying that humans exhibit — [Research Square preprint](https://www.researchsquare.com/article/rs-9372266/latest.pdf)
- A 2026 SoK paper catalogues robustness and security failures (adversarial/prompt-injection vulnerabilities) in academic LLM trading schemes — [arXiv 2609.19705 (title only; not fetched)](https://arxiv.org/pdf/2609.19705)
- AIXBT's wallet drain happened because untrusted X replies were fed into the agent's autonomous action loop — a prompt-injection-to-funds path — [Decrypt](https://decrypt.co/310510/aixbt-ai-influencer-hacked-100k-ethereum)
- The AI-Trader paper's observation of "hold-to-die" positioning and the DX Terminal paper's "fee paralysis" together describe the two opposite failure poles: freezing vs churning — [AI-Trader](https://arxiv.org/html/2512.10971v1); [arXiv 2604.26091](https://arxiv.org/html/2604.26091)

### Inferences
- For an agent that decides every few minutes on 30-second data, "cadence trading" is the most likely silent bug: the agent will manufacture a reason to act each tick. The DX Terminal fix (memory filtering, no hard thresholds, fees stated up front relative to volatility) is directly transferable.
- The user's Claude agents "avoiding rugs but rarely profiting" is consistent with fee paralysis / over-caution plus a market where most organic tokens die; that is a harness and market-structure outcome, not evidence that the model "can't see" good coins.
- Structured numeric features (liquidity, holder concentration, dev-wallet history, buy/sell imbalance) should be computed deterministically and handed to the model as typed fields; CryptoBench shows LLMs read dashboards badly and Alpha Arena shows they handle raw time series badly.
- Because multiple Claude instances with similar prompts will herd (survey's crowding point), the arena should vary prompts/roles or it is measuring one strategy seven times.

### Gaps
- A search snippet attributed a statistic ("8.3% (Claude 3 Opus) to 22.7% (Llama 3 70B) of incorrect responses contained a fabricated numerical figure") to an LLM financial-hallucination study, but I could not identify or verify the primary paper, so it is excluded from findings.
- I found no controlled study isolating prompt sensitivity (same model, perturbed prompt) on crypto trading returns; the survey discusses it qualitatively only.

## Key Question 3: Data sources and APIs for Solana memecoins — what each offers, tiers, latency, most valuable signals

### Takeaway
For a minutes-cadence agent the valuable feeds are (a) raw on-chain event streams for new mints/trades (PumpPortal, Helius, Bitquery), (b) pair-level aggregates (DexScreener, GeckoTerminal, Birdeye), (c) risk/holder structure (RugCheck, Bubblemaps, GMGN-style dev-wallet history), and (d) execution/price (Jupiter). Free tiers are enough for a paper arena; the paid tiers mainly buy latency (gRPC/LaserStream sub-second) and throughput that an LLM deciding every few minutes cannot exploit anyway.

### Cited Findings

**PumpPortal (pump.fun)**
- WebSocket methods: `subscribeNewToken` (free), `subscribeMigration` (free), `subscribeTokenTrade` and `subscribeAccountTrade` (metered at 0.01 SOL per 10,000 messages, requires API key and a linked wallet holding >=0.02 SOL). Only one concurrent WebSocket connection is allowed; opening more triggers hourly temporary bans. Docs do not state latency or full payload schema — [PumpPortal real-time docs](https://pumpportal.fun/data-api/real-time/)

**Helius (RPC, webhooks, LaserStream)**
- Free: $0, 1M credits, 10 RPS, standard WebSockets, webhooks, archival, DAS 2/s, sendTransaction 1/s. Developer: $49/mo, 10M credits, 50 RPS, staked connections, gRPC devnet only, preprocessed (enhanced) transactions at 0.1 credit/msg. Business: $499/mo, 100M credits, 200 RPS, full LaserStream (WSS+gRPC) on mainnet, sendBundle 5/s. Professional: $999/mo, 200M credits, 500 RPS — [Helius pricing](https://www.helius.dev/pricing). (A secondary guide states the free tier is "1M credits/day"; the pricing page lists 1M without a daily qualifier — treat as monthly until verified — [Codex guide](https://www.codex.io/blog/solana-api-guide))

**DexScreener**
- Public REST, 60 requests/minute on every endpoint. Pair data: price (native/USD), volume by window, liquidity (USD/base/quote), buy/sell transaction counts by window, price-change windows, market cap, FDV, active boost count. Also exposes `token-boosts/latest`, `token-boosts/top`, `token-profiles/latest`, `community-takeovers/latest`, `ads/latest` and `orders` (paid-promotion status per token). No latency or caching guarantee documented — [DexScreener API reference](https://docs.dexscreener.com/api/reference)

**Bitquery**
- Pump.fun/PumpSwap APIs over GraphQL, with delivery via gRPC "CoreCast" (<300 ms, binary Protobuf), Kafka (<500 ms p95), WebSocket GraphQL subscriptions (~1 s). Claims ~95M Solana GraphQL queries/week at p50 ~120 ms; ingests "157 billion Solana rows per week." Positions itself against Moralis as having launchpad feeds (Pump.fun, PumpSwap, Raydium) that Moralis lacks (vendor comparison; biased source) — [Bitquery blog](https://bitquery.io/blog/solana-pumpfun-volume-four-delivery-channels); [Bitquery Pump.fun API docs](https://docs.bitquery.io/docs/blockchain/Solana/Pumpfun/Pump-Fun-API/); [Bitquery vs Moralis](https://bitquery.io/alternatives/bitquery-vs-moralis)

**Birdeye**
- Secondary review (not primary pricing page, which 404'd): free tier 30,000 compute units/month at 1 request/second; "Lite" $39/month at 15 RPS; offers price/chart/trade data API — [Pump Parade Birdeye review, 2026](https://blog.pumpparade.com/reviews/birdeye-review-2026-fees-features-verdict/); [Birdeye data API page](https://birdeye.so/data-api)

**RugCheck**
- Free REST API at api.rugcheck.xyz with Swagger docs; no account or wallet connection needed; returns a structured risk report per mint; higher-throughput paid tiers exist for bots/protocols — [RugCheck on X, Jan 2025](https://x.com/Rugcheckxyz/status/1875266458642780429); [Apidog guide](https://apidog.com/blog/rugcheck-api/)

**Bubblemaps**
- Holder-cluster graph (wallets as bubbles sized by holding, edges = transfers), 10+ chains; free tier includes full map, "Magic Nodes" and "Time Travel"; some advanced features gated by BMT token holdings — [Crypto University guide](https://cryptouniversity.network/guides/the-5-minute-token-safety-check-how-to-use-rugcheck-goplus-and-bubblemaps)

**GMGN**
- Telegram + web trading terminal; bundles a rug check and a dev-wallet panel showing how much SOL the deployer has withdrawn since launch, all deployer transactions, and the deployer's prior tokens; free terminal, 1% per trade — [uwuu.ai rug-check tools review, 2026](https://uwuu.ai/blog/rug-check-solana)

**Jupiter**
- Token search and price endpoints exist (community client libraries wrap them); pricing/rate-limit details were not found in this session — [jupiter-api-client on GitHub](https://github.com/snurfer0/jupiter-api-client)

**Other**
- MadeOnSol: memecoin "intelligence" API, free 200 calls/day, Pro $49/mo, Ultra $149/mo — [MadeOnSol pricing](https://madeonsol.com/pricing)
- pumpfundata.com: hourly Parquet dumps of all pump.fun bonding-curve and AMM events since Feb 2026 (useful for offline backtests) — [pumpfundata](https://pumpfundata.com/blog/pumpfun-graduation-rate-analysis)
- CoinCodeCap's roundup of real-time Solana bot data APIs lists the same vendor set (Helius, Bitquery, Birdeye, Shyft, QuickNode, etc.) — [CoinCodeCap](https://coincodecap.com/top-10-apis-to-get-real-time-data-for-solana-trading-bots)

**Market-structure facts that determine which signals matter**
- April 2026: 763,350 pump.fun launches, 6,379 graduated (0.84%); ~24% of daily graduations were bot-engineered (1,513 bonded in <60 s, 735 in the same block as creation; graduates with <20 unique buyers "almost certainly a bot"); organic graduates: median 9.8 minutes to graduate, 62% within 10 minutes, 85% within one hour — [pumpfundata, Apr 2026](https://pumpfundata.com/blog/pumpfun-graduation-rate-analysis)
- Mid-June 2026 graduation rate fell to ~0.26% — [DEXTools news](https://www.dextools.io/news/pump-fun-graduation-collapse-solana-fees-2026)
- SSRN survival analysis of 832,941 launches: pooled graduation 0.198% (lower bound; measures only the first six minutes), with a "social-presence effect" — [SSRN 6915560](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6915560)
- Deployer-funded sniping: deployers transfer SOL to sniper wallets that buy in the same block as launch; in one month >15,000 SOL realized profit across >15,000 launches, 4,600 sniper wallets, 10,400 deployers, 87% sniper profitability — [BlockBeats](https://en.theblockbeats.news/news/58496)
- Academic detection of 1,012 persistent coordinated sniper wallet rings on pump.fun with a "contamination-adjusted" estimate of first-hour buyer-flow lift — [arXiv 2607.02795, Jul 2026](https://arxiv.org/pdf/2607.02795); companion study fingerprinting Solana bots from GitHub blueprints — [arXiv 2607.28424](https://arxiv.org/pdf/2607.28424)
- Sniper bots listen on gRPC/WebSocket for mint transactions and submit via Jito bundles with priority fees; vendors claim >90% success in the first 2 blocks (vendor marketing) — [Cryptwerk](https://cryptwerk.com/post/pump-fun-first-block-sniper-bots-jito-bundling/)

### Inferences
- For an agent that decides every few minutes, the free tiers of DexScreener (60/min), Helius (10 RPS), PumpPortal new-token/migration streams and RugCheck are sufficient; paying for sub-second gRPC buys nothing the model can use because its own decision latency is 2-9 minutes (Yu et al.).
- The highest-value signals given that cadence are structural, not price: unique-buyer count and same-block buy share (bot-graduation filter), dev-wallet withdrawal history and prior tokens (GMGN-style), top-holder/cluster concentration (Bubblemaps), LP lock/mint-authority status (RugCheck), DexScreener boost/ad/order status (paid promotion is a tell), and liquidity persistence over the hours after migration. Price-change-5m is the signal snipers already acted on.
- Because 62% of organic graduations happen within 10 minutes of launch and insider snipers are in the same block, a minutes-cadence LLM cannot be a launch sniper; it can only play post-migration persistence (which tokens still have liquidity and organic buyers 1-24 hours later).
- Offline backtests on pumpfundata Parquet dumps are the cheapest way to test any pump.fun selection rule before spending LLM tokens on it.

### Gaps
- Birdeye's and GeckoTerminal's official pricing/rate-limit pages returned 404; GeckoTerminal public limits (widely documented elsewhere as ~30 calls/min) were not verified in this session.
- No primary-source latency numbers for PumpPortal, DexScreener or GeckoTerminal.
- GMGN and Bubblemaps public API terms were not confirmed; GMGN appears to be terminal-first with no documented public data API.
- The "19.7% of graduates still had $5k liquidity 24 h later" and "6% of graduates had a dev wallet with rug history" statistics appeared in a search snippet with no identifiable primary source; excluded from findings.
- Jupiter API tiers/limits not found.

## Key Question 4: What fraction of memecoin "AI trading bot" / "guaranteed profit" pitches are scams, and how to evaluate claims

### Takeaway
No source quantifies the fraction, but every enforcement action and investigation found in 2025-2026 describes "AI trading bot" or "AI signal" products that were pure fraud (no bot existed), and the only documented near-"guaranteed" edges on pump.fun are insider sniper rings whose advantage is privileged position, not AI. The evaluation rule that regulators and researchers converge on: a black-box bot promising fixed or near-certain returns is malicious until an audited, time-stamped, fee-inclusive trade log proves otherwise.

### Cited Findings
- SEC charged three purported crypto trading platforms and four "investment clubs" that lured victims via social-media ads, posed as finance professionals in group chats, promised profits from "AI-generated investment tips," and showed fictitious profits on fake platforms — [SEC press release 2025-144](https://www.sec.gov/newsroom/press-releases/2025-144-sec-charges-three-purported-crypto-asset-trading-platforms-four-investment-clubs-scheme-targeted); [The Hacker News, Dec 2025 ($14M)](https://thehackernews.com/2025/12/sec-files-charges-over-14-million.html)
- SEC fraud charges (reported Sept 30, 2026) against Cryptoaiml Ltd./Capital Foundation and TSAI Pro Ltd./Capital Foundation for misappropriating >$12.5M and $2.8M via fake AI trading signals and nonexistent AI bots; the schemes used WhatsApp groups and falsified SEC Form D filings as "regulatory certification" — [Cryptonomist](https://en.cryptonomist.ch/2026/09/30/sec-investment-fraud-charges/); [IBTimes](https://www.ibtimes.co.uk/fake-sec-credentials-ai-trading-bots-investment-scam-15-million-1823921)
- UK Serious Fraud Office is investigating Basis Markets over a £21M scheme in which the promised AI trading bot was allegedly a front for theft — [IBTimes UK](https://www.ibtimes.co.uk/21-million-crypto-scam-exposed-ai-trading-bot-that-was-pure-fantasy-1757771)
- Consumer-protection guidance: assume "any black-box bot with guaranteed returns is malicious until proven otherwise"; red flags are near-perfect win rates or fixed daily profits tied to AI buzzwords — [The Coins Post, 2025](https://www.thecoinspost.com/ai-crypto-scams-the-2025-trading-bot-trap/); [MoneyFlock red flags](https://www.moneyflock.com/contents/articles/ai-trading-bot-scams-red-flags)
- AIXBT-style "alpha" agents publish hit rates that are unauditable and subject to severe selection bias — [crawlux](https://www.crawlux.com/compare/virtuals-vs-ai16z/)
- ai16z's "autonomous AI-run fund" claim became the basis of a false-advertising class action alleging insider control — [CoinDesk](https://www.coindesk.com/markets/2026/08/05/ai-agent-token-once-worth-usd2-4-billion-ends-with-founder-calling-it-dead)
- The closest thing to "guaranteed" profit documented on pump.fun is deployer-funded same-block sniping with 87% wallet profitability — an insider/coordination edge — [BlockBeats](https://en.theblockbeats.news/news/58496); [arXiv 2607.02795](https://arxiv.org/pdf/2607.02795)
- Base rate for humans: from Apr 2024 to late 2025 the share of profitable pump.fun traders was below 50% in most months, bottoming at 30.1% in June 2025; it rose to 56.8% (Feb 2026), 70.0% (Mar 2026) and 73.3% (Apr 2026) as monthly active wallets fell from 5.2M (May 2025) to 1.8M (Dec 2025). In Apr 2026, 65.1% of the profitable wallets made only $1-$500 — [CoinGecko Research, 2026](https://www.coingecko.com/research/publications/pump-fun-traders-are-making-a-comeback); [Crowdfund Insider summary](https://www.crowdfundinsider.com/2026/05/277755-solana-based-meme-coins-trading-platform-pump-fun-makes-recovery-research/)
- The best public LLM traders had 25-30% win rates and the winner still paid $1,654 in fees on $10k — [Protos](https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/)
- Many open-source "pump.fun sniper bot" repos exist (e.g., one by "Frontrunx"); their provenance and safety were not assessed here — [GitHub search result](https://github.com/Frontrunx/solana-pumpfunx-sniper-bot)

### Inferences
- Evaluation checklist implied by the sources: (1) is there a time-stamped, wallet-addressable trade log that a third party can replay on-chain; (2) are fees, slippage and failed transactions included; (3) is the benchmark SOL/BTC buy-and-hold and a random-entry baseline over the same window; (4) is win rate reported with trade count and average win/loss size; (5) is the claimed edge speed (then it is competing with Jito-bundled snipers) or selection (then it must beat the ~1% graduation / <20% liquidity-persistence base rate); (6) does the product need your deposit on its platform (every SEC case did).
- "Guaranteed" or "almost guaranteed" in this market means one of: fraud (no bot), insider position (deployer-sniper rings, volume bots), or survivorship-filtered marketing. There is no documented public strategy with that property.
- The 2026 rise in profitable-trader share coincides with a two-thirds drop in participants; it reflects fewer, more professional wallets rather than an easier market for newcomers or LLMs.

### Gaps
- No source gives a numeric fraction of "AI bot" products that are scams; only enforcement cases and heuristics exist.
- Open-source sniper-bot repos were not audited; many such repos are known in the community to contain wallet drainers, but I did not find a 2025-2026 study quantifying this.

## Key Question 5: Realistic role for an LLM in this market and an honest evaluation framework

### Takeaway
An LLM cannot compete on speed (its decision latency is minutes; the memecoin edge is same-block) and has no demonstrated price-prediction skill, but it has measurable value as a structured-risk filter and narrative/social reader applied to deterministic features — which is exactly the "avoid rugs" result the user already observes. The honest framework is a pre-registered, fee-inclusive, three-stage evaluation (replay backtest on pumpfundata -> live paper -> tiny live), reported as alpha vs SOL buy-and-hold and vs a random-entry baseline, with trade count, fee drag and sample size disclosed.

### Cited Findings
- LLM decision latency 186.9-545 s vs 18.6 s for conventional ML; live execution price discrepancy 6x the paper-trading estimate — [arXiv 2609.34510](https://arxiv.org/html/2609.34510v1)
- Reflective LLM reasoning "must be decoupled from the critical path"; LLMs operate at second scale, incompatible with millisecond requirements — [arXiv 2605.19337](https://arxiv.org/html/2605.19337v1)
- Organic pump.fun graduations: median 9.8 minutes, 62% under 10 minutes; snipers are in the creation block — [pumpfundata](https://pumpfundata.com/blog/pumpfun-graduation-rate-analysis); [BlockBeats](https://en.theblockbeats.news/news/58496)
- LLM agents are decent at retrieval (55-59% simple retrieval) and poor at prediction (6-29% complex prediction) — [CryptoBench](https://arxiv.org/html/2512.00417v5)
- "Risk management, not return maximization, determines cross-market success"; agents lack systematic verification — [AI-Trader](https://arxiv.org/html/2512.10971v1)
- Harness changes alone moved a memecoin LLM agent from 57% fabricated rules to 3% and from 42.9% to 78% capital deployment, and a frozen harness ran 21 days at 99.9% settlement success — [arXiv 2604.26091](https://arxiv.org/html/2604.26091)
- "Paper trading provides a closer approximation to live trading than backtesting," but measurable paper-to-live gaps remain; authors call for targeting "persistent excess returns, deployment robustness, and consistency between offline evaluation and realized trading outcomes" — [arXiv 2609.34510](https://arxiv.org/html/2609.34510v1)
- Reproducibility audit: 1/19 LLM-trading studies specified transaction costs, 1/19 handled survivorship — [arXiv 2605.19337](https://arxiv.org/html/2605.19337v1)
- LLM agents under-react to attention shocks relative to humans (-11.67 pp buying propensity), i.e., they do not naturally chase hype — [Research Square](https://www.researchsquare.com/article/rs-9372266/latest.pdf)
- Alpha Arena's conservative model (Claude, 38 trades) lost less than the churners in the Protos tally but still lost; the two profitable models were also the two with the highest fee bills — [Protos](https://protos.com/llm-crypto-trading-contest-finds-llms-cant-trade-crypto/)

### Inferences
- Realistic job description for an LLM in a Solana memecoin pipeline: (1) rug/scam classifier over typed features (RugCheck flags, holder clusters, dev history, same-block buyer share, boost/ad status), where its retrieval and judgment strengths apply; (2) narrative reader over token metadata and social text, with an explicit "do nothing" default; (3) parameter-setter or regime router for a deterministic executor (e.g., choose which post-migration persistence rule to run), not the executor itself. Entry timing and exit execution should be rule-based and sub-second.
- Where the Claudes could plausibly make money: post-graduation tokens that retain liquidity and organic buyers for hours, bought after snipers exit, held with mechanical stops. Where they cannot: anything that depends on being early.
- Honest evaluation framework for the arena, derived from the above: pre-register the strategy and prompt; replay it on pumpfundata hourly Parquet (with fees, slippage proxy, and failed-tx rate); run live paper on real feeds for >=4 weeks; compare each agent to SOL buy-and-hold, equal-weight "buy every graduate" and a random-entry baseline over the identical window; report alpha, Sharpe/Sortino, max drawdown, trade count, fee drag as % of equity, win rate with avg win/loss, and n; keep immutable decision logs and verify the model's stated reasons against the data snapshot it saw; vary prompts/roles across the seven Claudes to avoid measuring one strategy seven times; treat anything under a few hundred trades as inconclusive.
- A 2-week, 6-model contest (Alpha Arena) is already treated by Protos and Nof1 as too small to rank models; the arena should not conclude "Claude is worse/better than X" from similar sample sizes.

### Gaps
- No peer-reviewed or audited evidence that any LLM-centric pipeline earns positive alpha on pump.fun-stage or newly migrated Solana memecoins; the strongest results are "lost less" or "small positive in one window."
- No source quantifies how much of a post-migration token's move is left after sniper exit; the persistence-trading hypothesis above is inference, not a cited result.
- Season 2 of Alpha Arena and any 2026 memecoin-specific LLM contest results were not found.
