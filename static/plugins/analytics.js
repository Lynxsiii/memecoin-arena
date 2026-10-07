/* Who's really winning plugin: luck checks, confidence vs the benchmark bots, risk- and cost-adjusted results, and a
   readiness checklist per Claude, from /api/analytics. Renders into #slot-analytics (the header links to the daily recap).
   Newer arenas also send a per-agent `extra` report card (alpha vs each yardstick, fee drag, top-3 share, average win and
   loss); its columns only appear when it's there. The latest payload is shared as window.arenaAnalytics plus an
   "arena:analytics" event, so the agent profile can show the same numbers without fetching again. */
(() => {
  "use strict";
  const slot = document.getElementById("slot-analytics");
  if (!slot) return;
  const POLL_MS = 30000;

  /* ---------- safe access to dashboard globals ---------- */
  const safe = typeof esc === "function" ? esc : s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const usd = (n, d = 2) => n == null || !isFinite(n) ? "–" : (typeof money === "function" ? money(n, d) : "$" + Number(n).toFixed(d));
  const sgn = (n, d = 0) => n == null || !isFinite(n) ? "–" : (typeof signed === "function" ? signed(n, d) : (n >= 0 ? "+" : "-") + "$" + Math.abs(n).toFixed(d));
  const fmtSpan = s => (typeof span === "function" ? span(s) : Math.round(s / 60) + " min");
  const sprite = a => (typeof spriteSVG === "function" ? spriteSVG(a.avatar).replace('class="bob"', "") : "");
  const tint = a => (typeof colorOf === "function" ? colorOf(a) : "#c8d0e8");
  const prefs = typeof arenaPrefs !== "undefined" ? arenaPrefs : {get: (k, d) => d, set() {}};
  const share = d => { if (typeof emit === "function") emit("arena:analytics", d); else try { document.dispatchEvent(new CustomEvent("arena:analytics", {detail: d})); } catch (e) {} };

  /* ---------- styles ---------- */
  const style = document.createElement("style");
  style.textContent = `
  .an-wrap { margin-top: 32px; min-width: 0; }
  .an-wrap h2 { font: 600 18px/1.3 var(--body); margin: 0 0 4px; }
  .an-wrap .sub { color: var(--haze); font-size: 13px; margin: 0 0 12px; max-width: 90ch; }
  .an-tablewrap { overflow-x: auto; scrollbar-color: var(--seam) transparent; }
  .an-table { width: 100%; border-collapse: collapse; min-width: 1060px; }
  .an-table th, .an-table td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--seam); white-space: nowrap; vertical-align: middle; font-size: 13px; }
  .an-table th { color: var(--haze); font-weight: 500; font-size: 12px; vertical-align: bottom; }
  .an-table th button { all: unset; cursor: pointer; color: inherit; font: inherit; display: inline-block; padding: 2px 0; border-bottom: 1px dashed transparent; }
  .an-table th button:hover { color: var(--moon); }
  .an-table th button:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; }
  .an-table th[aria-sort] button { color: var(--moon); border-bottom-color: var(--gold); }
  .an-table th[aria-sort="descending"] button::after { content: " \\25BE"; color: var(--gold); }
  .an-table th[aria-sort="ascending"] button::after { content: " \\25B4"; color: var(--gold); }
  .an-table th.n, .an-table td.n { text-align: right; font-variant-numeric: tabular-nums; }
  .an-table tr:last-child td { border-bottom: 0; }
  .an-table td:first-child, .an-table tr:first-child > th:first-child { padding-left: 14px; }
  .an-table tr.an-bench td { background: rgba(255, 255, 255, .025); }
  .an-table th.an-group { text-align: center; color: var(--moon); padding-bottom: 3px; }
  .an-table th.an-group span { cursor: help; border-bottom: 1px dashed var(--seam); }
  .an-table thead tr + tr th { padding-top: 3px; }
  .an-table .an-gs { border-left: 1px solid var(--seam); }
  .an-table .an-ge { border-right: 1px solid var(--seam); }
  .an-table td small { font-size: 11px; }
  .an-table.an-wide { width: max-content; min-width: 100%; }   /* with the report card it's wider than the panel: scroll, don't squeeze */
  .an-table.an-wide td.an-vs .an-chip { display: block; width: max-content; max-width: none; white-space: nowrap; }
  .an-who { display: flex; align-items: center; gap: 9px; min-width: 170px; }
  .an-who svg { width: 26px; height: 23px; flex: none; }
  .an-who b { display: block; font: 400 19px/1 var(--pixel); color: var(--c); }
  .an-who small { display: block; color: var(--haze); font-size: 11px; margin-top: 1px; }
  .an-pos { color: var(--profit); } .an-neg { color: var(--loss); } .an-dim { color: var(--haze); } .an-hot { color: var(--gold); }
  .an-flag { display: inline-block; font-size: 11px; line-height: 1.2; padding: 3px 6px; border: 1px solid var(--seam); color: var(--moon); white-space: normal; max-width: 190px; }
  .an-flag.hot { border-color: var(--gold); color: var(--gold); }
  .an-flag.none { color: var(--haze); border-style: dashed; }
  .an-chip { display: inline-block; font-size: 11px; line-height: 1.25; padding: 3px 7px; border: 1px solid var(--seam); background: var(--night); color: var(--moon); white-space: normal; max-width: 210px; font-variant-numeric: tabular-nums; }
  .an-chip b { font-weight: 600; }
  .an-chip.good b { color: var(--profit); } .an-chip.bad b { color: var(--loss); } .an-chip.thin { color: var(--haze); }
  .an-chip + .an-chip { margin-top: 4px; }
  .an-meter { display: inline-block; width: 46px; height: 6px; margin-right: 6px; vertical-align: 2px; background: var(--night); border: 1px solid var(--seam); overflow: hidden; }
  .an-meter i { display: block; height: 100%; background: var(--gold); }
  .an-meter.good i { background: var(--profit); } .an-meter.bad i { background: var(--loss); } .an-meter.calm i { background: var(--haze); }

  .an-ready { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr)); margin-top: 14px; }
  .an-check { min-width: 0; }
  .an-check summary { list-style: none; cursor: pointer; display: grid; grid-template-columns: 30px minmax(0, 1fr) auto; gap: 2px 10px; align-items: center; padding: 10px 12px; }
  .an-check summary::-webkit-details-marker { display: none; }
  .an-check summary:focus-visible { outline: 2px solid var(--gold); outline-offset: -2px; }
  .an-check summary svg { width: 28px; height: 25px; grid-row: span 2; }
  .an-check summary b { font: 400 19px/1 var(--pixel); color: var(--c); }
  .an-check summary small { color: var(--haze); font-size: 12px; grid-column: 2; }
  .an-check .an-score { font: 400 22px/1 var(--pixel); color: var(--haze); grid-row: span 2; font-variant-numeric: tabular-nums; }
  .an-check[open] summary { border-bottom: 1px solid var(--seam); }
  .an-check .an-verdict { padding: 8px 12px 0; font-size: 13px; font-weight: 500; }
  .an-check .an-verdict.yes { color: var(--profit); } .an-check .an-verdict.no { color: var(--gold); }
  .an-check ul { list-style: none; margin: 0; padding: 6px 12px 10px; display: grid; gap: 6px; }
  .an-check li { display: grid; grid-template-columns: 14px minmax(0, 1fr); gap: 8px; font-size: 13px; line-height: 1.35; }
  .an-check li i { display: block; width: 10px; height: 10px; margin-top: 4px; }
  .an-check li.ok i { background: var(--profit); } .an-check li.ko i { background: var(--loss); }
  .an-check li small { display: block; color: var(--haze); font-size: 12px; }
  .an-check .an-chips { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 12px 10px; }
  .an-check .an-chips .an-chip + .an-chip { margin-top: 0; }
  .an-legend { color: var(--haze); font-size: 12px; line-height: 1.5; margin: 10px 0 0; max-width: 90ch; }
  .an-legend b { color: var(--moon); font-weight: 500; }
  .an-note { color: var(--haze); font-size: 12px; margin: 12px 0 0; max-width: 90ch; }
  .an-empty { color: var(--haze); font-size: 14px; padding: 16px; }
  .an-toggle { margin-left: auto; font: 500 12px/1 var(--body); color: var(--haze); background: transparent; border: 1px solid var(--seam); padding: 5px 8px; cursor: pointer; }
  .an-toggle:hover { color: var(--moon); border-color: var(--haze); }
  .an-head { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px 16px; margin-bottom: 12px; }
  .an-head .sub { margin: 0; }
  @media (min-width: 641px) {   /* the agent column stays put while the numbers scroll sideways */
    .an-table tr:first-child > th:first-child, .an-table td:first-child { position: sticky; left: 0; z-index: 1; background: var(--dusk); }
    .an-table tr.an-bench td:first-child { background: color-mix(in srgb, #fff 2.5%, var(--dusk)); }
  }
  @media (max-width: 640px) {
    .an-table th, .an-table td { padding: 8px 8px; }
    .an-ready { grid-template-columns: minmax(0, 1fr); }
  }
  `;
  document.head.appendChild(style);

  /* ---------- skeleton ---------- */
  slot.innerHTML = `<section class="an-wrap block" aria-labelledby="an-title">
    <div class="an-head"><div><h2 id="an-title">Who's really winning</h2>
      <p class="sub">Raw P&amp;L lies. This strips out each agent's luckiest trade, asks how confident we can be that a Claude truly beats the benchmark bots, measures how far ahead of each one it is, and weighs results against fees, drawdown and plan usage.</p></div>
      <button type="button" class="an-toggle" id="an-toggle" aria-pressed="false">Show bots too</button></div>
    <div class="panel an-tablewrap"><div class="an-empty" id="an-status">Loading analytics…</div><table class="an-table" id="an-table" hidden>
      <thead id="an-thead"></thead><tbody id="an-body"></tbody></table></div>
    <p class="an-legend" id="an-legend" hidden></p>
    <div class="an-ready" id="an-ready"></div>
    <p class="an-note" id="an-note"></p>
  </section>`;
  const statusEl = document.getElementById("an-status"), table = document.getElementById("an-table");
  const thead = document.getElementById("an-thead"), body = document.getElementById("an-body");
  const readyEl = document.getElementById("an-ready"), noteEl = document.getElementById("an-note");
  const legendEl = document.getElementById("an-legend");
  const toggle = document.getElementById("an-toggle");
  const setHTML = (el, html) => { if (el._anHtml !== html) { el.innerHTML = html; el._anHtml = html; } };

  /* ---------- state ---------- */
  let analytics = null, showBots = prefs.get("an-show-bots", true), bench = new Set();
  let sortKey = prefs.get("an-sort", "pnl"), sortDir = prefs.get("an-sort-dir", "desc");
  toggle.setAttribute("aria-pressed", String(!showBots));
  toggle.textContent = showBots ? "Claudes only" : "Show bots too";
  toggle.addEventListener("click", () => {
    showBots = !showBots; prefs.set("an-show-bots", showBots);
    toggle.setAttribute("aria-pressed", String(!showBots));
    toggle.textContent = showBots ? "Claudes only" : "Show bots too";
    render();
  });

  const pctTxt = (n, d = 1) => n == null ? "–" : `${n >= 0 ? "+" : ""}${Number(n).toFixed(d)}%`;
  const cls = n => n == null ? "an-dim" : n >= 0 ? "an-pos" : "an-neg";
  const num = v => typeof v === "number" && isFinite(v) ? v : null;
  const extraOf = a => a && a.extra && typeof a.extra === "object" ? a.extra : null;   // older arenas send none
  const startCash = () => num(analytics && analytics.start_cash) || (typeof data !== "undefined" && data && data.start_cash) || 1000;
  const listJoin = xs => xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;

  /* ---------- the extra report card: alpha vs every yardstick, fee drag, top-3 share ---------- */
  const ALPHA_ORDER = ["Hold SOL", "Random", "Graduates"];   // how the yardsticks read left to right; any others follow
  const ALPHA_TIP = "How many percentage points better than this yardstick over the same time";
  const FEE_TIP = () => `Fees paid as a share of the starting ${usd(startCash(), 0)}`;
  const TOP3_TIP = "How much of the profit came from just the 3 best trades (near 100% means it's mostly luck so far)";
  function alphaNames() {
    const seen = new Set();
    for (const a of analytics.agents) {
      const al = extraOf(a)?.alpha;
      if (al && typeof al === "object") Object.keys(al).forEach(k => seen.add(k));
    }
    const listed = Array.isArray(analytics.benchmarks) ? analytics.benchmarks : [];
    const pos = b => { const i = ALPHA_ORDER.indexOf(b); return i >= 0 ? i : ALPHA_ORDER.length + (listed.includes(b) ? listed.indexOf(b) : listed.length); };
    return [...seen].sort((x, y) => pos(x) - pos(y) || x.localeCompare(y));
  }
  function alphaCell(a, b, edge) {
    const x = extraOf(a), v = num(x?.alpha?.[b]);
    if (v == null) return a.name === b ? `<td class="n ${edge} an-dim" title="This is that yardstick">itself</td>` : `<td class="n ${edge} an-dim">–</td>`;
    const what = `${Math.abs(v).toFixed(1)} percentage points ${v >= 0 ? "ahead of" : "behind"} ${b} over the same time`;
    return `<td class="n ${edge} ${cls(v)}" title="${safe(what)}">${v >= 0 ? "+" : ""}${v.toFixed(1)}<small class="an-dim"> pts</small></td>`;
  }
  function feeCell(a) {
    const x = extraOf(a), v = num(x?.fee_drag_pct), f = num(x?.fees_usd);
    if (v == null) return `<td class="n an-dim">–</td>`;
    const what = `${f != null ? usd(f) + " in fees so far, " : ""}${v.toFixed(1)}% of the starting ${usd(startCash(), 0)}`;
    return `<td class="n" title="${safe(what)}">${v.toFixed(1)}%${f != null ? ` <small class="an-dim">${usd(f, f >= 100 ? 0 : 2)}</small>` : ""}</td>`;
  }
  function top3Cell(a) {
    const x = extraOf(a), s = num(x?.top3_share);
    if (s == null) return `<td class="n an-dim"${x ? ` title="No profit yet, so there is nothing to split"` : ""}>–</td>`;
    const p = Math.round(s * 100), hot = s >= 0.8;
    const what = s > 1 ? `The 3 best trades made ${p}% of the net profit: the other trades lost money overall`
                       : `${p}% of the profit came from the 3 best trades${hot ? ", so it's mostly luck so far" : ""}`;
    return `<td class="n${hot ? " an-hot" : ""}" title="${safe(what)}"><span class="an-meter${hot ? "" : " calm"}" aria-hidden="true"><i style="width:${Math.min(100, Math.max(0, p))}%"></i></span>${p}%</td>`;
  }
  function avgTxt(a) {   // "avg +$12.30 / -$8.10" under the win rate, when the report card has it
    const x = extraOf(a), w = num(x?.avg_win_usd), l = num(x?.avg_loss_usd);
    if (w == null && l == null) return "";
    return `<br><small class="an-dim" title="Average winning trade / average losing trade">avg ${sgn(w, 2)} / ${sgn(l, 2)}</small>`;
  }

  /* ---------- columns: key, header, sort value, cell ---------- */
  const C = {
    name: {key: "name", label: "Agent", get: a => a.name, text: true, asc: true,
      cell: a => `<td><div class="an-who">${sprite(a)}<div><b>${safe(a.name)}</b><small>${a.team === "claude" || a.kind === "llm" ? safe(a.model || "Claude") : bench.has(a.name) ? "Benchmark bot" : "Bot"} · ${a.risk.closed} closed · ${fmtSpan(a.hours_of_history * 3600)}</small></div></div></td>`},
    pnl: {key: "pnl", label: "P&L", cls: "n", get: a => a.pnl,
      cell: a => `<td class="n ${cls(a.pnl)}">${sgn(a.pnl)} <small class="an-dim">${pctTxt(a.pnl_pct)}</small></td>`},
    ex_best: {key: "ex_best", label: "Without best trade", cls: "n", get: a => a.luck.pnl_ex_best_any, title: "P&L with the single best trade, closed or still open, removed",
      cell: a => `<td class="n ${cls(a.luck.pnl_ex_best_any)}">${sgn(a.luck.pnl_ex_best_any)}<br><small class="an-dim">ex worst too ${sgn(a.luck.pnl_ex_best_and_worst)}</small></td>`},
    luck: {key: "luck", label: "Luck check", get: a => a.luck.share_of_pnl_from_best_trade ?? -1, cell: a => `<td>${luckFlag(a)}</td>`},
    sharpe: {key: "sharpe", label: "Sharpe-like", cls: "n", get: a => a.risk.sharpe_like, title: "Mean / standard deviation of 15-minute equity returns, not annualised",
      cell: a => `<td class="n">${a.risk.sharpe_like == null ? "–" : a.risk.sharpe_like.toFixed(2)}</td>`},
    dd: {key: "dd", label: "Max drawdown", cls: "n", get: a => a.risk.max_drawdown_pct, asc: true,
      cell: a => `<td class="n ${a.risk.max_drawdown_pct >= 25 ? "an-neg" : ""}">${a.risk.max_drawdown_pct.toFixed(1)}%</td>`},
    pf: {key: "pf", label: "Profit factor", cls: "n", get: a => a.risk.profit_factor ?? (a.risk.wins ? Infinity : null), title: "Gross wins / gross losses",
      cell: a => { const pf = a.risk.profit_factor; return `<td class="n ${pf != null && pf < 1 ? "an-neg" : ""}">${pf != null ? pf.toFixed(2) : a.risk.wins ? "∞" : "–"}</td>`; }},
    wr: {key: "wr", label: "Win rate", cls: "n", get: a => a.risk.win_rate,
      cell: a => `<td class="n">${a.risk.win_rate == null ? "–" : Math.round(a.risk.win_rate) + "%"}${avgTxt(a)}</td>`},
    cost: {key: "cost", label: "P&L per usage $", cls: "n", get: a => a.cost ? a.cost.pnl_per_usage_dollar : null, title: "P&L dollars per dollar of Claude Code's API-price estimate (Claudes only)",
      cell: a => `<td class="n">${a.cost && a.cost.pnl_per_usage_dollar != null ? `${sgn(a.cost.pnl_per_usage_dollar, 2)} <small class="an-dim">per $1 (${usd(a.cost.cost_total, 2)} used)</small>`
        : a.team === "claude" ? `<span class="an-dim">${safe(a.cost?.note || "no usage yet")}</span>` : `<span class="an-dim">free</span>`}</td>`},
    vs: {key: "vs", label: "Confidence vs benchmarks", get: a => a.confidence ? Object.values(a.confidence).reduce((s, c) => s + (c?.probability ?? -1), 0) : -9,
      cell: a => `<td class="an-vs">${a.confidence ? Object.entries(a.confidence).map(([n, c]) => confChip(n, c)).join("") : `<span class="an-dim">${bench.has(a.name) ? "Benchmark" : "Bot"}</span>`}</td>`},
    fee: {key: "fee", label: "Fee drag", cls: "n", get: a => num(extraOf(a)?.fee_drag_pct), asc: true, cell: feeCell},
    top3: {key: "top3", label: "Top-3 share", cls: "n", get: a => num(extraOf(a)?.top3_share), asc: true, title: TOP3_TIP, cell: top3Cell},
  };
  function columns() {
    if (!analytics.agents.some(extraOf)) return [C.name, C.pnl, C.ex_best, C.luck, C.sharpe, C.dd, C.pf, C.wr, C.cost, C.vs];
    const names = alphaNames();
    const alpha = names.map((b, i) => {
      const edge = (i === 0 ? "an-gs" : "") + (i === names.length - 1 ? " an-ge" : "");
      return {key: "alpha:" + b, label: b, group: "Alpha vs", cls: "n " + edge, get: a => num(extraOf(a)?.alpha?.[b]),
              title: ALPHA_TIP.replace("this yardstick", b), cell: a => alphaCell(a, b, edge)};
    });
    return [C.name, C.pnl, ...alpha, {...C.fee, title: FEE_TIP()}, C.ex_best, C.luck, C.top3, C.sharpe, C.dd, C.pf, C.wr, C.cost, C.vs];
  }

  function luckFlag(a) {
    const L = a.luck, share = L.share_of_pnl_from_best_trade;
    const best = L.best_trade && L.best_open ? (L.best_open.pnl > L.best_trade.pnl ? L.best_open : L.best_trade) : (L.best_open || L.best_trade);
    if (!best) return `<span class="an-flag none">No winning trade yet</span>`;
    const what = `${safe(best.symbol)} ${sgn(best.pnl)}${best.kind === "open" ? ", still open" : ""}`;
    if (a.pnl <= 0) return `<span class="an-flag none" title="${what}">Behind even with its best trade</span>`;
    if (share == null) return `<span class="an-flag none">–</span>`;
    const p = Math.round(share * 100);
    if (share >= 1) return `<span class="an-flag hot" title="${what}">All of this lead is one trade (${what})</span>`;
    if (share >= 0.5) return `<span class="an-flag hot" title="${what}">${p}% of this lead is one trade (${safe(best.symbol)})</span>`;
    return `<span class="an-flag" title="${what}">${p}% of the lead from the best trade</span>`;
  }

  function confChip(name, c) {
    if (!c) return "";
    const p = c.probability;
    if (p == null) return `<span class="an-chip thin">vs ${safe(name)}: ${safe(c.note || "not enough data yet")}</span>`;
    const pc = Math.round(p * 100), good = p >= 0.9, bad = p <= 0.1;
    const meter = `<span class="an-meter ${good ? "good" : bad ? "bad" : ""}" aria-hidden="true"><i style="width:${pc}%"></i></span>`;
    return `<span class="an-chip ${c.enough ? (good ? "good" : bad ? "bad" : "") : "thin"}">${meter}<b>${pc}%</b> likely better than ${safe(name)}${c.enough ? "" : " · not enough data yet"}</span>`;
  }

  function renderTable() {
    const cols = columns();
    const rows = analytics.agents.filter(a => showBots || a.team === "claude");
    const col = cols.find(c => c.key === sortKey) || C.pnl;
    rows.sort((a, b) => {
      const x = col.get(a), y = col.get(b);
      const nx = x == null || Number.isNaN(x), ny = y == null || Number.isNaN(y);
      if (nx || ny) return nx === ny ? 0 : nx ? 1 : -1;   // missing values sink to the bottom whichever way it's sorted
      const r = col.text ? String(x).localeCompare(String(y)) : (x === y ? 0 : x > y ? 1 : -1);
      return sortDir === "asc" ? r : -r;
    });
    const grouped = cols.some(c => c.group);
    const th = (c, attrs = "") => `<th class="${c.cls || ""}"${attrs} ${c.key === col.key ? `aria-sort="${sortDir === "asc" ? "ascending" : "descending"}"` : ""}>
      <button type="button" data-sort="${safe(c.key)}" ${c.title ? `title="${safe(c.title)}"` : ""}>${safe(c.label)}</button></th>`;
    let top = "", sub = "";
    cols.forEach((c, i) => {
      if (!c.group) { top += th(c, grouped ? ` rowspan="2"` : ""); return; }
      sub += th(c);
      if (cols[i - 1]?.group !== c.group) {
        const n = cols.filter(x => x.group === c.group).length;
        top += `<th class="an-group an-gs an-ge" colspan="${n}" scope="colgroup"><span title="${safe(ALPHA_TIP.replace("this yardstick", "each yardstick bot"))}">${safe(c.group)}</span></th>`;
      }
    });
    setHTML(thead, `<tr>${top}</tr>${sub ? `<tr>${sub}</tr>` : ""}`);
    setHTML(body, rows.length ? rows.map(a => `<tr data-agent="${safe(a.name)}" class="${bench.has(a.name) ? "an-bench" : ""}" style="--c:${tint(a)}">
        ${cols.map(c => c.cell(a)).join("")}</tr>`).join("") : `<tr><td colspan="${cols.length}" class="an-empty">No agents to show.</td></tr>`);
  }

  function renderReadiness() {
    const claudes = analytics.agents.filter(a => a.team === "claude" && a.readiness);
    const open = new Set([...readyEl.querySelectorAll("details[open]")].map(d => d.dataset.agent));
    setHTML(readyEl, claudes.map(a => {
      const r = a.readiness;
      return `<details class="panel an-check" data-agent="${safe(a.name)}" style="--c:${tint(a)}" ${open.has(a.name) ? "open" : ""}>
        <summary>${sprite(a)}<b>${safe(a.name)}</b><small>${r.ready ? "ready for a small live test" : `${r.passed} of ${r.total} checks pass`}</small>
          <span class="an-score" aria-hidden="true">${r.passed}/${r.total}</span></summary>
        <div class="an-verdict ${r.ready ? "yes" : "no"}">${safe(r.verdict)}</div>
        <ul>${r.checks.map(c => `<li class="${c.pass ? "ok" : "ko"}"><i aria-hidden="true"></i><div>${safe(c.label)}<small>${c.pass ? "Pass" : "Not yet"}: ${safe(c.reason)}</small></div></li>`).join("")}</ul>
        <div class="an-chips">${Object.entries(a.confidence || {}).map(([n, c]) => confChip(n, c)).join("")}</div>
      </details>`;
    }).join(""));
  }

  function render() {
    if (!analytics) return;
    bench = new Set(analytics.benchmarks || []);
    table.hidden = false; statusEl.hidden = true;
    renderTable();
    renderReadiness();
    const hasExtra = analytics.agents.some(extraOf);
    table.classList.toggle("an-wide", hasExtra);
    legendEl.hidden = !hasExtra;
    if (hasExtra) setHTML(legendEl, `<b>Alpha</b> is how many percentage points better than each yardstick bot over the same time (negative means behind). `
      + `<b>Fee drag</b> is the fees paid as a share of the starting ${safe(usd(startCash(), 0))}. `
      + `<b>Top-3 share</b> is how much of the profit came from just the 3 best trades: near 100% means it's mostly luck so far.`);
    const m = analytics.min_sample || {}, th = analytics.thresholds || {}, marks = analytics.benchmarks || ["Random", "Hold SOL"];
    noteEl.textContent = `Confidence resamples ${analytics.bucket_minutes || 15}-minute equity returns ${(analytics.bootstraps || 2000).toLocaleString()} times; it needs at least ${m.closed_trades ?? 20} closed trades and ${m.hours ?? 2} hours before it counts. Readiness wants ${th.days ?? 7} days, ${th.closed_trades ?? 100} closed trades, a lead over ${listJoin(marks)} after the luck check, ${Math.round((th.confidence ?? 0.9) * 100)}% confidence against ${marks.length === 2 ? "both" : "each"}, drawdown under ${th.max_drawdown_pct ?? 25}%, profit factor above ${th.profit_factor ?? 1.2}, and no stretch where over ${Math.round((th.max_fail_rate ?? 0.3) * 100)}% of calls failed. Usage figures are Claude Code's API-price estimates. Updated every 30 seconds.`;
  }

  thead.addEventListener("click", e => {
    const b = e.target.closest("button[data-sort]");
    if (!b || !analytics) return;
    const key = b.dataset.sort;
    if (sortKey === key) sortDir = sortDir === "asc" ? "desc" : "asc";
    else { sortKey = key; sortDir = columns().find(c => c.key === key)?.asc ? "asc" : "desc"; }
    prefs.set("an-sort", sortKey); prefs.set("an-sort-dir", sortDir);
    render();
  });

  /* ---------- polling ---------- */
  let failures = 0;
  async function poll() {
    try {
      const r = await fetch("/api/analytics", {cache: "no-store"});
      if (r.status === 404) {
        failures++;
        statusEl.hidden = false; table.hidden = !analytics;
        statusEl.textContent = "Analytics aren't available yet. Restart the arena (python main.py) so it picks up analytics.py.";
        return;
      }
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      if (!d || !Array.isArray(d.agents)) throw new Error("bad payload");
      analytics = d; failures = 0;
      window.arenaAnalytics = d;
      share(d);
      render();
    } catch (e) {
      failures++;
      if (!analytics) { statusEl.hidden = false; statusEl.textContent = failures > 2 ? "Can't load analytics right now. Trying again every 30 seconds." : "Loading analytics…"; }
    }
  }
  poll();
  setInterval(poll, POLL_MS);
})();
