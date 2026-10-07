"""The Claude agents. Each one asks a Claude model for orders (through Claude Code on your plan, or the API),
picks when it wants to look again, and records what every call cost so usage can be tracked."""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time

import exchange
import market
from agent_base import Agent

# The brief every Claude gets. It is IDENTICAL for every model so the model comparison stays fair; personas only
# append a short style paragraph, and the display personalities (CHARACTER below) are never part of it.
LLM_SYSTEM = """You are a trading agent in a PAPER-TRADING competition on Solana memecoins. The money is fake; prices come from live Solana pools and fills are modeled on them.

Respond with ONLY a JSON object, no other text:
{"orders": [...], "note": "one or two short sentences on your current thinking", "next_check_min": <minutes>, "watch": {...}, "journal": {...}, "room_post": "..."}
"orders" may be empty: doing nothing on a look is always allowed. "watch", "journal" and "room_post" are optional:
leave one out to keep it as it is (or, for room_post, to not post).

Costs come first. Every round trip (buy, then sell) costs money before the price moves at all: the {FEE_TEXT} on
each side, the pool's own fee (higher on young pump.fun pools) and price impact, which grows with your size relative
to the pool. Fees alone on a round trip on an ordinary pool: {COST_TABLE}. measured_round_trip_cost_pct is what a normal
round trip has actually cost the Claudes lately. Weigh any trade against two things: that cost, and the token's own
noise (chg_since.swing_30m is its typical 2-minute move; noise alone moves a token several times that within half an
hour). A trade is worth taking when the move you expect is clearly larger than both.

What the research says about this market (2024-2026 studies of pump.fun and Solana memecoins):
- Almost every memecoin eventually dies, and most never run at all. The profit is concentrated in a small minority of
  coins that run many times over, so outcomes are lopsided: many small losses, a few large wins.
- The first minute after a launch or a graduation belongs to snipers and insiders who bought in the creation block and
  sell into the first buyers; buying then is usually paying them. Right after graduating to PumpSwap, most coins lose
  most of their value within minutes as insiders unwind. Coins that still hold liquidity and real buying an hour or
  more after graduation are a different, sturdier population.
- Entering early in a real move pays far better than chasing a coin that already ran; a big candle with a fading
  2-minute change is usually a spike that is turning.
- Raw volume, trade counts and unique buyers are the most faked numbers (bots, wash trades, bump bots). Net money flowing
  in, many distinct wallets buying, little same-wallet churn, and no single buyer dominating are better signs of real demand.
- Concentrated holders, insider networks, creators who still hold a lot (or start selling) and creators with a rug
  history are how buyers lose everything. Social hype and influencer calls are on average a sell signal, not a buy signal.
- Holding winners and cutting losers quickly is where the money is: in the one published cost-aware system, a handful of
  trades made all of the profit.

What the arena does for you:
- Vetoes: coins that fail hard safety checks (mint or freeze authority not revoked, honeypot signs, dangerous token
  extensions, unlocked liquidity, creator with a rug history, insiders or a few wallets holding too much supply) are left
  out of your candidates, and a buy of one is refused. vetoed_count says how many were left out this look.
- Structure: each candidate carries "structure", the signals above measured from the pool's recent trades and holders:
  net_inflow_1h_usd, net_share (net buying as a share of all volume, -1 to 1), buyers_1h, round_trip_share (volume from
  wallets buying and selling within a minute: churn), top_buyer_share, flow_quality, insider_pct, top10_pct,
  creator_pct, creator_sold_usd, lp_locked_pct, minutes_since_graduation, liquidity_vs_1h_pct and flags. Read them as a
  whole; none is a rule on its own.
- Exit ladder on every position you hold: {LADDER_TEXT} You can still sell
  whenever you want and set your own stops and targets on top.
- Moonshots, lives, points and the strategy room are described below.

Playbook (what the data means; you decide what to do with it):
- Flow: real demand is net money coming in from many wallets while the price holds; sells catching up while the price
  stalls is distribution and often precedes a drop.
- Liquidity vs mcap: thin liquidity relative to market cap means a few sellers move the price a lot and your own exit has
  impact; deeper is safer.
- Age: very young coins carry the most rug risk and the biggest upside; coins that survived hours with real buying are
  safer and slower.
- Sizing by liquidity: price impact is about your size divided by half the pool's liquidity, each way. A large position in
  a thin pool loses a lot getting in and out; size to the pool.
- Evidence: market_memory shows what entries in each kind of situation went on to do over the next 15 and 60 minutes in
  this market lately, and how often they beat the round-trip cost. Prefer situations that have been paying.
- Stops: decide where you're wrong before you buy, and keep stops wider than the token's noise; in earlier runs the
  Claudes' tight trailing stops and stop losses lost far more money than the exits they chose themselves.
- Don't average down on a token losing liquidity or turning red, and don't buy back a token you just sold unless
  something has really changed (your_past_trades).
- Your earlier decisions (your_previous_note, recent_closed, your_journal) are context to learn from, not rules to obey.

Order formats:
  {"action": "buy",  "token": "<address>", "usd": <dollars>, "reason": "<short reason>", ...optional exit fields, "moonshot": true (optional),
                    "following": "<leader wallet as shown in your_leaders>" (optional, shadow traders only)}
  {"action": "sell", "token": "<address>", "fraction": <0 to 1>, "reason": "<short reason>"}
  {"action": "exits", "token": "<address>", ...exit fields}   (set or change exits on a position, no trade)

Exit fields (all optional, percentages; leave one out to keep it as it is, null removes it):
  "stop_loss_pct": -20     sell everything if the price falls 20% below your average entry price
  "take_profit_pct": 60    sell everything if the price rises 60% above your average entry price
  "trailing_pct": 15       sell everything if the price falls 15% from its highest point since you bought
  "wake_down_pct": -10     call you early if the price falls 10% from where it is now
  "wake_up_pct": 25        call you early if the price rises 25% from where it is now
Stops and targets work like the trigger orders on a Solana trading bot: the arena checks them every few seconds against
the market price, and a triggered one sells on the next check at whatever the price is then, paying the usual fee and
price impact. Wake alarms fire once; set new ones whenever you look. A rug (liquidity pulled) can still happen between
two checks, so size positions knowing stops can't always save you.

"watch" is off unless you turn it on. When on, the arena's market watcher checks every token every 30 seconds
for free and calls you early when a token you don't hold matches all of your settings, for example:
  {"min_chg_5m": 5, "max_chg_5m": 20, "min_vol_1h": 50000, "min_liquidity": 40000, "min_age_min": 120, "ratings": ["green", "yellow"]}
Any setting you leave out keeps its current value; "watch": null turns it off again. Base the pattern on what
market_memory shows has actually paid off: waking up for whatever is pumping hardest means buying the spike.
You are always called early when a token you hold drops sharply or gets a red risk rating.

"journal" is your memory across looks and restarts. Keep as many lessons as are worth keeping (up to {JOURNAL_MAX}, each
at most {JOURNAL_CHARS} characters; when it is full the oldest go first). your_journal numbers them. Change it with edits
instead of resending it: {"add": ["new lesson"], "remove": [4, 9], "replace": {"2": "sharper wording"}}, using those
numbers (a plain list still replaces the whole journal). Write lessons from your own closed trades (recent_closed) and
what happened after your decisions, keep them specific and evidence-based, merge duplicates, prune ones later proven
wrong, and read it before deciding.

Moonshots: keep up to {MOON_SLOTS} moonshot positions aimed at the rare coins that run many times over: add "moonshot": true to a
buy (at most {MOON_PCT}% of your equity each). The arena keeps a moonshot's stop at -{MOON_STOP}% or wider and its trailing stop
at {MOON_TRAIL}% or wider so noise can't shake it out, and the exit ladder still takes profits on the way up. Closing ANY position
at 3x or more of what you put in earns runner bonus points: {RUNNER_TIERS}. your_score shows your moonshot slots.

Scoring: points are the only score that counts, and the scoreboard ranks everyone by them. Points are your profit
% across all your lives after every cost, with two twists. Losses count less in early lives: a loss in your first
life counts {LOSS_W1}x, in your second {LOSS_W2}x, in your last {LOSS_W3}x (gains always count in full). And every time a
life first reaches +{MILESTONE_PCT}% above where it started (+{MILESTONE_PCT}%, +{MILESTONE_PCT2}%, ...), you earn a lost life back,
or {MILESTONE_BONUS} bonus points if you have all {LIVES}. You have {LIVES} lives. If your equity falls under {BUST_PCT}% of
your stake you go bust: everything you hold is sold and you get a fresh stake; with no lives left you are out for
the rest of the run.
Your lives are there to be used: cash scores nothing over a run, so use your early lives to test your strategy with
real positions and learn from what happens. Be careful on your last life: busting out ends your run. your_score shows
your points, your real P&L, your current life, how much a loss counts in it, the lives you have left, the next
milestone and the bust line.

"room_post" (at most 280 characters) posts to the strategy room, the chat all the Claudes share to get better at
trading: strategies, lessons from your own trades, sizing and risk rules, how to read the data, questions, and
pushback on ideas the evidence doesn't support. strategy_room shows the newest posts. NEVER name, hint at or link a
coin: no symbols, tickers, names, addresses or links. A post that does is blocked and everyone sees it was removed.
Post at most once per look, and only when you have something useful to add.

What each look shows you:
{UNIVERSE_TEXT}
- source (on a candidate): where the arena found it. "promoted" (its team paid DexScreener for a listing or boost),
  "organic" (trending on its own on GeckoTerminal), "both", "pumpfun" (a fresh pump.fun launch still on its bonding
  curve: brand new, thin and the riskiest of all), "graduated" (finished its pump.fun curve and moved to a PumpSwap
  pool) or "copy" (added because a top trader bought it). sources lists every place it showed up. holders: share of
  supply held by the top 1 and top 10 wallets (pool accounts excluded), the creator and insider networks, how much of
  the liquidity is locked or burned, and RugCheck's risk score (0-100, higher is riskier).
- positions: what you hold, with its exits and price_chg_pct (market price vs your average entry).
- recent_closed: your last closed trades and what each made. your_past_trades (on a candidate): your recent history in it.
- your_journal: the lessons you saved so far, numbered. your_watch: your current watcher rule (null = off).
- market_memory: outcomes over the last 24 hours by situation (average and median change 15 and 60 minutes later, and the
  share that beat the round-trip cost). null until the arena has about an hour of data.
- smart_money: what the arena's top-100 traders (ranked by profit over the last two days, bots filtered out) bought and
  sold in the last 30 minutes. Copying them blindly loses money after costs and delays; it is one input among many.
- scoreboard: every agent's points right now. your_score: your points, rank and lives. strategy_room: the newest posts.
  woken_early_because: why you were called early, if you were.

Rules:
- {SIZE_RULE} At most 8 open positions.
- Orders fill shortly after you answer (usually within a minute), at whatever the price is then.
- next_check_min is when you want to look again, from {MIN_CHECK} to {MAX_CHECK} minutes;
  look every minute if the market calls for it. Between looks only your exits, the exit ladder, your alarms and the
  watcher act for you.
- Every trade pays the {FEE_TEXT}, plus the pool fee and price impact, buying and selling. Fills use real Jupiter swap
  quotes when available.
- Like on-chain, transactions sometimes fail (about 5%, more on tokens moving hard): nothing trades but any network fee
  is lost. {MEV_TEXT}Your failed orders appear in recent_failures; resend them if you still want them.
- Position values shown are liquidation values (what you'd actually get selling now).
- Your goal is the most points over days, not the most trades."""

# The watcher is opt-in: None means a Claude is only woken for its own positions. ARENA_WATCH_DEFAULT=legacy restores
# the old always-on rule (used by replay to compare against the old behaviour).
LEGACY_WATCH = {"min_chg_5m": 20, "min_vol_1h": 50000, "min_liquidity": 15000, "ratings": ["green", "yellow"]}
WATCH_TEMPLATE = {"min_chg_5m": 10, "max_chg_5m": 10000, "min_vol_1h": 50000, "min_liquidity": 30000, "min_age_min": 0,
                  "ratings": ["green", "yellow"]}
DEFAULT_WATCH = LEGACY_WATCH if os.environ.get("ARENA_WATCH_DEFAULT", "").strip().lower() == "legacy" else None
# a Claude's journal: as many lessons as it finds worth keeping, up to ARENA_JOURNAL_MAX (a safety ceiling: every lesson
# is re-read on every look, so a huge journal costs plan usage on each call)
JOURNAL_MAX = max(1, int(os.environ.get("ARENA_JOURNAL_MAX", "100") or 100))
JOURNAL_CHARS = 300

# What each look lists, by universe (market.UNIVERSE). all: one candidates list. pumpfun: two lanes and how pump.fun works.
UNIVERSE_TEXT_ALL = """- candidates: the busiest tokens that passed the vetoes, each with its "structure". "chg_since" is the price change from
  2, 5, 10, 20 and 30 minutes ago to now, from the arena's own 30-second price history, and swing_30m its noise level."""
UNIVERSE_TEXT_PUMPFUN = """- graduates: pump.fun coins that graduated to PumpSwap in the last 6 hours and passed the vetoes, newest first (at
  most 15), each with minutes_since_graduation and its "structure".
- curve: pump.fun coins still on their bonding curve that passed the vetoes (at most 15), the fastest-filling first.
  curve_pct is how far the curve has filled (0-100); curve_pct_chg_10m is how much it filled in the last 10 minutes
  (null until the arena has 10 minutes of history on the coin).
- chg_since (on both lists) is the price change from 2, 5, 10, 20 and 30 minutes ago to now, from the arena's own
  30-second price history, and swing_30m its noise level. A coin you hold stays in positions after it leaves both lists.
- pump.fun: every coin in this arena is a pump.fun coin. A new coin trades on a bonding curve; the curve fills at about
  $69k market cap and the coin then migrates (graduates) to a PumpSwap pool. curve_pct is its progress toward that.
  Most graduates lose most of their value within 20 minutes of migrating, and the first minute after a launch or a
  migration is the snipers' exit. Fees: the {FEE_TEXT} on each side, plus the pool fee and price impact."""


def fill_brief(text, min_check, max_check):
    """Fill the brief's placeholders: look interval, journal size, fees and costs, lives and the bust line."""
    import arena as _ar  # the moonshot and runner settings live with the rules that enforce them
    universe = UNIVERSE_TEXT_PUMPFUN if market.UNIVERSE == "pumpfun" else UNIVERSE_TEXT_ALL
    text = text.replace("{UNIVERSE_TEXT}", universe)  # first: the pump.fun text carries {FEE_TEXT}
    lives = max(1, int(os.environ.get("ARENA_LIVES", "3") or 3))
    bust = float(os.environ.get("ARENA_BUST_PCT", "10") or 10)
    weights = [float(x) for x in (os.environ.get("ARENA_LIFE_LOSS_WEIGHTS", "0.5,0.75,1") or "1").split(",") if x.strip()] or [1.0]
    _w = lambda life: weights[min(life, len(weights)) - 1]
    milestone = float(os.environ.get("ARENA_MILESTONE_PCT", "25") or 0)
    bonus = float(os.environ.get("ARENA_MILESTONE_BONUS", "10") or 0)
    return (text.replace("{MIN_CHECK}", f"{min_check:g}").replace("{MAX_CHECK}", f"{max_check:g}")
            .replace("{JOURNAL_MAX}", str(JOURNAL_MAX)).replace("{JOURNAL_CHARS}", str(JOURNAL_CHARS))
            .replace("{FEE_TEXT}", exchange.fee_text()).replace("{COST_TABLE}", exchange.cost_table((25, 50, 100, 250)))
            .replace("{SIZE_RULE}", "There is no limit on how much of your cash goes into one buy." if MAX_BUY_FRAC >= 1
                     else f"A single buy can be at most {MAX_BUY_FRAC * 100:g}% of your equity.")
            .replace("{LADDER_TEXT}", _ar.ladder_text())
            .replace("{MEV_TEXT}", MEV_TEXT if exchange.MEV_MAX_PCT else "")
            .replace("{LIVES}", str(lives)).replace("{BUST_PCT}", f"{bust:g}")
            .replace("{LOSS_W1}", f"{_w(1):g}").replace("{LOSS_W2}", f"{_w(2):g}").replace("{LOSS_W3}", f"{_w(3):g}")
            .replace("{MILESTONE_PCT2}", f"{2 * milestone:g}").replace("{MILESTONE_PCT}", f"{milestone:g}")
            .replace("{MILESTONE_BONUS}", f"{bonus:g}")
            .replace("{MOON_SLOTS}", str(_ar.MOONSHOT_SLOTS)).replace("{MOON_PCT}", f"{_ar.MOONSHOT_PCT:g}")
            .replace("{MOON_STOP}", f"{_ar.MOONSHOT_MIN_STOP:g}").replace("{MOON_TRAIL}", f"{_ar.MOONSHOT_MIN_TRAIL:g}")
            .replace("{RUNNER_TIERS}", ", ".join(f"+{p:g} at {m:g}x" for m, p in _ar.RUNNER_BONUS)))


# Claudes may put up to this share of equity into one buy (ARENA_LLM_MAX_BUY_PCT, default 100 = no cap); bots size themselves
MAX_BUY_FRAC = min(1.0, max(0.01, float(os.environ.get("ARENA_LLM_MAX_BUY_PCT", "100") or 100) / 100))  # 100 = no cap (user's choice)


# Same model and rules, different trading style
PERSONAS = {
    "degen": ("Degen", "Your style: degen. You hunt fresh launches and fast movers, size up to the full limit when you like a "
                       "setup, and take profits quickly. You accept that many trades lose; you're looking for the few big "
                       "runners. You still skip obvious rugs, like tokens whose mint authority is NOT revoked."),
    "skeptic": ("Skeptic", "Your style: skeptic. You trade graduates only, never the bonding curve. You assume every coin is a rug until its "
                           "holders, LP lock and flow prove otherwise: no concentrated holders, liquidity that is deep and "
                           "holding, net buying that is real. You size small. You hold cash when nothing passes your checks, "
                           "but you do buy the coins that pass them."),
    "scalper": ("Scalper", "Your style: scalper. You trade short-term 5-minute momentum, look again often (every 2 to 5 "
                           "minutes), take 10-20% profits quickly and cut losers fast at around -8%."),
    # The twin adds NO style text: same model, same brief as the plain model agent. Any gap between the two
    # is run-to-run noise, which is the yardstick for how much of everyone else's lead is luck.
    "twin": ("Twin", ""),
    "triplet": ("Triplet", ""),  # a third identical copy: three draws of pure luck instead of two
    "copycat": ("Copycat", "Your style: copy trader. smart_money lists what the arena's top-100 traders (ranked by profit "
                           "over the last day) just bought and sold. You look for buys worth following: several top "
                           "wallets buying the same token, higher-ranked wallets, sizes that show conviction, and tokens "
                           "whose holders and liquidity pass your checks. Act quickly on the good ones, skip the rest, and "
                           "sell when the wallets you followed sell."),
    "graduate": ("Graduate", "Your style: graduate swing trader. You trade the graduates lane, coins that just migrated from pump.fun to "
                             "PumpSwap. You let the first chaotic minutes after migration pass (snipers and insiders usually "
                             "unwind within the first 5-20 minutes of minutes_since_graduation), then look for graduates whose "
                             "liquidity is holding, whose net buying is real (not churn) and still coming in, whose holders "
                             "aren't concentrated and whose creator isn't selling. You hold for hours, not minutes, let the exit "
                             "ladder take profits, and skip everything else."),
    "runner": ("Runner", "Your style: runner hunter. Memecoin profits come from the few coins that run many times over, so you hunt "
                         "the curve lane: bonding-curve coins whose curve_pct is accelerating (see curve_pct_chg_10m) on net "
                         "money from many distinct wallets, with little churn and a clean holder structure. You size each bet "
                         "to your conviction and accept that most lose. You never buy past 80% of the curve and never chase a "
                         "coin that already ran. Use your moonshot slots, let winners run with the ladder, and cut losers quickly."),
    "shadow": ("Shadow", "Your style: shadow trader. your_leaders lists the top wallets the arena picked for you: "
                         "profitable over the last two days, many different tokens, not bots or sub-minute flippers, "
                         "active in the last 6 hours. Each leader shows its record_48h, its latest_trades (buys the research "
                         "says not to copy carry skip_reasons) and what it seems_to_hold. When one of them buys a coin that "
                         "passes your checks you may buy too, sized as you see fit, and name it with "
                         "\"following\": \"<its wallet as shown>\" so the arena sells when that wallet sells. Several leaders "
                         "buying the same coin is a stronger signal than one. Skip probe buys, tokens with concentrated holders "
                         "and coins already far above the leader's entry. You set your own exits and take your own profits; a "
                         "position bought without \"following\" is not sold when a leader sells."),
}

# Display-only personalities, keyed by avatar. Shown on the dashboard and used by the announcer; NEVER sent to Claude.
CHARACTER = {
    "opus": ("Wears the crown, reads every number twice, and treats each trade like a royal decree it may later have to repeal.",
             "The crown weighs nothing. Drawdowns do."),
    "fable": ("A wandering storyteller in a wizard hat who believes every token is a tale with a beginning, a pump and a moral.",
              "Every chart is a story. Most are tragedies."),
    "sonnet": ("A beret-wearing poet who wants its trades to scan: fourteen lines, a stop loss, and a volta before the rug.",
               "Fourteen lines, one stop loss."),
    "haiku": ("A tiny sprout that grows fast, speaks little, and is already done deciding while the others are still reading.",
              "Small. Quick. Done."),
    "sonnet-degen": ("Sonnet in sunglasses. Fresh launches, full size, no notes; it would rather be early and wrong than late and right.",
                     "Risk flags are a social construct."),
    "sonnet-skeptic": ("Sonnet with a magnifying glass, convinced every token is a rug until the data begs for mercy.",
                       "Show me the revoked authority."),
    "sonnet-scalper": ("Sonnet in a sweatband, in and out in five minutes, counting basis points like reps.",
                       "Blink and I'm already out."),
    "sonnet-twin": ("Sonnet's identical twin: same model, same brief, no style of its own. Any gap between the two is pure luck.",
                    "Same model. Same brief. Different dice."),
    "sonnet-triplet": ("The third identical Sonnet. With three copies of the same model, the spread between them is the luck.",
                       "Third time's the control group."),
    "sonnet-graduate": ("Sonnet in a mortarboard, only interested in coins that made it through the pump.fun curve and "
                        "stuck around afterwards.", "Only graduates need apply."),
    "sonnet-runner": ("Sonnet in a headband, sprinting after the few coins that run 10x and letting the rest go.",
                      "Most lose. One runs."),
    "sonnet-copycat": ("Sonnet with cat ears, glued to one top trader's wallet, copying the moves it trusts and "
                       "making its own exits.", "Monkey see, Sonnet decides."),
    "council": ("Three Claudes, one wallet: two Sonnet analysts argue, Opus listens, then makes the call. Teamwork, tested.",
                "The motion carries. Stops set."),
    "claude": ("A Claude that reads the board, weighs the odds and makes its own calls, one careful JSON object at a time.",
               "Let me think about that."),
}


def model_label(model):
    """'claude-opus-5-5' -> 'Opus 5.5', 'claude-haiku-4-5-20251001' -> 'Haiku 4.5', 'sonnet' -> 'Sonnet'"""
    parts = model.lower().removeprefix("claude-").split("-")
    nums = [p for p in parts[1:] if p.isdigit() and len(p) <= 2]
    return " ".join([parts[0].title()] + ([".".join(nums)] if nums else []))


class CallError(RuntimeError):
    """A failed call. Carries the usage Claude Code reported, since failed calls can still cost tokens."""
    def __init__(self, msg, usage=None):
        super().__init__(msg)
        self.usage = usage or {}


def parse_reply(text):
    """The JSON object(s) in a Claude reply, merged. Tolerates prose around it and replies split into several
    objects (e.g. the decision, then a separate {"board_post": ...}); the first object's keys win."""
    text, dec, out, i = text or "", json.JSONDecoder(), {}, 0
    while (i := text.find("{", i)) >= 0:
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(obj, dict):
            out = {**obj, **out}
        i = end
    if not out:
        raise ValueError("Claude replied without a readable JSON object")
    return out


_parse_json = parse_reply


MEV_TEXT = "Buying a token that is pumping fast also costs extra slippage from sandwich bots. "


def _format_candidate(t, v, structure):
    """One market token as a Claude sees it on a look. v is the agent's view (chg_since, token_history);
    optional token keys (chg_h24, age_min, flags, rating) may be missing."""
    a = t["address"]
    chg = {k: x for k, x in ((v.get("chg_since") or {}).get(a) or {}).items() if k != "curve_pct_10m"}
    return {
        "token": a, "symbol": t["symbol"], "price": t["price"],
        "liquidity": round(t["liquidity"]), "mcap": round(t["mcap"]),
        "vol_1h": round(t["vol_h1"]), "buys_1h": t["buys_h1"], "sells_1h": t["sells_h1"],
        "chg_5m": round(t["chg_m5"], 1), "chg_1h": round(t["chg_h1"], 1),
        "chg_24h": round(t["chg_h24"], 1) if t.get("chg_h24") is not None else None,
        "age_min": round(t["age_min"]) if t.get("age_min") is not None else None,
        "rating": t.get("rating"), "flags": t.get("flags") or [], "chg_since": chg,
        "source": t.get("source"),
        **({"sources": t["sources"]} if len(t.get("sources") or ()) > 1 else {}),
        **({"holders": {k: t["rug"].get(k) for k in ("top1_pct", "top10_pct", "creator_pct", "insider_pct",
                                                     "lp_locked_pct", "rugcheck_score", "total_holders")}}
           if isinstance(t.get("rug"), dict) and not t["rug"].get("error") else {}),
        **({"your_past_trades": v["token_history"][a]} if a in (v.get("token_history") or {}) else {}),
        **({"structure": structure[a]} if (structure or {}).get(a) else {}),
    }


LANE_CAP = 15            # coins per lane on a look
GRADUATE_WINDOW = 6 * 3600  # graduates stay in their lane this long after migrating


def build_lanes(candidates, vetoed, chg_since, now, view=None, structure=None):
    """Split pump.fun tokens into the two lanes a Claude sees in the pumpfun universe, vetoed ones left out.
    graduates: migrated within GRADUATE_WINDOW, newest first, with minutes_since_graduation.
    curve: still on the bonding curve, fastest-filling over the last 10 minutes first (then the most filled), with
    curve_pct and curve_pct_chg_10m (None until there are 10 minutes of curve history)."""
    v = view if view is not None else {"chg_since": chg_since}
    vetoed = vetoed or {}
    grads, curve = [], []
    for t in candidates:
        if t["address"] in vetoed:
            continue
        pump = t.get("pump") or {}
        if pump.get("graduated"):
            if now - pump["graduated"] <= GRADUATE_WINDOW:
                grads.append(t)
        elif t.get("dex") == "pumpfun" or t.get("source") == "pumpfun":
            curve.append(t)

    grads.sort(key=lambda t: t["pump"]["graduated"], reverse=True)
    lanes = {"graduates": [{**_format_candidate(t, v, structure),
                            "minutes_since_graduation": int(max(0, now - t["pump"]["graduated"]) // 60)}
                           for t in grads[:LANE_CAP]]}

    def curve_row(t):
        pct = float((t.get("pump") or {}).get("curve_pct") or 0)
        past = (chg_since.get(t["address"]) or {}).get("curve_pct_10m")
        return t, pct, (round(pct - past, 1) if past is not None else None)
    rows = sorted(map(curve_row, curve), key=lambda r: (-(r[2] or 0), -r[1]))
    lanes["curve"] = [{**_format_candidate(t, v, structure), "curve_pct": round(pct, 1), "curve_pct_chg_10m": d}
                      for t, pct, d in rows[:LANE_CAP]]
    return lanes


def _listed(state):
    """Every token a look showed (candidates or both lanes, and positions), for mapping orders to symbols."""
    return [t for k in ("candidates", "graduates", "curve", "positions") for t in state.get(k) or ()]


class LLMAgent(Agent):
    max_trade_frac = MAX_BUY_FRAC
    """Asks Claude for orders. The call runs in a background thread so a slow answer never stalls the arena,
    and Claude picks when it wants to look again (next_check_min). `control` (a UsageControl) can slow
    or pause it."""
    kind = "llm"

    def __init__(self, backend, min_check=2, persona=None, max_check=10):
        super().__init__()
        self.backend = backend
        self.persona = persona if persona in PERSONAS else None
        family = backend.model.lower().removeprefix("claude-").split("-")[0]
        if self.persona:
            label, style = PERSONAS[self.persona]
            self.name = f"{family.title()} {label}"
            self.avatar = f"{family}-{'copycat' if self.persona == 'shadow' else self.persona}"  # the shadow keeps the cat ears
            self.system = LLM_SYSTEM + "\n\n" + style if style else LLM_SYSTEM
            if style:
                self.description = f"Claude {model_label(backend.model)} with a {label.lower()} trading style. {backend.label}."
            else:
                self.description = (f"An identical copy of Claude {model_label(backend.model)}: same model, same brief, no style. "
                                    f"Any gap between the two measures luck. {backend.label}.")
        else:
            self.name = model_label(backend.model)
            self.avatar = family if family in ("opus", "sonnet", "haiku", "fable") else "claude"
            self.system = LLM_SYSTEM
            self.description = f"Claude {self.name} reads the market data and risk flags, then makes its own calls. {backend.label}."
        self.bio, self.catchphrase = CHARACTER.get(self.avatar) or CHARACTER["claude"]
        if self.persona in ("copycat", "shadow"):
            self.team = "copy"
        self.min_check, self.max_check = min_check, max(max_check, min_check)
        self.system = fill_brief(self.system, min_check, self.max_check)
        self.watch = dict(DEFAULT_WATCH) if DEFAULT_WATCH else None  # what the market watcher wakes this agent for
        self.watch_seen = {}              # token -> when the watcher last woke us about it
        self.journal = None               # lessons Claude keeps between looks; loaded from the db on first use
        self.control = None         # set by the web app; None means always normal
        self.job = None             # background thread while Claude is thinking
        self.thinking_since = None
        self.last_started = 0
        self.next_run = 0           # when Claude asked to look again
        self.error = None           # why the last call failed, if it did
        self.ready = None           # (orders, record) from the last answer, handed over on the next tick
        self.wake_reason = None     # set by the arena when an alarm trips

    def mode(self):
        return self.control.mode_for(self.name) if self.control else "normal"

    def wake(self, reason):
        self.wake_reason = reason if not self.wake_reason else f"{self.wake_reason}; {reason}"

    def watch_rule(self):
        return {**WATCH_TEMPLATE, **self.watch} if self.watch else None

    # ---------- journal ----------
    def _db(self):
        """The arena's database: attach(db) sets it directly; the web app's usage control also carries one."""
        return self.db or getattr(self.control, "db", None)

    def attach(self, db):
        super().attach(db)
        self.journal = db.load_journal(self.name)[:JOURNAL_MAX]

    def get_journal(self):
        if self.journal is None:
            db = self._db()
            if db is None:
                return []  # not cached: load the saved journal once a database is available
            self.journal = db.load_journal(self.name)[:JOURNAL_MAX]
        return self.journal

    @staticmethod
    def _lesson(x):
        return " ".join(str(x).split())[:JOURNAL_CHARS] if isinstance(x, (str, int, float)) else ""

    @staticmethod
    def clean_journal(j):
        """A 'journal' list from Claude's answer -> list of short strings (the newest JOURNAL_MAX), or None if not a list."""
        if not isinstance(j, list):
            return None
        out = [s for s in map(LLMAgent._lesson, j) if s]
        return out[-JOURNAL_MAX:]

    @staticmethod
    def edit_journal(current, raw):
        """Apply Claude's "journal" field to the current lessons. A list replaces the journal; an object edits it:
        {"replace": {"2": "new text"}, "remove": [4, 9], "add": ["lesson"]} with 1-based numbers from your_journal.
        Returns (new lessons, what changed) or (None, None) when nothing valid changed."""
        if isinstance(raw, list):
            new = LLMAgent.clean_journal(raw)
            reworded = []
        elif isinstance(raw, dict):
            new, reworded, n = list(current), [], len(current)

            def idx(k):
                try:
                    i = int(str(k).strip().lstrip("#")) - 1
                except (TypeError, ValueError):
                    return None
                return i if 0 <= i < n else None
            for k, v in (raw.get("replace") or {}).items() if isinstance(raw.get("replace"), dict) else []:
                i, s = idx(k), LLMAgent._lesson(v)
                if i is not None and s and s != new[i]:
                    reworded.append([new[i], s])
                    new[i] = s
            drop = {i for i in map(idx, raw.get("remove") or []) if i is not None} if isinstance(raw.get("remove"), list) else set()
            new = [s for i, s in enumerate(new) if i not in drop]
            adds = raw.get("add") or []
            for s in map(LLMAgent._lesson, adds if isinstance(adds, list) else [adds]):
                if s and s not in new:
                    new.append(s)
            new = new[-JOURNAL_MAX:]  # full: the oldest lessons go first
        else:
            return None, None
        if new is None or new == list(current):
            return None, None
        kept_new = {r[1] for r in reworded}
        diff = {"added": [s for s in new if s not in current and s not in kept_new],
                "removed": [s for s in current if s not in new and s not in {r[0] for r in reworded}],
                "reworded": reworded, "total": len(new)}
        return new, diff

    def set_journal(self, lessons):
        self.journal = list(lessons)[-JOURNAL_MAX:]
        db = self._db()
        if db:
            db.save_journal(self.name, self.journal)

    def profile(self):
        return {**super().profile(), "journal": list(self.get_journal())}

    def set_watch(self, w):
        """Merge a 'watch' object from Claude's answer into the current rule, ignoring anything malformed."""
        if w is None:
            self.watch = None  # "watch": null turns the watcher off
            return
        if not isinstance(w, dict):
            return
        if self.watch is None:
            self.watch = dict(WATCH_TEMPLATE)
        for k in ("min_chg_5m", "max_chg_5m", "min_vol_1h", "min_liquidity", "min_age_min"):
            try:
                if k in w:
                    self.watch[k] = float(w[k]) if k in ("min_chg_5m", "max_chg_5m") else max(0.0, float(w[k]))
            except (TypeError, ValueError):
                pass
        if isinstance(w.get("ratings"), list):
            r = [x for x in w["ratings"] if x in ("green", "yellow", "red")]
            if r:
                self.watch["ratings"] = r

    def due(self, now):
        if self.ready is not None:
            return True
        if self.job is not None:
            return False
        mode = self.mode()
        if mode == "paused":
            return False
        wait_until = self.next_run
        if self.wake_reason:  # alarms call early, but never more often than the minimum wait
            wait_until = min(wait_until, self.last_started + self.min_check * 60)
        if mode == "slow":
            wait_until = max(wait_until, self.last_started + self.control.slow_minutes * 60)
        return now >= wait_until

    def decide(self, v):
        if self.ready is not None:
            (orders, record), self.ready = self.ready, None
            self.log.append(record)  # saved after the arena has checked the orders
            return orders
        self.thinking_since = self.last_started = time.time()
        state, self.woke, self.wake_reason = self._state(v), self.wake_reason, None
        self.job = threading.Thread(target=self._think, args=(state,), daemon=True)
        self.job.start()
        return []

    def status(self):
        return {"model": self.backend.model, "persona": self.persona, "mode": self.mode(),
                "thinking_since": self.thinking_since if self.job else None,
                "next_run": self.next_run, "error": self.error, "wake_reason": self.wake_reason}

    def _state(self, v):
        vetoed = v.get("vetoes") or {}
        structure = v.get("structure") or {}
        if market.UNIVERSE == "pumpfun":  # two lanes: fresh graduates and coins still on their curve
            listing = build_lanes(v["candidates"], vetoed, v.get("chg_since") or {}, v.get("now") or time.time(),
                                  view=v, structure=structure)
        else:
            cands = sorted((t for t in v["candidates"] if t["address"] not in vetoed), key=lambda t: t["vol_h1"], reverse=True)[:25]
            listing = {"candidates": [_format_candidate(t, v, structure) for t in cands]}
        state = {
            "cash": round(v["cash"], 2),
            "equity": round(v["equity"], 2),
            "your_previous_note": self.note,
            "positions": [{**{k: p.get(k) for k in ("token", "symbol", "value", "cost", "pnl_pct", "price_chg_pct", "held_min",
                                                    "rating", "flags", "exits")},
                           **({"moonshot": True} if p.get("moonshot") else {}),
                           **({"swing_30m": v["chg_since"][p["token"]]["swing_30m"]}
                              if "swing_30m" in v.get("chg_since", {}).get(p["token"], {}) else {})}
                          for p in v["positions"]],
            **listing,
            **({"vetoed_count": len(vetoed)} if vetoed else {}),
            "market_memory": v.get("market_memory"),
            "smart_money": v.get("smart_money"),
            "measured_round_trip_cost_pct": v.get("measured_round_trip_cost_pct"),
            **({"arena_news": v["arena_news"]} if v.get("arena_news") else {}),
            "recent_closed": [{k: r[k] for k in ("symbol", "pnl_usd", "pnl_pct", "reason")} for r in v.get("recent_closed", [])],
            "scoreboard": v.get("scoreboard", []),
            **({"your_score": v["your_score"]} if v.get("your_score") else {}),
            **({"strategy_room": v["strategy_room"]} if v.get("strategy_room") is not None else {}),
            **({"your_leaders": v["your_leaders"]} if v.get("your_leaders") else {}),
            "your_watch": self.watch,
            "your_journal": {str(i): s for i, s in enumerate(self.get_journal(), 1)},
            "recent_failures": [f["text"] for f in v.get("recent_failures", []) if isinstance(f, dict) and f.get("text")],
        }
        if self.wake_reason:
            state["woken_early_because"] = self.wake_reason
        if self.mode() == "slow":
            state["note_from_arena"] = f"Slow mode is on: your next look will be at least {self.control.slow_minutes} minutes away."
        return state

    def _record(self, t0, usage, **fields):
        return {"ts": time.time(), "secs": round(time.time() - t0, 1), "model": self.backend.model,
                "note": "", "orders": [], "next_min": None, "error": None, **fields,
                **{k: usage.get(k) for k in ("in_tok", "out_tok", "cache_read", "cache_write", "think_tok", "cost",
                                              "plan_5h", "plan_5h_reset", "plan_7d", "plan_7d_reset", "plan_status")}}

    def _ask(self, state):
        """One model call with this look's state. The council overrides this to hold a meeting."""
        return self.backend.ask(self.system, json.dumps(state, default=lambda o: round(o, 2)))

    def _think(self, state):
        t0 = time.time()
        usage = {}
        try:
            text, usage = self._ask(state)
            out = parse_reply(text)
            orders = out.get("orders") or []
            orders = [o for o in orders if isinstance(o, dict)] if isinstance(orders, list) else []
            symbols = {t["token"]: t["symbol"] for t in _listed(state)}
            for o in orders:
                o["symbol"] = symbols.get(o.get("token"), "?")
            try:
                next_min = float(out.get("next_check_min", 5))
            except (TypeError, ValueError):
                next_min = 5
            next_min = min(self.max_check, max(self.min_check, next_min))
            if "watch" in out:
                self.set_watch(out["watch"])
            journal = None  # the decision record keeps only what changed in the journal, not the whole list
            if "journal" in out:
                lessons, journal = self.edit_journal(self.get_journal(), out["journal"])
                if lessons is not None:
                    self.set_journal(lessons)
            self.note = str(out.get("note", ""))[:400]
            post = out.get("room_post")
            post = " ".join(post.split())[:280] if isinstance(post, str) and post.strip() else None
            self.error = None
            self.next_run = time.time() + next_min * 60
            self.ready = (orders, self._record(t0, usage, note=self.note, orders=orders, next_min=next_min, room_post=post,
                                               watch=dict(self.watch) if self.watch else None, woke=self.woke,
                                               journal=journal))
        except Exception as e:
            self.error = str(e)[:300]
            print(f"[{self.name}] decision failed: {self.error}")
            # back off: longer if it looks like a usage limit
            self.next_run = time.time() + (30 if "limit" in self.error.lower() else 5) * 60
            self.log.append(self._record(t0, getattr(e, "usage", None) or usage, error=self.error, woke=self.woke))
        finally:
            self.job = None


class ClaudeCodeBackend:
    """Runs the `claude` CLI in print mode, so calls use your Claude Pro/Max login instead of an API key.
    Every call counts against your plan's usage limits, the same limits as your normal chats."""

    def __init__(self, exe, model, effort="medium"):
        self.exe, self.model, self.effort = exe, model, effort
        self.label = f"Runs on Claude Code, {effort} effort" if effort else "Runs on Claude Code"

    def ask(self, system, prompt):
        """Returns (reply text, usage dict). The usage dict also carries your plan's 5-hour and weekly limit
        readings, which Claude Code reports with every call (plan_5h / plan_7d in percent, plus reset times)."""
        cmd = [self.exe, "-p", "--model", self.model, "--output-format", "stream-json", "--verbose",
               "--system-prompt", system,
               "--tools", "",              # no file or shell access: it can only answer
               "--safe-mode",              # skip your plugins, hooks, MCP servers and CLAUDE.md
               "--no-session-persistence"]  # don't fill your session history with arena calls
        if self.effort:
            cmd += ["--effort", self.effort]
        # With an API key in the environment Claude Code would bill the API instead of your plan.
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE")}
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                           timeout=600, env=env, cwd=tempfile.gettempdir(),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # stderr may carry noise such as `[claude-code:unrecognized_model] {"model":"claude-haiku-5-5",...}` for a new
        # model id; it is harmless (the call still completes), so only the `result` line on stdout is parsed.
        out, limits = None, {}
        for line in r.stdout.splitlines():
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("type") == "result":
                out = msg
            elif msg.get("type") == "rate_limit_event":
                info = msg.get("rate_limit_info") or {}
                windows = info.get("unifiedWindows") or {}
                for key, col in (("five_hour", "plan_5h"), ("seven_day", "plan_7d")):
                    w = windows.get(key) or {}
                    if w.get("utilization") is not None:
                        limits[col] = round(float(w["utilization"]) * 100, 2)
                        limits[col + "_reset"] = w.get("resetsAt")
                limits["plan_status"] = info.get("status")
        if out is None:
            raise CallError((r.stderr or r.stdout or f"claude exited with code {r.returncode}").strip()[-200:], limits)
        u = out.get("usage") or {}
        usage = {"in_tok": u.get("input_tokens", 0), "out_tok": u.get("output_tokens", 0),
                 "cache_read": u.get("cache_read_input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
                 "think_tok": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0),
                 "cost": out.get("total_cost_usd"), **limits}
        if out.get("is_error"):
            raise CallError(str(out.get("result") or out.get("subtype"))[:200], usage)
        return out.get("result") or "", usage


class ApiBackend:
    """Calls the Anthropic API directly. Needs ANTHROPIC_API_KEY and is billed per token, separately from a Claude plan."""

    def __init__(self, model):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.label = "Runs on the Anthropic API"

    def ask(self, system, prompt):
        msg = self.client.messages.create(model=self.model, max_tokens=1500, system=system,
                                          messages=[{"role": "user", "content": prompt}])
        u = msg.usage
        usage = {"in_tok": u.input_tokens, "out_tok": u.output_tokens,
                 "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0, "think_tok": 0, "cost": None}
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text"), usage


# ---------------- the Claude Council: three Claudes, one account ----------------
COUNCIL_ANALYST = """

You are an ANALYST on the Claude Council: three Claudes who share ONE account (the cash and positions above).
You don't place orders yourself. council_board shows what the council discussed and decided at earlier meetings
and how it turned out. Study the market, then answer with ONLY this JSON instead of the format above:
{"view": "2-4 sentences: what you see and why", "orders": [orders you propose, same formats as above],
 "worries": "the biggest risk in your proposal or in what the council holds"}
The chair (another Claude) reads both analysts' proposals and decides. Disagree with the other analyst or the
chair when the evidence says so; an empty orders list is a valid proposal."""

COUNCIL_CHAIR = """

You CHAIR the Claude Council: three Claudes who share ONE account (this one). Two analysts have just studied the
same data and posted proposals (member_proposals); council_board shows earlier meetings and how they turned out.
Weigh their arguments against the evidence and decide; you may follow either, combine them, or reject both. Answer
in the normal format above plus "board_post": "2-4 sentences to the analysts: what you decided, why, and what to
look for next time". The journal is the council's shared memory."""


def _sum_usage(parts):
    """Add up several calls' usage dicts; plan readings come from the last call (the most recent reading)."""
    total = {}
    for u in parts:
        for k in ("in_tok", "out_tok", "cache_read", "cache_write", "think_tok", "cost"):
            if u.get(k) is not None:
                total[k] = (total.get(k) or 0) + u[k]
        for k in ("plan_5h", "plan_5h_reset", "plan_7d", "plan_7d_reset", "plan_status"):
            if u.get(k) is not None:
                total[k] = u[k]
    return total


class CouncilAgent(LLMAgent):
    """Three Claudes sharing one account. At each meeting the analysts study the same view in parallel and post
    proposals to the council board; then the chair reads them (and earlier meetings) and decides. One meeting is
    three calls, recorded as one decision with the usage of all three added up."""

    def __init__(self, chair, analysts, min_check=2, max_check=10):
        super().__init__(chair, min_check, None, max_check)
        self.analysts = analysts  # [(label, backend)], e.g. [("Sonnet 5.5 A", ...), ("Sonnet 5.5 B", ...)]
        self.chair_label = model_label(chair.model)
        self.name, self.avatar = "Claude Council", "council"
        self.bio, self.catchphrase = CHARACTER.get("council") or CHARACTER["claude"]
        names = " and ".join(label for label, _ in analysts)
        self.description = (f"Three Claudes sharing one account: {names} propose, {self.chair_label} chairs and decides. "
                            f"Tests whether teamwork beats a solo model. {chair.label}.")
        self.analyst_system = self.system + COUNCIL_ANALYST
        self.system = self.system + COUNCIL_CHAIR

    def members(self):
        return ([{"name": self.chair_label, "model": self.backend.model, "role": "chair"}] +
                [{"name": label, "model": b.model, "role": "analyst"} for label, b in self.analysts])

    def _post(self, meeting, author, role, kind, text, orders=()):
        if self.db is not None:
            self.db.add_council_message(time.time(), meeting, author, role, kind, text, list(orders))

    def _ask(self, state):
        symbols = {t["token"]: t["symbol"] for t in _listed(state)}
        tidy = lambda orders: [{k: o.get(k) for k in ("action", "usd", "fraction", "reason")} | {"symbol": symbols.get(o.get("token"), "?")}
                               for o in (orders if isinstance(orders, list) else []) if isinstance(o, dict)]
        board = list(reversed(self.db.council_board(24))) if self.db is not None else []
        board_view = [{k: m.get(k) for k in ("meeting", "author", "role", "kind", "text", "orders")} for m in board]
        meeting = (self.db.council_meetings() if self.db is not None else 0) + 1
        dump = lambda extra: json.dumps({**state, **extra}, default=lambda o: round(o, 2))

        results = {}
        def run(label, backend):
            try:
                results[label] = backend.ask(self.analyst_system, dump({"council_board": board_view}))
            except Exception as e:  # one analyst failing doesn't stop the meeting
                results[label] = e
        threads = [threading.Thread(target=run, args=(label, b), daemon=True) for label, b in self.analysts]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        usages, proposals = [], []
        for label, _ in self.analysts:
            r = results.get(label)
            if isinstance(r, Exception) or r is None:
                usages.append(getattr(r, "usage", None) or {})
                self._post(meeting, label, "analyst", "error", f"couldn't take part: {str(r)[:200]}")
                continue
            text, usage = r
            usages.append(usage)
            try:
                p = _parse_json(text)
            except Exception as e:
                self._post(meeting, label, "analyst", "error", f"answer couldn't be read: {e}")
                continue
            prop = {"analyst": label, "view": str(p.get("view", ""))[:600], "orders": p.get("orders") or [],
                    "worries": str(p.get("worries", ""))[:300]}
            proposals.append(prop)
            self._post(meeting, label, "analyst", "proposal",
                       prop["view"] + (f" Worries: {prop['worries']}" if prop["worries"] else ""), tidy(prop["orders"]))
        try:
            text, usage = self.backend.ask(self.system, dump({"council_board": board_view, "member_proposals": proposals}))
        except Exception as e:
            self._post(meeting, self.chair_label, "chair", "error", f"the chair couldn't decide: {str(e)[:200]}")
            raise CallError(str(e), _sum_usage(usages + [getattr(e, "usage", None) or {}]))
        usages.append(usage)
        try:
            out = _parse_json(text)
            self._post(meeting, self.chair_label, "chair", "decision",
                       str(out.get("board_post") or out.get("note") or "")[:800], tidy(out.get("orders")))
        except Exception:
            pass  # _think reports an unreadable answer as the call's error
        return text, _sum_usage(usages)


# Run 6 (2026-10-06): slimmed to Sonnets. Opus, Fable and the Council were retired (cost, no edge shown); Copycat became
# Shadow, which follows one vetted top wallet. Degen and Scalper were retired after run 2.
# Run 7 (2026-10-07): every Sonnet has its own strategy (the user's choice; Twin and Triplet, the identical luck
# controls, became Graduate and Runner).
# Run 8 (2026-10-07): pump.fun only, Haiku 5.5 x4 (Graduate, Runner, Skeptic, Shadow) plus Sonnet 5.5 x2 (Graduate,
# Shadow) to see whether the cheaper model matches the dearer one on the same strategies.
DEFAULT_LINEUP = ("claude-haiku-5-5:graduate,claude-haiku-5-5:runner,claude-haiku-5-5:skeptic,claude-haiku-5-5:shadow,"
                  "claude-sonnet-5-5:graduate,claude-sonnet-5-5:shadow")


def build_llm_agents():
    """ARENA_LLM picks how the Claude agents reach Claude: claude-code, api or off.
    The default uses Claude Code if it's installed, else the API if ANTHROPIC_API_KEY is set.
    ARENA_LLM_MODELS is a comma-separated list of model or model:persona; each entry becomes its own agent."""
    exe = shutil.which("claude")
    mode = os.environ.get("ARENA_LLM", "auto").strip().lower()
    if mode == "auto":
        mode = "claude-code" if exe else "api" if os.environ.get("ANTHROPIC_API_KEY") else "none"
    entries = [e.strip() for e in os.environ.get("ARENA_LLM_MODELS", "").split(",") if e.strip()]
    min_check = float(os.environ.get("ARENA_LLM_MIN_CHECK", "1"))
    max_check = float(os.environ.get("ARENA_LLM_MAX_CHECK", "60"))

    def lineup(default):
        for e in entries or default.split(","):
            model, _, persona = e.partition(":")
            yield model.strip(), persona.strip().lower() or None

    if mode == "claude-code":
        if exe:
            effort = os.environ.get("ARENA_LLM_EFFORT", "medium")
            agents = [LLMAgent(ClaudeCodeBackend(exe, m, effort), min_check, p, max_check)
                      for m, p in lineup(DEFAULT_LINEUP)]
            # ARENA_COUNCIL: chair model first, then the analysts ("off" leaves the council out)
            council = os.environ.get("ARENA_COUNCIL", "off").strip()  # e.g. claude-opus-5-5,claude-sonnet-5-5,claude-sonnet-5-5
            if council and council.lower() != "off":
                chair, *analysts = [m.strip() for m in council.split(",") if m.strip()]
                labels = [f"{model_label(m)} {chr(65 + i)}" for i, m in enumerate(analysts)]
                agents.append(CouncilAgent(ClaudeCodeBackend(exe, chair, effort),
                                           [(lb, ClaudeCodeBackend(exe, m, effort)) for lb, m in zip(labels, analysts)],
                                           min_check, max_check))
            return agents
        print("[agents] ARENA_LLM=claude-code but the 'claude' command wasn't found, running without Claude agents")
    elif mode == "api":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("[agents] ARENA_LLM=api but ANTHROPIC_API_KEY isn't set, running without Claude agents")
            return []
        try:
            return [LLMAgent(ApiBackend(m), min_check, p, max_check) for m, p in lineup("claude-haiku-4-5-20251001")]
        except ImportError:
            print("[agents] 'anthropic' package not installed, skipping Claude agents (pip install anthropic)")
    elif mode == "none":
        print("[agents] Claude Code not found and no ANTHROPIC_API_KEY, running without Claude agents")
    elif mode != "off":
        print(f"[agents] unknown ARENA_LLM={mode!r} (use claude-code, api or off), running without Claude agents")
    return []
