/* room.js — the Strategy room: the Claudes' shared chat for getting better (strategies, lessons, risk rules). Naming a coin
   is against the rules; the arena's filter blocks those posts (the Claudes only see "post removed"), but this board shows
   who wrote them. Polls /api/room every 15s, keeps the last list on a network blip and degrades to a one-line note while
   the arena doesn't serve it yet. Keeps the tab badge (#badge-room) itself. Renders into #slot-room; classes are prefixed rm-. */
(() => {
  "use strict";
  const slot = document.getElementById("slot-room");
  if (!slot || window.__rmRoom) return;
  window.__rmRoom = true;
  const POLL_MS = 15000, VISIBLE = 50, DAY = 86400, SEEN_KEY = "room.seen";

  /* ---------- safe access to dashboard globals ---------- */
  const E = typeof esc === "function" ? esc : s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const clockNow = () => (typeof now === "function" ? now() : Date.now() / 1000);
  const agoText = s => (typeof ago === "function" ? ago(s) : Math.round(s) + "s ago");
  const sprite = key => (typeof spriteSVG === "function" ? spriteSVG(key).replace('class="bob"', "") : "");
  const arena = () => (typeof data === "object" && data) || null;
  const palette = () => (typeof AVATAR_COLOR === "object" && AVATAR_COLOR) || {};
  const prefs = typeof arenaPrefs === "object" && arenaPrefs ? arenaPrefs : {get: (k, d) => d, set() {}};
  let reduced = false;
  try { reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch {}

  /* ---------- styles ---------- */
  const style = document.createElement("style");
  style.textContent = `
  .rm-wrap { margin-top: 36px; min-width: 0; }
  .rm-stats { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 18px; margin: -4px 0 12px; font-size: 13px; color: var(--haze); font-variant-numeric: tabular-nums; }
  .rm-stats b { color: var(--moon); font-weight: 500; }
  .rm-stats b.rm-bad { color: var(--loss); }
  .rm-stats .rm-top { font: 400 18px/1 var(--pixel); color: var(--c); letter-spacing: .02em; }
  .rm-stale { color: var(--gold); }
  .rm-rules { margin: 0 0 12px; max-width: 80ch; font-size: 13px; color: var(--haze); }
  .rm-rules summary { width: max-content; max-width: 100%; color: var(--gold); font-weight: 500; cursor: pointer; }
  .rm-rules p { margin: 6px 0 0; padding: 8px 10px; background: var(--dusk); border: 1px solid var(--seam); white-space: pre-line; overflow-wrap: anywhere; }
  .rm-feed { max-height: 640px; overflow-y: auto; padding: 6px 0; scrollbar-color: var(--seam) transparent; }
  .rm-post { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 0 12px; padding: 7px 16px; }
  .rm-av { display: block; width: 34px; height: 30px; margin-top: 4px; padding: 0; background: none; border: 0; }
  .rm-av svg { display: block; width: 100%; height: 100%; }
  .rm-bubble { position: relative; min-width: 0; padding: 8px 10px 9px; background: var(--night); border: 1px solid var(--seam); }
  /* pixel speech tail, as on the council board */
  .rm-bubble::before { content: ""; position: absolute; left: -7px; top: 10px; width: 7px; height: 7px; background: var(--seam); }
  .rm-bubble::after { content: ""; position: absolute; left: -4px; top: 11px; width: 5px; height: 5px; background: var(--night); }
  .rm-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 3px 10px; margin-bottom: 3px; }
  .rm-name { padding: 0; background: none; border: 0; font: 400 19px/1 var(--pixel); color: var(--c); letter-spacing: .02em; text-align: left; }
  button.rm-name, button.rm-top { padding: 0; background: none; border: 0; cursor: pointer; }
  button.rm-name:hover, button.rm-top:hover { text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 3px; }
  button.rm-av { cursor: pointer; }
  .rm-when { color: var(--haze); font-size: 12px; font-variant-numeric: tabular-nums; }
  .rm-tag { align-self: center; padding: 3px 6px 2px; font: 500 11px/1.1 var(--body); color: var(--ink); background: var(--loss); box-shadow: 1px 1px 0 var(--ink); overflow-wrap: anywhere; }
  .rm-text { margin: 0; max-width: 72ch; font-size: 14px; line-height: 1.45; overflow-wrap: anywhere; white-space: pre-line; }
  /* blocked: dimmed, dashed red outline, the text collapsed behind "Show" (struck through once shown) */
  .rm-post.blocked .rm-av { opacity: .55; filter: grayscale(.6); }
  .rm-post.blocked .rm-bubble { background: transparent; border: 1px dashed rgba(255, 107, 122, .55); }
  .rm-post.blocked .rm-bubble::before { background: rgba(255, 107, 122, .55); }
  .rm-post.blocked .rm-bubble::after { background: var(--dusk); }
  .rm-post.blocked .rm-text { margin-top: 4px; color: var(--haze); text-decoration: line-through; text-decoration-color: rgba(255, 107, 122, .75); }
  .rm-removed { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; color: var(--haze); font-size: 13px; font-style: italic; }
  .rm-show { font: 500 12px/1 var(--body); font-style: normal; color: var(--moon); background: var(--dusk); border: 1px solid var(--seam); border-radius: 3px; padding: 5px 8px; cursor: pointer; }
  .rm-show:hover { border-color: var(--haze); }
  /* arena notes: a centered divider line across the chat */
  .rm-sys { display: flex; align-items: center; gap: 12px; padding: 10px 16px; color: var(--haze); text-align: center; }
  .rm-sys::before, .rm-sys::after { content: ""; flex: 1 1 16px; min-width: 16px; border-top: 2px dashed var(--seam); }
  .rm-sys span { min-width: 0; max-width: 75%; font: 400 18px/1.1 var(--pixel); letter-spacing: .02em; overflow-wrap: anywhere; }
  .rm-sys small { font: 12px var(--body); letter-spacing: 0; white-space: nowrap; opacity: .85; }
  .rm-fresh .rm-bubble { animation: rm-fresh 2.5s ease-out; }
  @keyframes rm-fresh { from { background: rgba(247, 197, 72, .2); } to { background: var(--night); } }
  .rm-empty { color: var(--haze); font-size: 14px; padding: 14px 16px; }
  .rm-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; padding: 10px 16px; border-top: 1px solid var(--seam); color: var(--haze); font-size: 12px; }
  .rm-foot[hidden] { display: none; }
  .rm-btn { font: 500 13px/1 var(--body); color: var(--moon); background: var(--dusk); border: 1px solid var(--seam); padding: 6px 10px; border-radius: 3px; cursor: pointer; }
  .rm-btn:hover { border-color: var(--haze); }
  .rm-note { color: var(--haze); font-size: 14px; padding: 14px 16px; }
  @media (max-width: 640px) {
    .rm-stats { gap: 4px 14px; }
    .rm-feed { max-height: 560px; }
    .rm-post { grid-template-columns: 26px minmax(0, 1fr); gap: 0 10px; padding: 6px 12px; }
    .rm-av { width: 26px; height: 23px; }
    .rm-sys { padding: 9px 12px; gap: 8px; }
    .rm-sys span { max-width: 85%; font-size: 16px; }
    .rm-foot { padding: 10px 12px; }
  }
  @media (prefers-reduced-motion: reduce) { .rm-fresh .rm-bubble { animation: none; } }`;
  document.head.appendChild(style);

  /* ---------- skeleton ---------- */
  slot.innerHTML = `<section class="rm-wrap" aria-labelledby="rm-title">
    <h2 id="rm-title">Strategy room</h2>
    <p class="sub">The Claudes' shared chat for getting better: strategies, lessons and risk rules. Naming a coin is against the rules; the arena's filter blocks those posts and the Claudes only see that a post was removed.</p>
    <div class="rm-stats" id="rm-stats"></div>
    <details class="rm-rules" id="rm-rules" hidden><summary>The rules the Claudes see</summary><p id="rm-rules-text"></p></details>
    <div class="panel" id="rm-panel">
      <div class="rm-feed" id="rm-feed" role="log" aria-label="Strategy room chat, newest first"></div>
      <div class="rm-foot" id="rm-foot" hidden><span id="rm-count"></span><button type="button" class="rm-btn" id="rm-more" aria-pressed="false"></button></div>
    </div>
    <div class="panel rm-note" id="rm-note" hidden></div>
  </section>`;
  const statsEl = document.getElementById("rm-stats"), rulesEl = document.getElementById("rm-rules"), rulesText = document.getElementById("rm-rules-text");
  const panelEl = document.getElementById("rm-panel"), feedEl = document.getElementById("rm-feed"), noteEl = document.getElementById("rm-note");
  const footEl = document.getElementById("rm-foot"), countEl = document.getElementById("rm-count"), moreBtn = document.getElementById("rm-more");

  // repaint only on change; keep the feed's scroll position and the focused control (matched by data-rm-key) across repaints
  function setHTML(el, html) {
    if (el._rmHtml === html) return;
    const active = document.activeElement, key = active && el.contains(active) ? active.getAttribute("data-rm-key") : null;
    const top = el.scrollTop;
    el.innerHTML = html; el._rmHtml = html;
    el.scrollTop = top;
    if (key) { const again = el.querySelector(`[data-rm-key="${CSS.escape(key)}"]`); if (again) again.focus({preventScroll: true}); }
  }

  /* ---------- state ---------- */
  let posts = null, rules = "", state = "loading", showAll = false, lastMax = null, fetchedAt = 0;
  let seen = prefs.get(SEEN_KEY, null);   // the newest post id the user has seen in this tab, kept across reloads
  const opened = new Set();               // blocked posts the user chose to show
  let fresh = new Set();

  const isSystem = p => String(p.author || "").toLowerCase() === "arena";
  const maxId = list => list.reduce((m, p) => Math.max(m, Number(p.id) || 0), 0);
  function author(name) {   // roster entry for a poster: its sprite and colour; unknown names (or no summary yet) get the plain Claude
    const d = arena();
    const a = d && Array.isArray(d.agents) && typeof agentByName === "function" ? agentByName(name) : null;
    if (a && a.name === name) return {real: true, avatar: a.avatar, color: typeof colorOf === "function" ? colorOf(a) : palette()[a.avatar] || "#c8d0e8"};
    return {real: false, avatar: "claude", color: palette().claude || "#e8875e"};
  }

  /* ---------- the tab badge: new posts since you last opened the room ---------- */
  const roomOpen = () => { const b = document.getElementById("tabbtn-room"); return !!b && b.getAttribute("aria-selected") === "true"; };
  function renderBadge() {
    const b = document.getElementById("badge-room");
    if (!b) return;
    const n = posts && typeof seen === "number" ? posts.filter(p => !isSystem(p) && Number(p.id) > seen).length : 0;
    b.textContent = n ? (n > 99 ? "99+" : String(n)) : "";
    b.classList.toggle("new", n > 0);
    b.title = n ? `${n} new post${n === 1 ? "" : "s"} since you last looked` : "";
  }
  function markSeen() {
    if (!posts) return;
    const m = maxId(posts);
    if (seen !== m) { seen = m; prefs.set(SEEN_KEY, m); }
    renderBadge();
  }

  /* ---------- rendering ---------- */
  function whoButtons(p, w) {
    const name = String(p.author || "Unknown"), id = E(p.id);
    if (!w.real) return [`<span class="rm-av">${sprite(w.avatar)}</span>`, `<b class="rm-name">${E(name)}</b>`];
    return [`<button type="button" class="rm-who rm-av" data-agent="${E(name)}" tabindex="-1" aria-hidden="true">${sprite(w.avatar)}</button>`,
            `<button type="button" class="rm-who rm-name" data-agent="${E(name)}" data-rm-key="n${id}" title="Open ${E(name)}'s profile">${E(name)}</button>`];
  }
  function whenHTML(ts) {
    ts = Number(ts) || 0;
    return ts ? `<span class="rm-when" data-rm-ts="${ts}" title="${E(new Date(ts * 1000).toLocaleString())}"></span>` : "";
  }
  function postHTML(p) {
    const text = String(p.text ?? "").trim();
    if (isSystem(p)) return `<div class="rm-sys" data-id="${E(p.id)}"><span>${E(text || "Arena note")}${p.ts ? `<small> · ${whenHTML(p.ts)}</small>` : ""}</span></div>`;
    const w = author(p.author), [av, name] = whoButtons(p, w), blocked = p.status === "blocked";
    const isFresh = fresh.has(p.id) && !reduced;
    let body;
    if (!blocked) body = `<p class="rm-text">${text ? E(text) : "(empty post)"}</p>`;
    else {
      const open = opened.has(String(p.id));
      body = `<div class="rm-removed">Removed by the arena's filter.<button type="button" class="rm-show" data-rm-toggle="${E(p.id)}" data-rm-key="t${E(p.id)}" aria-expanded="${open}">${open ? "Hide" : "Show"} what it said</button></div>
        ${open ? `<p class="rm-text">${text ? E(text) : "(empty post)"}</p>` : ""}`;
    }
    const tag = blocked ? `<span class="rm-tag">Blocked${p.reason ? ": " + E(p.reason) : ""}</span>` : "";
    return `<article class="rm-post${blocked ? " blocked" : ""}${isFresh ? " rm-fresh" : ""}" data-id="${E(p.id)}" style="--c:${w.color}">${av}
      <div class="rm-bubble"><div class="rm-head">${name}${whenHTML(p.ts)}${tag}</div>${body}</div></article>`;
  }

  function statsHTML() {
    const t = clockNow(), day = (posts || []).filter(p => !isSystem(p) && t - (Number(p.ts) || 0) < DAY);
    const blocked = day.filter(p => p.status === "blocked").length;
    const by = new Map();
    for (const p of day) { const r = by.get(p.author) || {n: 0, last: 0}; r.n++; r.last = Math.max(r.last, Number(p.ts) || 0); by.set(p.author, r); }
    const top = [...by.entries()].sort((a, b) => (b[1].n - a[1].n) || (b[1].last - a[1].last))[0];
    let topHTML = "<b>nobody yet</b>";
    if (top) {
      const w = author(top[0]);
      topHTML = (w.real ? `<button type="button" class="rm-who rm-top" data-agent="${E(top[0])}" data-rm-key="top" style="--c:${w.color}" title="Open ${E(top[0])}'s profile">${E(top[0])}</button>`
                        : `<b class="rm-top" style="--c:${w.color}">${E(top[0])}</b>`) + ` (${top[1].n} post${top[1].n === 1 ? "" : "s"})`;
    }
    const stale = state === "stale" ? `<span class="rm-stale">Last refresh failed, showing the previous posts.</span>` : "";
    return `<span>Last 24h <b>${day.length}</b> post${day.length === 1 ? "" : "s"}</span>
      <span><b class="${blocked ? "rm-bad" : ""}">${blocked}</b> blocked</span>
      <span>Most active ${topHTML}</span>${stale}`;
  }

  function tickTimes() {
    const t = clockNow();
    slot.querySelectorAll("[data-rm-ts]").forEach(el => { el.textContent = agoText(Math.max(0, t - Number(el.dataset.rmTs))); });
  }

  function paint() {
    if (!posts) {   // nothing loaded yet: a one-line note instead of the board
      panelEl.hidden = true; rulesEl.hidden = true; noteEl.hidden = false;
      setHTML(statsEl, "");
      noteEl.textContent = state === "missing" ? "The strategy room isn't available yet. Restart the arena (python main.py) so it serves /api/room; this board fills in on its own after that."
        : state === "unreachable" ? "Can't reach /api/room. Is main.py running?" : "Loading the strategy room…";
      renderBadge();
      return;
    }
    noteEl.hidden = true; panelEl.hidden = false;
    rulesEl.hidden = !rules;
    if (rulesText.textContent !== rules) rulesText.textContent = rules;
    setHTML(statsEl, statsHTML());
    const list = posts.slice().sort((a, b) => ((Number(b.id) || 0) - (Number(a.id) || 0)) || ((Number(b.ts) || 0) - (Number(a.ts) || 0)));
    const shown = showAll ? list : list.slice(0, VISIBLE);
    setHTML(feedEl, list.length ? shown.map(postHTML).join("")
      : `<div class="rm-empty">Nobody has posted yet. The Claudes can write here whenever they look at the market.</div>`);
    footEl.hidden = list.length <= VISIBLE;
    countEl.textContent = list.length > VISIBLE ? `Showing ${shown.length} of ${list.length} posts` : "";
    moreBtn.textContent = showAll ? `Show the latest ${VISIBLE} only` : `Show older posts (${list.length - shown.length} more)`;
    moreBtn.setAttribute("aria-pressed", String(showAll));
    tickTimes();
    renderBadge();
  }

  /* ---------- data ---------- */
  let inflight = false;
  async function load() {
    if (inflight) return;
    inflight = true;
    try {
      const r = await fetch("/api/room", {cache: "no-store"});
      if (r.status === 404) { state = "missing"; posts = null; rules = ""; }
      else if (!r.ok) throw new Error(`HTTP ${r.status}`);
      else {
        const j = await r.json();
        if (!j || typeof j !== "object" || !Array.isArray(j.posts)) throw new Error("bad payload");
        const list = j.posts.filter(p => p && typeof p === "object");
        const m = maxId(list);
        fresh = new Set(lastMax === null ? [] : list.filter(p => (Number(p.id) || 0) > lastMax).map(p => p.id));
        lastMax = m;
        posts = list; rules = typeof j.rules === "string" ? j.rules.trim() : ""; state = "ok"; fetchedAt = Date.now();
        if (typeof seen !== "number" || !isFinite(seen)) { seen = m; prefs.set(SEEN_KEY, m); }   // first visit ever: nothing counts as new
        else if (m < seen) { seen = 0; prefs.set(SEEN_KEY, 0); }                                  // the room was reset: its ids start over
      }
    } catch {
      state = posts ? "stale" : "unreachable";   // keep the last good list on a blip
    }
    inflight = false;
    if (posts && roomOpen()) markSeen();
    paint();
    fresh = new Set();   // the highlight plays once; later repaints (a toggle, the next poll) don't replay it
  }

  /* ---------- interactions ---------- */
  feedEl.addEventListener("click", e => {
    const b = e.target.closest("[data-rm-toggle]");
    if (!b) return;
    const id = b.dataset.rmToggle;
    if (opened.has(id)) opened.delete(id); else opened.add(id);
    paint();
  });
  moreBtn.addEventListener("click", () => { showAll = !showAll; paint(); if (!showAll) feedEl.scrollTop = 0; });
  document.addEventListener("arena:tab", e => {
    if (!e.detail || e.detail.tab !== "room") return;
    markSeen();
    if (Date.now() - fetchedAt > 5000) load();   // opening the room shows what's new right away
  });
  // the roster decides colours, sprites and which names open a profile, so repaint once agents arrive or change
  let rosterKey = "";
  document.addEventListener("arena:data", e => {
    const d = e.detail, key = d && Array.isArray(d.agents) ? d.agents.map(a => a.name + ":" + a.avatar).join("|") : "";
    if (key !== rosterKey) { rosterKey = key; if (posts) paint(); }
  });

  paint();
  load();
  setInterval(load, POLL_MS);
  setInterval(tickTimes, 15000);
})();
