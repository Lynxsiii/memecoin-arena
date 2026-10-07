/* Ticker tape plugin — scrolling market marquee in #slot-top, toggle in #toolbar. */
(() => {
  "use strict";
  const slot = document.getElementById("slot-top");
  const toolbar = document.getElementById("toolbar");
  if (!slot) return;

  const PREF = "ticker.visible";
  const POLL_MS = 10000;
  const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");

  const css = `
  #slot-top { overflow: hidden; max-width: 100%; }
  .tk-tape { position: relative; height: 34px; overflow: hidden; background: var(--ink, #1b1640);
    border: 2px solid var(--seam, #342c63); box-shadow: inset 0 0 0 1px var(--night, #16122e);
    margin: 0 0 12px; font-family: var(--body, Rubik, sans-serif); font-size: 13px; color: var(--moon, #eeeafb);
    outline: none; }
  .tk-tape[hidden] { display: none; }
  .tk-track { display: flex; width: max-content; height: 100%; align-items: center;
    animation: tk-scroll var(--tk-dur, 40s) linear infinite; will-change: transform; }
  .tk-tape:hover .tk-track, .tk-tape:focus-within .tk-track, .tk-tape.tk-paused .tk-track { animation-play-state: paused; }
  .tk-group { display: flex; align-items: center; height: 100%; flex: none; }
  .tk-item { display: inline-flex; align-items: center; gap: 7px; height: 100%; padding: 0 14px; color: inherit;
    text-decoration: none; border-right: 1px solid var(--seam, #342c63); white-space: nowrap; }
  .tk-item:hover, .tk-item:focus-visible { background: var(--dusk, #1f1a40); outline: none; }
  .tk-item:focus-visible { box-shadow: inset 0 0 0 2px var(--gold, #f7c548); }
  .tk-rate { width: 8px; height: 8px; flex: none; }
  .tk-rate[data-r="green"] { background: var(--profit, #59e3a7); }
  .tk-rate[data-r="yellow"] { background: var(--gold, #f7c548); }
  .tk-rate[data-r="red"] { background: var(--loss, #ff6b7a); }
  .tk-rate[data-r="none"] { background: var(--seam, #342c63); }
  .tk-sym { font-family: var(--pixel, "Jersey 10", monospace); font-size: 20px; line-height: 1; letter-spacing: 0.5px; }
  .tk-price { color: var(--moon, #eeeafb); font-variant-numeric: tabular-nums; }
  .tk-price sub { font-size: 9px; vertical-align: baseline; position: relative; top: 3px; color: var(--haze, #a39dcb); }
  .tk-chg { font-variant-numeric: tabular-nums; }
  .tk-chg small { color: var(--haze, #a39dcb); font-size: 10px; margin-right: 2px; }
  .tk-up { color: var(--profit, #59e3a7); } .tk-down { color: var(--loss, #ff6b7a); } .tk-flat { color: var(--haze, #a39dcb); }
  .tk-pips { display: inline-flex; gap: 2px; align-items: center; }
  .tk-pip { width: 5px; height: 5px; display: inline-block; flex: none; }
  .tk-more { font-size: 10px; color: var(--haze, #a39dcb); margin-left: 2px; }
  .tk-empty { display: flex; align-items: center; height: 100%; padding: 0 14px; color: var(--haze, #a39dcb); }
  @keyframes tk-scroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
  @media (prefers-reduced-motion: reduce) {
    .tk-tape { overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; }
    .tk-track { animation: none; }
    .tk-group.tk-dup { display: none; }
  }
  .tk-btn { font: 13px var(--body, Rubik, sans-serif); color: var(--moon, #eeeafb); background: var(--dusk, #1f1a40);
    border: 1px solid var(--seam, #342c63); padding: 3px 9px; cursor: pointer; line-height: 1.3; }
  .tk-btn:hover { border-color: var(--haze, #a39dcb); }
  .tk-btn[aria-pressed="false"] { color: var(--haze, #a39dcb); }
  .tk-btn[aria-pressed="true"]::before { content: ""; display: inline-block; width: 6px; height: 6px; margin-right: 6px;
    background: var(--profit, #59e3a7); vertical-align: 1px; }
  .tk-btn:focus-visible { outline: 2px solid var(--gold, #f7c548); outline-offset: 1px; }
  `;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  const escText = s => (typeof esc === "function" ? esc(String(s ?? "")) : String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])));

  // Smart price formatting: 0.0000123 → 0.0₄123 ; 0.0456 → 0.0456 ; 1.23 → 1.23 ; 1234 → 1,234
  function fmtPrice(p) {
    if (!(p > 0)) return "$0";
    if (p >= 1000) return "$" + Math.round(p).toLocaleString();
    if (p >= 1) return "$" + p.toFixed(p >= 100 ? 1 : 2);
    if (p >= 0.01) return "$" + p.toFixed(4);
    const s = p.toFixed(20);
    const m = s.match(/^0\.(0*)(\d+)/);
    if (!m) return "$" + p.toPrecision(3);
    const zeros = m[1].length, digits = m[2].slice(0, 3);
    if (zeros < 3) return "$0." + m[1] + digits;
    return `$0.0<sub>${zeros}</sub>${digits}`;
  }
  function fmtChg(n) {
    if (n == null || isNaN(n)) return `<span class="tk-flat">—</span>`;
    const cls = n > 0.005 ? "tk-up" : n < -0.005 ? "tk-down" : "tk-flat";
    return `<span class="${cls}">${n > 0 ? "+" : ""}${n.toFixed(1)}%</span>`;
  }
  function agentColor(name) {
    try {
      if (typeof agentByName === "function" && typeof data !== "undefined" && data) {
        const a = agentByName(name);
        if (typeof colorOf === "function") return colorOf(a);
        if (typeof AVATAR_COLOR !== "undefined") return AVATAR_COLOR[a.avatar] || "#c8d0e8";
      }
    } catch {}
    return "#c8d0e8";
  }

  // Build DOM
  const tape = document.createElement("div");
  tape.className = "tk-tape";
  tape.setAttribute("role", "region");
  tape.setAttribute("aria-label", "Market ticker");
  tape.tabIndex = 0;
  const track = document.createElement("div");
  track.className = "tk-track";
  const g1 = document.createElement("div"); g1.className = "tk-group";
  const g2 = document.createElement("div"); g2.className = "tk-group tk-dup"; g2.setAttribute("aria-hidden", "true");
  track.append(g1, g2);
  tape.appendChild(track);
  slot.appendChild(tape);

  // Pause on focus as well as hover (keyboard users)
  tape.addEventListener("focusin", () => tape.classList.add("tk-paused"));
  tape.addEventListener("focusout", () => tape.classList.remove("tk-paused"));
  // A plain click opens the in-arena price chart (tokenchart.js); modifier clicks and middle clicks still follow the DexScreener link.
  tape.addEventListener("click", e => {
    const a = e.target.closest(".tk-item[data-token]");
    if (!a || !a.dataset.token || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button !== 0) return;
    if (!window.arenaTokenChart) return;
    e.preventDefault();
    document.dispatchEvent(new CustomEvent("arena:token-chart", {detail: {address: a.dataset.token, symbol: a.dataset.symbol, trigger: a}}));
  });

  let lastHTML = "";
  function render(rows) {
    let html;
    if (!rows || !rows.length) {
      html = `<span class="tk-empty">Waiting for market data…</span>`;
    } else {
      html = rows.map(t => {
        // With 14 agents a popular token can be held by many; cap the pips and show the overflow as "+N".
        const holders = t.held_by || [], MAX_PIPS = 7;
        const pips = holders.slice(0, MAX_PIPS).map(n =>
          `<i class="tk-pip" style="background:${agentColor(n)}" title="${escText(n)}"></i>`).join("") +
          (holders.length > MAX_PIPS ? `<small class="tk-more">+${holders.length - MAX_PIPS}</small>` : "");
        const href = t.address ? `https://dexscreener.com/solana/${encodeURIComponent(t.address)}` : (t.url || "#");
        const rating = ["green", "yellow", "red"].includes(t.rating) ? t.rating : "none";
        const title = `${escText(t.name || t.symbol)} — rating ${rating}` + (t.held_by && t.held_by.length ? ` — held by ${escText(t.held_by.join(", "))}` : "");
        return `<a class="tk-item" href="${href}" target="_blank" rel="noopener noreferrer" title="${title}" data-token="${escText(t.address || "")}" data-symbol="${escText(t.symbol || "")}">` +
          `<span class="tk-rate" data-r="${rating}" aria-label="rating ${rating}"></span>` +
          `<span class="tk-sym">${escText(t.symbol || "?")}</span>` +
          `<span class="tk-price">${fmtPrice(+t.price)}</span>` +
          `<span class="tk-chg"><small>5m</small>${fmtChg(+t.chg_m5)}</span>` +
          `<span class="tk-chg"><small>1h</small>${fmtChg(+t.chg_h1)}</span>` +
          (pips ? `<span class="tk-pips" aria-label="held by ${escText((t.held_by || []).join(", "))}">${pips}</span>` : "") +
        `</a>`;
      }).join("");
    }
    if (html === lastHTML) return;
    lastHTML = html;
    g1.innerHTML = html;
    g2.innerHTML = rows && rows.length ? html : "";
    // Scroll speed proportional to content width (~70px/s), so long tapes don't zip past.
    const w = g1.scrollWidth || (rows ? rows.length * 230 : 800);
    track.style.setProperty("--tk-dur", Math.max(18, Math.round(w / 70)) + "s");
  }

  let timer = null, inflight = false;
  async function poll() {
    if (inflight || tape.hidden) return;
    inflight = true;
    try {
      const r = await fetch("/api/market", {cache: "no-store"});
      if (r.ok) render(await r.json());
    } catch (e) { /* keep last tape on error */ }
    inflight = false;
  }
  function start() { stop(); poll(); timer = setInterval(poll, POLL_MS); }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }

  // Re-color pips when agent data lands (agentByName needs `data`).
  let colored = false;
  document.addEventListener("arena:data", () => {
    if (!colored && lastHTML) { colored = true; lastHTML = ""; poll(); }
  });

  // Toolbar toggle
  let visible = true;
  try { visible = typeof arenaPrefs !== "undefined" ? arenaPrefs.get(PREF, true) !== false : true; } catch {}
  let btn = null;
  if (toolbar) {
    btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tk-btn";
    btn.textContent = "Ticker";
    btn.title = "Show or hide the market ticker";
    btn.addEventListener("click", () => {
      visible = !visible;
      try { if (typeof arenaPrefs !== "undefined") arenaPrefs.set(PREF, visible); } catch {}
      apply();
    });
    toolbar.appendChild(btn);
  }
  function apply() {
    tape.hidden = !visible;
    if (btn) btn.setAttribute("aria-pressed", String(visible));
    if (visible) start(); else stop();
  }
  document.addEventListener("arena:prefs", e => {
    if (e.detail && e.detail.key === PREF) { visible = e.detail.value !== false; apply(); }
  });

  // Pause polling when the tab is hidden
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop(); else if (visible) start();
  });

  render(null);
  apply();
})();
