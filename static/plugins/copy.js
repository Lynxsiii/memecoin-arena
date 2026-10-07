/* copy.js — Team Copy's "Top traders" board: the top-100 wallet leaderboard the copy bots follow, a live feed of
   the buys and sells they copy, and a status line. Polls /api/traders every 15s and degrades to a one-line note
   while the arena doesn't serve it yet. Renders into #slot-copy; classes are prefixed cp-. */
(() => {
  "use strict";
  const slot = document.getElementById("slot-copy");
  if (!slot || window.__cpTraders) return;
  window.__cpTraders = true;
  const POLL_MS = 15000, TOP_VISIBLE = 25, SIGNALS_MAX = 60;

  /* ---------- safe access to dashboard globals ---------- */
  const E = typeof esc === "function" ? esc : s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const usd = (n, d = 0) => (typeof money === "function" ? money(Number(n) || 0, d) : "$" + (Number(n) || 0).toFixed(d));
  const sgn = (n, d = 0) => (typeof signed === "function" ? signed(Number(n) || 0, d) : ((n >= 0 ? "+" : "-") + usd(Math.abs(n), d)));
  const pctText = n => (typeof pct === "function" ? pct(Number(n) || 0) : (n >= 0 ? "+" : "") + (Number(n) || 0).toFixed(1) + "%");
  const clockNow = () => (typeof now === "function" ? now() : Date.now() / 1000);
  const agoText = s => (typeof ago === "function" ? ago(s) : Math.round(s) + "s ago");
  const sprite = key => (typeof spriteSVG === "function" ? spriteSVG(key).replace('class="bob"', "") : "");
  const arena = () => (typeof data === "object" && data) || null;
  const palette = () => (typeof AVATAR_COLOR === "object" && AVATAR_COLOR) || {};
  const FALLBACK = {"Copy 1-33": ["copy-a", "#ff5fd2"], "Copy 34-66": ["copy-b", "#3d8bff"], "Copy 67-100": ["copy-c", "#ffa132"]};
  let reduced = false;
  try { reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch {}

  /* ---------- styles ---------- */
  const style = document.createElement("style");
  style.textContent = `
  .cp-wrap { margin-top: 36px; min-width: 0; }
  .cp-status { display: flex; flex-wrap: wrap; gap: 4px 18px; margin: -4px 0 12px; font-size: 13px; color: var(--haze); font-variant-numeric: tabular-nums; }
  .cp-status b { color: var(--moon); font-weight: 500; }
  .cp-status .cp-dot { display: inline-block; width: 8px; height: 8px; margin-right: 6px; background: var(--profit); box-shadow: 0 0 0 1px var(--night); vertical-align: 0; }
  .cp-status .cp-dot.off { background: var(--loss); } .cp-status .cp-dot.warn { background: var(--gold); }
  .cp-note { color: var(--haze); font-size: 14px; padding: 14px 16px; }
  .cp-grid { display: grid; gap: 20px; grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr); align-items: start; }
  .cp-bhead, .cp-fhead { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; padding: 10px 14px; border-bottom: 1px solid var(--seam); }
  .cp-bhead h3, .cp-fhead h3 { margin: 0; font: 400 22px/1 var(--pixel); color: var(--moon); letter-spacing: .02em; }
  .cp-fhead small, .cp-bhead small { color: var(--haze); font-size: 12px; }
  .cp-bhead .cp-legend { display: flex; flex-wrap: wrap; gap: 4px; margin-left: auto; }
  .cp-pill { display: inline-flex; align-items: center; gap: 4px; padding: 2px 5px 0; font: 400 13px/1.1 var(--pixel); letter-spacing: .02em; white-space: nowrap;
             color: var(--ink); background: var(--c, var(--haze)); box-shadow: 1px 1px 0 var(--ink); vertical-align: 1px; }
  .cp-pill svg { width: 12px; height: 11px; display: block; }
  .cp-pill.none { background: transparent; color: var(--haze); box-shadow: inset 0 0 0 1px var(--seam); }
  .cp-scroll { max-height: 520px; overflow: auto; scrollbar-color: var(--seam) transparent; }
  .cp-table th, .cp-table td { padding: 6px 7px; font-size: 12px; }
  .cp-table th:first-child, .cp-table td:first-child { padding-left: 12px; }
  .cp-table th:last-child, .cp-table td:last-child { padding-right: 12px; }
  .cp-table td.cp-rank { font: 400 20px/1 var(--pixel); color: var(--haze); width: 1%; }
  .cp-table tr:nth-child(-n+3) td.cp-rank { color: var(--gold); }
  .cp-table .cp-wallet { display: inline-flex; align-items: center; gap: 6px; }
  .cp-table code { font: 12px/1 ui-monospace, Consolas, monospace; color: var(--moon); background: var(--night); padding: 3px 5px; }
  .cp-ib { font: 500 11px/1 var(--body); color: var(--haze); background: var(--dusk); border: 1px solid var(--seam); padding: 3px 5px; cursor: pointer; }
  .cp-ib:hover { border-color: var(--haze); color: var(--moon); }
  .cp-ib.done { color: var(--profit); border-color: var(--profit); }
  .cp-table a.cp-ib { text-decoration: none; }
  .cp-table td.n small { display: block; color: var(--haze); font-size: 11px; }
  .cp-more { display: block; width: 100%; padding: 9px; font: 500 13px var(--body); color: var(--gold); background: transparent; border: 0; border-top: 1px solid var(--seam); cursor: pointer; }
  .cp-more:hover { background: #26204c; }
  .cp-sig { display: grid; grid-template-columns: 62px minmax(0, 1fr) auto; gap: 2px 10px; padding: 9px 14px; border-bottom: 1px solid var(--seam); font-size: 13px; }
  .cp-sig:last-child { border-bottom: 0; }
  .cp-sig .cp-t { color: var(--haze); font-size: 12px; font-variant-numeric: tabular-nums; padding-top: 2px; white-space: nowrap; }
  .cp-sig .cp-what { min-width: 0; overflow-wrap: anywhere; }
  .cp-sig .cp-what b.cp-r { font: 400 18px/1 var(--pixel); color: var(--haze); margin-right: 2px; }
  .cp-sig .cp-what code { font: 12px/1 ui-monospace, Consolas, monospace; color: var(--haze); }
  .cp-sig .cp-what .cp-sym { font-weight: 600; }
  .cp-sig .cp-usd { font-variant-numeric: tabular-nums; }
  .cp-sig .cp-foll { grid-column: 2; display: flex; flex-wrap: wrap; gap: 4px 8px; align-items: center; font-size: 12px; color: var(--haze); }
  .cp-src { font-size: 11px; line-height: 1.2; color: var(--haze); border: 1px solid var(--seam); padding: 2px 5px; white-space: nowrap; align-self: start; }
  .cp-src.helius { color: var(--profit); border-color: color-mix(in srgb, var(--profit) 45%, var(--seam)); }
  .cp-src.gecko { color: var(--gold); border-color: color-mix(in srgb, var(--gold) 45%, var(--seam)); }
  .cp-sig.cp-fresh { animation: cp-fresh 2.5s ease-out; }
  @keyframes cp-fresh { from { background: rgba(255, 95, 210, .14); } to { background: transparent; } }
  @media (max-width: 900px) { .cp-grid { grid-template-columns: minmax(0, 1fr); } .cp-scroll { max-height: 440px; } }
  @media (max-width: 640px) {
    .cp-table th.cp-hide-sm, .cp-table td.cp-hide-sm { display: none; }
    .cp-sig { grid-template-columns: 54px minmax(0, 1fr); }
    .cp-sig .cp-src { grid-column: 2; justify-self: start; }
    .cp-bhead .cp-legend { margin-left: 0; }
  }
  @media (prefers-reduced-motion: reduce) { .cp-sig.cp-fresh { animation: none; } }`;
  document.head.appendChild(style);

  /* ---------- skeleton ---------- */
  slot.innerHTML = `<section class="cp-wrap block" aria-labelledby="cp-title">
    <h2 id="cp-title">Top traders</h2>
    <p class="sub">The 100 most profitable human wallets trading the tokens this arena watches, by profit over the last 48 hours (bots filtered out, re-ranked hourly). Team Copy's three bots each mirror a slice of this list trade for trade; Sonnet Copycat reads the same signals and picks which buys are worth copying.</p>
    <div class="cp-status" id="cp-status"></div>
    <div class="cp-grid" id="cp-grid" hidden>
      <div class="panel cp-board">
        <div class="cp-bhead"><h3>Leaderboard</h3><small id="cp-bcount"></small><div class="cp-legend" id="cp-legend"></div></div>
        <div class="tablewrap cp-scroll"><table class="cp-table">
          <thead><tr><th>#</th><th>Wallet</th><th class="n">P&amp;L</th><th class="n">ROI</th><th class="n cp-hide-sm">Win rate</th><th class="n cp-hide-sm">Tokens</th><th class="n">Last trade</th><th>Followed by</th></tr></thead>
          <tbody id="cp-rows"></tbody></table></div>
        <button type="button" class="cp-more" id="cp-more" hidden></button>
      </div>
      <div class="panel cp-feed">
        <div class="cp-fhead"><h3>Copy signals</h3><small id="cp-fcount"></small></div>
        <div class="cp-scroll" id="cp-signals"></div>
      </div>
    </div>
    <div class="panel cp-note" id="cp-note" hidden></div>
  </section>`;
  const statusEl = document.getElementById("cp-status"), gridEl = document.getElementById("cp-grid"), noteEl = document.getElementById("cp-note");
  const rowsEl = document.getElementById("cp-rows"), moreBtn = document.getElementById("cp-more"), legendEl = document.getElementById("cp-legend");
  const sigEl = document.getElementById("cp-signals"), bcount = document.getElementById("cp-bcount"), fcount = document.getElementById("cp-fcount");
  const setHTML = (el, html) => { if (el._cpHtml !== html) { el.innerHTML = html; el._cpHtml = html; } };

  /* ---------- state ---------- */
  let traders = null, state = "loading", showAll = false, fetchedAt = 0;
  const seenSignals = new Set();
  let firstSignals = true;

  /* ---------- who follows whom ---------- */
  const shortAddr = w => (w = String(w || ""), w.length > 12 ? w.slice(0, 4) + "…" + w.slice(-4) : w);
  function copiers() {   // Team Copy's bots from the roster (name, avatar, colour), else the fallback trio
    const d = arena(), out = {};
    for (const a of (d && d.agents) || []) {
      const team = a.team || (a.kind === "llm" ? "claude" : "bots");
      if (team === "copy" && a.kind !== "llm") out[a.name] = {avatar: a.avatar, color: palette()[a.avatar] || "#c8d0e8"};
    }
    for (const [name, [avatar, color]] of Object.entries(FALLBACK)) if (!out[name]) out[name] = {avatar, color};
    return out;
  }
  function followerIndex() {   // wallet → copier name, plus rank slices parsed from names like "Copy 34-66"
    const byWallet = new Map(), slices = [];
    const following = (traders && traders.following) || {};
    for (const [name, ws] of Object.entries(following)) for (const w of ws || []) byWallet.set(w, name);
    for (const name of new Set([...Object.keys(following), ...Object.keys(copiers())])) {
      const m = /(\d+)\s*-\s*(\d+)/.exec(name);
      if (m) slices.push([+m[1], +m[2], name]);
    }
    return {byWallet, slices};
  }
  function followerOf(wallet, rank, idx) {
    if (idx.byWallet.has(wallet)) return idx.byWallet.get(wallet);
    const s = idx.slices.find(([lo, hi]) => rank >= lo && rank <= hi);
    return s ? s[2] : null;
  }
  function pill(name, cps) {
    if (!name) return `<span class="cp-pill none">nobody</span>`;
    const c = cps[name] || {avatar: "copy-a", color: "#c8d0e8"};
    return `<span class="cp-pill" style="--c:${c.color}" title="${E(name)} copies this wallet">${sprite(c.avatar)}${E(name)}</span>`;
  }

  /* ---------- rendering ---------- */
  function renderStatus() {
    const t = clockNow();
    if (state === "missing") {
      setHTML(statusEl, `<span><i class="cp-dot warn"></i>Top-trader feed not available yet</span>`);
      return;
    }
    if (!traders) {
      setHTML(statusEl, `<span><i class="cp-dot ${state === "unreachable" ? "off" : "warn"}"></i>${state === "unreachable" ? "Can't reach /api/traders" : "Loading the leaderboard…"}</span>`);
      return;
    }
    const st = traders.status || {}, following = traders.following || {};
    const followed = Object.values(following).reduce((s, ws) => s + ((ws && ws.length) || 0), 0);
    const watched = st.wallets_watched ?? st.watched ?? (followed || (traders.top || []).length);
    const sources = Object.entries(st).filter(([k, v]) => /helius|gecko/i.test(k) && (typeof v === "string" || typeof v === "boolean"))
      .map(([k, v]) => `<span>${E(k[0].toUpperCase() + k.slice(1).replace(/_/g, " "))} <b>${E(v === true ? "ok" : v === false ? "off" : v)}</b></span>`).join("");
    const stale = state === "unreachable" || state === "stale";
    setHTML(statusEl, `<span><i class="cp-dot ${stale ? "off" : traders.updated && t - traders.updated > 1800 ? "warn" : ""}"></i>Ranking updated <b data-cp-ts="${+traders.updated || 0}">${traders.updated ? E(agoText(t - traders.updated)) : "—"}</b></span>
      <span>Wallets watched <b>${Number(watched).toLocaleString()}</b></span>
      <span>Signals <b>${((traders.signals || []).length).toLocaleString()}</b></span>${sources}
      ${stale ? `<span>Showing the last board; <b>can't reach /api/traders</b></span>` : ""}`);
  }
  function renderBoard() {
    const top = (traders.top || []).slice().sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0));
    const idx = followerIndex(), cps = copiers(), t = clockNow();
    const rows = showAll ? top : top.slice(0, TOP_VISIBLE);
    setHTML(rowsEl, rows.map(r => {
      const who = followerOf(r.wallet, r.rank, idx);
      return `<tr>
        <td class="cp-rank">${E(r.rank)}</td>
        <td><span class="cp-wallet"><code title="${E(r.wallet)}">${E(shortAddr(r.wallet))}</code>
          <button type="button" class="cp-ib cp-copy" data-wallet="${E(r.wallet)}" aria-label="Copy address ${E(r.wallet)}">Copy</button>
          <a class="cp-ib" href="https://solscan.io/account/${encodeURIComponent(r.wallet || "")}" target="_blank" rel="noopener noreferrer" aria-label="Open ${E(shortAddr(r.wallet))} on Solscan">Solscan</a></span></td>
        <td class="n ${(r.pnl_usd || 0) >= 0 ? "pos" : "neg"}"${r.volume_usd ? ` title="${usd(r.volume_usd, 0)} traded"` : ""}>${sgn(r.pnl_usd || 0, 0)}</td>
        <td class="n ${(r.roi_pct || 0) >= 0 ? "pos" : "neg"}">${pctText(r.roi_pct || 0)}</td>
        <td class="n cp-hide-sm">${r.win_rate == null ? "—" : Math.round(r.win_rate) + "%"}${r.trades != null ? `<small>${Number(r.trades).toLocaleString()} trades</small>` : ""}</td>
        <td class="n cp-hide-sm">${r.tokens == null ? "—" : Number(r.tokens).toLocaleString()}</td>
        <td class="n">${r.last_trade_ts ? `<span data-cp-ts="${+r.last_trade_ts}">${E(agoText(t - r.last_trade_ts))}</span>` : "—"}</td>
        <td>${pill(who, cps)}</td></tr>`;
    }).join("") || `<tr><td colspan="8" class="empty">No wallets ranked yet.</td></tr>`);
    bcount.textContent = top.length ? `${rows.length} of ${top.length}` : "";
    moreBtn.hidden = top.length <= TOP_VISIBLE;
    moreBtn.textContent = showAll ? `Show the top ${TOP_VISIBLE}` : `Show all ${top.length}`;
    // legend: which copier takes which slice
    const slices = idx.slices.slice().sort((a, b) => a[0] - b[0]);
    setHTML(legendEl, slices.map(([lo, hi, name]) => `<span title="ranks ${lo} to ${hi}">${pill(name, cps)}</span>`).join(""));
  }
  function renderSignals() {
    const sigs = (traders.signals || []).slice(0, SIGNALS_MAX), idx = followerIndex(), cps = copiers(), t = clockNow();
    const fresh = new Set();
    for (const s of sigs) { if (!firstSignals && !seenSignals.has(s.id)) fresh.add(s.id); seenSignals.add(s.id); }
    firstSignals = false;
    setHTML(sigEl, sigs.map(s => {
      const who = followerOf(s.wallet, s.rank, idx), buy = s.side !== "sell";
      const src = s.source === "helius" ? ["helius", "Helius · seconds", "Seen on-chain within seconds"]
                : s.source === "gecko" ? ["gecko", "Gecko · minutes late", "From GeckoTerminal, a few minutes behind the chain"]
                : ["", E(s.source || "unknown"), "Signal source"];
      return `<div class="cp-sig ${buy ? "buy" : "sell"}${fresh.has(s.id) && !reduced ? " cp-fresh" : ""}" data-id="${E(s.id)}">
        <span class="cp-t" data-cp-ts="${+s.ts || 0}">${s.ts ? E(agoText(t - s.ts)) : ""}</span>
        <div class="cp-what"><b class="cp-r">#${E(s.rank ?? "?")}</b> <code title="${E(s.wallet)}">${E(shortAddr(s.wallet))}</code>
          <span class="side ${buy ? "buy" : "sell"}">${buy ? "bought" : "sold"}</span> <span class="cp-sym">${E(s.symbol || shortAddr(s.mint))}</span>
          ${s.usd != null ? `<span class="cp-usd">for ${usd(s.usd, 0)}</span>` : ""}</div>
        <span class="cp-src ${src[0]}" title="${src[2]}">${src[1]}</span>
        <div class="cp-foll">${who ? `copied by ${pill(who, cps)}` : `<span class="cp-pill none">outside every slice</span>`}</div>
      </div>`;
    }).join("") || `<div class="empty">No copy signals yet. They appear when a ranked wallet buys or sells.</div>`);
    fcount.textContent = sigs.length ? `${sigs.length} newest` : "";
  }
  function paint() {
    renderStatus();
    if (state === "missing" && !traders) {
      gridEl.hidden = true; noteEl.hidden = false;
      noteEl.textContent = "The top-trader feed isn't available yet. Restart the arena (python main.py) so it serves /api/traders; this board fills in on its own after that.";
      return;
    }
    if (!traders) {
      gridEl.hidden = true; noteEl.hidden = false;
      noteEl.textContent = state === "unreachable" ? "Can't reach /api/traders. Is main.py running?" : "Loading the leaderboard…";
      return;
    }
    noteEl.hidden = true; gridEl.hidden = false;
    renderBoard(); renderSignals();
  }
  function tickAgo() {
    const t = clockNow();
    slot.querySelectorAll("[data-cp-ts]").forEach(el => { const ts = +el.dataset.cpTs; if (ts) el.textContent = agoText(t - ts); });
  }

  /* ---------- interactions ---------- */
  moreBtn.addEventListener("click", () => { showAll = !showAll; if (traders) renderBoard(); });
  slot.addEventListener("click", e => {
    const b = e.target.closest(".cp-copy");
    if (!b) return;
    const w = b.dataset.wallet || "", label = b.textContent;
    const done = ok => { b.textContent = ok ? "Copied" : "Failed"; b.classList.toggle("done", ok); setTimeout(() => { b.textContent = label; b.classList.remove("done"); }, 1200); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(w).then(() => done(true), () => done(false));
    else done(false);
  });

  /* ---------- polling ---------- */
  let inflight = false;
  async function poll() {
    if (inflight) return;
    inflight = true;
    try {
      const r = await fetch("/api/traders", {cache: "no-store"});
      if (r.status === 404) { state = "missing"; }
      else if (!r.ok) throw new Error(`HTTP ${r.status}`);
      else {
        const j = await r.json();
        if (!j || typeof j !== "object") throw new Error("bad payload");
        traders = j; state = "ok"; fetchedAt = clockNow();
      }
    } catch {
      state = traders ? "stale" : "unreachable";
    }
    inflight = false;
    paint();
  }
  poll();
  setInterval(poll, POLL_MS);
  setInterval(tickAgo, 10000);
  // the roster decides pill colours and the slice legend, so repaint once agents arrive or change
  let rosterKey = "";
  document.addEventListener("arena:data", e => {
    const d = e.detail, key = d && d.agents ? d.agents.map(a => a.name + ":" + a.avatar).join("|") : "";
    if (key !== rosterKey) { rosterKey = key; if (traders) paint(); }
  });
})();
