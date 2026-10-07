/* filters.js — QoL tools for the two live feeds: agent chips, side / outcome / trades-only
   filters, text search, token popover, pause-feed overlay, "/" and Esc keyboard shortcuts.
   Filtering survives the main script's innerHTML re-renders: structural filters are CSS rules in a
   generated <style>; text search / win-loss use a MutationObserver that re-tags children. */
(() => {
  "use strict";
  if (window.__flFilters) return;
  window.__flFilters = true;

  const byId = id => document.getElementById(id);
  const prefs = typeof arenaPrefs !== "undefined" ? arenaPrefs : { get: (k, d) => d, set() {} };
  const E = typeof esc === "function" ? esc : s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cssStr = s => JSON.stringify(String(s));  // quoted, escaped CSS string
  const PREF = { decisions: "fl.decisions", trades: "fl.trades" };

  const st = {
    decisions: Object.assign({ agent: "all", orders: false }, prefs.get(PREF.decisions, {}) || {}, { q: "" }),
    trades: Object.assign({ agent: "all", side: "all", outcome: "all" }, prefs.get(PREF.trades, {}) || {}, { q: "" }),
  };
  const ui = { decisions: {}, trades: {} };

  /* ---------- styles ---------- */
  const base = document.createElement("style");
  base.textContent = `
.fl-tools{display:flex;flex-direction:column;gap:6px;margin:0 0 8px;font:13px var(--body,Rubik,sans-serif);color:var(--moon,#eeeafb);min-width:0}
.fl-row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;min-width:0}
.fl-group{display:inline-flex;flex-wrap:wrap;gap:4px}
.fl-chip,.fl-btn{display:inline-flex;align-items:center;gap:6px;padding:3px 8px;border:1px solid var(--seam,#342c63);background:var(--dusk,#1f1a40);color:var(--moon,#eeeafb);border-radius:3px;font:inherit;line-height:1.3;cursor:pointer;box-shadow:0 1px 0 var(--night,#16122e);white-space:nowrap;max-width:100%}
.fl-chip.fl-agent{gap:4px;padding:2px 6px;font-size:12px;border-color:color-mix(in srgb,var(--c) 45%,var(--seam,#342c63))}
.fl-chip.fl-agent .fl-name{overflow:hidden;text-overflow:ellipsis;max-width:14ch}
.fl-chip.fl-team{font-size:12px;padding:2px 7px;gap:4px}
.fl-chip.fl-team .fl-av{width:12px;height:11px}.fl-chip.fl-team .fl-av svg{width:12px;height:11px}
.fl-chip.fl-team .fl-av+.fl-av{margin-left:-6px}
.fl-chip.fl-team.fl-claude{border-color:color-mix(in srgb,var(--gold,#f7c548) 45%,var(--seam,#342c63))}
.fl-chip.fl-team.fl-bots{border-color:color-mix(in srgb,#c8d0e8 45%,var(--seam,#342c63))}
.fl-chip.fl-team.fl-copy{border-color:color-mix(in srgb,#ff5fd2 45%,var(--seam,#342c63))}
.fl-chips .fl-group{align-items:center}
.fl-chips .fl-sepv{width:1px;height:16px;background:var(--seam,#342c63);margin:0 2px;flex:none}
.fl-chip:hover,.fl-btn:hover{border-color:var(--haze,#a39dcb);background:#26204c}
.fl-chip[aria-pressed="true"],.fl-btn[aria-pressed="true"]{border-color:var(--gold,#f7c548);background:#2b2555;color:#fff;box-shadow:0 1px 0 var(--night,#16122e),inset 0 0 0 1px rgba(247,197,72,.25)}
.fl-chip:focus-visible,.fl-btn:focus-visible,.fl-search:focus-visible{outline:2px solid var(--gold,#f7c548);outline-offset:1px}
.fl-av{display:inline-block;width:16px;height:14px;line-height:0;flex:none}
.fl-av svg{width:16px;height:14px;display:block}
.fl-search{flex:1 1 140px;min-width:0;padding:3px 8px;border:1px solid var(--seam,#342c63);background:var(--night,#16122e);color:var(--moon,#eeeafb);border-radius:3px;font:inherit;line-height:1.3}
.fl-search::placeholder{color:var(--haze,#a39dcb);opacity:.8}
.fl-search:focus{outline:none;border-color:var(--gold,#f7c548)}
.fl-empty{color:var(--haze,#a39dcb);padding:2px 0}
.fl-sep{flex:1 1 0;min-width:0}
#decisions .fl-hide,#trades .fl-hide,.fl-frozen .fl-hide{display:none!important}
#decisions.fl-paused,#trades.fl-paused{display:none!important}
.fl-frozen{outline:1px dashed var(--gold,#f7c548);outline-offset:-1px}
#trades .trade .what,.fl-frozen .trade .what,#bags tr[data-token] td:first-child{cursor:pointer}
#trades .trade .what:hover,.fl-frozen .trade .what:hover,#bags tr[data-token]:hover td:first-child{text-decoration:underline dotted var(--haze,#a39dcb)}
.fl-pop{position:fixed;z-index:9000;width:260px;max-width:calc(100vw - 24px);background:var(--dusk,#1f1a40);border:1px solid var(--gold,#f7c548);border-radius:6px;padding:10px 12px;box-shadow:0 10px 28px rgba(0,0,0,.55);font:13px var(--body,Rubik,sans-serif);color:var(--moon,#eeeafb)}
.fl-pop-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px}
.fl-pop-head b{font:22px var(--pixel,"Jersey 10"),var(--body,Rubik);letter-spacing:.5px;color:var(--gold,#f7c548)}
.fl-x{background:none;border:0;color:var(--haze,#a39dcb);font-size:18px;line-height:1;cursor:pointer;padding:0 4px}
.fl-x:hover{color:#fff}
.fl-addr{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.fl-addr code{font-size:12px;color:var(--haze,#a39dcb);background:var(--night,#16122e);padding:2px 6px;border-radius:3px}
.fl-links{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.fl-links .fl-chart{border-color:var(--gold,#f7c548);color:var(--gold,#f7c548)}
.fl-links a{color:var(--gold,#f7c548);text-decoration:none;border-bottom:1px dotted var(--gold,#f7c548)}
.fl-links a:hover{color:#fff;border-color:#fff}
@media (max-width:640px){.fl-chip.fl-agent .fl-name{max-width:9ch}}
@media (max-width:480px){
  .fl-chip.fl-agent{padding:3px 5px}
  .fl-chip.fl-agent .fl-av{width:18px;height:16px}.fl-chip.fl-agent .fl-av svg{width:18px;height:16px}
  .fl-chip.fl-agent .fl-name{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%)}
  .fl-chip.fl-agent[aria-pressed="true"] .fl-name{position:static;width:auto;height:auto;clip:auto;clip-path:none;max-width:9ch}
  .fl-chips .fl-sepv{display:none}
  .fl-search{flex-basis:100%}
}
`;
  document.head.appendChild(base);
  const dyn = document.createElement("style");  // generated filter rules
  document.head.appendChild(dyn);

  /* "team:claude" / "team:bots" / "team:copy" agent values select a whole team; resolved against the current roster.
     Older saved prefs used "team:llm" / "team:bot", which map onto the first two. */
  const ORDER = typeof TEAM_ORDER !== "undefined" ? TEAM_ORDER : ["claude", "bots", "copy"];
  const NAMES = typeof TEAM_INFO !== "undefined" ? TEAM_INFO : { claude: "Team Claude", bots: "Team Bots", copy: "Team Copy" };
  const teamKey = a => (typeof teamOf === "function" ? teamOf(a) : (NAMES[a.team] ? a.team : a.kind === "llm" ? "claude" : "bots"));
  const LEGACY = { llm: "claude", bot: "bots" };
  const isTeam = v => typeof v === "string" && v.startsWith("team:");
  const teamOfValue = v => { const k = v.slice(5); return LEGACY[k] || k; };
  function teamNames(v) {
    const key = teamOfValue(v), ags = typeof data !== "undefined" && data && data.agents ? data.agents : [];
    return ags.filter(a => teamKey(a) === key).map(a => a.name);
  }
  function agentMatches(v, name) {
    if (v === "all") return true;
    if (isTeam(v)) return teamNames(v).includes(name);
    return name === v;
  }
  function agentNot(v) {  // CSS :not() chain hiding everything outside the selection
    if (isTeam(v)) return teamNames(v).map(n => `:not([data-agent=${cssStr(n)}])`).join("");
    return `:not([data-agent=${cssStr(v)}])`;
  }

  function buildCSS() {
    const r = [];
    const D = ["#decisions", '.fl-frozen[data-for="decisions"]'], T = ["#trades", '.fl-frozen[data-for="trades"]'];
    const rule = (roots, sel) => r.push(roots.map(x => `${x} ${sel}`).join(",") + "{display:none!important}");
    const d = st.decisions, t = st.trades;
    if (d.agent !== "all") rule(D, `.decision${agentNot(d.agent)}`);
    if (d.orders) rule(D, `.decision:not(.has-orders):not(.live)`);
    if (t.agent !== "all") rule(T, `.trade${agentNot(t.agent)}`);
    if (t.side !== "all") rule(T, `.trade:not([data-side=${cssStr(t.side)}])`);
    if (t.outcome !== "all") rule(T, `.trade:not([data-side="sell"])`);
    dyn.textContent = r.join("\n");
  }

  /* ---------- matching (mirrors the CSS, adds search / win-loss) ---------- */
  function decVisible(el) {
    const s = st.decisions;
    if (!agentMatches(s.agent, el.dataset.agent)) return false;
    if (el.classList.contains("live")) return true;
    if (s.orders && !el.classList.contains("has-orders")) return false;
    if (s.q) {
      const note = el.querySelector(".note"), ord = el.querySelector(".orders");
      const txt = ((note ? note.textContent : "") + " " + (ord ? ord.textContent : el.textContent)).toLowerCase();
      if (!txt.includes(s.q)) return false;
    }
    return true;
  }
  function symbolOf(el, symOf) {
    if (symOf && symOf.has(el.dataset.id)) return symOf.get(el.dataset.id);
    const w = el.querySelector(".what");
    const words = (w ? w.textContent : "").trim().split(/\s+/);
    return words[words.length - 1] || "";
  }
  function trVisible(el, symOf) {
    const s = st.trades;
    if (!agentMatches(s.agent, el.dataset.agent)) return false;
    if (s.side !== "all" && el.dataset.side !== s.side) return false;
    if (s.outcome !== "all") {
      if (el.dataset.side !== "sell") return false;
      const sm = el.querySelector(".amt small");
      if (!sm) return false;
      const pos = sm.classList.contains("pos");
      if (s.outcome === "win" ? !pos : pos) return false;
    }
    if (s.q) {
      const sym = symbolOf(el, symOf).toLowerCase(), addr = (el.dataset.token || "").toLowerCase();
      if (!sym.includes(s.q) && !addr.startsWith(s.q)) return false;
    }
    return true;
  }

  function apply(which) {
    const cont = byId(which), u = ui[which];
    if (!cont || !u.empty) return;
    const symOf = which === "trades" && typeof data !== "undefined" && data && data.trades
      ? new Map(data.trades.map(t => [String(t.id), t.symbol])) : null;
    let shown = 0, total = 0;
    for (const el of cont.children) {
      if (!el.matches(".decision,.trade")) continue;
      total++;
      const ok = which === "trades" ? trVisible(el, symOf) : decVisible(el);
      el.classList.toggle("fl-hide", !ok);
      if (ok) shown++;
    }
    u.empty.hidden = !(total && !shown);
  }

  /* ---------- tools rows ---------- */
  const sprite = av => spriteSVG(av).replace('class="bob"', "");
  const byOrder = xs => xs.slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0));  // stage order, same as the lanes
  function chipsHTML(agents, withTeams) {
    const teams = ORDER.map(key => ({ key, label: NAMES[key] || ("Team " + key), list: byOrder(agents.filter(a => teamKey(a) === key)) })).filter(t => t.list.length);
    const chip = a => `<button type="button" class="fl-chip fl-agent" data-k="agent" data-v="${E(a.name)}" style="--c:${colorOf(a)}" title="${E(a.name)}" aria-label="${E(a.name)}">
        <span class="fl-av">${sprite(a.avatar)}</span><span class="fl-name">${E(a.name)}</span></button>`;
    const teamChip = t => `<button type="button" class="fl-chip fl-team fl-${E(t.key)}" data-k="agent" data-v="team:${E(t.key)}" title="${E(t.label)}: ${E(t.list.map(a => a.name).join(", "))}">
        ${t.list.slice(0, 2).map(a => `<span class="fl-av">${sprite(a.avatar)}</span>`).join("")}<span class="fl-name">${E(t.label)}</span></button>`;
    let html = `<button type="button" class="fl-chip" data-k="agent" data-v="all">All</button>`;
    if (withTeams && teams.length > 1) html += teams.map(teamChip).join("") + `<span class="fl-sepv" aria-hidden="true"></span>`;
    html += teams.map((t, i) => `${i ? `<span class="fl-sepv" aria-hidden="true"></span>` : ""}<span class="fl-group" role="group" aria-label="${E(t.label)}">${t.list.map(chip).join("")}</span>`).join("");
    return html;
  }

  function build(which) {
    const slot = byId(which === "trades" ? "slot-trades-tools" : "slot-decisions-tools");
    if (!slot || ui[which].root) return;
    const root = document.createElement("div");
    root.className = "fl-tools";
    root.dataset.for = which;
    root.innerHTML = which === "trades" ? `
      <div class="fl-row fl-chips" role="group" aria-label="Filter trades by agent"></div>
      <div class="fl-row">
        <div class="fl-group" role="group" aria-label="Side">
          <button type="button" class="fl-btn" data-k="side" data-v="all">All</button>
          <button type="button" class="fl-btn" data-k="side" data-v="buy">Buys</button>
          <button type="button" class="fl-btn" data-k="side" data-v="sell">Sells</button>
        </div>
        <div class="fl-group" role="group" aria-label="Outcome">
          <button type="button" class="fl-btn" data-k="outcome" data-v="win" data-toggle>Wins only</button>
          <button type="button" class="fl-btn" data-k="outcome" data-v="loss" data-toggle>Losses only</button>
        </div>
        <input class="fl-search" type="search" placeholder="Search symbol  ( / )" aria-label="Search trades by symbol" autocomplete="off">
        <button type="button" class="fl-btn fl-pause" aria-pressed="false">Pause feed</button>
      </div>
      <div class="fl-empty" hidden>No trades match these filters</div>` : `
      <div class="fl-row fl-chips" role="group" aria-label="Filter decisions by agent"></div>
      <div class="fl-row">
        <button type="button" class="fl-btn" data-k="orders" data-v="true" data-toggle>Only with trades</button>
        <input class="fl-search" type="search" placeholder="Search notes and orders" aria-label="Search decisions" autocomplete="off">
        <button type="button" class="fl-btn fl-pause" aria-pressed="false">Pause feed</button>
      </div>
      <div class="fl-empty" hidden>No decisions match these filters</div>`;
    slot.appendChild(root);
    const u = ui[which];
    u.root = root; u.chips = root.querySelector(".fl-chips"); u.search = root.querySelector(".fl-search");
    u.empty = root.querySelector(".fl-empty"); u.pauseBtn = root.querySelector(".fl-pause");
    u.frozen = null; u.newCount = 0; u.agentKey = null;

    root.addEventListener("click", e => {
      const b = e.target.closest("button");
      if (!b || !root.contains(b)) return;
      if (b.classList.contains("fl-pause")) { togglePause(which); return; }
      const k = b.dataset.k; if (!k) return;
      const s = st[which];
      let v = b.dataset.v === "true" ? true : b.dataset.v;
      if (b.hasAttribute("data-toggle")) {
        const active = String(s[k]) === String(v);
        v = active ? (k === "orders" ? false : "all") : v;
      }
      s[k] = v;
      if (which === "trades") {  // keep side and outcome coherent
        if (k === "outcome" && v !== "all") s.side = "sell";
        if (k === "side" && v !== "sell") s.outcome = "all";
      }
      persist(which); buildCSS(); refreshPressed(which); apply(which);
    });
    u.search.addEventListener("input", () => { st[which].q = u.search.value.trim().toLowerCase(); apply(which); });

    const cont = byId(which);
    if (cont) new MutationObserver(() => apply(which)).observe(cont, { childList: true });
  }

  function persist(which) {
    const s = st[which], out = {};
    for (const k of Object.keys(s)) if (k !== "q") out[k] = s[k];
    prefs.set(PREF[which], out);
  }

  function refreshPressed(which) {
    const s = st[which];
    ui[which].root.querySelectorAll("button[data-k]").forEach(b => {
      const v = b.dataset.v === "true" ? true : b.dataset.v;
      b.setAttribute("aria-pressed", String(String(s[b.dataset.k]) === String(v)));
    });
  }

  function ensureChips(which) {
    const u = ui[which];
    if (!u.root || typeof data === "undefined" || !data || !data.agents) return;
    const agents = which === "trades" ? data.agents : data.agents.filter(a => a.kind === "llm");
    const key = byOrder(agents).map(a => a.name + ":" + a.avatar + ":" + teamKey(a)).join("|");
    if (key === u.agentKey) return;
    u.agentKey = key;
    u.chips.innerHTML = chipsHTML(agents, which === "trades");
    if (isTeam(st[which].agent) && LEGACY[st[which].agent.slice(5)]) { st[which].agent = "team:" + teamOfValue(st[which].agent); persist(which); }  // migrate old prefs
    const sel = st[which].agent;
    const valid = sel === "all" || (isTeam(sel) ? which === "trades" && teamNames(sel).length > 0 : agents.some(a => a.name === sel));
    if (!valid) { st[which].agent = "all"; persist(which); }
    buildCSS();  // roster may have changed, so team :not() chains need rebuilding
    refreshPressed(which);
  }

  /* ---------- pause ---------- */
  function pauseLabel(which) {
    const u = ui[which];
    u.pauseBtn.textContent = u.frozen ? (u.newCount ? `Paused, ${u.newCount} new` : "Paused") : "Pause feed";
    u.pauseBtn.setAttribute("aria-pressed", String(!!u.frozen));
    u.pauseBtn.title = u.frozen ? "Resume the live feed" : "Freeze the feed so it stops moving while you read";
  }
  function togglePause(which) {
    const u = ui[which], cont = byId(which);
    if (!cont) return;
    if (u.frozen) {
      u.frozen.remove(); u.frozen = null; u.newCount = 0;
      cont.classList.remove("fl-paused");
      apply(which);
    } else {
      const c = document.createElement("div");
      c.className = cont.className + " fl-frozen";
      c.dataset.for = which;
      c.setAttribute("aria-label", "Paused snapshot of the feed");
      c.innerHTML = cont.innerHTML;
      cont.after(c);
      cont.classList.add("fl-paused");
      u.frozen = c; u.newCount = 0;
    }
    pauseLabel(which);
  }
  document.addEventListener("arena:trade", () => { if (ui.trades.frozen) { ui.trades.newCount++; pauseLabel("trades"); } });
  document.addEventListener("arena:decision", () => { if (ui.decisions.frozen) { ui.decisions.newCount++; pauseLabel("decisions"); } });

  /* ---------- token popover ---------- */
  const pop = document.createElement("div");
  pop.className = "fl-pop"; pop.hidden = true; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", "Token links");
  document.body.appendChild(pop);
  const shortAddr = a => a.length > 12 ? a.slice(0, 4) + "…" + a.slice(-4) : a;
  function openPop(host, e) {
    const addr = host.dataset.token || "";
    let sym = "";
    if (host.classList.contains("trade")) {
      const symOf = typeof data !== "undefined" && data && data.trades ? new Map(data.trades.map(t => [String(t.id), t.symbol])) : null;
      sym = symbolOf(host, symOf);
    } else {
      const td = host.querySelector("td");
      sym = td ? td.textContent.trim() : "";
    }
    pop.innerHTML = `
      <div class="fl-pop-head"><b>${E(sym || "Token")}</b><button type="button" class="fl-x" aria-label="Close">×</button></div>
      <div class="fl-addr"><code title="${E(addr)}">${E(shortAddr(addr))}</code><button type="button" class="fl-btn fl-copy">Copy address</button></div>
      <div class="fl-links">
        <button type="button" class="fl-btn fl-chart" aria-pressed="false">Price chart</button>
        <a href="https://dexscreener.com/solana/${encodeURIComponent(addr)}" target="_blank" rel="noopener noreferrer">DexScreener</a>
        <a href="https://solscan.io/token/${encodeURIComponent(addr)}" target="_blank" rel="noopener noreferrer">Solscan</a>
      </div>`;
    pop.hidden = false;
    const w = pop.offsetWidth || 260, h = pop.offsetHeight || 120;
    const x = Math.max(12, Math.min(e.clientX + 8, window.innerWidth - w - 12));
    const y = e.clientY + 12 + h > window.innerHeight ? Math.max(12, e.clientY - h - 8) : e.clientY + 12;
    pop.style.left = x + "px"; pop.style.top = y + "px";
    pop.querySelector(".fl-x").addEventListener("click", closePop);
    pop.querySelector(".fl-chart").addEventListener("click", () => {  // tokenchart.js listens for this; the trigger gets focus back on close
      closePop();
      document.dispatchEvent(new CustomEvent("arena:token-chart", { detail: { address: addr, symbol: sym, trigger: host } }));
    });
    pop.querySelector(".fl-copy").addEventListener("click", ev => {
      const b = ev.currentTarget;
      const done = ok => { b.textContent = ok ? "Copied" : "Copy failed"; setTimeout(() => { b.textContent = "Copy address"; }, 1200); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(addr).then(() => done(true), () => done(false));
      else done(false);
    });
  }
  function closePop() { pop.hidden = true; }
  document.addEventListener("click", e => {
    if (!pop.hidden && pop.contains(e.target)) return;
    const what = e.target.closest("#trades .trade[data-token] .what, .fl-frozen .trade[data-token] .what");
    const host = what ? what.closest(".trade") : e.target.closest("#bags tr[data-token]");
    if (!host) { if (!pop.hidden) closePop(); return; }
    if (e.target.closest("a, button")) return;
    e.preventDefault();
    openPop(host, e);
  });

  /* ---------- keyboard ---------- */
  document.addEventListener("keydown", e => {
    const a = document.activeElement;
    const typing = a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.tagName === "SELECT" || a.isContentEditable);
    if (e.key === "Escape") {
      if (!pop.hidden) { closePop(); e.preventDefault(); return; }
      if (a && a.classList.contains("fl-search")) {
        e.preventDefault();
        if (a.value) { a.value = ""; a.dispatchEvent(new Event("input", { bubbles: true })); } else a.blur();
      }
      return;
    }
    if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey && !typing && ui.trades.search) {
      e.preventDefault();
      ui.trades.search.focus(); ui.trades.search.select();
    }
  });

  /* ---------- boot ---------- */
  function init() {
    build("decisions"); build("trades");
    buildCSS();
    refreshPressed("decisions"); refreshPressed("trades");
    ensureChips("decisions"); ensureChips("trades");
    apply("decisions"); apply("trades");
  }
  function onData() { ensureChips("decisions"); ensureChips("trades"); apply("decisions"); apply("trades"); }
  const start = () => { init(); document.addEventListener("arena:data", onData); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
