/* commentary.js — arcade announcer play-by-play bar for the memecoin arena dashboard.
   Renders into #slot-under-stage; adds "Announcer" and "Voice" toolbar toggles. */
(function () {
  "use strict";
  if (window.__cmAnnouncer) return;
  window.__cmAnnouncer = true;

  var PREF_ON = "announcer";
  var MAX_HISTORY = 4;
  var IDLE_SECS = 60;

  /* ---------- styles ---------- */
  var css = [
    ".cm-wrap{position:relative;margin-top:16px;background:var(--dusk);border:1px solid var(--seam);padding:12px 14px 10px;",
    "clip-path:polygon(0 6px,6px 6px,6px 0,calc(100% - 6px) 0,calc(100% - 6px) 6px,100% 6px,100% calc(100% - 6px),",
    "calc(100% - 6px) calc(100% - 6px),calc(100% - 6px) 100%,6px 100%,6px calc(100% - 6px),0 calc(100% - 6px));",
    "max-width:100%;box-sizing:border-box;overflow:hidden}",
    ".cm-wrap[hidden]{display:none}",
    ".cm-head{display:flex;align-items:center;gap:8px;font:12px var(--body);color:var(--haze);letter-spacing:.02em;margin-bottom:6px}",
    ".cm-dot{width:8px;height:8px;background:var(--loss);box-shadow:0 0 0 1px var(--night);animation:cm-blink 1.2s steps(1,end) infinite}",
    ".cm-live{font:22px/1.15 var(--pixel);color:var(--moon);min-height:26px;overflow-wrap:anywhere;word-break:break-word}",
    ".cm-live .cm-ch{opacity:0;animation:cm-pop 1ms steps(1,end) forwards;animation-delay:calc(var(--i) * 32ms)}",
    ".cm-a{font-weight:700}",
    ".cm-hist{list-style:none;margin:8px 0 0;padding:6px 0 0;border-top:1px dashed var(--seam);display:grid;gap:3px}",
    ".cm-hist li{display:flex;gap:10px;justify-content:space-between;align-items:baseline;font:13px/1.3 var(--body);color:var(--haze);opacity:.85}",
    ".cm-hist li:nth-child(2){opacity:.7}.cm-hist li:nth-child(3){opacity:.55}.cm-hist li:nth-child(4){opacity:.42}",
    ".cm-hist .cm-txt{overflow-wrap:anywhere;min-width:0}",
    ".cm-hist .cm-a{opacity:.9}",
    ".cm-ago{flex:none;font-size:11px;color:var(--haze);opacity:.8;white-space:nowrap}",
    ".cm-btn{font:13px var(--body);color:var(--moon);background:var(--dusk);border:1px solid var(--seam);padding:4px 9px;cursor:pointer;",
    "line-height:1.2;clip-path:polygon(0 3px,3px 3px,3px 0,calc(100% - 3px) 0,calc(100% - 3px) 3px,100% 3px,100% calc(100% - 3px),",
    "calc(100% - 3px) calc(100% - 3px),calc(100% - 3px) 100%,3px 100%,3px calc(100% - 3px),0 calc(100% - 3px))}",
    ".cm-btn:hover{border-color:var(--haze)}",
    ".cm-btn[aria-pressed=\"true\"]{border-color:var(--gold);color:var(--gold)}",
    ".cm-btn[aria-pressed=\"true\"]::before{content:\"\\25A0  \";font-size:9px;vertical-align:1px}",
    ".cm-btn[aria-pressed=\"false\"]::before{content:\"\\25A1  \";font-size:9px;vertical-align:1px;opacity:.6}",
    "@keyframes cm-blink{0%,55%{opacity:1}56%,100%{opacity:.15}}",
    "@keyframes cm-pop{to{opacity:1}}",
    "@media (prefers-reduced-motion: reduce){.cm-dot{animation:none}.cm-live .cm-ch{animation:none;opacity:1}}"
  ].join("");
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  /* ---------- state ---------- */
  var lines = [];            // newest first: {segs, text, ts}
  var leader = null;         // name of data.agents[0]
  var lastLineAt = 0;
  var statusIdx = 0;
  var enabled = arenaPrefs.get(PREF_ON, true) !== false;
  var voice = false;         // session-only; speaks only after the user clicks Voice
  var reduced = false;
  try { reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}

  var slot = $("slot-under-stage");
  if (!slot) return;
  var wrap = document.createElement("div");
  wrap.className = "cm-wrap";
  wrap.setAttribute("role", "log");
  wrap.setAttribute("aria-live", "polite");
  wrap.innerHTML = '<div class="cm-head"><span class="cm-dot" aria-hidden="true"></span><span>On air</span></div>' +
    '<div class="cm-live" id="cm-live"></div><ul class="cm-hist" id="cm-hist"></ul>';
  slot.appendChild(wrap);
  var liveEl = wrap.querySelector("#cm-live"), histEl = wrap.querySelector("#cm-hist");

  /* ---------- toolbar ---------- */
  var toolbar = $("toolbar");
  var btnOn, btnVoice;
  function mkBtn(label, pressed, title) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "cm-btn";
    b.textContent = label;
    b.title = title;
    b.setAttribute("aria-pressed", pressed ? "true" : "false");
    return b;
  }
  if (toolbar) {
    btnOn = mkBtn("Announcer", enabled, "Show or hide the play-by-play announcer");
    btnOn.addEventListener("click", function () {
      enabled = !enabled;
      arenaPrefs.set(PREF_ON, enabled);
      applyEnabled();
    });
    btnVoice = mkBtn("Voice", false, "Read new announcer lines aloud");
    if (!("speechSynthesis" in window)) btnVoice.disabled = true;
    btnVoice.addEventListener("click", function () {
      voice = !voice;
      btnVoice.setAttribute("aria-pressed", voice ? "true" : "false");
      if (!voice) { try { speechSynthesis.cancel(); } catch (e) {} }
      else if (lines[0]) speak(lines[0].text);
    });
    toolbar.appendChild(btnOn);
    toolbar.appendChild(btnVoice);
  }
  function applyEnabled() {
    wrap.hidden = !enabled;
    if (btnOn) btnOn.setAttribute("aria-pressed", enabled ? "true" : "false");
    if (!enabled) { try { speechSynthesis.cancel(); } catch (e) {} }
  }
  applyEnabled();
  document.addEventListener("arena:prefs", function (e) {
    if (e.detail && e.detail.key === PREF_ON) { enabled = e.detail.value !== false; applyEnabled(); }
  });

  /* ---------- line building ---------- */
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
  function A(name) {
    var ag = agentByName(name);
    return { t: name, c: colorOf(ag) };
  }
  function T(s) { return { t: String(s) }; }
  // tpl("{a} buys {s} for {u}", {a: A(name), s: T(sym), u: T(money(usd))}) → segs
  function tpl(str, vars) {
    var segs = [], re = /\{(\w+)\}/g, last = 0, m;
    while ((m = re.exec(str))) {
      if (m.index > last) segs.push(T(str.slice(last, m.index)));
      segs.push(vars[m[1]] || T(""));
      last = m.index + m[0].length;
    }
    if (last < str.length) segs.push(T(str.slice(last)));
    return segs;
  }
  function segText(segs) { return segs.map(function (s) { return s.t; }).join(""); }
  function segHTML(segs, typewriter) {
    var i = 0;
    return segs.map(function (s) {
      var inner;
      if (typewriter && !reduced) {
        inner = Array.prototype.map.call(s.t, function (ch) {
          return '<span class="cm-ch" style="--i:' + (i++) + '">' + esc(ch) + "</span>";
        }).join("");
      } else inner = esc(s.t);
      return s.c ? '<b class="cm-a" style="color:' + s.c + '">' + inner + "</b>" : inner;
    }).join("");
  }
  // Flavor key: persona first (skeptic / twin / copycat ...), then avatar (fable, haiku, rocket, sniper, ...).
  // The three copy bots share one voice ("copy"); lines for agents that have left the roster simply never fire.
  function kindOf(name) {
    var ag = agentByName(name);
    if (!ag) return "claude";
    if (ag.persona) return String(ag.persona);
    var av = ag.avatar || "claude";
    if (/^copy-/.test(av)) return "copy";
    if (av === "sonnet-copycat") return "copycat";
    return av;
  }
  /* teams: the dashboard's helpers when present, else the same fallback (team key, or llm → claude / bot → bots) */
  var ORDER = typeof TEAM_ORDER !== "undefined" ? TEAM_ORDER : ["claude", "bots", "copy"];
  var NAMES = typeof TEAM_INFO !== "undefined" ? TEAM_INFO : { claude: "Team Claude", bots: "Team Bots", copy: "Team Copy" };
  function teamKey(a) { return typeof teamOf === "function" ? teamOf(a) : (NAMES[a.team] ? a.team : a.kind === "llm" ? "claude" : "bots"); }
  function tName(k) { return NAMES[k] || ("Team " + k); }
  // per-team equity totals and averages, best average first
  function teamTable(ags) {
    var rows = ORDER.map(function (k) {
      var xs = ags.filter(function (a) { return teamKey(a) === k; });
      if (!xs.length) return null;
      var eq = xs.reduce(function (s, a) { return s + a.equity; }, 0);
      return { key: k, n: xs.length, equity: eq, avg: eq / xs.length, best: xs[0] };   // data.agents is ranked, so xs[0] is the team's best
    }).filter(Boolean);
    rows.sort(function (a, b) { return b.avg - a.avg; });
    return rows;
  }
  function shorten(s, n) {
    s = String(s || "").replace(/\s+/g, " ").trim();
    return s.length > n ? s.slice(0, n - 1).replace(/[\s,.;:]+$/, "") + "…" : s;
  }

  function buyLine(t) {
    var v = { a: A(t.agent), s: T(t.symbol || t.token), u: T(money(t.usd, 0)) };
    var k = kindOf(t.agent), opts;
    if (k === "robot") opts = [
      "{a} runs the checklist and buys {s} ({u})",
      "Beep. {a} allocates {u} to {s}. Boop.",
      "{a} finds a signal in {s} and buys {u} worth"
    ];
    else if (k === "monkey") opts = [
      "{a} throws a dart at {s} ({u})",
      "{a} flings {u} at {s}. Why? No reason.",
      "{a} picks {s} out of a hat for {u}"
    ];
    else if (k === "monkey-green") opts = [
      "{a} throws a dart, but only at the green board: {s} ({u})",
      "{a} checks the risk filter, then flings {u} at {s} anyway",
      "{a}: random, but responsibly. {u} into {s}"
    ];
    else if (k === "turtle") opts = ["{a} stirs, buys {s} for {u}, goes back to sleep"];
    else if (k === "rocket") opts = [
      "{a} sees {s} moving and chases it with {u}",
      "Liftoff? {a} rides the momentum into {s} ({u})",
      "{a} buys {s} for {u} because it is going up. That is the whole thesis."
    ];
    else if (k === "sniper") opts = [
      "{a} spots a fresh launch, {s}, and takes the shot ({u})",
      "{a} lines up {s} seconds after launch. {u} in.",
      "Fresh out of the oven: {a} snipes {s} for {u}"
    ];
    else if (k === "index") opts = [
      "{a} rebalances, adding {u} of {s} to the basket",
      "{a} tops up {s} ({u}) to keep the index even",
      "Rebalance day for {a}: {u} into {s}"
    ];
    else if (k === "degen") opts = [
      "{a} apes {u} into {s}. No notes.",
      "{a} full sends {s} with {u}. Risk flags are a social construct.",
      "WAGMI, says {a}, buying {s} for {u}"
    ];
    else if (k === "skeptic") opts = [
      "Against all odds, {a} is convinced: {s} for {u}",
      "{a} grudgingly buys {s} ({u}) after finding nothing wrong with it",
      "{a} drops the arms-crossed pose and buys {s} for {u}"
    ];
    else if (k === "scalper") opts = [
      "{a} darts into {s} with {u}. Blink and it is gone.",
      "{a} opens {s} for {u}, already eyeing the exit",
      "Quick in: {a} grabs {s} ({u})"
    ];
    else if (k === "fable") opts = [
      "Once upon a tick, {a} bought {s} for {u}",
      "{a} starts a new chapter: {u} into {s}",
      "{a} writes {s} into the story with {u}"
    ];
    else if (k === "haiku") opts = [
      "{a}, small but quick, buys {s} for {u}",
      "{a} decided already. {s}, {u}. Next.",
      "Seventeen syllables later, {a} owns {s} ({u})"
    ];
    else if (k === "twin") opts = [
      "{a} buys {s} for {u}. Did the original do the same? That is the experiment.",
      "Same brief, different dice: {a} puts {u} into {s}",
      "{a} takes {u} of {s}. Any gap to its twin is luck, remember."
    ];
    else if (k === "dip-buyer") opts = [
      "{a} sees {s} on sale and grabs {u} worth",
      "Discount spotted: {a} buys the dip in {s} ({u})",
      "{a} catches {s} on the way down and drops {u} in the basket"
    ];
    else if (k === "copy") opts = [
      "{a} sees a top wallet buy {s} and copies it: {u}",
      "Monkey see, monkey do. {a} mirrors a buy of {s} ({u})",
      "{a} photocopies a top-100 trade: {u} into {s}",
      "Someone on the leaderboard bought {s}, so {a} did too ({u})"
    ];
    else if (k === "copycat") opts = [
      "{a} picks one top-trader buy worth copying: {s} for {u}",
      "Of all the signals, {a} chooses {s} ({u}). Selective copying.",
      "{a} tails a top wallet into {s} with {u}, ears up"
    ];
    else if (k === "graduate") opts = [
      "{s} just left the bonding curve and {a} is there with {u}",
      "Commencement day: {a} puts {u} into {s}",
      "{a} checks the graduate's pool, then buys {s} for {u}"
    ];
    else if (k === "runner") opts = [
      "{a} spots {s} breaking into a sprint and chases it with {u}",
      "On your marks: {a} buys {s} early for {u}",
      "{a} gets in on {s} before the crowd ({u})"
    ];
    else if (k === "graduates") opts = [
      "{s} graduated, so {a} bought it: {u}. Rules are rules.",
      "{a} adds {s} to the class photo ({u})",
      "Another graduate for {a}: {s}, {u}"
    ];
    else opts = [
      "{a} apes into {s} with {u}",
      "{a} reasons its way into {s} ({u})",
      "{a} likes the look of {s}. {u} in.",
      "{a} buys {s} for {u}. What could go wrong?"
    ];
    return tpl(pick(opts), v);
  }
  function sellLine(t) {
    var pnl = typeof t.pnl === "number" ? t.pnl : 0;
    var v = { a: A(t.agent), s: T(t.symbol || t.token), p: T(signed(pnl)) };
    var k = kindOf(t.agent), opts;
    if (Math.abs(pnl) < 0.005) opts = ["{a} exits {s} flat. Nothing to see here.", "{a} closes {s} at breakeven. Thrilling."];
    else if (k === "scalper") opts = pnl > 0
      ? ["And out. {a} scalps {p} from {s}", "{a} is already gone from {s}: {p}", "Quick out: {a} pockets {p} on {s}"]
      : ["{a} bails on {s} fast for {p}. Next.", "In, out, {p}. {a} shrugs at {s}"];
    else if (k === "degen") opts = pnl > 0
      ? ["{a} actually made {p} on {s}. Degen wins, somehow.", "LFG. {a} prints {p} on {s}"]
      : ["{a} gets rekt on {s}: {p}. It was never about the money.", "{a} donates {p} to {s} holders. Diamond hands, pasted."];
    else if (k === "skeptic") opts = pnl > 0
      ? ["{a} takes {p} on {s}, still unconvinced", "Fine, {a} admits {s} worked: {p}"]
      : ["{a} knew it. {s} out for {p}.", "{a} sells {s} for {p}. Told you so, says {a}."];
    else if (k === "fable") opts = pnl > 0
      ? ["{a} closes the chapter on {s}: {p}. Happy ending.", "The end, says {a}, booking {p} on {s}"]
      : ["{a}'s {s} story ends in tragedy: {p}", "Plot twist. {a} exits {s} at {p}"];
    else if (k === "rocket") opts = pnl > 0
      ? ["{a} rode {s} up and jumps off with {p}", "Momentum paid: {a} banks {p} on {s}"]
      : ["Momentum reversed. {a} dumps {s} for {p}", "{a} chased {s} and caught a {p} loss"];
    else if (k === "sniper") opts = pnl > 0
      ? ["Headshot. {a} exits {s} with {p}", "{a} hit the fresh launch {s} for {p}"]
      : ["{a} missed on {s}: {p}", "Rug check failed in hindsight. {a} leaves {s} at {p}"];
    else if (k === "index") opts = pnl > 0
      ? ["{a} trims {s} for {p} to rebalance", "Rebalance: {a} sells down {s}, {p}"]
      : ["{a} rotates out of {s} at {p}. The basket moves on.", "{a} rebalances {s} away for {p}"];
    else if (k === "haiku") opts = pnl > 0
      ? ["{a} sells {s}. {p}. Brief, like a haiku.", "Short poem, good ending: {a} takes {p} on {s}"]
      : ["{a} sells {s} for {p}. Short and bitter.", "Five, seven, {p}. {a} exits {s}."];
    else if (k === "twin") opts = pnl > 0
      ? ["{a} books {p} on {s}. Skill or dice? Ask the original.", "The control group scores: {a} takes {p} on {s}"]
      : ["{a} loses {p} on {s}. Same brief as its twin, different dice.", "{a} exits {s} at {p}. Noise, probably."];
    else if (k === "dip-buyer") opts = pnl > 0
      ? ["Bounce caught. {a} flips {s} for {p}", "{a} bought the dip in {s} and sells the bounce: {p}"]
      : ["The dip kept dipping. {a} drops {s} for {p}", "{a} caught a falling knife in {s}: {p}"];
    else if (k === "copy") opts = pnl > 0
      ? ["The wallet sold, so {a} sold: {p} on {s}", "{a} copies the exit from {s} and keeps {p}", "Carbon copy profit: {a} books {p} on {s}"]
      : ["The wallet sold, so {a} sold: {p} on {s}. Copying cuts both ways.", "{a} mirrors a loss too: {s} out at {p}", "{a} copied the entry and the exit on {s}: {p}"];
    else if (k === "copycat") opts = pnl > 0
      ? ["{a} lands on its feet: {p} on {s}", "Copied well. {a} takes {p} on {s}"]
      : ["{a} copied the wrong cat. {s} out at {p}", "{a} exits {s} at {p}. Not every top trader is worth tailing."];
    else if (k === "graduate") opts = pnl > 0
      ? ["{a} takes {p} on {s}. Graduated with honours.", "{a} cashes in its {s} diploma: {p}"]
      : ["{s} flunked out after graduating. {a} sells at {p}", "{a} exits {s} at {p}. Not every graduate makes it."];
    else if (k === "runner") opts = pnl > 0
      ? ["{a} caught the run on {s}: {p}", "{a} crosses the finish line on {s} with {p}"]
      : ["{s} ran out of breath. {a} walks off at {p}", "False start: {a} exits {s} for {p}"];
    else if (k === "graduates") opts = pnl > 0
      ? ["Class dismissed: {a} sells {s} for {p}", "{a} lets {s} go at {p}. A graduate that delivered."]
      : ["{s} dropped out. {a} sells at {p}", "{a} drops {s} at {p}. Not every graduate makes it."];
    else if (pnl > 0) opts = [
      "{a} cashes out {s} for {p}",
      "Ka-ching. {a} books {p} on {s}",
      "{a} takes profit on {s}: {p}",
      "{a} sells {s}. {p}. Not bad."
    ];
    else opts = [
      "Ouch. {a} dumps {s} at {p}",
      "{a} cuts {s} loose for {p}",
      "{a} bails on {s}. {p}. Rough.",
      "{a} sells {s} for {p} and pretends it was the plan"
    ];
    return tpl(pick(opts), v);
  }
  function decisionLine(d) {
    var v = { a: A(d.agent) };
    if (d.error) return tpl(pick(["{a}'s call failed", "{a} tried to think and hit an error", "Static on the line: {a}'s call failed"]), v);
    var live = (d.orders || []).filter(function (o) { return !o.rejected; });
    var k = kindOf(d.agent);
    if (d.note) { v.n = T(shorten(d.note, 70)); return tpl("{a}: “{n}”", v); }
    if (!live.length) {
      v.m = T(d.next_min != null ? d.next_min : "a few");
      if (k === "skeptic") return tpl(pick(["{a} refuses. Nothing passes the sniff test. Back in {m} min", "{a} is not buying it. Literally. Back in {m} min"]), v);
      if (k === "degen") return tpl(pick(["Even {a} found nothing to ape into. Back in {m} min", "{a} sits out. Rare. Back in {m} min"]), v);
      if (k === "scalper") return tpl(pick(["No quick flips for {a}. Back in {m} min", "{a} finds no edge to scalp. Back in {m} min"]), v);
      if (k === "haiku") return tpl(pick(["{a}: nothing. Back in {m} min.", "{a} passes, briefly. Back in {m} min"]), v);
      if (k === "fable") return tpl(pick(["{a} leaves this page blank. Back in {m} min", "No new chapter from {a}. Back in {m} min"]), v);
      if (k === "twin" || k === "triplet") return tpl(pick(["{a} passes. Did the original pass too? Back in {m} min", "Nothing from {a}, the control group. Back in {m} min"]), v);
      if (k === "copycat") return tpl(pick(["{a} saw the signals and copied none of them. Back in {m} min", "No top-trader buy worth copying, says {a}. Back in {m} min"]), v);
      if (k === "graduate") return tpl(pick(["No graduate worth buying, says {a}. Back in {m} min", "{a} reads the class list and passes. Back in {m} min"]), v);
      if (k === "runner") return tpl(pick(["{a} sees no runner yet. Back in {m} min", "Nothing is running, so neither is {a}. Back in {m} min"]), v);
      return tpl(pick(["{a}: no trades, back in {m} min", "{a} sits this one out. Back in {m} min"]), v);
    }
    v.n = T(live.length + (live.length === 1 ? " order" : " orders"));
    return tpl("{a} sends {n}", v);
  }
  function leaderLine(name) {
    var ag = agentByName(name) || {};
    var v = { a: A(name), e: T(money(ag.equity || 0, 0)), t: T(tName(teamKey(ag))) };
    return tpl(pick(["New leader: {a}!", "{a} takes the lead!", "{a} climbs to the top at {e}", "{a} puts {t} on top at {e}"]), v);
  }
  function statusLine() {
    if (!data || !data.agents || !data.agents.length) return null;
    var ags = data.agents, tries = 7;
    while (tries--) {
      var which = statusIdx++ % 7;
      if (which === 0 && ags.length > 1) {
        var diff = ags[0].equity - ags[1].equity;
        var v = { a: A(ags[0].name), b: A(ags[1].name), d: T(money(Math.abs(diff))) };
        if (diff < 0.005) return tpl("{a} and {b} are neck and neck", v);
        return tpl(pick(["{a} leads {b} by {d}", "{a} is up on {b} by {d}. Can it hold?"]), v);
      }
      if (which === 1) {
        // team standings by average equity per agent (team sizes differ), best first
        var tt = teamTable(ags);
        if (tt.length > 1) {
          var gap = tt[0].avg - tt[1].avg;
          var v2 = { x: T(tName(tt[0].key)), y: T(tName(tt[1].key)), d: T(money(Math.abs(gap), 0)), e: T(money(tt[0].avg, 0)) };
          if (tt.length > 2) {
            v2.z = T(tName(tt[2].key)); v2.g = T(money(Math.abs(tt[1].avg - tt[2].avg), 0));
            if (Math.abs(gap) < 0.5) return tpl("{x} and {y} are dead even per agent, {z} trails by {g}", v2);
            return tpl(pick(["{x} leads {y} by {d} an agent, {z} third", "Standings: {x}, then {y} ({d} back), then {z}", "{x} is on top at {e} an agent. {y} second, {z} third."]), v2);
          }
          if (Math.abs(gap) < 0.5) return tpl("{x} and {y} are dead even at {e} an agent", v2);
          return tpl(pick(["{x} leads {y} by {d} an agent", "{x} is up {d} an agent on {y}"]), v2);
        }
      }
      if (which === 2) {
        var tur = ags.filter(function (a) { return a.avatar === "turtle"; })[0];
        if (tur) {
          var v3 = { a: A(tur.name), e: T(money(tur.equity, 0)) };
          return tpl(pick(["{a} is asleep at {e}", "{a} has not moved. Still {e}.", "Meanwhile, {a} naps on {e}"]), v3);
        }
      }
      if (which === 3) {
        // the best agent of each team (data.agents is ranked by equity), best team first
        var bt = teamTable(ags).slice().sort(function (a, b) { return b.best.equity - a.best.equity; });
        if (bt.length > 1) {
          var SHORT = { claude: "Claude", bots: "bot", copy: "copier" };
          var v4 = { a: A(bt[0].best.name), b: A(bt[1].best.name), d: T(money(Math.abs(bt[0].best.equity - bt[1].best.equity), 0)),
                     x: T(SHORT[bt[0].key] || bt[0].key), y: T(SHORT[bt[1].key] || bt[1].key) };
          if (bt.length > 2) { v4.c = A(bt[2].best.name); v4.z = T(SHORT[bt[2].key] || bt[2].key); }
          if (Math.abs(bt[0].best.equity - bt[1].best.equity) < 0.5) return tpl("Top {x} {a} and top {y} {b} are tied", v4);
          return tpl(bt.length > 2 ? "Best {x} {a} is {d} ahead of best {y} {b}; best {z} {c} trails" : "Best {x} {a} is {d} ahead of best {y} {b}", v4);
        }
      }
      if (which === 4) {
        // personality check: a base model vs its personas (the twin, triplet and copycat aren't personalities, so they sit this one out)
        var isStyle = function (p) { return p.persona && p.persona !== "twin" && p.persona !== "triplet" && p.persona !== "copycat"; };
        var base = ags.filter(function (a) { return a.kind === "llm" && !a.persona && ags.some(function (p) { return isStyle(p) && p.model === a.model; }); })[0];
        if (base) {
          var pers = ags.filter(function (p) { return isStyle(p) && p.model === base.model; });
          var top = pers.reduce(function (m, p) { return p.equity > m.equity ? p : m; }, pers[0]);
          var v5 = { a: A(base.name), p: A(top.name), d: T(money(Math.abs(top.equity - base.equity), 0)) };
          if (top.equity > base.equity + 0.5) return tpl("Personality check: {p} is beating plain {a} by {d}", v5);
          if (base.equity > top.equity + 0.5) return tpl("Personality check: plain {a} is ahead of its best persona {p} by {d}", v5);
          return tpl("Personality check: {a} and {p} are level. Same model, same result.", v5);
        }
      }
      if (which === 5) {
        // noise check: a model vs its identical twin. Same model, same brief, so the gap is luck.
        var tw = ags.filter(function (a) { return a.persona === "twin"; })[0];
        var orig = tw && ags.filter(function (a) { return a.kind === "llm" && !a.persona && a.model === tw.model; })[0];
        var trip = tw && ags.filter(function (a) { return a.persona === "triplet" && a.model === tw.model; })[0];
        if (tw && orig) {
          if (trip) {   // three copies: the spread between the best and worst of them is the luck
            var trio = [orig, tw, trip].sort(function (a, b) { return b.equity - a.equity; });
            var spread = trio[0].equity - trio[2].equity;
            var v6b = { a: A(trio[0].name), c: A(trio[2].name), d: T(money(spread, 0)) };
            if (spread < 0.5) return tpl("Noise check: all three Sonnets are level. Same model, same brief, same result.", v6b);
            return tpl(pick(["Noise check: {a} to {c}, the three identical Sonnets span {d}. That spread is pure luck.",
                             "Three copies of one model are {d} apart, {a} on top and {c} at the bottom. Call it the margin of luck."]), v6b);
          }
          var gap6 = Math.abs(tw.equity - orig.equity);
          var v6 = { a: A(orig.name), b: A(tw.name), d: T(money(gap6, 0)) };
          if (gap6 < 0.5) return tpl("Noise check: {a} and its twin {b} are level. Same model, same brief, same result.", v6);
          return tpl(pick(["Noise check: {a} and its twin {b} are {d} apart. That gap is pure luck.",
                           "Same model, same brief: {a} vs {b} differ by {d}. Call it the margin of luck."]), v6);
        }
      }
      if (which === 6) {
        // a catchphrase from someone on the stage
        var talkers = ags.filter(function (a) { return a.catchphrase; });
        if (talkers.length) {
          var who = pick(talkers);
          var v7 = { a: A(who.name), c: T(String(who.catchphrase)) };
          return tpl(pick(["{a}: “{c}”", "{a}, to nobody in particular: “{c}”", "Overheard from {a}: “{c}”"]), v7);
        }
      }
    }
    return null;
  }

  /* ---------- rendering ---------- */
  function push(segs, ts, opts) {
    opts = opts || {};
    if (!segs) return;
    var line = { segs: segs, text: segText(segs), ts: ts != null ? ts : now() };
    lines.unshift(line);
    if (lines.length > MAX_HISTORY + 1) lines.length = MAX_HISTORY + 1;
    lastLineAt = now();
    render(!opts.quiet);
    if (!opts.quiet && enabled && voice) speak(line.text);
  }
  function render(animate) {
    if (!lines.length) return;
    liveEl.innerHTML = segHTML(lines[0].segs, animate);
    var t = now();
    histEl.innerHTML = lines.slice(1).map(function (l) {
      return '<li><span class="cm-txt">' + segHTML(l.segs, false) + '</span><span class="cm-ago" data-cm-ts="' + l.ts + '">' + esc(ago(t - l.ts)) + "</span></li>";
    }).join("");
  }
  function tickAgo() {
    var t = now();
    histEl.querySelectorAll("[data-cm-ts]").forEach(function (el) { el.textContent = ago(t - +el.dataset.cmTs); });
  }
  function speak(text) {
    if (!("speechSynthesis" in window)) return;
    try {
      if (speechSynthesis.pending) speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(text.replace(/[“”]/g, ""));
      u.rate = 1.1;
      speechSynthesis.speak(u);
    } catch (e) {}
  }

  /* ---------- events ---------- */
  function onTrade(t) {
    if (!t || !t.agent) return;
    push(t.side === "sell" ? sellLine(t) : buyLine(t), t.ts);
  }
  function onDecision(d) {
    if (!d || !d.agent) return;
    push(decisionLine(d), d.ts);
  }
  function onData(d) {
    if (!d || !d.agents || !d.agents.length) return;
    var top = d.agents[0].name;
    if (leader === null) { leader = top; return; }
    if (top !== leader) { leader = top; push(leaderLine(top)); }
  }
  document.addEventListener("arena:trade", function (e) { onTrade(e.detail); });
  document.addEventListener("arena:decision", function (e) { onDecision(e.detail); });
  document.addEventListener("arena:data", function (e) { onData(e.detail); });

  // idle status chatter
  setInterval(function () {
    if (!enabled || !data) return;
    if (now() - lastLineAt >= IDLE_SECS) push(statusLine());
  }, 5000);
  setInterval(tickAgo, 10000);

  // initial render from whatever is already loaded
  function seed() {
    if (!data || !data.agents) return;
    leader = data.agents[0] && data.agents[0].name;
    var recent = (data.trades || []).slice(0, 3).reverse();
    recent.forEach(function (t) { push(t.side === "sell" ? sellLine(t) : buyLine(t), t.ts, { quiet: true }); });
    var s = statusLine();
    if (s) push(s, now(), { quiet: true });
    render(true);
    lastLineAt = now();
  }
  if (data) seed();
  else document.addEventListener("arena:data", function first() { document.removeEventListener("arena:data", first); seed(); });
})();
