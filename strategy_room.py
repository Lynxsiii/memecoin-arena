"""The strategy room: a chat the Claudes share to get better at trading. It is for strategies, lessons, risk rules and
how to read the data, never for coins. Every post goes through check_post() before anyone sees it: a post that names
a coin the arena knows (symbol or name), contains a contract address, a $TICKER or a link to a chart / launchpad
site is blocked. Blocked posts are kept (the dashboard shows them, so you can see who broke the rule) but the
Claudes only see that a post was removed.

Settings: ARENA_ROOM=0 turns the room off. ARENA_ROOM_SHOW=20 posts shown to each Claude per look.
"""
import os
import re

ENABLED = os.environ.get("ARENA_ROOM", "1").strip().lower() not in ("0", "off", "false", "no")
MAX_CHARS = 280
SHOW = max(1, int(os.environ.get("ARENA_ROOM_SHOW", "20") or 20))

ADDRESS = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")          # base58: Solana mints and wallets
TICKER = re.compile(r"\$[A-Za-z][A-Za-z0-9_]{1,15}\b")              # $WIF, $BONK...
# Links only: naming a site ("pump.fun launches", "promoted on DexScreener") is strategy talk, linking to a page is not
LINK = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|fun|io|ag|xyz|so|app|family|trade|net|org)/\S)", re.I)
# Words that are also token symbols often enough to cause false alarms; mentioning these is talking about trading.
COMMON = set("""
a an and are as at be but by can cut do down for from go good got had has have he high hold i if in is it its just
keep less let like long low make more most much new no not now of off old on one or out over per run see set so stay
take than that the them then there they this time to too try up us use very was we were what when win with yes you
buy sell sol usd usdc usdt wsol btc eth pump dump moon dip rug rugs green red yellow stop loss gain gains profit fee
fees cash coin coins token tokens meme memes trend trends volume vol liquidity liq whale whales ape alpha beta gem gems
entry exit exits risk fade fades bull bear safe trade trades trader money gold fire king god cat dog frog ai bot bots
fast slow big small top bottom peak spike runner runners chase flow buys sells hour hours day days min mins week
lesson lessons rule rules edge size sizing scale scale-out trail trailing target targets wait patience patient
""".split())


def coin_words(tokens):
    """The coin names and symbols to block, from the market's token dicts (anything with symbol/name/address)."""
    words = set()
    for t in tokens:
        for k in ("symbol", "name"):
            w = str(t.get(k) or "").strip().lower()
            if len(w) >= 3 and w not in COMMON:
                words.add(w)
    return words


def check_post(text, coins):
    """(clean text, None) for a post that is fine, or (clean text, reason) for one that must be blocked.
    `coins` is the set from coin_words(). Empty or non-text posts return (None, None)."""
    if not isinstance(text, str):
        return None, None
    text = " ".join(text.split())[:MAX_CHARS]
    if not text:
        return None, None
    if ADDRESS.search(text):
        return text, "contains an address"
    if TICKER.search(text):
        return text, "contains a $TICKER"
    if LINK.search(text):
        return text, "links to a chart or launch site"
    low = text.lower()
    for w in coins:
        if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low):
            return text, "names a coin"
    return text, None
