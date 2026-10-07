/* tokenchart.js — per-token price chart modal. Opens from the token popover's "Price chart" button
   (filters.js), ticker items, and the symbol on a decision's order lines. Reads the arena's own
   price history from /api/token/<address>/history and marks every agent's buys and sells in their
   colours, with current market stats from /api/market and links out to DexScreener and Solscan.
   Other plugins can open it with: document.dispatchEvent(new CustomEvent("arena:token-chart",
   {detail: {address, symbol}})) or window.arenaTokenChart.open({address, symbol}). */
(() => {
  "use strict";
  if (window.arenaTokenChart) return;

  const E = typeof esc === "function" ? esc : s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const usd = (n, d = 2) => (typeof money === "function" ? money(n, d) : "$" + Number(n).toFixed(d));
  const sgn = n => (typeof signed === "function" ? signed(n) : (n >= 0 ? "+" : "") + Number(n).toFixed(2));
  const clockNow = () => (typeof now === "function" ? now() : Date.now() / 1000);
  const agoText = s => (typeof ago === "function" ? ago(s) : Math.round(s) + "s ago");
  const spanText = s => (typeof span === "function" ? span(s) : Math.round(s) + "s");
  const colour = name => { try { return colorOf(agentByName(name)); } catch { return "#c8d0e8"; } };
  const sprite = name => { try { return spriteSVG(agentByName(name).avatar).replace('class="bob"', ""); } catch { return ""; } };

  /* ---------- styles ---------- */
  const style = document.createElement("style");
  style.textContent = `
  .orders li[data-symbol] .sym { cursor: pointer; }
  .orders li[data-symbol] .sym:hover { text-decoration: underline dotted var(--haze); }
  .tc-root { position: fixed; inset: 0; z-index: 920; display: none; }
  .tc-root.open { display: block; }
  .tc-back { position: absolute; inset: 0; background: rgba(10, 8, 24, .8); }
  .tc-dlg { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); width: min(860px, calc(100vw - 32px));
    max-height: calc(100vh - 32px); overflow: auto; overscroll-behavior: contain; background: var(--dusk); color: var(--moon);
    border: 2px solid var(--gold); font: 14px/1.45 var(--body); outline: none;
    clip-path: polygon(0 8px, 4px 8px, 4px 4px, 8px 4px, 8px 0, calc(100% - 8px) 0, calc(100% - 8px) 4px, calc(100% - 4px) 4px, calc(100% - 4px) 8px, 100% 8px,
      100% calc(100% - 8px), calc(100% - 4px) calc(100% - 8px), calc(100% - 4px) calc(100% - 4px), calc(100% - 8px) calc(100% - 4px), calc(100% - 8px) 100%,
      8px 100%, 8px calc(100% - 4px), 4px calc(100% - 4px), 4px calc(100% - 8px), 0 calc(100% - 8px)); }
  .tc-root.open .tc-dlg { animation: tc-in .22s steps(4) both; }
  @keyframes tc-in { from { opacity: 0; transform: translate(-50%, -50%) scale(.9); } to { opacity: 1; transform: translate(-50%, -50%) scale(1); } }
  .tc-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px; padding: 18px 76px 10px 20px; border-bottom: 1px solid var(--seam); }
  .tc-sym { font: 400 40px/1 var(--pixel); color: var(--gold); text-shadow: 2px 2px 0 var(--ink); margin: 0; display: inline-flex; align-items: center; gap: 10px; }
  .tc-sym i { width: 10px; height: 10px; flex: none; }
  .tc-sym i.green { background: var(--profit); } .tc-sym i.yellow { background: var(--gold); } .tc-sym i.red { background: var(--loss); } .tc-sym i.none { background: var(--seam); }
  .tc-name { color: var(--haze); font-size: 13px; }
  .tc-price { font: 400 30px/1 var(--pixel); font-variant-numeric: tabular-nums; margin-left: auto; }
  .tc-price small { font: 400 13px/1 var(--body); margin-left: 8px; }
  .tc-up { color: var(--profit); } .tc-down { color: var(--loss); } .tc-flat { color: var(--haze); }
  .tc-chart { position: relative; height: 300px; margin: 12px 20px 0; background: var(--night); border: 1px solid var(--seam); padding: 8px; }
  .tc-chart canvas { display: block; }
  .tc-note { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; text-align: center; color: var(--haze); padding: 20px; font-size: 13px; }
  .tc-legend { display: flex; flex-wrap: wrap; gap: 6px 14px; padding: 8px 20px 0; font-size: 12px; color: var(--haze); }
  .tc-legend span { display: inline-flex; align-items: center; gap: 5px; }
  .tc-legend svg { width: 16px; height: 14px; }
  .tc-legend .tc-tri { width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; }
  .tc-legend .tc-tri.up { border-bottom: 9px solid var(--moon); } .tc-legend .tc-tri.down { border-top: 9px solid var(--moon); }
  .tc-stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px; padding: 12px 20px 0; }
  .tc-stat { background: var(--night); border: 1px solid var(--seam); padding: 8px 10px; min-width: 0; }
  .tc-stat small { display: block; color: var(--haze); font-size: 11px; }
  .tc-stat span { font: 400 24px/1.05 var(--pixel); font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
  .tc-flags { padding: 10px 20px 0; display: flex; flex-wrap: wrap; gap: 6px; }
  .tc-flag { font: 500 11px/1 var(--body); padding: 4px 7px; border: 1px solid var(--loss); color: var(--loss); background: var(--night); }
  .tc-sec { padding: 14px 20px 0; }
  .tc-sec h4 { margin: 0 0 6px; font: 400 22px/1 var(--pixel); color: var(--haze); }
  .tc-tbl { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
  .tc-tbl th { text-align: left; color: var(--haze); font-weight: 500; font-size: 11px; padding: 2px 6px; border-bottom: 1px solid var(--seam); }
  .tc-tbl td { padding: 4px 6px; border-bottom: 1px solid rgba(52, 44, 99, .5); white-space: nowrap; }
  .tc-tbl td.r, .tc-tbl th.r { text-align: right; }
  .tc-tbl td.why { white-space: normal; color: var(--haze); font-size: 12px; max-width: 280px; }
  .tc-tbl .tc-who { display: inline-flex; align-items: center; gap: 6px; font: 400 17px/1 var(--pixel); }
  .tc-tbl .tc-who svg { width: 18px; height: 16px; }
  .tc-buy { color: var(--profit); } .tc-sell { color: var(--gold); }
  .tc-empty { color: var(--haze); font-size: 13px; padding: 4px 0; }
  .tc-foot { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; padding: 14px 20px 18px; color: var(--haze); font-size: 12px; }
  .tc-links { display: flex; flex-wrap: wrap; gap: 6px; }
  .tc-links a, .tc-btn { font: 500 13px/1 var(--body); color: var(--moon); background: var(--night); border: 1px solid var(--seam); padding: 8px 12px; cursor: pointer; text-decoration: none; }
  .tc-links a:hover, .tc-btn:hover, .tc-links a:focus-visible, .tc-btn:focus-visible { border-color: var(--gold); color: var(--gold); outline: none; }
  .tc-close { position: absolute; top: 12px; right: 14px; }
  .tc-addr code { font-family: ui-monospace, Consolas, monospace; font-size: 12px; color: var(--haze); }
  .tc-err { color: var(--loss); padding: 14px 20px 0; }
  @media (max-width: 640px) {
    .tc-dlg { left: 0; top: 0; transform: none; width: 100vw; max-width: 100vw; height: 100vh; max-height: 100vh; clip-path: none; border-width: 0; }
    @keyframes tc-in { from { opacity: 0; transform: scale(.94); } to { opacity: 1; transform: none; } }
    .tc-head { padding: 14px 52px 8px 16px; }
    .tc-sym { font-size: 32px; } .tc-price { font-size: 24px; margin-left: 0; flex-basis: 100%; }
    .tc-chart { height: 220px; margin: 10px 16px 0; }
    .tc-legend, .tc-stats, .tc-flags, .tc-sec, .tc-foot, .tc-err { padding-left: 16px; padding-right: 16px; }
    .tc-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .tc-sec { overflow-x: auto; }
    .tc-close { top: 10px; right: 10px; }
  }
  @media (prefers-reduced-motion: reduce) { .tc-root.open .tc-dlg { animation: none; } }
  `;
  document.head.appendChild(style);

  /* ---------- DOM ---------- */
  const root = document.createElement("div");
  root.className = "tc-root";
  root.innerHTML = `<div class="tc-back"></div>
    <div class="tc-dlg" role="dialog" aria-modal="true" aria-labelledby="tc-title" tabindex="-1">
      <button class="tc-btn tc-close" type="button" aria-label="Close">Esc</button>
      <div class="tc-body"></div>
    </div>`;
  document.body.appendChild(root);
  const dlg = root.querySelector(".tc-dlg"), body = root.querySelector(".tc-body");

  let current = null, trigger = null, chart = null, timer = 0, market = null, marketAt = 0, hist = null, reqId = 0;

  /* ---------- formatting ---------- */
  // 0.0000123 → $0.0₄123 as plain text (subscript digits), 0.0456 → $0.0456, 1234 → $1,234
  const SUB = "₀₁₂₃₄₅₆₇₈₉";
  function price(p) {
    if (!(p > 0)) return "$0";
    if (p >= 1000) return "$" + Math.round(p).toLocaleString();
    if (p >= 1) return "$" + p.toFixed(p >= 100 ? 1 : 2);
    if (p >= 0.01) return "$" + p.toFixed(4);
    const m = p.toFixed(20).match(/^0\.(0*)(\d+)/);
    if (!m) return "$" + p.toPrecision(3);
    const zeros = m[1].length, digits = m[2].slice(0, 3);
    if (zeros < 3) return "$0." + m[1] + digits;
    return "$0.0" + [...String(zeros)].map(c => SUB[+c]).join("") + digits;
  }
  const big = n => n == null ? "–" : n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}k` : usd(n, 0);
  const chg = n => n == null || isNaN(n) ? `<span class="tc-flat">–</span>` : `<span class="${n > .005 ? "tc-up" : n < -.005 ? "tc-down" : "tc-flat"}">${n > 0 ? "+" : ""}${n.toFixed(1)}%</span>`;

  /* ---------- data ---------- */
  async function loadMarket(force) {
    if (!force && market && Date.now() - marketAt < 10000) return market;
    try { const r = await fetch("/api/market", {cache: "no-store"}); if (r.ok) { market = await r.json(); marketAt = Date.now(); } } catch {}
    return market;
  }
  async function loadHistory(addr) {
    const r = await fetch(`/api/token/${encodeURIComponent(addr)}/history`, {cache: "no-store"});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }
  // address for a symbol: trades in the summary, open positions, then the market list
  function resolve(symbol) {
    const d = typeof data !== "undefined" ? data : null;
    if (d) {
      const t = (d.trades || []).find(x => x.symbol === symbol);
      if (t) return t.token;
      for (const a of d.agents || []) for (const p of a.positions || []) if (p.symbol === symbol) return p.token;
    }
    const m = (market || []).find(x => x.symbol === symbol);
    return m ? m.address : null;
  }

  /* ---------- rendering ---------- */
  function render() {
    if (!current) return;
    const t = (market || []).find(x => x.address === current.address) || {};
    const sym = hist?.symbol || t.symbol || current.symbol || "Token";
    const pts = hist?.points || [], trades = hist?.trades || [];
    const last = pts.length ? pts[pts.length - 1][1] : t.price;
    const first = pts.length ? pts[0][1] : null;
    const sinceStart = first && last ? (last / first - 1) * 100 : null;
    const rating = ["green", "yellow", "red"].includes(t.rating) ? t.rating : "none";
    const agents = [...new Set(trades.map(x => x.agent))];
    const tnow = clockNow();
    const stat = (k, v) => `<div class="tc-stat"><small>${k}</small><span>${v}</span></div>`;
    body.innerHTML = `
      <div class="tc-head">
        <h3 class="tc-sym" id="tc-title"><i class="${rating}" title="${rating === "none" ? "No risk rating" : rating + " risk rating"}"></i>${E(sym)}</h3>
        <span class="tc-name">${E(t.name || "")}${t.age_min != null ? ` · ${spanText(t.age_min * 60)} old` : ""}</span>
        <span class="tc-price">${last != null ? price(last) : "–"}${sinceStart != null ? `<small>${chg(sinceStart)} since first seen</small>` : ""}</span>
      </div>
      <div class="tc-chart"><canvas aria-label="Price history for ${E(sym)} with every agent's buys and sells marked"></canvas>
        ${pts.length < 2 ? `<div class="tc-note">${hist ? "No price history yet. The arena records a point every tick, so give it a minute." : "Loading price history…"}</div>` : ""}</div>
      <div class="tc-legend"><span><i class="tc-tri up"></i> buy</span><span><i class="tc-tri down"></i> sell</span>
        ${agents.map(n => `<span style="color:${colour(n)}">${sprite(n)}${E(n)}</span>`).join("")}</div>
      <div class="tc-stats">
        ${stat("Liquidity", big(t.liquidity))}${stat("Volume 1 h", big(t.vol_h1))}${stat("Market cap", big(t.mcap))}
        ${stat("Buys / sells 1 h", t.buys_h1 == null ? "–" : `${t.buys_h1} / ${t.sells_h1}`)}
        ${stat("5 min", chg(t.chg_m5))}${stat("1 hour", chg(t.chg_h1))}${stat("24 hours", chg(t.chg_h24))}
        ${stat("Held by", t.held_by && t.held_by.length ? t.held_by.length + (t.held_by.length === 1 ? " agent" : " agents") : "nobody")}
      </div>
      ${t.flags && t.flags.length ? `<div class="tc-flags">${t.flags.map(f => `<span class="tc-flag">${E(f)}</span>`).join("")}</div>` : ""}
      <div class="tc-sec"><h4>Arena trades in ${E(sym)}</h4>${trades.length ? `<table class="tc-tbl"><thead><tr><th>When</th><th>Agent</th><th>Side</th><th class="r">Size</th><th class="r">Fill</th><th class="r">P&amp;L</th><th>Reason</th></tr></thead><tbody>
        ${trades.slice(0, 40).map(x => `<tr><td>${E(agoText(tnow - x.ts))}</td><td><span class="tc-who" style="color:${colour(x.agent)}">${sprite(x.agent)}${E(x.agent)}</span></td>
          <td class="tc-${x.side}">${x.side}</td><td class="r">${usd(x.usd)}</td><td class="r">${price(x.fill)}</td>
          <td class="r ${x.pnl == null ? "" : x.pnl >= 0 ? "tc-up" : "tc-down"}">${x.pnl == null ? "–" : sgn(x.pnl)}</td><td class="why">${E(x.reason || "")}</td></tr>`).join("")}
        </tbody></table>` : `<div class="tc-empty">No agent has traded this token yet.</div>`}</div>
      <div class="tc-foot">
        <span class="tc-addr"><code title="${E(current.address)}">${E(current.address.length > 16 ? current.address.slice(0, 6) + "…" + current.address.slice(-6) : current.address)}</code>
          <button type="button" class="tc-btn tc-copy">Copy address</button></span>
        <div class="tc-links">
          <a href="https://dexscreener.com/solana/${encodeURIComponent(current.address)}" target="_blank" rel="noopener noreferrer">DexScreener</a>
          <a href="https://solscan.io/token/${encodeURIComponent(current.address)}" target="_blank" rel="noopener noreferrer">Solscan</a>
        </div>
      </div>`;
    body.querySelector(".tc-copy").addEventListener("click", ev => {
      const b = ev.currentTarget, done = ok => { b.textContent = ok ? "Copied" : "Copy failed"; setTimeout(() => { b.textContent = "Copy address"; }, 1200); };
      if (navigator.clipboard?.writeText) navigator.clipboard.writeText(current.address).then(() => done(true), () => done(false)); else done(false);
    });
    drawChart(pts, trades, sym);
  }

  function drawChart(pts, trades, sym) {
    const canvas = body.querySelector(".tc-chart canvas");
    if (chart) { chart.destroy(); chart = null; }
    if (!canvas || typeof Chart === "undefined" || pts.length < 2) return;
    const line = pts.map(([x, y]) => ({x, y}));
    const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
    // marker y: the recorded fill price when we have it, else the nearest history point
    const yAt = ms => { let best = pts[0]; for (const p of pts) if (Math.abs(p[0] - ms) < Math.abs(best[0] - ms)) best = p; return best[1]; };
    const marks = trades.filter(x => x.ts * 1000 >= t0 - 60000 && x.ts * 1000 <= t1 + 60000)
      .map(x => ({x: Math.max(t0, Math.min(t1, x.ts * 1000)), y: x.fill > 0 ? x.fill : yAt(x.ts * 1000), trade: x}));
    const up = line[line.length - 1].y >= line[0].y;
    chart = new Chart(canvas, {
      type: "line",
      data: {datasets: [
        {label: sym, data: line, borderColor: up ? "#59e3a7" : "#ff6b7a", backgroundColor: up ? "rgba(89,227,167,.12)" : "rgba(255,107,122,.12)", fill: true,
         borderWidth: 2, pointRadius: 0, tension: 0, stepped: false, order: 1},
        {label: "Trades", type: "scatter", data: marks, order: 0, marker: true, pointStyle: "triangle", pointRadius: 6, pointHoverRadius: 8, pointBorderWidth: 1.5,
         pointRotation: marks.map(m => m.trade.side === "buy" ? 0 : 180),
         pointBackgroundColor: marks.map(m => colour(m.trade.agent)), pointBorderColor: "#1b1640"},
      ]},
      options: {
        animation: false, maintainAspectRatio: false, interaction: {mode: "nearest", intersect: false},
        scales: {
          x: {type: "linear", min: t0, max: t1, ticks: {maxTicksLimit: 6, color: "#a39dcb", callback(v) {
                const range = this.max - this.min, d = new Date(v);
                if (range > 2 * 86400e3) return d.toLocaleDateString([], {month: "short", day: "numeric"});
                return d.toLocaleTimeString([], range < 20 * 60e3 ? {hour: "numeric", minute: "2-digit", second: "2-digit"} : {hour: "numeric", minute: "2-digit"});
              }}, grid: {color: "#2a2352"}},
          y: {ticks: {color: "#a39dcb", maxTicksLimit: 6, callback: v => price(v)}, grid: {color: "#2a2352"}},
        },
        plugins: {
          legend: {display: false},
          tooltip: {
            backgroundColor: "#1b1640", borderColor: "#342c63", borderWidth: 1, titleColor: "#eeeafb", bodyColor: "#eeeafb", padding: 10,
            callbacks: {
              title: i => new Date(i[0].parsed.x).toLocaleTimeString(),
              label: i => {
                if (!i.dataset.marker) return `${sym} ${price(i.parsed.y)}`;
                const x = i.raw.trade, verb = x.side === "buy" ? `bought for ${usd(x.usd)}` : `sold for ${usd(x.usd)}${x.pnl == null ? "" : `, ${sgn(x.pnl)}`}`;
                const out = [`${x.agent} ${verb} at ${price(x.fill)}`];
                if (x.reason) out.push(x.reason.length > 90 ? x.reason.slice(0, 88) + "…" : x.reason);
                return out;
              },
            },
          },
        },
      },
    });
  }

  /* ---------- open / close ---------- */
  async function load() {
    if (!current) return;
    const id = ++reqId, addr = current.address;
    await loadMarket(false);
    if (id !== reqId) return;
    try { hist = await loadHistory(addr); }
    catch (e) { if (id === reqId) { body.insertAdjacentHTML("beforeend", `<div class="tc-err">Couldn't load price history (${E(e.message)}).</div>`); } return; }
    if (id === reqId && current && current.address === addr) render();
  }
  function open(tok, from) {
    if (!tok || !tok.address) return;
    if (!current) trigger = from || document.activeElement;
    current = {address: String(tok.address), symbol: tok.symbol || ""};
    hist = null;
    root.classList.add("open");
    document.body.style.overflow = "hidden";
    render();
    load();
    clearInterval(timer);
    timer = setInterval(() => { if (!document.hidden) load(); }, 10000);
    dlg.scrollTop = 0;
    dlg.focus({preventScroll: true});
  }
  function close() {
    if (!current) return;
    current = null; hist = null;
    clearInterval(timer); timer = 0;
    if (chart) { chart.destroy(); chart = null; }
    root.classList.remove("open");
    document.body.style.overflow = "";
    const t = trigger; trigger = null;
    if (t && document.contains(t) && typeof t.focus === "function") t.focus({preventScroll: true});
  }
  async function openSymbol(symbol, from) {
    let addr = resolve(symbol);
    if (!addr) { await loadMarket(true); addr = resolve(symbol); }
    if (addr) open({address: addr, symbol}, from);
  }

  /* ---------- events ---------- */
  document.addEventListener("arena:token-chart", e => { const d = e.detail || {}; if (d.address) open(d, d.trigger); else if (d.symbol) openSymbol(d.symbol, d.trigger); });
  document.addEventListener("click", e => {
    if (root.contains(e.target)) {
      if (e.target.closest(".tc-back") || e.target.closest(".tc-close")) close();
      return;
    }
    const sym = e.target.closest("#decisions .orders li[data-symbol] .sym, .fl-frozen .orders li[data-symbol] .sym");
    if (sym) {
      const s = sym.closest("li").dataset.symbol;
      if (s) { e.preventDefault(); e.stopPropagation(); openSymbol(s, sym); }
    }
  }, true);
  document.addEventListener("keydown", e => {
    if (!current) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); return; }
    if (e.key === "Tab") {  // keep focus inside the dialog
      const f = [...dlg.querySelectorAll("button, [href], [tabindex]:not([tabindex='-1'])")].filter(x => !x.disabled);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === dlg)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }, true);
  window.addEventListener("resize", () => { if (current && chart) chart.resize(); });

  window.arenaTokenChart = {open, openSymbol, close};
})();
