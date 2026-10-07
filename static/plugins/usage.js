/* Claude usage plugin: how much plan usage each Claude agent eats, plus global and per-agent speed controls. */
(() => {
  "use strict";
  const slot = document.getElementById("slot-usage");
  if (!slot) return;
  const POLL_MS = 5000;

  /* ---------- safe access to dashboard globals ---------- */
  const safe = typeof esc === "function" ? esc : s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const usd = (n, d = 2) => n == null || !isFinite(n) ? "–" : (typeof money === "function" ? money(n, d) : "$" + Number(n).toFixed(d));
  const fmtSpan = s => (typeof span === "function" ? span(s) : Math.round(s) + "s");
  const clockNow = () => (typeof now === "function" ? now() : Date.now() / 1000);
  const sprite = a => (typeof spriteSVG === "function" ? spriteSVG(a.avatar).replace('class="bob"', "") : "");
  const tint = a => (typeof colorOf === "function" ? colorOf(a) : "#c8d0e8");
  const MODE_LABEL = {normal: "Normal", slow: "Slow", paused: "Paused"};

  /* ---------- styles ---------- */
  const style = document.createElement("style");
  style.textContent = `
  .us-wrap { margin-top: 36px; min-width: 0; }
  .us-wrap .sub { max-width: 90ch; }
  .us-panel + .us-panel { margin-top: 12px; }
  .us-plan { padding: 16px 16px 6px; border-bottom: 1px solid var(--seam); display: grid; gap: 14px; }
  .us-plan-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; align-items: baseline; }
  .us-plan-head b { font-weight: 600; font-size: 15px; }
  .us-plan-head span { color: var(--haze); font-size: 12px; }
  .us-win { display: grid; grid-template-columns: 112px minmax(0, 1fr) 64px; gap: 4px 14px; align-items: center; }
  .us-win .us-wl { font-size: 14px; font-weight: 500; }
  .us-win .us-wp { font: 400 34px/1 var(--pixel); text-align: right; font-variant-numeric: tabular-nums; }
  .us-win .us-wmeta { grid-column: 2 / 4; color: var(--haze); font-size: 12px; display: flex; flex-wrap: wrap; gap: 2px 14px; }
  .us-segbar { display: grid; grid-template-columns: repeat(25, 1fr); gap: 3px; height: 18px; }
  .us-segbar i { background: var(--night); box-shadow: inset 0 0 0 1px var(--seam); }
  .us-segbar i.on { background: var(--lvl); box-shadow: inset 0 -4px 0 rgba(0, 0, 0, .22), inset 0 3px 0 rgba(255, 255, 255, .25); }
  .us-plan-warn { color: var(--loss); font-size: 13px; }
  @media (max-width: 560px) {
    .us-win { grid-template-columns: minmax(0, 1fr) 56px; }
    .us-win .us-wl { grid-column: 1 / -1; }
    .us-win .us-wmeta { grid-column: 1 / -1; }
    .us-segbar { grid-template-columns: repeat(20, 1fr); gap: 2px; }
  }
  .us-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); }
  .us-tile { padding: 12px 14px 10px; border-right: 1px solid var(--seam); border-bottom: 1px solid var(--seam); min-width: 0; }
  .us-tile .us-k { color: var(--haze); font-size: 12px; }
  .us-tile .us-v { font: 400 30px/1 var(--pixel); font-variant-numeric: tabular-nums; margin-top: 2px; letter-spacing: .01em;
                   white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .us-tile .us-v.small { font: 400 20px/1.15 var(--pixel); white-space: normal; }
  .us-tile .us-v.m-normal { color: var(--profit); } .us-tile .us-v.m-slow { color: var(--gold); } .us-tile .us-v.m-paused { color: var(--loss); }
  .us-tile .us-note { color: var(--haze); font-size: 12px; margin-top: 3px; }
  .us-tile .us-note.warn { color: var(--gold); }
  .us-bar { position: relative; height: 10px; margin-top: 7px; background: var(--night); border: 2px solid var(--seam); overflow: hidden; }
  .us-bar i { display: block; height: 100%; background: var(--gold); transition: width .6s steps(6); }
  .us-bar.full i { background: var(--loss); }
  .us-bar.off i { background: var(--seam); }

  .us-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 18px; padding: 12px 14px; }
  .us-group { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .us-lbl { color: var(--haze); font-size: 13px; }
  .us-seg { display: inline-flex; border: 1px solid var(--seam); background: var(--night); }
  .us-seg button { font: 500 13px/1 var(--body); color: var(--moon); background: transparent; border: 0; border-right: 1px solid var(--seam);
                   padding: 7px 12px; cursor: pointer; }
  .us-seg button:last-child { border-right: 0; }
  .us-seg button:hover:not(:disabled) { background: var(--dusk); }
  .us-seg button[aria-pressed="true"] { background: #2a2350; box-shadow: inset 0 -3px 0 var(--gold); color: var(--moon); }
  .us-seg button[aria-pressed="true"].slow { box-shadow: inset 0 -3px 0 var(--gold); }
  .us-seg button[aria-pressed="true"].normal { box-shadow: inset 0 -3px 0 var(--profit); }
  .us-seg button[aria-pressed="true"].paused { box-shadow: inset 0 -3px 0 var(--loss); }
  .us-seg button:disabled, .us-btn:disabled { opacity: .45; cursor: default; }
  .us-cap input { width: 92px; font: 400 15px/1 var(--body); font-variant-numeric: tabular-nums; color: var(--moon); background: var(--night);
                  border: 1px solid var(--seam); padding: 6px 8px; }
  .us-cap input:focus { outline: 2px solid var(--gold); outline-offset: 1px; }
  .us-btn { font: 500 13px/1 var(--body); color: var(--moon); background: var(--dusk); border: 1px solid var(--seam); padding: 7px 10px; cursor: pointer; }
  .us-btn:hover:not(:disabled) { border-color: var(--haze); }
  .us-hint { color: var(--haze); font-size: 12px; flex-basis: 100%; }
  .us-err { flex-basis: 100%; color: var(--loss); font-size: 13px; }
  .us-err:empty { display: none; }

  .us-tablewrap { overflow-x: auto; scrollbar-color: var(--seam) transparent; }
  .us-table { width: 100%; border-collapse: collapse; min-width: 980px; }
  .us-table th, .us-table td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--seam); white-space: nowrap; vertical-align: middle; }
  .us-table th { color: var(--haze); font-weight: 500; font-size: 12px; }
  .us-table th button { all: unset; cursor: pointer; color: inherit; font: inherit; display: inline-block; padding: 2px 0; border-bottom: 1px dashed transparent; }
  .us-table th button:hover { color: var(--moon); }
  .us-table th button:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; }
  .us-table th[aria-sort] button { color: var(--moon); border-bottom-color: var(--gold); }
  .us-table th[aria-sort="descending"] button::after { content: " ▾"; color: var(--gold); }
  .us-table th[aria-sort="ascending"] button::after { content: " ▴"; color: var(--gold); }
  .us-table th.n, .us-table td.n { text-align: right; font-variant-numeric: tabular-nums; }
  .us-table tr:last-child td { border-bottom: 0; }
  .us-table td:first-child, .us-table th:first-child { padding-left: 14px; }
  .us-who { display: flex; align-items: center; gap: 9px; min-width: 190px; }
  .us-who svg { width: 28px; height: 25px; flex: none; }
  .us-who b { display: block; font: 400 20px/1 var(--pixel); color: var(--c); }
  .us-who small { display: block; color: var(--haze); font-size: 11px; margin-top: 1px; }
  .us-badge { display: inline-block; font-size: 12px; line-height: 1; padding: 4px 7px; border: 1px solid var(--seam); color: var(--moon); font-variant-numeric: tabular-nums; }
  .us-badge.m-normal { border-color: var(--profit); color: var(--profit); }
  .us-badge.m-slow { border-color: var(--gold); color: var(--gold); }
  .us-badge.m-paused { border-color: var(--loss); color: var(--loss); }
  .us-badge.m-think { border-color: var(--haze); color: var(--moon); background: var(--night); }
  .us-badge.m-think i { display: inline-block; width: 6px; height: 6px; background: var(--gold); margin-right: 6px; vertical-align: 1px; animation: us-blink 1s steps(2) infinite; }
  @keyframes us-blink { 50% { opacity: .25; } }
  .us-dim { color: var(--haze); font-size: 12px; }
  .us-cost { font-weight: 600; color: var(--moon); }
  .us-share { display: flex; align-items: center; gap: 8px; min-width: 130px; }
  .us-share .us-sbar { flex: 1; height: 10px; background: var(--night); border: 2px solid var(--seam); overflow: hidden; }
  .us-share .us-sbar i { display: block; height: 100%; background: var(--c); transition: width .6s steps(6); }
  .us-share span { width: 36px; text-align: right; font-size: 12px; font-variant-numeric: tabular-nums; color: var(--haze); }
  .us-table .us-seg button { padding: 5px 8px; font-size: 11px; }
  .us-rowerr { color: var(--loss); font-size: 11px; max-width: 220px; white-space: normal; }

  .us-callout { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 4px 16px; align-items: center; padding: 14px 16px; }
  .us-callout svg { width: 44px; height: 39px; grid-row: span 2; }
  .us-callout .us-head { font: 400 26px/1.05 var(--pixel); color: var(--moon); }
  .us-callout .us-head em { font-style: normal; color: var(--gold); }
  .us-callout .us-head em.cheap { color: var(--profit); }
  .us-callout .us-detail { color: var(--haze); font-size: 13px; }
  .us-callout .us-detail b { color: var(--moon); font-weight: 500; font-variant-numeric: tabular-nums; }
  .us-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; grid-column: 2; }
  .us-chip { font-size: 12px; padding: 3px 7px; border: 1px solid var(--seam); background: var(--night); color: var(--moon); font-variant-numeric: tabular-nums; }
  .us-chip b { font-weight: 600; color: var(--c); }
  .us-empty { color: var(--haze); font-size: 14px; padding: 16px; }
  @media (max-width: 640px) {
    .us-tile .us-v { font-size: 26px; }
    .us-callout .us-head { font-size: 22px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .us-badge.m-think i { animation: none; }
    .us-bar i, .us-share .us-sbar i { transition: none; }
  }
  `;
  document.head.appendChild(style);

  /* ---------- skeleton (built once so the cap input keeps focus and typed text) ---------- */
  slot.innerHTML = `
  <section class="us-wrap" aria-labelledby="us-title">
    <h2 id="us-title">Claude usage</h2>
    <p class="sub">How much of the Claude plan each agent eats, and the brakes. Costs are Claude Code's API-price estimates in dollars:
      on a Max plan you aren't charged them, they're a relative measure of plan usage.</p>
    <div class="panel us-panel">
      <div class="us-plan" id="us-plan"></div>
      <div class="us-strip" id="us-strip"></div>
      <div class="us-controls">
        <div class="us-group" role="group" aria-label="Speed for all Claude agents">
          <span class="us-lbl">All Claudes</span>
          <div class="us-seg" id="us-global">
            <button type="button" class="normal" data-mode="normal" aria-pressed="false">Normal</button>
            <button type="button" class="slow" data-mode="slow" aria-pressed="false">Slow</button>
            <button type="button" class="paused" data-mode="paused" aria-pressed="false">Pause</button>
          </div>
        </div>
        <form class="us-group us-cap" id="us-capform" aria-label="Daily cap">
          <label class="us-lbl" for="us-capin">Daily cap $</label>
          <input id="us-capin" type="number" min="0" step="0.5" inputmode="decimal" placeholder="5.00">
          <button type="submit" class="us-btn" id="us-setcap">Set cap</button>
          <button type="button" class="us-btn" id="us-rmcap">Remove cap</button>
        </form>
        <div class="us-hint" id="us-hint"></div>
        <div class="us-err" id="us-err" role="alert"></div>
      </div>
    </div>
    <div class="panel us-panel us-tablewrap" id="us-tablewrap"></div>
    <div class="panel us-panel us-callout" id="us-callout" hidden></div>
  </section>`;

  const $u = id => document.getElementById(id);
  const stripEl = $u("us-strip"), globalEl = $u("us-global"), capIn = $u("us-capin"), setCapBtn = $u("us-setcap"), rmCapBtn = $u("us-rmcap");
  const hintEl = $u("us-hint"), errEl = $u("us-err"), tableEl = $u("us-tablewrap"), calloutEl = $u("us-callout"), planEl = $u("us-plan");

  let usage = null, busy = false, err = "", unreachable = false, syncedCap;
  let sortKey = "cost_total", sortDir = -1;

  /* ---------- data ---------- */
  async function load() {
    try {
      const r = await fetch("/api/usage");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      usage = await r.json();
      unreachable = false;
    } catch (e) {
      unreachable = true;
    }
    paint();
  }

  async function control(body) {
    if (busy) return;
    busy = true; err = ""; paint();
    try {
      const r = await fetch("/api/llm/control", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      let j = null;
      try { j = await r.json(); } catch {}
      if (!r.ok || !j || j.error) throw new Error((j && j.error) || `Request failed (HTTP ${r.status})`);
      usage = j;
    } catch (e) {
      err = e.message || "Request failed";
    }
    busy = false; paint();
  }

  /* ---------- rendering ---------- */
  function setHTML(el, html) {
    if (el._html === html) return;
    const active = document.activeElement, fk = active && el.contains(active) ? active.dataset.fk : null;
    el.innerHTML = html; el._html = html;
    if (fk) { const again = el.querySelector(`[data-fk="${CSS.escape(fk)}"]`); if (again) again.focus(); }
  }

  function tile(k, v, extra = "", cls = "") {
    return `<div class="us-tile"><div class="us-k">${k}</div><div class="us-v ${cls}">${v}</div>${extra}</div>`;
  }

  // Your plan's real 5-hour and weekly limits, as Claude Code reported them on the arena's latest call
  const lvl = pct => pct >= 80 ? "var(--loss)" : pct >= 50 ? "var(--gold)" : "var(--profit)";
  const dur = s => {
    s = Math.max(0, Math.round(s));
    const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    return s < 60 ? `${s}s` : d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
  };
  function paintPlan() {
    const plan = usage && usage.plan;
    if (!plan || !plan.windows || !plan.windows.length) {
      setHTML(planEl, `<div class="us-plan-head"><b>Claude plan limits</b></div>
        <div class="us-note">Your 5-hour and weekly limits show here after the arena's next Claude call.</div>`);
      return;
    }
    const now = usage.now, segs = window.matchMedia("(max-width: 560px)").matches ? 20 : 25;
    const wins = plan.windows.map(w => {
      const on = Math.round(Math.min(100, w.pct) / 100 * segs);
      const bar = Array.from({length: segs}, (_, i) => `<i${i < on ? ' class="on"' : ""}></i>`).join("");
      const pace = w.burn_per_hour == null ? "Pace: measuring (needs 30 min of readings)"
        : w.burn_per_hour <= 0 ? "Pace: flat over the last few hours"
        : `Pace +${w.burn_per_hour.toFixed(1)}% an hour, ${w.full_at ? `full in about ${dur(w.full_at - now)}` : "won't reach 100% before it resets"}`;
      return `<div class="us-win" style="--lvl:${lvl(w.pct)}">
        <div class="us-wl">${safe(w.label)}</div>
        <div class="us-segbar" role="meter" aria-label="${safe(w.label)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${w.pct}">${bar}</div>
        <div class="us-wp" style="color:${lvl(w.pct)}">${Math.round(w.pct)}%</div>
        <div class="us-wmeta">${w.resets_at ? `<span>Resets in ${dur(w.resets_at - now)}</span>` : ""}<span>${pace}</span></div>
      </div>`;
    }).join("");
    const warn = plan.status && plan.status !== "allowed"
      ? `<div class="us-plan-warn">Claude reports your plan status as "${safe(plan.status)}". The arena's calls may be refused.</div>` : "";
    setHTML(planEl, `<div class="us-plan-head"><b>Claude plan limits</b>
      <span>Your account's real figures, from the arena's last Claude call ${dur(now - plan.as_of)} ago. The pace counts everything on your account, not only the arena.</span></div>${wins}${warn}`);
  }

  function paintStrip() {
    if (!usage) {
      setHTML(stripEl, `<div class="us-empty">${unreachable ? "Can't reach /api/usage. Is main.py running?" : "Loading usage…"}</div>`);
      return;
    }
    const u = usage;
    let capV, capExtra;
    if (u.cap == null) {
      capV = `<div class="us-v small">No cap</div>`;
      capExtra = `<div class="us-bar off"><i style="width:0"></i></div><div class="us-note">Set one below to auto-slow everyone.</div>`;
    } else {
      const frac = Math.min(1, u.cap > 0 ? u.spent_today / u.cap : 1);
      capV = u.capped ? `<div class="us-v small" style="color:var(--loss)">Cap reached</div>` : `<div class="us-v">${usd(u.cap)}</div>`;
      capExtra = `<div class="us-bar${u.capped ? " full" : ""}"><i style="width:${(frac * 100).toFixed(1)}%"></i></div>
        <div class="us-note${u.capped ? " warn" : ""}">${u.capped ? `Running slow until midnight. ${usd(u.spent_today)} of ${usd(u.cap)} used.` : `${usd(u.cap)} a day, ${usd(u.spent_today)} used`}</div>`;
    }
    const modeNote = u.mode === "normal" ? (u.capped ? "Cap forces slow" : "Agents pick their own pace")
                   : u.mode === "slow" ? `One look every ${u.slow_minutes} min` : "No Claude calls until resumed";
    const html = [
      tile("Spent today", usd(u.spent_today), `<div class="us-note">since midnight</div>`),
      tile("Last 24 hours", usd(u.spent_24h)),
      tile("Total", usd(u.spent_total), `<div class="us-note">${(u.agents || []).reduce((s, a) => s + a.calls, 0).toLocaleString()} calls</div>`),
      u.projected_week == null
        ? tile("Projected per week", `<span class="us-v small" style="color:var(--haze)">Measuring…</span>`, `<div class="us-note">needs 15 min of data</div>`)
        : tile("Projected per week", usd(u.projected_week), `<div class="us-note">from the last 24 h</div>`),
      tile("Mode", MODE_LABEL[u.mode] || safe(u.mode), `<div class="us-note">${modeNote}</div>`, "m-" + u.mode),
      `<div class="us-tile"><div class="us-k">Daily cap</div>${capV}${capExtra}</div>`,
    ].join("");
    setHTML(stripEl, html);
  }

  function paintControls() {
    const u = usage;
    globalEl.querySelectorAll("button").forEach(b => {
      b.setAttribute("aria-pressed", String(!!u && b.dataset.mode === u.mode));
      b.disabled = busy || !u;
    });
    setCapBtn.disabled = busy || !u;
    rmCapBtn.disabled = busy || !u || u.cap == null;
    capIn.disabled = !u;
    if (u && u.cap !== syncedCap) {  // mirror a cap set elsewhere, but never over the user's typing
      syncedCap = u.cap;
      if (document.activeElement !== capIn) capIn.value = u.cap == null ? "" : String(u.cap);
    }
    hintEl.textContent = u
      ? `Slow means each Claude looks at the market once every ${u.slow_minutes} minutes. Pause stops Claude calls entirely (open positions are kept, bots keep going). Settings survive restarts.`
      : "";
    errEl.textContent = err;
  }

  const COLS = [
    {key: "name", label: "Agent", num: false},
    {key: "mode", label: "Mode", num: false},
    {key: "calls", label: "Calls", num: true, title: "total calls (last hour)"},
    {key: "avg_tokens", label: "Tokens per call", num: true},
    {key: "avg_secs", label: "Thinking per call", num: true},
    {key: "cost_1h", label: "Cost 1 h", num: true},
    {key: "cost_24h", label: "Cost 24 h", num: true},
    {key: "cost_total", label: "Total cost", num: true},
    {key: "avg_cost", label: "Per call", num: true},
    {key: "share", label: "Share", num: false},
    {key: "est_weekly_pct_per_day", label: "≈ Weekly/day", num: true, title: "rough share of your weekly limit per day, from this agent's share of arena spend and the weekly pace"},
    {key: "control", label: "Speed", num: false, nosort: true},
  ];
  const MODE_RANK = {normal: 0, slow: 1, paused: 2};

  function sortValue(a, key, total) {
    switch (key) {
      case "name": return a.name.toLowerCase();
      case "mode": return (a.thinking_since ? -1 : MODE_RANK[a.mode] ?? 9);
      case "share": return total ? a.cost_total / total : 0;
      default: return a[key] == null ? -Infinity : a[key];
    }
  }

  function paintTable() {
    if (!usage) { setHTML(tableEl, ""); return; }
    const agents = usage.agents || [];
    if (!agents.length) { setHTML(tableEl, `<div class="us-empty">No Claude agents are running.</div>`); return; }
    const total = agents.reduce((s, a) => s + (a.cost_total || 0), 0);
    const rows = [...agents].sort((x, y) => {
      const a = sortValue(x, sortKey, total), b = sortValue(y, sortKey, total);
      const c = typeof a === "string" ? a.localeCompare(b) : a - b;
      return (c || x.name.localeCompare(y.name)) * sortDir;
    });
    const head = COLS.map(c => `<th class="${c.num ? "n" : ""}"${c.key === sortKey ? ` aria-sort="${sortDir < 0 ? "descending" : "ascending"}"` : ""}${c.title ? ` title="${safe(c.title)}"` : ""}>
      ${c.nosort ? safe(c.label) : `<button type="button" data-sort="${c.key}" data-fk="sort:${c.key}">${safe(c.label)}</button>`}</th>`).join("");
    const body = rows.map(a => {
      const badge = a.thinking_since
        ? `<span class="us-badge m-think"><i></i>thinking <span data-since="${a.thinking_since}">${fmtSpan(clockNow() - a.thinking_since)}</span></span>`
        : `<span class="us-badge m-${safe(a.mode)}">${(MODE_LABEL[a.mode] || safe(a.mode)).toLowerCase()}</span>`;
      const share = total ? a.cost_total / total * 100 : 0;
      const seg = ["normal", "slow", "paused"].map(m => `<button type="button" class="${m}" data-agent="${safe(a.name)}" data-mode="${m}"
          data-fk="row:${safe(a.name)}:${m}" aria-pressed="${a.override === m}" aria-label="${safe(a.name)}: ${MODE_LABEL[m]}"${busy ? " disabled" : ""}>${m === "paused" ? "Pause" : MODE_LABEL[m]}</button>`).join("");
      const sub = [a.persona, a.model].filter(Boolean).map(safe).join(" · ");
      return `<tr data-agent="${safe(a.name)}" style="--c:${tint(a)}">
        <td><div class="us-who">${sprite(a)}<div><b>${safe(a.name)}</b>${sub ? `<small>${sub}</small>` : ""}</div></div></td>
        <td>${badge}${a.error ? `<div class="us-rowerr">${safe(a.error)}</div>` : ""}</td>
        <td class="n">${a.calls.toLocaleString()} <span class="us-dim">(${a.calls_1h} in 1 h)</span>${a.errors ? `<div class="us-dim" style="color:var(--loss)">${a.errors} failed</div>` : ""}</td>
        <td class="n">${a.avg_tokens == null ? "–" : a.avg_tokens.toLocaleString()}</td>
        <td class="n">${a.avg_secs == null ? "–" : a.avg_secs.toFixed(1) + "s"}</td>
        <td class="n">${usd(a.cost_1h, 3)}</td>
        <td class="n">${usd(a.cost_24h)}</td>
        <td class="n"><span class="us-cost">${usd(a.cost_total)}</span></td>
        <td class="n">${usd(a.avg_cost, 3)}</td>
        <td><div class="us-share"><div class="us-sbar"><i style="width:${share.toFixed(1)}%"></i></div><span>${share.toFixed(0)}%</span></div></td>
        <td class="n">${a.est_weekly_pct_per_day == null ? `<span class="us-dim">measuring</span>` : `≈${a.est_weekly_pct_per_day.toFixed(1)}%`}</td>
        <td><div class="us-seg">${seg}</div></td>
      </tr>`;
    }).join("");
    setHTML(tableEl, `<table class="us-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
  }

  function paintCallout() {
    const agents = usage ? usage.agents || [] : [];
    const fable = agents.find(a => /fable/i.test(a.name) || /fable/i.test(a.model || ""));
    const rest = agents.filter(a => a !== fable && a.calls > 0 && a.avg_cost != null);
    if (!fable || !fable.calls || fable.avg_cost == null || !rest.length) { calloutEl.hidden = true; return; }
    const restAvg = rest.reduce((s, a) => s + a.avg_cost, 0) / rest.length;
    const ratio = restAvg > 0 ? fable.avg_cost / restAvg : null;
    const x = r => r == null ? "–" : (r >= 10 ? r.toFixed(0) : r.toFixed(1)) + "x";
    const headline = ratio == null ? `${safe(fable.name)} costs ${usd(fable.avg_cost, 3)} per call`
      : ratio >= 1.05 ? `${safe(fable.name)} costs <em>${x(ratio)}</em> the other Claudes per call`
      : ratio <= 0.95 ? `${safe(fable.name)} costs <em class="cheap">${x(ratio)}</em> the other Claudes per call`
      : `${safe(fable.name)} costs <em class="cheap">about the same</em> as the other Claudes per call`;
    const chips = [...rest].sort((a, b) => b.avg_cost - a.avg_cost).map(a =>
      `<span class="us-chip" style="--c:${tint(a)}">${x(a.avg_cost > 0 ? fable.avg_cost / a.avg_cost : null)} <b>${safe(a.name)}</b></span>`).join("");
    calloutEl.hidden = false;
    calloutEl.style.setProperty("--c", tint(fable));
    setHTML(calloutEl, `${sprite(fable)}
      <div class="us-head">${headline}</div>
      <div class="us-detail"><b>${usd(fable.avg_cost, 3)}</b> per call over ${fable.calls} call${fable.calls === 1 ? "" : "s"},
        against an average of <b>${usd(restAvg, 3)}</b> for the other ${rest.length} Claude${rest.length === 1 ? "" : "s"}.
        Per call, ${safe(fable.name)} is:</div>
      <div class="us-chips">${chips}</div>`);
  }

  function paint() { paintPlan(); paintStrip(); paintControls(); paintTable(); paintCallout(); }

  /* ---------- interaction ---------- */
  globalEl.addEventListener("click", e => {
    const b = e.target.closest("button[data-mode]");
    if (b && !b.disabled) control({mode: b.dataset.mode});
  });
  $u("us-capform").addEventListener("submit", e => {
    e.preventDefault();
    const v = capIn.value.trim();
    const n = Number(v);
    if (!v || !isFinite(n) || n < 0) { err = "Enter a dollar amount of 0 or more for the daily cap."; paintControls(); return; }
    control({cap: n});
  });
  rmCapBtn.addEventListener("click", () => { if (!rmCapBtn.disabled) control({cap: null}); });
  tableEl.addEventListener("click", e => {
    const s = e.target.closest("button[data-sort]");
    if (s) {
      const key = s.dataset.sort;
      if (key === sortKey) sortDir = -sortDir;
      else { sortKey = key; sortDir = key === "name" ? 1 : -1; }
      paintTable();
      return;
    }
    const b = e.target.closest("button[data-agent][data-mode]");
    if (b && !b.disabled) control({mode: b.dataset.mode, agent: b.dataset.agent});
  });

  /* ---------- loop ---------- */
  paint();
  load();
  setInterval(load, POLL_MS);
  let bump;
  document.addEventListener("arena:decision", () => { clearTimeout(bump); bump = setTimeout(load, 400); });
})();
