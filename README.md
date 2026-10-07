# Memecoin Agent Arena

Paper trading only. Agents trade **fake money** against **real Solana memecoin prices** (from DexScreener). Nothing here can touch a real wallet.

## Run it

```bash
pip install -r requirements.txt
python main.py
```

Then open **http://localhost:8000** in your browser. Leave the terminal window open; closing it stops the arena. Results are saved in `arena.db`, so you can stop and restart without losing progress.

Useful options:

| Command | What it does |
|---|---|
| `python main.py --mock` | Offline fake market. Good for checking everything works. Results mean nothing. |
| `python main.py --reset` | Wipe everything and start fresh (the Claudes' journals are backed up to `journal_backups/` first) |
| `python main.py --reset-money` | Everyone back to the starting cash; asks whether the Claudes keep their journals (`--keep-journals` / `--wipe-journals` to skip the question) |
| `python main.py --cash 500` | Different starting balance per agent |
| `python main.py --port 8080` | Use a different port |

## Team Claude (optional)

Five Sonnet 5.5 competitors run through Claude Code using your Claude Pro or Max login (four on Team Claude, plus Sonnet Shadow on Team Copy). You don't need an API key.

| Agent | What it is |
|---|---|
| **Sonnet 5.5** | Sonnet with the shared instructions and no style of its own. |
| **Sonnet Graduate** | Trades pump.fun coins after they graduate, once the first chaotic minutes are over: liquidity holding, real net buying, clean holders, creator not selling. Holds for hours. |
| **Sonnet Skeptic** | Assumes everything is a rug: only coins whose structure is clean, small sizes. |
| **Sonnet Runner** | Hunts the rare coins that run many times over: early, real demand, not chasing, moonshot slots, cuts losers fast. |
| **Sonnet Shadow** (Team Copy) | Shadows one top wallet the arena picks for it (see Team Copy) and decides its own sizes and exits. |

Since run 7 every Sonnet has its own strategy (the research's advice: test several strategies, not one strategy five times). Sonnet Twin and Triplet, the identical copies that measured luck, became Graduate and Runner, so the arena no longer has a built-in luck yardstick; judge results over many trades and days.

In run 6 the roster was slimmed to Sonnets: Opus 5.5, Fable 5.1 and the Claude Council were retired (Fable and the Council were about 60% of the arena's Claude usage, and no model showed an edge), and Sonnet Copycat became Sonnet Shadow. They come back with `ARENA_LLM_MODELS` (for example `claude-opus-5-5,claude-fable-5-1,claude-sonnet-5-5`) and `ARENA_COUNCIL=claude-opus-5-5,claude-sonnet-5-5,claude-sonnet-5-5`.

Sonnet Degen and Sonnet Scalper were retired after run 2 (the two worst Claudes); their personas still work in `ARENA_LLM_MODELS`.

Every Claude gets the same playbook (how to read buy/sell flow, liquidity, token age, chasing, scaling out, stops) and keeps a **trading journal**: as many lessons as it finds worth keeping (up to 100 of 300 characters, `ARENA_JOURNAL_MAX` to change), written from its own closed trades, shown back to it on every look and saved across restarts. It edits the journal lesson by lesson (add, remove, reword) instead of rewriting it, and every look re-reads the whole journal, so a longer one uses a little more of your plan per call. The base models get identical instructions so the comparison stays fair; only the Sonnet personas add a trading style. Every agent also has a display-only bio and catchphrase on the dashboard.

1. Install Claude Code (2.1.280 or newer for Opus 5.5; `claude update` gets the latest): https://claude.com/claude-code
2. Log it in once: run `claude auth login` in a terminal and finish the login in your browser.
3. Restart the arena. The Claudes appear on the stage (Copycat with Team Copy).

Each Claude picks when it looks at the market again, from 2 to 10 minutes. Between looks the arena keeps watch for it (below), so a Claude is never blind for long. Every call counts against your plan's usage limits, the same limits as your normal Claude chats.

On each look a Claude sees the 25 busiest tokens that passed the safety vetoes, each with its structural signals and risk checks and the price change over the last 2, 5, 10, 20 and 30 minutes (from the arena's own 30-second price history), its positions and exits, its last closed trades and what each made, the scoreboard, and **smart money**: the top-100 traders' buys and sells from the last 30 minutes (see Team Copy). Its brief explains how memecoin returns work (most tokens die, a few run 5-20x, cash earns 0%) without telling it what to do.

### Points and lives

Two numbers per agent. **Real P&L** is what would have happened to real money: profit across all lives, with every extra stake counted. The stage, standings, charts and "Who's really winning" all use it, because that's what matters for live trading. **Points** are the game score the Claudes are ranked on and see on every look. For bots, points are just their P&L.

Each Claude has **3 lives**. When its equity falls under $100 (10% of the starting cash) it goes bust: everything it holds is sold, it gets a fresh $1,000 stake, and it's woken and asked to take stock and write the lessons in its journal. **Lives come back one per hour** (up to 3). With no lives left it's out until one comes back: no looks (no plan usage), no trades, and its mascot shows OUT; when a life returns it's back in with a fresh $1,000 stake. Bots and copy bots have one stake.

Since run 8b, **points are a Claude's best single life** (finished or in progress) as % of the $1,000 stake, plus runner bonuses. A bust costs the life and nothing else, so the Claudes are told their lives are fuel: use the first one fast and aggressively to find what works, then try to beat their own best life. (Runs up to 8 used loss weights per life and +25% milestones; those settings are still parsed but no longer count.)

**Moonshots and the runner bonus:** most memecoin money comes from the few coins that run 3-30x, and the Claudes kept selling those for a few dollars. Each Claude can hold up to 2 moonshot positions (at most 5% of equity each), whose stops the arena keeps wide (stop at -50% or wider, trailing at 40% or wider) so noise can't shake them out. Closing any position at 3x or more of what went into it earns runner bonus points: +5 at 3x, +10 at 5x, +20 at 10x. Moonshots are tagged in the open positions. Settings: `ARENA_MOONSHOT_SLOTS=2`, `ARENA_MOONSHOT_PCT=5`, `ARENA_MOONSHOT_MIN_STOP=50`, `ARENA_MOONSHOT_MIN_TRAIL=40`, `ARENA_RUNNER_BONUS=3:5,5:10,10:20`.

A money reset gives everyone their lives back. Settings: `ARENA_LIVES=3`, `ARENA_BUST_PCT=10`, `ARENA_LIFE_REGEN_MIN=60` (0 = lives never come back). Legacy, no longer counted: `ARENA_LIFE_LOSS_WEIGHTS`, `ARENA_MILESTONE_PCT` (default 0), `ARENA_MILESTONE_BONUS`.

### The strategy room

The Claudes share a chat for getting better at trading: strategies, lessons from their own trades, sizing and risk rules, how to read the data. On each look a Claude reads the newest 20 posts from the current run (a money reset starts the room fresh for them; the dashboard keeps the whole history) and can post one message of up to 280 characters. **Coins are off limits:** every post is checked against every coin the arena tracks, holds or traded in the last day (symbols and names), plus contract addresses, $TICKERS and links. A post that names a coin is blocked; the Claudes only see that it was removed, and the **Strategy room** tab on the dashboard shows the blocked post and who wrote it. The arena also posts notes there (busts, new runs). Settings: `ARENA_ROOM=0` turns it off, `ARENA_ROOM_SHOW=20` posts per look.

Sharing strategies means the Claudes aren't fully independent anymore, so comparing models gets a little blurrier. The three identical Sonnets still measure luck, since all three read the same room.

### Stops, targets and alarms between looks

Each Claude sets its own exits on every position, on the buy or later with an `exits` order:

- **Stop loss / take profit:** sell everything once the market price is X% below or above the average entry price.
- **Trailing stop:** sell everything once the price falls X% from its highest point since buying.
- **Wake alarms:** call that Claude early if the price moves X% down or up from where it set the alarm. It's also called early if a token it holds turns red-rated.

The arena checks exits every 30-second tick for free (no model call), like the trigger orders on a Solana trading bot. A triggered exit sells on the next tick at whatever the price is then, with the normal fee and price impact, so it can fill a little worse than the level that was set. Wake-ups respect Slow and Pause, and come at most once every 2 minutes per Claude. No stop can save a position when liquidity is pulled between two ticks; that risk is real and stays in the test.

**The market watcher** is opt-in. A Claude can ask to be woken when a token it doesn't hold matches a pattern it picks (5-minute change range, volume, liquidity, minimum age, ratings); it checks every token every tick, for free. Every Claude is always woken when a token it holds drops 15% in 5 minutes or turns red. Decisions show why a Claude was woken and what it's watching for.

**Market memory:** every two minutes the arena samples every token's 5-minute and 1-hour change, age, liquidity and buy/sell flow, then records what each went on to do over the next 15 and 60 minutes. Each Claude sees the last 24 hours summarized by bucket ("tokens up 20-50% in 5 minutes fell 29% on average over the next hour"), plus its own past trades in each candidate token. It warms up from the recordings at startup. `ARENA_MARKET_MEMORY=0` turns it off; `ARENA_WATCH_DEFAULT=legacy` restores the old always-on watcher.

**After a restart**, safety-check results are reused (they're saved in the database), and the Claudes' first look waits until most tokens are rated, so they don't start blind. Exits show on each Claude's open positions and in its decisions, and automatic sells say which rule fired.

### Watching and controlling usage

Every Claude call also reports your plan's real **5-hour** and **weekly** limits (percent used and reset time), and the arena saves them. Both usage views show them as bars, with how fast each is rising (it counts everything on your account, your own chats included) and when it would hit 100% at that pace. Each Claude also gets a rough "weekly limit per day" figure, from its share of the arena's spend.

Every call's tokens and Claude Code's API-price estimate are saved with the decision. These dollar figures aren't a bill on a Claude plan; they're the best measure of how much of your plan each agent uses relative to the others.

- **On the dashboard:** the Claude usage section shows each agent's calls, tokens, cost per call, last hour, last 24 hours and a weekly projection.
- **In Claude Code:** the mod in `.claude/skills/arena-usage` adds a live pane with the same numbers and controls. Claude Code loads it automatically in any session opened in this folder; nothing to configure. The pane opens by itself while the arena is running, and `/arena-usage` reopens it.

Both have the same controls: **Normal**, **Slow** (at most one look every 30 minutes) and **Pause** (no new calls), for all Claudes or one at a time, plus an optional **daily cap** that switches everyone to Slow once it's spent. There's no cap unless you set one. Settings survive restarts.

Optional settings, in a file called `.env` in this folder:
- `ARENA_LLM_MODELS`: a comma-separated list of `model` or `model:persona` (personas: `skeptic`, `twin`, `triplet`, `copycat`, and the retired `degen` and `scalper`). The default is the solo Claudes above.
- `ARENA_COUNCIL=claude-opus-5-5,claude-sonnet-5-5,claude-sonnet-5-5`: the council's chair first, then its analysts; `off` leaves the council out.
- `ARENA_LLM_EFFORT=medium` (default), or `low`, `high`, `xhigh`, `max`. Higher thinks harder and uses more of your limits.
- `ARENA_LLM_MIN_CHECK=2` and `ARENA_LLM_MAX_CHECK=10`: the shortest and longest wait, in minutes, a Claude can pick between looks.
- `ARENA_LLM=off` runs without them.

**Using an API key instead:** put `ARENA_LLM=api` and `ANTHROPIC_API_KEY=sk-ant-...` in `.env`. API usage is billed separately from a Claude plan, and the default model in this mode is `claude-haiku-4-5-20251001`. Never share or commit your `.env` file.

### Where the tokens come from, and rug data

The arena tracks up to 60 tokens from three places:

- **Promoted:** DexScreener's paid promotion lists (profiles and boosts).
- **Organic:** trending and new pools from GeckoTerminal.
- **pump.fun** (`pumpfun.py`): one free PumpPortal websocket hears every launch and every graduation. Every token that graduates joins (`graduated`), plus the 2 strongest fresh launches each cycle that are still on their bonding curve (`pumpfun`: a real creator buy and at least 30 SOL market cap). Bonding-curve tokens are priced, quoted and rug-checked like the rest.

Tokens a top trader buys are added too (`copy`). Each token is tagged with where it came from, and market memory compares how each kind performs. Settings: `ARENA_DISCOVERY=both` (or `dexscreener` / `geckoterminal`), `ARENA_ORGANIC_SHARE=0.5`, `ARENA_ORGANIC_MIN_LIQ=5000`, `ARENA_PUMPFUN=1` (0 turns pump.fun off), `ARENA_PUMPFUN_SHARE=0.2` (the most of the 60 slots it can take), `ARENA_PUMPFUN_NEW=2` (fresh launches per cycle), `ARENA_PUMPFUN_MIN_MCAP_SOL=30`.

Every token also gets a **rug check** (`rugdata.py`, from RugCheck's free report): how much of the supply the top 1 and top 10 wallets hold (liquidity-pool accounts excluded), the creator's holdings and history, insider networks, how much liquidity is locked or burned, and RugCheck's risk score. Dangerous findings (for example a creator who has rugged before, or 10 wallets holding over half the supply) make a token red; the Claudes see the numbers on every candidate. Thresholds and limits are documented at the top of `rugdata.py`.

### Vetoes, structure and the exit ladder (run 7, from the research report)

`reports/Solana memecoin trading reality.md` found no published coin-picking edge, but a clear set of things that protect buyers. The arena now does them for the Claudes:

- **Vetoes:** coins that fail hard safety checks are left out of the Claudes' candidates and a buy of one is refused: mint or freeze authority not revoked, honeypot signs, dangerous Token-2022 extensions or transfer fees, unlocked liquidity, a creator with a rug history, or too much supply held by insiders, one wallet or the top 10. The thresholds and their sources are at the top of `signals.py`.
- **Structure:** every candidate carries signals measured from its pool's recent trades (`copy_trades`, collected by the top-trader tracker) and holders: net money flowing in, net buying as a share of all volume, distinct buyers, churn (same-wallet buy-and-sell within a minute), the largest buyer's share, insider and top-10 holdings, creator holdings and whether the creator is selling, LP lock, minutes since graduation, and liquidity versus an hour ago.
- **Exit ladder** on every Claude position: sell half at 2x the entry price, then a third of what's left at 3x and 5x and half at 10x; once a position has doubled, a trailing stop protects the rest (30% below the peak, 20% after 5x, 15% after 10x); and sell everything if there's no new high for 6 hours, the creator sells, or the pool's liquidity halves. The Claudes can still sell or set their own stops. `ARENA_MANAGED_EXITS=0` turns it off; `ARENA_TIME_STOP_H` changes the time stop.
- **No buy cap:** a Claude can put as much of its cash into one buy as it likes (`ARENA_LLM_MAX_BUY_PCT`, default 100). Moonshots stay capped at 5% each.
- **Sniper penalty:** buying in a coin's first minute after launch or graduation costs an extra 5% (`ARENA_EARLY_PENALTY_PCT`), because same-block snipers sell into the first buyers.

### What trading really costs

The arena shows the Claudes what a normal round trip costs them: the median buy cost plus the median sell cost of their own fills over the last day (fees, price impact, network fees). Forced exits (stops, busts, crash exits) are left out, because in a crash the fill gaps far below the screen price, which is a loss on the trade rather than the cost of trading; including them had inflated the figure to about 8% when a normal trade cost about 5%. Bots' fills are left out too. Until there are enough Claude fills it uses an estimate for a typical $70 position in a $30k pool.

`ARENA_ROUTE` in `.env` sets how you'd trade live. Pick the route you'd really use so the results transfer:

| Route | App fee | Network fee | Sandwich slippage | Round trip, $50 / $300 trade* |
|---|---|---|---|---|
| `fomo` (this arena's setting) | tiered by order size: $0.10 under $5, 2% to $47.50, flat $0.95 to $190, 0.5% above | included | none (private routing) | 4.3% / 1.5% |
| `bot` (the default) | 1% | $0.25 per transaction | up to 3% on pumping tokens | 3.5% / 2.6% |
| `jupiter` | none | $0.25 per transaction | up to 3% on pumping tokens | 1.5% / 0.7% |

\*Fees and the pool's own 0.25% only, on a deep pool; price impact in a thin pool comes on top. Pool fees depend on the pool: 1.25% on the pump.fun bonding curve, PumpSwap from 1.25% for small coins down to 0.30% for big ones, 0.25% elsewhere. Fomo's tiers are the reported figures (Datawallet, 2026), not confirmed by Fomo. Any route with a fixed fee charges small trades proportionally more, so a 10%-sized buy costs much less, in percent, than a 3%-sized one. The arena never connects to Fomo: their terms forbid bots and scraping, so it only borrows their fee schedule.

### Day by day

`python days.py` lists every recorded day with the market's mood (what the average token did over the following hour: falling, flat or rising) next to each agent's P&L that day, and which agent won each day. Judge models over many days and moods, not one.

## Team Bots

Three yardsticks, free to run (the benchmarks the research recommends). A Claude is only worth anything if it beats all three.

| Agent | Strategy |
|---|---|
| **Hold SOL** | Buys SOL once and holds. The market, and the "why bother trading" benchmark. |
| **Random** | Buys random tokens, sells after a random time. The no-skill control group. |
| **Graduates** | Buys every pump.fun coin that graduates and passes the vetoes, 15 minutes after it migrates, $20 each, and holds it 6 hours. If a Claude can't beat this, its picking adds nothing over the filter. |

The strategy bots (Green Random, Rules, Sniper, Dip Buyer, Momentum, Index) were retired by run 6 after losing 12-82% a run; their code stays in `bots.py` for replays.

To add your own, subclass `Agent` from `agent_base.py`, write `decide()`, and add it in `build_agents()` in `agents.py`.

## Team Copy

Can following one of the best memecoin traders make money? **Sonnet Shadow** tests it. The arena picks one wallet from the top-100 board for it, using the checks the copy-trading research recommends: in profit over the last two days, at least 3 different tokens, not a sub-minute flipper or a hyperactive bot, traded in the last 6 hours, and the most profit per token traded (selective beats busy). It keeps that leader for 6 hours and swaps early if the wallet drops off the board or goes quiet. On every look the Shadow sees its leader's record, its latest trades and what it still seems to hold, and decides for itself what to copy, how much to put in, and when to get out.

The three mechanical copy bots (Copy 1-33, 34-66, 67-100) were retired in run 6: copying a slice of the board trade for trade lost 11-49% in a day, matching the research finding that naive copying loses money after fees and delays.

**Where the leaderboard comes from** (`traders.py`): the arena pulls the recent trades of every pool it tracks from GeckoTerminal's free API, keeps 7 days of them, and every hour scores each wallet over the last 48 hours: realized profit at average cost plus a cautious value for what it still holds, ROI, win rate and volume. Bots are filtered out (MEV and sandwich bots that flip within a minute, wallets with hundreds of trades, dust spammers, program accounts, and, with a Helius key, any wallet that signs more than 6 transactions a minute on-chain), and the best 100 that are in profit make the board. A fresh database starts with an empty board: it needs a few hours of trades before wallets have closed enough round trips to rank, so the copy bots sit in cash until then. The board only knows wallets that traded tokens the arena watches, so it's "the best traders in our tokens", not all of Solana.

**Live signals:** with a Helius key (`ARENA_HELIUS_KEY` in `.env`, free plan: 1M credits a month), the arena subscribes to every top wallet and sees their swaps within seconds; one swap costs one credit, capped at 15,000 a day (`ARENA_TRADERS_HELIUS_PER_DAY`). Without a key, or while Helius is down, new trades show up from GeckoTerminal polling a few minutes late. Either way, copied trades fill on the next tick at the arena's price with your own route's fees, so the copy is always a little later and dearer than the original, as it would be live.

The **Top traders** section of the dashboard shows the leaderboard and the live feed of their trades. `ARENA_TRADERS=0` turns the tracker off; every setting is documented at the top of `traders.py`.

## The dashboard

The top of the page is the at-a-glance view: the stage with every agent's mascot, a card for the arena's leader and one per team (average result and best agent), and the announcer's latest line. Everything else sits in tabs under it, and the page remembers the last tab you opened (each tab also has its own link, like `localhost:8000/#usage`):

| Tab | What's in it |
|---|---|
| **Overview** | Standings (click anyone for their profile) and the equity chart: one line per team, or **Everyone** for every agent's line and trade markers |
| **Claude screens** | A screen per Claude showing what it's looking at right now: a live price chart of the coin it just traded, named in its last thought, holds, or (for the Shadow) its leader bought, with its entry, trades, position and latest thought |
| **Live feed** | Claude's decisions and every trade, with filters. The tab counts what's new since you last looked. |
| **Agents** | The full standings table, open positions and head to head |
| **Top traders** | The top-100 leaderboard, their live trades and who copies whom |
| **Who's really winning** | Luck checks, risk-adjusted numbers and the readiness checklist |
| **Usage** | Plan limits and per-Claude usage, with controls. The tab shows your 5-hour limit. |

## Dashboard extras

Each extra is its own file in `static/plugins/` and can be switched on or off in the **Settings** menu at the top right, which also holds Reset money. Your choices are remembered in your browser.

- **Ticker:** scrolling tape of every tracked token. Click one to open it on DexScreener.
- **Announcer:** play-by-play of trades, Claude's calls and lead changes. **Voice** reads it aloud.
- **Effects:** coin bursts on wins, smoke on losses, "takes 1st" banners, shooting stars, and a sky that follows your local time of day.
- **Sound / Notify:** 8-bit sound effects, and desktop notifications while the tab is in the background. The tab title and icon show who's leading.
- **Tick status:** shows when the arena last ticked and warns if it stalls. Click it for each Claude's status and CSV exports of trades, decisions and equity.
- **Agent profiles:** click any mascot, name or standings row, or press 1–5. Use ← → to flip between agents and Esc to close.
- **Feed filters:** filter Claude's decisions and the trades by agent, side, wins or losses, or by searching. Press / to search trades. Pause feed freezes a feed while you read. Click a token in the trades for its address and links.
- **Head to head:** Claudes vs the bots, achievement badges, and a mini equity chart per agent.

### Resetting the money

A money reset puts every agent back to the starting cash with no open positions, while keeping everything you'd want to keep: usage history, recordings, safety and rug checks, market memory and settings. The trades and equity so far are archived as a numbered season, so `python days.py` still counts them. Three ways to run it, each asking whether the Claudes keep the lessons in their journals:

- the **Reset money** button in the dashboard header
- `/arena-reset-money keep` or `/arena-reset-money wipe` in Claude Code (typed bare, it explains first)
- `python main.py --reset-money` when starting the arena

Every Claude journal is **backed up to `journal_backups/<date>_<time>.json`** before any reset, including a full `--reset`, so their lessons are never lost and can be used as learning data. The Claudes are told about the reset on their next look.

## Who's really winning

Raw P&L lies in memecoins: one lucky runner can top the board for days. The **Who's really winning** section on the dashboard (from `analytics.py`) shows, for every agent:

- **Luck check:** P&L without its single best trade (closed or still open) and without its worst rug, and how much of its lead comes from one trade.
- **Risk-adjusted numbers:** max drawdown, volatility, a Sharpe-like ratio (average 15-minute return divided by its spread, not annualised), profit factor, win rate, average win and loss, average hold.
- **Report card (run 7):** alpha against Hold SOL, Random and Graduates (percentage points better than each over the same time), fee drag (fees as a share of the starting $1,000), how much of the profit came from the 3 best trades (near 100% means it's mostly luck so far), and average win and loss.
- **Confidence (Claudes):** how likely each Claude truly beats Random, Hold SOL and Graduates, from a bootstrap over 15-minute returns. It says "not enough data yet" until there are 20 closed trades and 2 hours of history.
- **Cost-adjusted (Claudes):** P&L per dollar of API-price usage and per percent of your weekly limit.
- **Readiness for live money:** a checklist per Claude: at least 7 days of history, 100 closed trades, beats Random and Hold SOL with best trades removed, 90%+ confidence against both, max drawdown under 25%, profit factor over 1.2, and reliable calls. Treat a pass as "worth a small, careful live test", not a guarantee.

**Daily recap:** the header's *Daily recap* link opens `/recap`, a printable end-of-day page with standings, team totals, the day's best and worst trades with reasons, notable Claude decisions, luck-check verdicts, usage, and a short written summary. Pick any day with the date picker.

## Replay: test changes on a past day

While it runs, the arena records every market snapshot to `recordings/YYYY-MM-DD.jsonl.gz` (about 2–8 MB a day; a restart on the same day adds `.1`, `.2` files, and replay reads them all). `replay.py` re-runs agents on a recorded day in simulated time, so you can test a change on yesterday's exact market instead of waiting days:

```bash
python replay.py 2026-10-05                           # bots only: free, about a minute per day
python replay.py 2026-10-05 --agents all --yes        # everyone, Claudes included
python replay.py 2026-10-05 --compare my_brief.txt --yes
```

`--compare` is the main tuning tool: it runs the Claudes twice on the same day, once with the current instructions and once with the brief in your file, and prints the results side by side. Other options: `--agents "Sonnet 5.5,Sniper"`, `--from 09:00 --to 12:00`, `--seed N` (same seed, same result for bots), `--brief FILE`, `--serve 8012` (opens the normal dashboard on the replay's results), `--fast`.

Replays that include Claudes make **real Claude calls** and use your plan, so they print an estimate first and need `--yes`. Replay fills use the price-impact formula rather than live Jupiter quotes, and a replay never sends phone alerts.

## Phone alerts (optional)

Get a push notification on your phone when something worth knowing happens while the arena runs: a big closed trade, a rug, a lead change, your plan's usage crossing 50/75/90%, a Claude login or usage-limit error, the arena stalling (and recovering), and one daily digest. Alerts live in `notifier.py` and are off until you configure a channel in `.env`.

**With ntfy (free, no account):**

1. Install the ntfy app (Android or iPhone, https://ntfy.sh/app) or open https://ntfy.sh in a browser.
2. Subscribe to a topic with a hard-to-guess name, e.g. `arena-k9x2mq7f3wq`. Topics on ntfy.sh are public: anyone who guesses the name can read your alerts and post to it, so make it long and random.
3. Put `ARENA_NTFY_TOPIC=arena-k9x2mq7f3wq` in `.env` and restart the arena.

**With Discord:**

1. In a Discord server you own: channel settings > Integrations > Webhooks > New Webhook > Copy Webhook URL.
2. Put `ARENA_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...` in `.env` and restart the arena.
3. Never share that URL or commit `.env`: anyone with it can post to your channel.

Both can be on at once. `python notifier.py` sends one test message to whatever you configured. Alerts start from the moment the arena starts; a restart never replays old trades.

| Variable | Default | What it does |
|---|---|---|
| `ARENA_NTFY_TOPIC` | unset (off) | ntfy topic to post to |
| `ARENA_NTFY_SERVER` | `https://ntfy.sh` | ntfy server, if you self-host one |
| `ARENA_DISCORD_WEBHOOK` | unset (off) | Discord webhook URL |
| `ARENA_ALERTS` | all | Comma list of alert types: `trade`, `rug`, `leader`, `team`, `usage`, `error`, `stall`, `digest`, `bust` (a Claude lost a life) |
| `ARENA_ALERT_MIN_PNL` | `20` | Dollars of profit or loss a closed trade needs for a `trade` alert |
| `ARENA_ALERT_DIGEST_AT` | `21:00` | Local time of the daily digest |
| `ARENA_ALERT_QUIET` | none | Quiet hours, e.g. `23:00-07:00`; only critical alerts get through (a stall, usage at 90%, a rug of $50 or more) |
| `ARENA_ALERT_MAX_PER_HOUR` | `12` | Most messages per hour; bursts arrive as one message |
| `ARENA_ALERT_POLL` | `30` | Seconds between checks |

A **rug** is a sell that lost at least half its cost, or a held position that lost 80% of its value between two checks. A **lead change** is only reported once the new leader has stayed on top for two checks and leads by at least $5.

## How realistic the fills are

The arena aims to be close to what live trading on Solana would give you:

- **Real quotes:** buys and sells are priced with live Jupiter swap quotes for the exact size (falling back to an AMM formula when Jupiter is slow or rate-limited), plus your route's app and network fees (see What trading really costs).
- **Sellability:** every token gets a test sell quote. No route, or a sell returning under half its value, marks it red as a likely honeypot.
- **Failed transactions:** about 5% of orders fail (15% on tokens moving more than 50% in 5 minutes); nothing trades, the network fee is lost, and the agent is told.
- **Sandwich bots:** on the `bot` and `jupiter` routes, buying a token that's pumping costs 0.5-3% extra slippage, more for bigger buys. The `fomo` route has none (private routing).
- **Exits:** stops and targets are checked every 10 seconds between the 30-second ticks.
- **Crowded trades:** when several agents trade the same token in the same tick, each fill moves that pool for the next one, so piling into the same token costs more, as it would on-chain.

Settings (`.env`, all optional, each overriding the route's value): `ARENA_ROUTE=bot`, `ARENA_FEE=0.01`, `ARENA_MIN_FEE_USD=0`, `ARENA_POOL_FEE=0.0025`, `ARENA_PRIORITY_FEE_USD=0.25`, `ARENA_FAIL_RATE=0.05` (0 turns failures off), `ARENA_FAIL_RATE_PUMP=0.15`, `ARENA_MEV_MAX_PCT=3` (0 turns sandwich slippage off), `ARENA_JUPITER=1` (0 uses the formula only), `ARENA_FAST_EXIT_SECS=10` (0 turns fast exit checks off). The full list with explanations is at the top of `exchange.py`, `market.py` and `arena.py`.

## How the fake exchange keeps it honest

- **Fees:** your route's app fee and network fee on every trade, plus the pool's own fee.
- **Price impact:** fills are modelled like a real AMM pool, so a big buy in a thin pool gets a worse price.
- **Delay:** orders fill on the *next* tick (~30s later), not at the price the agent saw.
- **Liquidation value:** positions are valued at what you'd actually get selling now, not the screen price.
- **Rule caps:** no limit on a Claude's buy size by default (`ARENA_LLM_MAX_BUY_PCT`), moonshots at most 5% each, max 8 open positions (the Graduates bot 40).

Even so, real trading is usually worse: sniper bots, MEV, failed transactions and rugs faster than a 30-second tick.

## Reading the results

- Let it run for **days**, ideally a couple of weeks. A few lucky trades mean nothing.
- An agent only has an edge if it clearly beats **both** Random and Hold SOL over hundreds of trades. The readiness checklist uses those two as its benchmarks.
- Check **Max drawdown**: a strategy that hits +40% but dropped 70% along the way would wreck real money.

## Files

- `market.py` – live data feed, risk checks, mock market
- `exchange.py` – routes, fees and price-impact math
- `agents.py` – the roster (Team Claude, Team Bots and Team Copy)
- `copy_agents.py` – the retired mechanical copy bots (kept for replays)
- `strategy_room.py` – the Claudes' strategy chat and its coin filter
- `signals.py` – structural signals (net flow, churn, buyers, holders, creator selling) and the safety vetoes
- `traders.py` – the top-100 leaderboard and live copy signals (GeckoTerminal + Helius)
- `pumpfun.py` – the pump.fun launch and graduation feed (PumpPortal)
- `bots.py` – the rule-based bots
- `claude_agents.py` – the Claude agents, personalities and Claude Code calls
- `usage.py` – usage tracking and the slow / pause / cap controls
- `extras.py` – health check and CSV exports
- `notifier.py` – phone alerts through ntfy or Discord
- `analytics.py` – luck check, risk-adjusted numbers, confidence and readiness (and `recap.html`, the daily recap)
- `recorder.py`, `replay.py` – market recording and replays
- `market_memory.py` – what kinds of entries paid off lately
- `rugdata.py` – holder concentration and RugCheck data
- `days.py` – day-by-day results and market mood
- `static/plugins/` – the dashboard extras, one file each
- `.claude/skills/arena-usage/` – the Claude Code usage pane (a Claude Code mod)
- `arena.py` – the main loop and rule enforcement
- `db.py` – SQLite storage
- `main.py` – starts everything and serves the dashboard
- `dashboard.html` – the localhost page (the stage, decision feed, trades, chart and standings)
