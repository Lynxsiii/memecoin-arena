/* screens.js — "Claude screens": one pixel monitor per Claude agent, showing what it is looking at right now. The big
   chart is the coin it is most focused on (the arena's own 30-second prices over up to the last hour, its buys and
   sells marked, a dashed line at its entry while it holds the coin); up to three more coins sit underneath as thumbnails
   (click one to put it on the big chart), then its latest thought. Polls /api/screens every 5s while this tab is open
   and once a minute otherwise (not at all while the browser tab is hidden), keeps the last screens on a network blip
   and shows a one-line note while the arena doesn't serve it yet. Renders into #slot-screens; classes are prefixed sc-. */
(() => {
  "use strict";
  const slot = document.getElementById("slot-screens");
  if (!slot || window.__scScreens) return;
  window.__scScreens = true;
  const FAST_MS = 5000, SLOW_MS = 60000, WINDOW_MS = 60 * 60e3;

  /* ---------- safe access to dashboard globals ---------- */
  const E = typeof esc === "function" ? esc : s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const usd = (n, d = 2) => (typeof money === "function" ? money(Number(n) || 0, d) : "$" + (Number(n) || 0).toFixed(d));
  const sgn = (n, d = 2) => (typeof signed === "function" ? signed(Number(n) || 0, d) : (n >= 0 ? "+" : "-") + usd(Math.abs(n), d));
  const pctText = n => (typeof pct === "function" ? pct(Number(n) || 0) : (n >= 0 ? "+" : "") + (Number(n) || 0).toFixed(1) + "%");
  const spanText = s => (typeof span === "function" ? span(s) : Math.max(0, Math.round(s)) + "s");
  const agoText = s => (typeof ago === "function" ? ago(s) : Math.round(s) + "s ago");
  const sprite = key => (typeof spriteSVG === "function" ? spriteSVG(key).replace('class="bob"', "") : "");
  const arena = () => (typeof data === "object" && data) || null;
  const palette = () => (typeof AVATAR_COLOR === "object" && AVATAR_COLOR) || {};
  const agentOf = name => { const d = arena(); return d && Array.isArray(d.agents) ? d.agents.find(a => a && a.name === name) || null : null; };
  const colourFor = (s, a) => { try { if (a && typeof colorOf === "function") return colorOf(a); } catch {} return palette()[s.avatar] || "#c8d0e8"; };
  const heartsOf = a => { try { return a && typeof heartsHTML === "function" ? heartsHTML(a) : ""; } catch { return ""; } };
  const exitsOf = x => { try { return x && typeof exitsText === "function" ? exitsText(x) : ""; } catch { return ""; } };
  let skew = 0;                                   // server clock minus browser clock, from the screens payload
  const tnow = () => Date.now() / 1000 + skew;

  /* ---------- formatting ---------- */
  const SUB = "₀₁₂₃₄₅₆₇₈₉";
  const subZeros = n => [...String(n)].map(c => SUB[+c]).join("");
  // 0.0000123 → $0.0₄123, 0.0456 → $0.0456, 1234 → $1,234 (the token chart's format)
  function price(p) {
    if (!(p > 0)) return "–";
    if (p >= 1000) return "$" + Math.round(p).toLocaleString();
    if (p >= 1) return "$" + p.toFixed(p >= 100 ? 1 : 2);
    if (p >= 0.01) return "$" + p.toFixed(4);
    const [mant, ex] = p.toExponential(2).split("e"), zeros = -Number(ex) - 1, digits = mant.replace(".", "");   // three significant digits, rounded
    return zeros < 3 ? "$0." + "0".repeat(Math.max(0, zeros)) + digits : "$0.0" + subZeros(zeros) + digits;
  }
  // axis labels: the tick step's own decimals, so neighbouring ticks never read the same
  function axisPrice(v, dec) {
    if (!(v > 0)) return "$0";
    if (v >= 1000) return "$" + Math.round(v).toLocaleString();
    const s = v.toFixed(Math.min(14, Math.max(v >= 100 ? 0 : v >= 1 ? 2 : 0, dec))), m = s.match(/^0\.(0{3,})(\d+)$/);
    return m ? "$0.0" + subZeros(m[1].length) + (m[2].length > 2 ? m[2].replace(/0+$/, "").padEnd(2, "0") : m[2]) : "$" + s;
  }
  // about n ticks on a 1 / 2 / 2.5 / 5 step, with the decimals that step needs
  function niceTicks(lo, hi, n) {
    const raw = (hi - lo) / n;
    if (!(raw > 0)) return {dec: 2, ticks: []};
    const exp = Math.floor(Math.log10(raw)), mag = Math.pow(10, exp), f = raw / mag;
    const m = [1, 2, 2.5, 5, 10].reduce((b, c) => Math.abs(c - f) < Math.abs(b - f) ? c : b), step = m * mag, ticks = [];
    for (let k = Math.ceil(lo / step - 1e-9); k <= Math.floor(hi / step + 1e-9) && ticks.length < 8; k++) ticks.push(k * step);
    return {dec: Math.max(0, -exp + (m === 2.5 ? 1 : 0) - (m === 10 ? 1 : 0)), ticks};
  }
  const big = n => n == null ? "–" : n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}k` : usd(n, 0);
  const chg = n => n == null ? `<b class="sc-flat">–</b>` : `<b class="${n > 0.05 ? "pos" : n < -0.05 ? "neg" : "sc-flat"}">${n > 0 ? "+" : ""}${n.toFixed(1)}%</b>`;
  const short = w => (w = String(w || ""), w.length > 12 && !w.includes("…") ? w.slice(0, 4) + "…" + w.slice(-4) : w);
  const clockHM = ms => new Date(ms).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"});
  const nextText = (ts, t) => ts > t + 1 ? `Next look in ${spanText(ts - t)}` : "Looking again any moment";
  const WHY = {ordered: "it just ordered this", mentioned: "mentioned in its last look", holding: "holding", leader: "its leader bought it"};
  const COIN = `<svg class="sc-coin" viewBox="0 0 8 8" shape-rendering="crispEdges" aria-hidden="true"><path fill="#c9961f" d="M2 0h4v1h1v1h1v4H7v1H6v1H2V7H1V6H0V2h1V1h1z"/><path fill="#f7c548" d="M2 1h4v1h1v4H6v1H2V6H1V2h1z"/><path fill="#ffe08a" d="M2 1h2v1H2zM1 2h1v2H1z"/><path fill="#c9961f" d="M3 2h2v1H3zM3 3h1v2H3zM3 5h2v1H3z"/></svg>`;

  /* ---------- the payload, checked field by field (anything malformed is dropped, never thrown) ---------- */
  const num = v => (typeof v === "number" && isFinite(v) ? v : typeof v === "string" && v.trim() !== "" && isFinite(+v) ? +v : null);
  const secs = v => { const n = num(v); return n && n > 0 ? (n > 1e11 ? n / 1000 : n) : null; };   // epoch seconds (milliseconds tolerated)
  function cleanToken(f) {
    if (!f || typeof f !== "object" || !f.token) return null;
    const points = (Array.isArray(f.points) ? f.points : [])
      .map(p => Array.isArray(p) ? [num(p[0]), num(p[1])] : [null, null])
      .filter(([x, y]) => x != null && x > 0 && y != null && y > 0)
      .map(([x, y]) => [x > 1e11 ? x : x * 1000, y])          // epoch ms expected; seconds tolerated
      .sort((a, b) => a[0] - b[0]);
    const trades = (Array.isArray(f.trades) ? f.trades : []).filter(t => t && typeof t === "object" && secs(t.ts))
      .map(t => ({ts: secs(t.ts), side: t.side === "sell" ? "sell" : "buy", usd: num(t.usd), pnl: num(t.pnl)}));
    const p = f.position && typeof f.position === "object" ? f.position : null;
    const position = p ? {cost: num(p.cost), value: num(p.value), pnl_pct: num(p.pnl_pct), held_min: num(p.held_min), moonshot: p.moonshot === true,
                          entry_price: num(p.entry_price), exits: p.exits && typeof p.exits === "object" ? p.exits : null} : null;
    const why = Object.hasOwn(WHY, f.why) ? f.why : "";
    return {token: String(f.token), symbol: String(f.symbol || short(f.token)), why, why_text: String(f.why_text || WHY[why] || ""),
            price: num(f.price), chg_m5: num(f.chg_m5), chg_h1: num(f.chg_h1), liquidity: num(f.liquidity),
            rating: ["green", "yellow", "red"].includes(f.rating) ? f.rating : "", age_min: num(f.age_min), position, points, trades};
  }
  function cleanAgent(s) {
    if (!s || typeof s !== "object" || !s.name) return null;
    const lead = s.leader && typeof s.leader === "object" ? {wallet: String(s.leader.wallet || ""), rank: num(s.leader.rank)} : null;
    return {name: String(s.name), avatar: String(s.avatar || "claude"), persona: s.persona ? String(s.persona) : null, out: s.out === true,
            thinking_since: secs(s.thinking_since), next_run: secs(s.next_run), last_look: secs(s.last_look),
            note: typeof s.note === "string" ? s.note.trim() : "", leader: lead,
            focus: (Array.isArray(s.focus) ? s.focus : []).map(cleanToken).filter(Boolean).slice(0, 4)};
  }

  /* ---------- styles ---------- */
  const style = document.createElement("style");
  style.textContent = `
  .sc-live { display: flex; flex-wrap: wrap; gap: 4px 18px; margin: -4px 0 14px; font-size: 13px; color: var(--haze); font-variant-numeric: tabular-nums; }
  .sc-live b { color: var(--moon); font-weight: 500; }
  .sc-live:empty { display: none; }
  .sc-dot { display: inline-block; width: 8px; height: 8px; margin-right: 6px; background: var(--profit); box-shadow: 0 0 6px var(--profit); }
  .sc-dot.warn { background: var(--gold); box-shadow: none; } .sc-dot.off { background: var(--loss); box-shadow: none; }
  .sc-msg { color: var(--haze); font-size: 14px; padding: 14px 16px; }
  .sc-msg[hidden], .sc-grid[hidden] { display: none; }
  .sc-grid { display: grid; gap: 22px 18px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr)); }

  /* the monitor: a pixel-cornered case with the agent's colour as a power strip on top, a dark CRT screen, a stand.
     Monitors in a row share a height (the screens stretch), so the stands line up. */
  .sc-mon { --c: #c8d0e8; min-width: 0; display: flex; flex-direction: column; }
  .sc-case { position: relative; flex: 1 1 auto; display: flex; flex-direction: column; padding: 11px 10px 10px; background: #29224f;
    box-shadow: inset 0 3px 0 var(--c), inset 3px 0 0 rgba(255, 255, 255, .05), inset -3px -4px 0 rgba(0, 0, 0, .3);
    clip-path: polygon(0 8px, 4px 8px, 4px 4px, 8px 4px, 8px 0, calc(100% - 8px) 0, calc(100% - 8px) 4px, calc(100% - 4px) 4px, calc(100% - 4px) 8px, 100% 8px,
      100% calc(100% - 8px), calc(100% - 4px) calc(100% - 8px), calc(100% - 4px) calc(100% - 4px), calc(100% - 8px) calc(100% - 4px), calc(100% - 8px) 100%,
      8px 100%, 8px calc(100% - 4px), 4px calc(100% - 4px), 4px calc(100% - 8px), 0 calc(100% - 8px)); }
  .sc-stand { position: relative; height: 16px; }
  .sc-stand::before { content: ""; position: absolute; left: 50%; top: 0; width: 44px; height: 10px; margin-left: -22px; background: #1f1944; box-shadow: inset 0 3px 0 rgba(0, 0, 0, .35); }
  .sc-stand::after { content: ""; position: absolute; left: 50%; top: 10px; width: 132px; height: 6px; margin-left: -66px; background: #29224f;
    box-shadow: inset 0 2px 0 rgba(255, 255, 255, .06); clip-path: polygon(4px 0, calc(100% - 4px) 0, calc(100% - 4px) 2px, 100% 2px, 100% 100%, 0 100%, 0 2px, 4px 2px); }

  /* header: sprite, name and hearts, status line with a power LED, points and P&L on the right */
  .sc-head { display: grid; grid-template-columns: 38px minmax(0, 1fr) auto; gap: 3px 10px; align-items: center; padding: 2px 2px 0; }
  .sc-av { grid-row: 1 / 3; width: 38px; height: 33px; padding: 0; background: none; border: 0; cursor: pointer; }
  .sc-av svg { display: block; width: 100%; height: 100%; }
  .sc-id { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .sc-name { min-width: 0; padding: 0; background: none; border: 0; font: 400 24px/1 var(--pixel); letter-spacing: .02em; color: var(--c); text-align: left;
             text-shadow: 2px 2px 0 var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
  .sc-name:hover { text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 3px; }
  .sc-id .hearts { flex: none; }
  .sc-id .hearts svg { width: 11px; }
  .sc-score { grid-column: 3; grid-row: 1 / 3; text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .sc-score b { display: block; font: 400 22px/1 var(--pixel); text-shadow: 2px 2px 0 var(--ink); }
  .sc-score small { display: block; margin-top: 2px; font-size: 12px; color: var(--haze); }
  .sc-state { grid-column: 2; display: flex; flex-wrap: wrap; align-items: center; gap: 2px 10px; min-width: 0; font-size: 12px; color: var(--haze); }
  .sc-led { width: 8px; height: 8px; flex: none; margin-right: -4px; background: var(--profit); box-shadow: 0 0 6px var(--profit); }
  .sc-st { color: var(--moon); font-variant-numeric: tabular-nums; }
  .sc-shadow { color: #ff5fd2; white-space: nowrap; }
  .sc-shadow code { font: 11px/1 ui-monospace, Consolas, monospace; color: var(--moon); background: var(--night); padding: 2px 4px; }
  .sc-mon.thinking .sc-st { color: var(--gold); animation: sc-pulse 1.2s steps(2) infinite; }
  .sc-mon.thinking .sc-led { background: var(--gold); box-shadow: 0 0 6px var(--gold); animation: sc-blink .8s steps(2) infinite; }
  .sc-mon.paused .sc-led { background: var(--haze); box-shadow: none; }
  .sc-mon.out .sc-led { background: var(--loss); box-shadow: none; }
  .sc-mon.out .sc-st { color: var(--loss); }
  .sc-mon.out .sc-av, .sc-mon.out .sc-name { filter: grayscale(1); opacity: .55; }
  @keyframes sc-pulse { 50% { opacity: .45; } }
  @keyframes sc-blink { 50% { opacity: .2; } }

  /* the screen */
  .sc-screen { position: relative; flex: 1 1 auto; display: flex; flex-direction: column; margin-top: 10px; padding: 10px; overflow: hidden; border: 2px solid #0a0818;
    background: radial-gradient(120% 70% at 50% 0%, color-mix(in srgb, var(--c) 9%, transparent), transparent 70%), #0d0a21;
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--c) 22%, transparent), inset 0 0 28px rgba(0, 0, 0, .55); }
  .sc-screen::after { content: ""; position: absolute; inset: 0; z-index: 2; pointer-events: none;
    background: repeating-linear-gradient(0deg, rgba(0, 0, 0, .16) 0 1px, transparent 1px 3px); }
  .sc-mon.thinking .sc-screen::before { content: ""; position: absolute; left: 0; right: 0; top: -40px; height: 40px; z-index: 2; pointer-events: none;
    background: linear-gradient(transparent, color-mix(in srgb, var(--c) 13%, transparent), transparent); animation: sc-scan 2.6s steps(26) infinite; }
  @keyframes sc-scan { to { top: 100%; } }
  .sc-screen [hidden] { display: none !important; }
  .sc-mon.out .sc-screen > :not(.sc-empty) { filter: grayscale(1); opacity: .5; }

  .sc-row1 { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; min-width: 0; }
  .sc-sym { display: inline-flex; align-items: center; gap: 7px; min-width: 0; max-width: 100%; padding: 0; background: none; border: 0; cursor: pointer;
            font: 400 26px/1 var(--pixel); letter-spacing: .02em; color: var(--gold); text-shadow: 2px 2px 0 var(--ink); }
  .sc-sym span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sc-sym:hover span { text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 3px; }
  .sc-rate { width: 8px; height: 8px; flex: none; background: var(--seam); }
  .sc-why { min-width: 0; max-width: 100%; padding: 3px 5px 2px; font: 500 11px/1.1 var(--body); color: var(--ink); background: var(--haze);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sc-why.ordered { background: var(--gold); } .sc-why.holding { background: var(--profit); } .sc-why.leader { background: #ff5fd2; }
  .sc-why.mentioned { background: transparent; color: var(--haze); box-shadow: inset 0 0 0 1px var(--seam); }
  .sc-px { margin-left: auto; font: 400 26px/1 var(--pixel); color: var(--moon); font-variant-numeric: tabular-nums; white-space: nowrap; }
  .sc-meta { display: flex; flex-wrap: wrap; gap: 2px 12px; margin-top: 5px; font-size: 12px; color: var(--haze); font-variant-numeric: tabular-nums; }
  .sc-meta b { font-weight: 500; color: var(--moon); }
  .sc-meta b.pos { color: var(--profit); } .sc-meta b.neg { color: var(--loss); }
  .sc-flat { color: var(--haze); font-weight: 500; }

  .sc-chart { position: relative; flex: none; height: 172px; margin-top: 8px; touch-action: pan-y; cursor: crosshair; outline-offset: 3px; }
  .sc-svg, .sc-svg svg { display: block; width: 100%; height: 100%; }
  .sc-svg svg { overflow: visible; }
  .sc-svg text { font: 400 13px/1 var(--pixel); fill: var(--haze); letter-spacing: .02em; }
  .sc-svg .sc-xl { font-size: 12px; opacity: .85; }
  .sc-svg .sc-gh, .sc-svg .sc-gv { stroke: rgba(163, 157, 203, .14); stroke-width: 1; shape-rendering: crispEdges; }
  .sc-svg .sc-gv { stroke-dasharray: 2 3; }
  .sc-svg .sc-base { stroke: var(--seam); stroke-width: 1; shape-rendering: crispEdges; }
  .sc-svg .sc-first { stroke: rgba(163, 157, 203, .4); stroke-width: 1; stroke-dasharray: 1 3; shape-rendering: crispEdges; }
  .sc-svg .sc-line { fill: none; stroke-width: 2; stroke-linejoin: miter; shape-rendering: crispEdges; }
  .sc-svg .sc-entry { stroke: var(--moon); stroke-opacity: .7; stroke-width: 1; stroke-dasharray: 4 3; shape-rendering: crispEdges; }
  .sc-svg .sc-el { fill: var(--moon); font-size: 13px; paint-order: stroke; stroke: #0d0a21; stroke-width: 3px; stroke-linejoin: round; }
  .sc-svg .sc-mk { stroke: var(--ink); stroke-width: 2px; paint-order: stroke; stroke-linejoin: miter; shape-rendering: crispEdges; }   /* a 1px ink outline */
  .sc-svg .sc-wait { fill: var(--moon); font-size: 20px; } .sc-svg .sc-wait2 { font: 12px var(--body); }
  .sc-svg .sc-ping { transform-box: fill-box; transform-origin: center; animation: sc-ping 1.6s steps(6) infinite; }
  @keyframes sc-ping { from { transform: scale(1); opacity: .7; } to { transform: scale(3); opacity: 0; } }
  .sc-xh { position: absolute; width: 1px; margin-left: 0; background: rgba(238, 234, 251, .5); pointer-events: none; z-index: 1; }
  .sc-xd { position: absolute; width: 8px; height: 8px; margin: -4px 0 0 -4px; background: var(--moon); box-shadow: 0 0 0 2px var(--ink); pointer-events: none; z-index: 1; }
  .sc-tip { position: absolute; z-index: 3; display: grid; gap: 1px; padding: 5px 8px 6px; background: var(--ink); border: 1px solid var(--seam); pointer-events: none;
            box-shadow: 2px 2px 0 rgba(0, 0, 0, .4); font-size: 12px; line-height: 1.25; color: var(--haze); white-space: nowrap; font-variant-numeric: tabular-nums; }
  .sc-tip b { font: 400 20px/1 var(--pixel); color: var(--moon); }
  .sc-tip .sc-tb { color: var(--profit); } .sc-tip .sc-ts { color: var(--gold); } .sc-tip .sc-ts.neg { color: var(--loss); }

  .sc-facts:empty { display: none; }
  .sc-facts { display: grid; gap: 6px; margin-top: 8px; }
  .sc-pos { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 8px; padding: 6px 8px; font-size: 12px; color: var(--haze);
            background: rgba(238, 234, 251, .04); border: 1px solid var(--seam); font-variant-numeric: tabular-nums; }
  .sc-pv { font: 400 19px/1 var(--pixel); color: var(--moon); white-space: nowrap; }
  .sc-pp { font: 400 21px/1 var(--pixel); white-space: nowrap; }
  .sc-pos .moon { margin-left: 0; }
  .sc-ex { flex-basis: 100%; color: var(--gold); }
  .sc-back { justify-self: start; padding: 2px 0; background: none; border: 0; font: 500 12px var(--body); color: var(--gold); cursor: pointer; text-align: left; }
  .sc-back:hover { text-decoration: underline; }

  .sc-thumbs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin-top: 8px; }
  .sc-thumbs:empty { display: none; }
  .sc-thumb { display: grid; gap: 3px; min-width: 0; padding: 5px 6px 4px; background: rgba(238, 234, 251, .03); border: 1px solid var(--seam);
              color: var(--moon); font: inherit; text-align: left; cursor: pointer; }
  .sc-thumb:hover { border-color: var(--haze); background: rgba(238, 234, 251, .06); }
  .sc-tt { display: flex; align-items: baseline; justify-content: space-between; gap: 4px; min-width: 0; font-size: 11px; font-variant-numeric: tabular-nums; }
  .sc-tt b:first-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 400 17px/1 var(--pixel); letter-spacing: .02em; color: var(--gold); }
  .sc-thumb.lead .sc-tt b:first-child::before { content: ""; display: inline-block; width: 5px; height: 5px; margin-right: 4px; vertical-align: 3px; background: var(--gold); }
  .sc-thumb svg { display: block; width: 100%; height: 26px; }
  .sc-thumb svg path { fill: none; stroke-width: 1.5; }
  .sc-thumb small { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; color: var(--haze); }

  .sc-empty { flex: 1 1 auto; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; min-height: 214px; padding: 10px; text-align: center; color: var(--haze); font-size: 13px; }
  .sc-empty b { font: 400 25px/1.1 var(--pixel); letter-spacing: .02em; color: var(--moon); text-shadow: 2px 2px 0 var(--ink); }
  .sc-coin { width: 30px; height: 30px; }
  .sc-cur::after { content: "_"; margin-left: 2px; animation: sc-blink 1s steps(2) infinite; }
  .sc-mon.out .sc-empty b { color: var(--loss); }

  .sc-thought { margin-top: 10px; padding: 0 2px; }
  .sc-tk { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 8px; font: 400 17px/1 var(--pixel); letter-spacing: .02em; color: var(--haze); }
  .sc-tk small { font: 12px var(--body); letter-spacing: 0; }
  .sc-note { margin: 5px 0 0; font-size: 13px; line-height: 1.45; color: var(--moon); overflow-wrap: anywhere; white-space: pre-line;
             display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .sc-note.open { display: block; -webkit-line-clamp: unset; overflow: visible; }
  .sc-note.quiet { color: var(--haze); font-style: italic; }
  .sc-more { margin-top: 2px; padding: 3px 0; background: none; border: 0; font: 500 12px var(--body); color: var(--gold); cursor: pointer; }
  .sc-more:hover { text-decoration: underline; }
  .sc-more[hidden] { display: none; }

  @media (max-width: 640px) {
    .sc-grid { gap: 18px; }
    .sc-case { padding: 10px 8px 8px; }
    .sc-screen { padding: 8px; }
    .sc-head { grid-template-columns: 34px minmax(0, 1fr) auto; gap: 3px 8px; }
    .sc-av { width: 34px; height: 30px; }
    .sc-name { font-size: 22px; }
    .sc-score b { font-size: 20px; }
    .sc-sym, .sc-px { font-size: 23px; }
    .sc-chart { height: 150px; }
    .sc-thumbs { gap: 5px; }
    .sc-thumb { padding: 4px 5px 3px; }
    .sc-tt b:first-child { font-size: 15px; }
    .sc-empty { min-height: 190px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .sc-mon.thinking .sc-st, .sc-mon.thinking .sc-led, .sc-cur::after { animation: none !important; }
    .sc-mon.thinking .sc-screen::before, .sc-svg .sc-ping { display: none; }
  }`;
  document.head.appendChild(style);

  /* ---------- skeleton ---------- */
  slot.innerHTML = `<section class="sc-wrap" aria-labelledby="sc-title">
    <h2 id="sc-title">Claude screens</h2>
    <p class="sub">What each Claude is looking at right now: the coin it's most focused on, drawn from the arena's own 30-second prices over up to the last hour, with its buys and sells marked and its latest thought underneath. Click a small chart to put it on the big screen, a coin's name for its full chart, a Claude's name for its profile.</p>
    <div class="sc-live" id="sc-live"></div>
    <div class="sc-grid" id="sc-grid" hidden></div>
    <div class="panel sc-msg" id="sc-msg" hidden></div>
  </section>`;
  const liveEl = document.getElementById("sc-live"), gridEl = document.getElementById("sc-grid"), msgEl = document.getElementById("sc-msg");

  // repaint only on change, and keep the focused control (matched by data-sc-key) focused across repaints
  function put(el, html) {
    if (el._sc === html) return false;
    const act = document.activeElement, key = act && el.contains(act) ? act.getAttribute("data-sc-key") : null;
    el.innerHTML = html; el._sc = html;
    if (key) { const again = el.querySelector(`[data-sc-key="${CSS.escape(key)}"]`); if (again) again.focus({preventScroll: true}); }
    return true;
  }

  /* ---------- state ---------- */
  let payload = null, state = "loading", fetchedAt = 0, timer = 0, inflight = false, uid = 0;
  const screens = new Map();   // agent name → {el, r (its parts), sel (token picked from a thumbnail), focusKey, noteOpen, hover, geo, s}
  const isOpen = () => { const b = document.getElementById("tabbtn-screens"); return !!b && b.getAttribute("aria-selected") === "true"; };

  /* ---------- one monitor ---------- */
  function build(name) {
    const el = document.createElement("article"), id = ++uid;
    el.className = "sc-mon";
    el.setAttribute("aria-label", `${name}'s screen`);
    el.innerHTML = `<div class="sc-case">
        <div class="sc-head">
          <button type="button" class="sc-who sc-av" tabindex="-1" aria-hidden="true"></button>
          <div class="sc-id"><button type="button" class="sc-who sc-name"></button><span class="sc-hearts"></span></div>
          <div class="sc-score"></div>
          <div class="sc-state"></div>
        </div>
        <div class="sc-screen">
          <div class="sc-bar"></div>
          <div class="sc-chart" tabindex="0" role="img"><div class="sc-svg"></div><i class="sc-xh" hidden></i><i class="sc-xd" hidden></i><div class="sc-tip" hidden></div></div>
          <div class="sc-facts"></div>
          <div class="sc-thumbs"></div>
          <div class="sc-empty" hidden></div>
        </div>
        <div class="sc-thought"><div class="sc-tk"></div><p class="sc-note" id="sc-note-${id}"></p>
          <button type="button" class="sc-more" aria-controls="sc-note-${id}" aria-expanded="false" hidden>more</button></div>
      </div>
      <div class="sc-stand" aria-hidden="true"></div>`;
    const q = c => el.querySelector(c);
    const st = {id, name, el, sel: null, focusKey: null, noteOpen: false, noteText: null, hover: null, geo: null, s: null, tipT: 0,
      r: {av: q(".sc-av"), name: q(".sc-name"), hearts: q(".sc-hearts"), score: q(".sc-score"), state: q(".sc-state"), bar: q(".sc-bar"),
          chart: q(".sc-chart"), svg: q(".sc-svg"), xh: q(".sc-xh"), xd: q(".sc-xd"), tip: q(".sc-tip"), facts: q(".sc-facts"),
          thumbs: q(".sc-thumbs"), empty: q(".sc-empty"), tk: q(".sc-tk"), note: q(".sc-note"), more: q(".sc-more")}};
    el.querySelectorAll(".sc-who").forEach(b => { b.dataset.agent = name; });   // agent-modal.js opens the profile
    st.r.name.textContent = name;
    st.r.name.title = `Open ${name}'s profile`;
    wire(st);
    return st;
  }

  function wire(st) {
    const {chart} = st.r;
    const localX = e => e.clientX - chart.getBoundingClientRect().left;
    const later = () => { clearTimeout(st.tipT); st.tipT = setTimeout(() => hideHover(st), 2500); };   // a tap keeps its readout a moment
    chart.addEventListener("pointermove", e => { clearTimeout(st.tipT); hoverAt(st, localX(e)); });
    chart.addEventListener("pointerdown", e => { clearTimeout(st.tipT); hoverAt(st, localX(e)); });
    chart.addEventListener("pointerleave", e => { if (e.pointerType === "mouse") hideHover(st); else later(); });
    chart.addEventListener("pointerup", e => { if (e.pointerType !== "mouse") later(); });
    chart.addEventListener("pointercancel", later);
    chart.addEventListener("focus", () => { if (st.geo && chart.matches(":focus-visible")) showIndex(st, st.geo.P.length - 1); });
    chart.addEventListener("blur", () => hideHover(st));
    chart.addEventListener("keydown", e => {   // arrow keys walk the readout along the line
      const g = st.geo;
      if (!g) return;
      if (e.key === "Escape") { if (st.hover) { e.preventDefault(); hideHover(st); } return; }
      const d = {ArrowLeft: e.shiftKey ? -10 : -1, ArrowRight: e.shiftKey ? 10 : 1, Home: -1e9, End: 1e9}[e.key];
      if (d === undefined) return;
      e.preventDefault();
      const cur = st.hover && st.hover.ms != null ? indexAtMs(g.P, st.hover.ms) : g.P.length - 1;
      showIndex(st, st.hover && st.hover.ms != null ? cur + d : g.P.length - 1);
    });
    st.el.addEventListener("click", e => {
      const th = e.target.closest(".sc-thumb");
      if (th) {
        st.sel = th.dataset.token; hideHover(st); paintScreen(st);
        if (e.detail === 0) st.r.chart.focus({preventScroll: true});   // from the keyboard: land on the chart it just changed
        return;
      }
      if (e.target.closest(".sc-back")) { st.sel = null; paintScreen(st); if (e.detail === 0) st.r.chart.focus({preventScroll: true}); return; }
      const sym = e.target.closest(".sc-sym");
      if (sym) { openToken(sym.dataset.token, sym.dataset.symbol, sym); return; }
      if (e.target.closest(".sc-more")) { st.noteOpen = !st.noteOpen; paintNote(st); }
    });
  }

  function openToken(address, symbol, from) {
    if (!address) return;
    if (window.arenaTokenChart && typeof window.arenaTokenChart.open === "function") window.arenaTokenChart.open({address, symbol}, from);
    else document.dispatchEvent(new CustomEvent("arena:token-chart", {detail: {address, symbol, trigger: from}}));
  }

  /* ---------- painting ---------- */
  function scoreHTML(a) {
    if (!a) return "";
    const pts = typeof a.points === "number" && isFinite(a.points) ? a.points : null;
    const pnl = typeof a.pnl_pct === "number" && isFinite(a.pnl_pct) ? a.pnl_pct : null;
    const top = pts != null ? `<b class="${pts >= 0 ? "pos" : "neg"}" title="Game points: losses count less in early lives, +25% milestones pay">${pts >= 0 ? "+" : ""}${pts.toFixed(1)} pts</b>`
              : pnl != null ? `<b class="${pnl >= 0 ? "pos" : "neg"}">${pctText(pnl)}</b>` : "";
    const sub = [pts != null && pnl != null ? `<span class="${pnl >= 0 ? "pos" : "neg"}" title="Real profit">${pctText(pnl)}</span>` : "",
                 typeof a.equity === "number" && isFinite(a.equity) ? usd(a.equity, 0) : ""].filter(Boolean).join(" · ");
    return top + (sub ? `<small>${sub}</small>` : "");
  }

  // live status: the summary (the page's 3-second heartbeat, which the stage also uses) wins over the screens payload
  function liveStatus(s, a) {
    const has = k => a && Object.hasOwn(a, k);
    return {out: has("out") ? a.out === true : s.out, thinking: has("thinking_since") ? secs(a.thinking_since) : s.thinking_since,
            next: has("next_run") ? secs(a.next_run) : s.next_run, paused: !!a && a.mode === "paused"};
  }
  function stateHTML(s, live) {
    let text;
    if (live.out) text = "Out of lives";
    else if (live.thinking) text = `Thinking… <span data-sc-since="${live.thinking}"></span>`;
    else if (live.paused) text = "Paused";
    else if (live.next) text = `<span data-sc-next="${live.next}"></span>`;
    else text = "Idle";
    let shadow = "";
    if (s.leader && s.leader.wallet) shadow = `<span class="sc-shadow" title="Copies this top-100 wallet's trades">Shadowing${s.leader.rank != null ? ` #${E(s.leader.rank)}` : ""} <code>${E(short(s.leader.wallet))}</code></span>`;
    else if (s.persona === "shadow") shadow = `<span class="sc-shadow">Picking a trader to shadow</span>`;
    return `<i class="sc-led" aria-hidden="true"></i><span class="sc-st">${text}</span>${shadow}`;
  }

  function paintHead(st) {
    const s = st.s, a = agentOf(s.name), live = liveStatus(s, a);
    st.el.style.setProperty("--c", colourFor(s, a));
    st.el.classList.toggle("out", live.out);
    st.el.classList.toggle("thinking", !live.out && !!live.thinking);
    st.el.classList.toggle("paused", !live.out && !live.thinking && live.paused);
    put(st.r.av, sprite((a && a.avatar) || s.avatar));
    put(st.r.hearts, heartsOf(a));
    put(st.r.score, scoreHTML(a));
    put(st.r.state, stateHTML(s, live));
    return live;
  }

  function barHTML(f) {
    const last = f.price > 0 ? f.price : f.points.length ? f.points[f.points.length - 1][1] : null;
    const rate = `<i class="sc-rate${f.rating ? " r-" + f.rating : ""}" title="${f.rating ? f.rating + " risk rating" : "No risk rating"}"></i>`;
    return `<div class="sc-row1">
        <button type="button" class="sc-sym" data-token="${E(f.token)}" data-symbol="${E(f.symbol)}" data-sc-key="s:${E(f.token)}" title="Open the ${E(f.symbol)} price chart">${rate}<span>${E(f.symbol)}</span></button>
        ${f.why_text ? `<span class="sc-why ${f.why}" title="${E(f.why_text)}">${E(f.why_text)}</span>` : ""}
        <span class="sc-px" title="Latest price">${E(price(last))}</span></div>
      <div class="sc-meta"><span title="Price change, last 5 minutes">5m ${chg(f.chg_m5)}</span><span title="Price change, last hour">1h ${chg(f.chg_h1)}</span>
        <span>liq <b>${E(big(f.liquidity))}</b></span>${f.age_min != null ? `<span><b>${E(spanText(f.age_min * 60))}</b> old</span>` : ""}</div>`;
  }

  function factsHTML(f, lead, picked) {
    const p = f.position;
    let html = "";
    if (p) {
      const ex = exitsOf(p.exits);
      html += `<div class="sc-pos"><span>Position</span>
        <span class="sc-pv">${p.cost != null ? usd(p.cost) : "?"} → ${p.value != null ? usd(p.value) : "?"}</span>
        ${p.pnl_pct != null ? `<span class="sc-pp ${p.pnl_pct >= 0 ? "pos" : "neg"}">${pctText(p.pnl_pct)}</span>` : ""}
        ${p.held_min != null ? `<span>held ${E(spanText(p.held_min * 60))}</span>` : ""}
        ${p.moonshot ? `<span class="moon" title="Moonshot: a small position held for a big runner, stops kept wide">moonshot</span>` : ""}
        ${ex ? `<span class="sc-ex">Exits: ${E(ex)}</span>` : ""}</div>`;
    }
    if (picked && lead) html += `<button type="button" class="sc-back" data-sc-key="back">← Back to ${E(lead.symbol)}, its main focus</button>`;
    return html;
  }

  function emptyHTML(s, live) {
    if (live.out) return `<b>Screen off</b><span>Out of lives: it doesn't trade any more.</span>`;
    return `${COIN}<b>Nothing on screen: sitting in cash<span class="sc-cur" aria-hidden="true"></span></b>
      <span>${live.thinking ? "Thinking about what to look at next." : "No coin in focus right now."}</span>`;
  }

  // the last hour's points, plus the live price at "now" when the last recorded point is older
  function windowPoints(tok, t1) {
    const t0 = t1 - WINDOW_MS, pts = tok.points.filter(p => p[0] >= t0 && p[0] <= t1 + 60e3);
    const last = pts[pts.length - 1];
    if (tok.price > 0 && (!last || t1 - last[0] > 1500)) pts.push([t1, tok.price]);
    return pts;
  }
  // the time span shown: the history there is, rounded up to 5 minutes, between 10 and 60 (a fresh coin isn't squeezed into a corner)
  const spanFor = (pts, t1) => Math.min(WINDOW_MS, Math.max(10 * 60e3, Math.ceil((pts.length ? t1 - pts[0][0] : WINDOW_MS) / 300e3 - 1e-6) * 300e3));
  // the chart is stepped (a price holds until the next one), so a moment reads the step it falls on
  function priceAt(pts, m) {
    if (m <= pts[0][0]) return pts[0][1];
    if (m >= pts[pts.length - 1][0]) return pts[pts.length - 1][1];
    let lo = 0, hi = pts.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (pts[mid][0] <= m) lo = mid; else hi = mid; }
    return pts[lo][1];
  }
  const triUp = (cx, y) => `M${cx - 1} ${y}h2v2h2v2h2v2h2v2h-14v-2h2v-2h2v-2h2z`;      // pixel triangles, 14 wide and 8 tall
  const triDown = (cx, y) => `M${cx - 7} ${y}h14v2h-2v2h-2v2h-2v2h-2v-2h-2v-2h-2v-2h-2z`;

  function chartSVG(st, tok, W, H) {
    const t1 = tnow() * 1000, pts = windowPoints(tok, t1), win = spanFor(pts, t1), t0 = t1 - win, mins = Math.round(win / 60e3);
    const padL = 1, padR = W < 330 ? 50 : 58, padT = 10, padB = 20, pw = W - padL - padR, ph = H - padT - padB, bottom = padT + ph;
    const X = m => Math.round(padL + Math.max(0, Math.min(1, (m - t0) / win)) * pw);
    let grid = "";
    for (let q = 1; q < 4; q++) { const x = Math.round(padL + pw * q / 4) + .5; grid += `<line class="sc-gv" x1="${x}" x2="${x}" y1="${padT}" y2="${bottom}"/>`; }
    grid += `<line class="sc-base" x1="${padL}" x2="${padL + pw}" y1="${bottom + .5}" y2="${bottom + .5}"/>`;
    const xl = `<text class="sc-xl" x="${padL}" y="${H - 4}">${mins} min ago</text><text class="sc-xl" x="${padL + pw / 2}" y="${H - 4}" text-anchor="middle">${+(mins / 2).toFixed(1)} min</text>`
             + `<text class="sc-xl" x="${padL + pw}" y="${H - 4}" text-anchor="end">now</text>`;
    const open = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true" focusable="false">`;
    if (pts.length < 2) {
      return {geo: null, label: `${tok.symbol}: no price history yet. The arena records a price every 30 seconds.`,
              svg: `${open}${grid}${xl}<text class="sc-wait" x="${padL + pw / 2}" y="${padT + ph / 2 - 2}" text-anchor="middle">Collecting prices…</text>`
                 + `<text class="sc-wait2" x="${padL + pw / 2}" y="${padT + ph / 2 + 16}" text-anchor="middle">the arena records one every 30 seconds</text></svg>`};
    }
    const ys = pts.map(p => p[1]);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    const pos = tok.position, entry = pos && pos.entry_price > 0 ? pos.entry_price : null;
    let entryIn = false;
    if (entry) {   // the entry joins the scale unless it would squash the line flat; then it gets an arrow at the edge
      const nlo = Math.min(lo, entry), nhi = Math.max(hi, entry);
      if (nhi - nlo <= Math.max(hi - lo, hi * 0.02) * 4) { lo = nlo; hi = nhi; entryIn = true; }
    }
    if (hi - lo < hi * 0.004) { const m = (hi + lo) / 2; lo = m * 0.997; hi = m * 1.003; }
    const padY = (hi - lo) * 0.12;
    lo = Math.max(0, lo - padY); hi += padY;
    const Y = p => Math.round(padT + (hi - p) / (hi - lo) * ph);
    // price ticks on the right
    const {dec, ticks} = niceTicks(lo, hi, 4), seen = new Set();
    let yl = "";
    for (const v of ticks) {
      const y = Y(v), label = axisPrice(v, dec);
      if (seen.has(label)) continue;
      seen.add(label);
      grid += `<line class="sc-gh" x1="${padL}" x2="${padL + pw}" y1="${y + .5}" y2="${y + .5}"/>`;
      yl += `<text x="${padL + pw + 6}" y="${y + 4}">${E(label)}</text>`;
    }
    // the stepped price line, its fill, where the history starts
    const up = ys[ys.length - 1] >= ys[0], col = up ? "var(--profit)" : "var(--loss)";
    const P = pts.map(([m, p]) => ({x: X(m), y: Y(p), ms: m, p}));
    let d = `M${P[0].x} ${P[0].y}`;
    for (let i = 1; i < P.length; i++) d += `H${P[i].x}V${P[i].y}`;
    const gid = `sc-g${st.id}`;
    let svg = `${open}<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:${col};stop-opacity:.3"/>`
            + `<stop offset="1" style="stop-color:${col};stop-opacity:0"/></linearGradient></defs>${grid}${yl}`;
    if (P[0].x > padL + 6) svg += `<line class="sc-first" x1="${P[0].x + .5}" x2="${P[0].x + .5}" y1="${padT}" y2="${bottom}"/>`;
    svg += `<path d="${d}V${bottom}H${P[0].x}Z" fill="url(#${gid})"/><path class="sc-line" d="${d}" style="stroke:${col}"/>`;
    // the entry of an open position
    if (entry) {
      if (entryIn) {
        const ey = Y(entry), ly = ey - 5 < padT + 9 ? ey + 14 : ey - 5;
        svg += `<line class="sc-entry" x1="${padL}" x2="${padL + pw}" y1="${ey + .5}" y2="${ey + .5}"/><text class="sc-el" x="${padL + 4}" y="${ly}">entry ${E(price(entry))}</text>`;
      } else {
        const above = entry > hi;
        svg += `<text class="sc-el" x="${padL + 4}" y="${above ? padT + 10 : bottom - 5}">entry ${E(price(entry))} ${above ? "↑" : "↓"} off the chart</text>`;
      }
    }
    // its buys (green, pointing up at the line) and sells (gold, or red at a loss, pointing down at it)
    const marks = [];
    for (const tr of tok.trades) {
      const m = tr.ts * 1000;
      if (m < t0 || m > t1 + 60e3) continue;
      const p = priceAt(pts, m);
      marks.push({x: X(m), y: Y(p), ms: m, p, trade: tr});
    }
    marks.sort((a, b) => a.ms - b.ms);
    for (const mk of marks) {
      const buy = mk.trade.side === "buy";
      const fill = buy ? "var(--profit)" : (mk.trade.pnl ?? 0) < 0 ? "var(--loss)" : "var(--gold)";
      const path = buy ? triUp(mk.x, Math.min(mk.y + 3, bottom - 2)) : triDown(mk.x, Math.max(mk.y - 11, 1));
      svg += `<path class="sc-mk" d="${path}" style="fill:${fill}"/>`;
    }
    const L = P[P.length - 1];
    svg += `<rect class="sc-ping" x="${L.x - 3}" y="${L.y - 3}" width="6" height="6" style="fill:${col}"/><rect x="${L.x - 3}" y="${L.y - 3}" width="6" height="6" style="fill:${col}"/>`;
    svg += `${xl}</svg>`;
    const first = ys[0], last = ys[ys.length - 1], buys = marks.filter(m => m.trade.side === "buy").length, sells = marks.length - buys;
    const label = `${tok.symbol} price over the last ${spanText((t1 - pts[0][0]) / 1000)}: ${price(first)} to ${price(last)}, ${pctText((last / first - 1) * 100)}.`
      + (marks.length ? ` ${buys} buy${buys === 1 ? "" : "s"} and ${sells} sell${sells === 1 ? "" : "s"} marked.` : "")
      + (pos && pos.pnl_pct != null ? ` Holding it, ${pctText(pos.pnl_pct)}${entry ? ` from an entry at ${price(entry)}` : ""}.` : "")
      + " Arrow keys read the prices.";
    return {svg, label, geo: {P, marks, W, H, padT, bottom}};
  }

  function paintChart(st, tok) {
    const el = st.r.chart, W = Math.round(el.clientWidth), H = Math.round(el.clientHeight);
    if (W < 120 || !H) { st.geo = null; return; }   // the tab is hidden: painted again when it opens
    const c = chartSVG(st, tok, W, H);
    st.r.svg.innerHTML = c.svg;
    el.setAttribute("aria-label", c.label);
    st.geo = c.geo;
    if (!st.geo) { hideHover(st); return; }
    if (st.hover && st.hover.ms != null) showIndex(st, indexAtMs(st.geo.P, st.hover.ms));
    else if (st.hover && st.hover.x != null) hoverAt(st, st.hover.x);
  }

  function spark(f) {
    const t1 = tnow() * 1000, pts = windowPoints(f, t1), win = spanFor(pts, t1), t0 = t1 - win;
    if (pts.length < 2) return {d: "", col: "var(--haze)"};
    const ys = pts.map(p => p[1]);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    if (hi - lo < hi * 0.004) { const m = (hi + lo) / 2; lo = m * 0.997; hi = m * 1.003; }
    const X = m => (Math.max(0, Math.min(1, (m - t0) / win)) * 100).toFixed(1), Y = p => (25 - (p - lo) / (hi - lo) * 22).toFixed(1);
    let d = `M${X(pts[0][0])} ${Y(pts[0][1])}`;
    for (let i = 1; i < pts.length; i++) d += `H${X(pts[i][0])}V${Y(pts[i][1])}`;
    return {d, col: ys[ys.length - 1] >= ys[0] ? "var(--profit)" : "var(--loss)"};
  }
  function thumbHTML(f, isLead) {
    const sp = spark(f), small = f.why_text || (f.position ? "holding" : "");
    return `<button type="button" class="sc-thumb${isLead ? " lead" : ""}" data-token="${E(f.token)}" data-sc-key="t:${E(f.token)}"
        aria-label="Show ${E(f.symbol)} on the big chart${isLead ? ", its main focus" : ""}" title="${E(small)}">
      <span class="sc-tt"><b>${E(f.symbol)}</b>${chg(f.chg_h1)}</span>
      <svg viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true" focusable="false">${sp.d ? `<path d="${sp.d}" style="stroke:${sp.col}" vector-effect="non-scaling-stroke"/>` : ""}</svg>
      <small>${E(small)}</small></button>`;
  }

  function paintNote(st) {
    const s = st.s, text = s.note, n = st.r.note, more = st.r.more;
    if (text !== st.noteText) { st.noteText = text; st.noteOpen = false; }
    put(st.r.tk, `<span>Last thought</span>${s.last_look ? `<small data-sc-ago="${s.last_look}"></small>` : ""}`);
    if (n._sc !== text) { n.textContent = text || (s.out ? "Out of lives. Not trading any more." : "No thought written yet."); n._sc = text; }
    n.classList.toggle("quiet", !text);
    n.classList.toggle("open", st.noteOpen);
    more.textContent = st.noteOpen ? "less" : "more";
    more.setAttribute("aria-expanded", String(st.noteOpen));
    more.hidden = !st.noteOpen && !(n.clientHeight && n.scrollHeight > n.clientHeight + 1);
  }

  function paintScreen(st) {
    const s = st.s;
    if (!s) return;
    const live = paintHead(st), focus = s.focus, key = focus.map(f => f.token).join("|");
    if (key !== st.focusKey) { st.focusKey = key; st.sel = null; }   // its focus moved on: back to what it's looking at
    const main = (st.sel && focus.find(f => f.token === st.sel)) || focus[0] || null;
    if (!main || main === focus[0]) st.sel = null;
    const empty = !main, r = st.r;
    r.empty.hidden = !empty;
    r.bar.hidden = r.chart.hidden = r.facts.hidden = r.thumbs.hidden = empty;
    if (empty) {
      put(r.empty, emptyHTML(s, live));
      st.geo = null; hideHover(st);
    } else {
      put(r.bar, barHTML(main));
      paintChart(st, main);
      put(r.facts, factsHTML(main, focus[0], !!st.sel));
      put(r.thumbs, focus.filter(f => f !== main).slice(0, 3).map(f => thumbHTML(f, f === focus[0])).join(""));
    }
    paintNote(st);
  }

  /* ---------- the chart readout (hover, tap, arrow keys) ---------- */
  function indexAtX(P, x) {
    let lo = 0, hi = P.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (P[mid].x <= x) lo = mid; else hi = mid; }
    return Math.abs(P[hi].x - x) < Math.abs(P[lo].x - x) ? hi : lo;
  }
  function indexAtMs(P, ms) {
    let lo = 0, hi = P.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (P[mid].ms <= ms) lo = mid; else hi = mid; }
    return Math.abs(P[hi].ms - ms) < Math.abs(P[lo].ms - ms) ? hi : lo;
  }
  function hoverAt(st, x) {
    st.hover = {x};
    const g = st.geo;
    if (!g) return;
    let mk = null;   // a trade marker within a few pixels wins over the plain line
    for (const m of g.marks) if (Math.abs(m.x - x) <= 7 && (!mk || Math.abs(m.x - x) < Math.abs(mk.x - x))) mk = m;
    if (mk) { showAt(st, mk.x, mk.y, mk.p, mk.ms, mk.trade); return; }
    const p = g.P[indexAtX(g.P, x)];
    showAt(st, p.x, p.y, p.p, p.ms, null);
  }
  function showIndex(st, i) {
    const g = st.geo;
    if (!g) return;
    const p = g.P[Math.max(0, Math.min(g.P.length - 1, i))];
    st.hover = {ms: p.ms};
    const mk = g.marks.find(m => Math.abs(m.ms - p.ms) <= 15000);
    showAt(st, p.x, p.y, p.p, p.ms, mk ? mk.trade : null);
  }
  function showAt(st, x, y, p, ms, trade) {
    const {xh, xd, tip} = st.r, g = st.geo;
    xh.hidden = xd.hidden = tip.hidden = false;
    xh.style.left = x + "px"; xh.style.top = g.padT + "px"; xh.style.height = (g.bottom - g.padT) + "px";
    xd.style.left = x + "px"; xd.style.top = y + "px";
    let html = `<b>${E(price(p))}</b><span>${E(clockHM(ms))} · ${E(agoText(Math.max(0, tnow() - ms / 1000)))}</span>`;
    if (trade) {
      const buy = trade.side === "buy";
      html += `<span class="${buy ? "sc-tb" : (trade.pnl ?? 0) < 0 ? "sc-ts neg" : "sc-ts"}">${buy ? "Bought" : "Sold"}${trade.usd != null ? " " + usd(trade.usd) : ""}${!buy && trade.pnl != null ? `, ${sgn(trade.pnl)}` : ""}</span>`;
    }
    if (tip._sc !== html) { tip.innerHTML = html; tip._sc = html; }
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(0, Math.min(g.W - w, x - w / 2)) + "px";
    tip.style.top = (y - h - 12 >= 0 ? y - h - 12 : Math.max(0, Math.min(g.H - h, y + 14))) + "px";
  }
  function hideHover(st) {
    st.hover = null; clearTimeout(st.tipT);
    st.r.xh.hidden = st.r.xd.hidden = st.r.tip.hidden = true;
  }

  /* ---------- the whole tab ---------- */
  function liveHTML() {
    if (state === "missing") return "";   // the note below says it
    if (!payload) return state === "loading" ? `<span><i class="sc-dot warn"></i>Loading the screens…</span>` : "";   // the note below explains a failure
    const list = payload.agents.map(s => liveStatus(s, agentOf(s.name)));
    const n = list.length, thinking = list.filter(l => !l.out && l.thinking).length, out = list.filter(l => l.out).length;
    return `<span><i class="sc-dot${state === "stale" ? " off" : ""}"></i>${state === "stale" ? "Last refresh failed, showing the screens from" : "Live, updated"} <b data-sc-ago="${payload.now}"></b></span>
      <span><b>${n}</b> Claude${n === 1 ? "" : "s"}${thinking ? `, <b>${thinking}</b> thinking` : ""}${out ? `, <b>${out}</b> out of lives` : ""}</span>
      <span>Prices every 30 seconds, up to the last hour</span>`;
  }

  function syncGrid(agents) {
    const names = new Set(agents.map(s => s.name));
    for (const [name, st] of screens) if (!names.has(name)) { st.el.remove(); screens.delete(name); }
    agents.forEach((s, i) => {
      let st = screens.get(s.name);
      if (!st) { st = build(s.name); screens.set(s.name, st); }
      st.s = s;
      const at = gridEl.children[i];
      if (at !== st.el) gridEl.insertBefore(st.el, at || null);
    });
  }

  function paint() {
    put(liveEl, liveHTML());
    if (!payload || !payload.agents.length) {
      gridEl.hidden = true; msgEl.hidden = false;
      msgEl.textContent = state === "missing" ? "Claude screens aren't available yet. Restart the arena (python main.py) so it serves /api/screens; the screens fill in on their own after that."
        : state === "unreachable" ? "Can't reach /api/screens. Is main.py running?"
        : state === "bad" ? "/api/screens answered, but not with a list of agents, so there's nothing to draw. The arena and this page may be out of step; restart the arena."
        : payload ? "No Claude agents are running, so there's nothing on screen. See the README to log Claude Code in, then restart the arena."
        : "Loading the screens…";
      tickTimes();
      return;
    }
    msgEl.hidden = true; gridEl.hidden = false;
    syncGrid(payload.agents);
    for (const st of screens.values()) paintScreen(st);
    tickTimes();
  }

  function tickTimes() {
    const t = tnow();
    slot.querySelectorAll("[data-sc-since]").forEach(el => { el.textContent = spanText(Math.max(0, t - el.dataset.scSince)); });
    slot.querySelectorAll("[data-sc-next]").forEach(el => { el.textContent = nextText(+el.dataset.scNext, t); });
    slot.querySelectorAll("[data-sc-ago]").forEach(el => { el.textContent = agoText(Math.max(0, t - el.dataset.scAgo)); });
  }

  /* ---------- polling: fast while the tab is open, slow otherwise, never while the browser tab is hidden ---------- */
  function schedule(ms) { clearTimeout(timer); timer = setTimeout(load, ms ?? (isOpen() ? FAST_MS : SLOW_MS)); }
  async function load() {
    clearTimeout(timer); timer = 0;
    if (inflight || document.hidden) return;   // visibilitychange picks it up again
    inflight = true;
    try {
      const r = await fetch("/api/screens", {cache: "no-store"});
      if (r.status === 404) { state = "missing"; payload = null; }
      else if (!r.ok) throw new Error(`HTTP ${r.status}`);
      else {
        const j = await r.json();
        if (!j || typeof j !== "object" || !Array.isArray(j.agents)) throw new Error("bad payload");
        const seen = new Set(), agents = [];
        for (const s of j.agents.map(cleanAgent)) if (s && !seen.has(s.name)) { seen.add(s.name); agents.push(s); }
        const n = num(j.now);
        if (n) skew = n - Date.now() / 1000;
        payload = {now: n || tnow(), agents}; state = "ok";
      }
    } catch (e) {
      state = payload ? "stale" : e && e.message === "bad payload" ? "bad" : "unreachable";   // keep the last screens on a blip
    }
    inflight = false; fetchedAt = Date.now();
    if (isOpen()) paint();
    schedule();
  }

  document.addEventListener("arena:tab", e => {
    if (e.detail && e.detail.tab === "screens") {
      paint();   // widths are measurable now that the panel shows
      const age = Date.now() - fetchedAt;
      if (age > 2500) load(); else schedule(FAST_MS - age);
    } else {
      for (const st of screens.values()) hideHover(st);
      if (!inflight) schedule(SLOW_MS);
    }
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !timer && !inflight) load(); });
  // the summary carries points, P&L, hearts and the thinking status: refresh the headers with it
  document.addEventListener("arena:data", () => {
    if (!payload || !isOpen()) return;
    for (const st of screens.values()) if (st.s) paintHead(st);
    put(liveEl, liveHTML());
    tickTimes();
  });
  let raf = 0;
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(() => {
      if (!payload || !isOpen()) return;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => { for (const st of screens.values()) if (st.s) paintScreen(st); });
    }).observe(gridEl);
  }
  setInterval(() => { if (isOpen() && !document.hidden) tickTimes(); }, 1000);

  paint();
  load();
})();
