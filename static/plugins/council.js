/* Council chat plugin: the Claude Council's private message board. Two Sonnet analysts propose, Opus chairs and decides. */
(() => {
  "use strict";
  const slot = document.getElementById("slot-council");
  if (!slot) return;
  const POLL_MS = 10000;        // the board changes once a meeting, so a slow poll is plenty; arena:decision bumps it
  const VISIBLE = 6;            // meetings shown before "show older"; the board scrolls inside either way

  /* ---------- safe access to dashboard globals ---------- */
  const safe = typeof esc === "function" ? esc : s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const usd = (n, d = 0) => (typeof money === "function" ? money(n, d) : "$" + Number(n).toFixed(d));
  const pctText = n => (typeof pct === "function" ? pct(n) : (n >= 0 ? "+" : "") + Number(n).toFixed(1) + "%");
  const clockNow = () => (typeof now === "function" ? now() : Date.now() / 1000);
  const agoText = s => (typeof ago === "function" ? ago(s) : Math.round(s) + "s ago");
  const sprite = key => (typeof spriteSVG === "function" ? spriteSVG(key).replace('class="bob"', "") : "");
  const palette = () => (typeof AVATAR_COLOR === "object" && AVATAR_COLOR) || {};
  const tintOf = key => palette()[key] || "#c8d0e8";
  const arena = () => (typeof data === "object" && data) || null;

  const FAMILIES = ["opus", "sonnet", "haiku", "fable"];
  const DEFAULT_MEMBERS = [
    {name: "Opus 5.5", model: "claude-opus-5-5", role: "chair"},
    {name: "Sonnet 5.5 A", model: "claude-sonnet-5-5", role: "analyst"},
    {name: "Sonnet 5.5 B", model: "claude-sonnet-5-5", role: "analyst"},
  ];
  const ROLE_NOTE = {chair: "Chair: reads the proposals, decides", analyst: "Analyst: proposes trades"};
  const KIND_LABEL = {proposal: "proposal", decision: "decision", error: "call failed"};

  /* ---------- styles ---------- */
  const style = document.createElement("style");
  style.textContent = `
  .cc-wrap { margin-top: 36px; min-width: 0; }
  .cc-members { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 22px; padding: 12px 16px; border-bottom: 1px solid var(--seam); }
  .cc-member { display: flex; align-items: center; gap: 9px; min-width: 0; }
  .cc-member svg { width: 30px; height: 26px; flex: none; }
  .cc-member b { display: block; font: 400 20px/1 var(--pixel); color: var(--c); }
  .cc-member small { display: block; color: var(--haze); font-size: 11px; margin-top: 2px; }
  .cc-member.chair small { color: var(--gold); }
  .cc-account { margin-left: auto; display: flex; align-items: center; gap: 9px; min-width: 0; }
  .cc-account svg { width: 34px; height: 30px; flex: none; }
  .cc-account b { display: block; font: 400 20px/1 var(--pixel); color: var(--c); }
  .cc-account small { display: block; color: var(--haze); font-size: 11px; margin-top: 2px; font-variant-numeric: tabular-nums; }
  .cc-account small .pos { color: var(--profit); } .cc-account small .neg { color: var(--loss); }

  .cc-board { max-height: 560px; overflow-y: auto; scrollbar-color: var(--seam) transparent; }
  .cc-meeting { padding: 12px 16px 14px; border-bottom: 1px solid var(--seam); }
  .cc-meeting:last-child { border-bottom: 0; }
  .cc-mhead { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 2px 12px; }
  .cc-mhead b { font: 400 21px/1 var(--pixel); color: var(--moon); letter-spacing: .02em; }
  .cc-mhead .cc-when { color: var(--haze); font-size: 12px; font-variant-numeric: tabular-nums; }
  .cc-msg { display: grid; grid-template-columns: 30px minmax(0, 1fr); gap: 0 12px; margin-top: 10px; }
  .cc-msg .cc-av { width: 30px; height: 26px; margin-top: 4px; }
  .cc-bubble { position: relative; min-width: 0; background: var(--night); border: 1px solid var(--seam); padding: 8px 10px 9px; }
  /* pixel speech tail: a seam-coloured tab with the bubble's fill punched into it */
  .cc-bubble::before { content: ""; position: absolute; left: -7px; top: 10px; width: 7px; height: 7px; background: var(--seam); }
  .cc-bubble::after { content: ""; position: absolute; left: -4px; top: 11px; width: 5px; height: 5px; background: var(--night); }
  .cc-who { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 8px; margin-bottom: 3px; }
  .cc-who b { font: 400 18px/1 var(--pixel); color: var(--c); }
  .cc-who .cc-kind { font-size: 11px; line-height: 1.2; color: var(--haze); border: 1px solid var(--seam); padding: 1px 5px; }
  .cc-who .cc-kind.decision { color: var(--gold); border-color: var(--gold); }
  .cc-who .cc-kind.error { color: var(--loss); border-color: var(--loss); }
  .cc-text { margin: 0; font-size: 14px; line-height: 1.45; max-width: 72ch; overflow-wrap: anywhere; white-space: pre-line; }
  .cc-text.quiet { color: var(--haze); }
  .cc-msg.chair .cc-bubble { background: #272052; border-color: var(--gold); box-shadow: inset 3px 0 0 var(--gold); }
  .cc-msg.chair .cc-bubble::before { background: var(--gold); }
  .cc-msg.chair .cc-bubble::after { background: #272052; }
  .cc-msg.error .cc-bubble { border-color: var(--loss); box-shadow: none; }
  .cc-msg.error .cc-bubble::before { background: var(--loss); }
  .cc-msg.error .cc-text { color: #ffb3bd; }
  .cc-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .cc-chip { font-size: 12px; line-height: 1; padding: 5px 7px; border: 1px solid var(--seam); background: var(--dusk); color: var(--moon);
             font-variant-numeric: tabular-nums; white-space: nowrap; }
  .cc-chip b { font-weight: 600; }
  .cc-chip.buy { border-color: var(--profit); } .cc-chip.buy b { color: var(--profit); }
  .cc-chip.sell { border-color: var(--gold); } .cc-chip.sell b { color: var(--gold); }
  .cc-chip.exits { border-color: var(--haze); } .cc-chip.exits b { color: var(--haze); font-weight: 500; }
  .cc-chip.none { color: var(--haze); }
  .cc-wait { display: block; margin: 10px 0 0 42px; color: var(--haze); font-size: 12px; }
  .cc-wait::after { content: "..."; display: inline-block; width: 1.4em; text-align: left; overflow: hidden; vertical-align: bottom; animation: cc-dots 1.2s steps(4) infinite; }
  @keyframes cc-dots { 0% { width: 0; } 100% { width: 1.4em; } }
  .cc-fresh .cc-bubble { animation: cc-fresh 2.5s ease-out; }
  @keyframes cc-fresh { from { background: rgba(247, 197, 72, .22); } to { background: var(--night); } }
  .cc-msg.chair.cc-fresh .cc-bubble { animation-name: cc-fresh-chair; }
  @keyframes cc-fresh-chair { from { background: rgba(247, 197, 72, .3); } to { background: #272052; } }
  .cc-empty { color: var(--haze); font-size: 14px; padding: 18px 16px; }
  .cc-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 12px; padding: 10px 16px; border-top: 1px solid var(--seam);
             color: var(--haze); font-size: 12px; }
  .cc-foot[hidden] { display: none; }
  .cc-btn { font: 500 13px/1 var(--body); color: var(--moon); background: var(--dusk); border: 1px solid var(--seam); padding: 6px 10px; border-radius: 3px; cursor: pointer; }
  .cc-btn:hover { border-color: var(--haze); }
  .cc-stale { color: var(--gold); }
  @media (max-width: 640px) {
    .cc-members { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 10px 12px; padding: 10px 12px; }
    .cc-account { margin-left: 0; grid-column: 1 / -1; }
    .cc-meeting { padding: 10px 12px 12px; }
    .cc-msg { grid-template-columns: 26px minmax(0, 1fr); gap: 0 10px; }
    .cc-msg .cc-av { width: 26px; height: 22px; }
    .cc-wait { margin-left: 36px; }
    .cc-board { max-height: 520px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .cc-fresh .cc-bubble, .cc-wait::after { animation: none; }
    .cc-wait::after { width: 1.4em; }
  }
  `;
  document.head.appendChild(style);

  /* ---------- skeleton (built once; the footer button keeps focus across repaints) ---------- */
  slot.innerHTML = `
  <section class="cc-wrap" aria-labelledby="cc-title">
    <h2 id="cc-title">Council chat</h2>
    <p class="sub">Two Sonnet analysts propose, Opus chairs and decides. One shared account.</p>
    <div class="panel">
      <div class="cc-members" id="cc-members"></div>
      <div class="cc-board" id="cc-board" role="log" aria-label="Council message board"></div>
      <div class="cc-foot" id="cc-foot" hidden><span id="cc-count"></span><button type="button" class="cc-btn" id="cc-toggle" aria-pressed="false"></button></div>
    </div>
  </section>`;
  const membersEl = document.getElementById("cc-members"), boardEl = document.getElementById("cc-board");
  const footEl = document.getElementById("cc-foot"), countEl = document.getElementById("cc-count"), toggleBtn = document.getElementById("cc-toggle");

  let council = null, status = "loading", showOlder = false, first = true;
  const seen = new Set();

  /* ---------- data ---------- */
  let gone = false;
  function hideCouncil() {   // no council in this arena (ARENA_COUNCIL=off): drop its tab and stop asking
    gone = true;
    const b = document.getElementById("tabbtn-council");
    if (b) b.hidden = true;
    try { const i = TABS.indexOf("council"); if (i >= 0) TABS.splice(i, 1); } catch {}
    try { if (activeTab === "council") showTab("overview"); } catch {}
  }

  async function load() {
    if (gone) return;
    try {
      const r = await fetch("/api/council", {cache: "no-store"});
      if (r.status === 404) { council = null; status = "missing"; hideCouncil(); }
      else if (!r.ok) throw new Error(`HTTP ${r.status}`);
      else { council = await r.json(); status = "ok"; }
    } catch {
      status = council ? "stale" : "unreachable";   // keep the last good board on a blip
    }
    paint();
  }

  /* ---------- helpers ---------- */
  function setHTML(el, html) {   // the board scrolls, so only touch the DOM when something changed, and keep the scroll position
    if (el._html === html) return;
    const top = el.scrollTop;
    el.innerHTML = html; el._html = html;
    el.scrollTop = top;
  }
  const avatarFor = m => FAMILIES.find(f => String(m.model || m.name || "").toLowerCase().includes(f)) || (m.role === "chair" ? "opus" : "claude");
  function decorate(members) {   // colour and avatar per member; the second Sonnet wears the pale tint so the two analysts tell apart
    let analysts = 0;
    return members.map(m => {
      const avatar = avatarFor(m);
      let colour = tintOf(avatar);
      if (m.role !== "chair" && analysts++ === 1 && avatar === "sonnet") colour = tintOf("sonnet-twin");
      return {...m, avatar, colour};
    });
  }
  function memberFor(msg, members) {
    return members.find(m => m.name === msg.author) || members.find(m => m.role === (msg.role || "analyst"))
      || {name: msg.author, role: msg.role || "analyst", avatar: msg.role === "chair" ? "opus" : "sonnet", colour: tintOf(msg.role === "chair" ? "opus" : "sonnet")};
  }
  function councilAgent() {
    const d = arena();
    if (!d || !Array.isArray(d.agents)) return null;
    const name = council && council.name;
    return d.agents.find(a => a.avatar === "council") || (name ? d.agents.find(a => a.name === name) : null) || null;
  }
  function groupMeetings(msgs) {
    const byMeeting = new Map();
    for (const m of msgs) { const k = Number(m.meeting) || 0; if (!byMeeting.has(k)) byMeeting.set(k, []); byMeeting.get(k).push(m); }
    return [...byMeeting.entries()].map(([meeting, list]) => {
      list.sort((a, b) => (a.ts - b.ts) || (a.id - b.id));
      return {meeting, list, last: Math.max(...list.map(m => Number(m.ts) || 0))};
    }).sort((a, b) => (b.last - a.last) || (b.meeting - a.meeting));
  }

  /* ---------- rendering ---------- */
  function chip(o) {
    const sym = safe(o.symbol || "?"), why = o.reason ? ` title="${safe(o.reason)}"` : "";
    if (o.action === "sell") {
      const f = Number(o.fraction ?? 1);
      return `<span class="cc-chip sell"${why}><b>Sell</b> ${f >= .999 || !isFinite(f) ? "all" : Math.round(f * 100) + "%"} ${sym}</span>`;
    }
    if (o.action === "exits") return `<span class="cc-chip exits"${why}><b>Exits</b> on ${sym}</span>`;
    const amt = Number(o.usd);
    return `<span class="cc-chip buy"${why}><b>Buy</b> ${sym}${isFinite(amt) && amt > 0 ? " " + usd(amt) : ""}</span>`;
  }

  function msgHTML(m, members) {
    const who = memberFor(m, members), role = m.role || who.role || "analyst";
    const kind = KIND_LABEL[m.kind] ? m.kind : (role === "chair" ? "decision" : "proposal");
    const fresh = !first && !seen.has(m.id);
    const cls = ["cc-msg", role === "chair" ? "chair" : "analyst", kind === "error" ? "error" : "", fresh ? "cc-fresh" : ""].filter(Boolean).join(" ");
    const orders = Array.isArray(m.orders) ? m.orders : [];
    const chips = orders.map(chip).join("") + (kind === "decision" && !orders.length ? `<span class="cc-chip none">No trades this meeting</span>` : "");
    const text = String(m.text || "").trim();
    return `<div class="${cls}" data-id="${safe(m.id)}" style="--c:${who.colour}"><div class="cc-av">${sprite(who.avatar)}</div>
      <div class="cc-bubble">
        <div class="cc-who"><b>${safe(m.author || who.name)}</b><span class="cc-kind ${kind}">${KIND_LABEL[kind]}</span></div>
        <p class="cc-text${text ? "" : " quiet"}">${text ? safe(text) : kind === "error" ? "The call failed with no message." : "No comment."}</p>
        ${chips ? `<div class="cc-chips">${chips}</div>` : ""}
      </div></div>`;
  }

  function meetingHTML(g, members) {
    const decided = g.list.some(m => (m.role === "chair" || m.kind === "decision") && m.kind !== "proposal");
    return `<section class="cc-meeting" data-meeting="${safe(g.meeting)}" aria-label="Meeting ${safe(g.meeting)}">
      <div class="cc-mhead"><b>Meeting ${safe(g.meeting)}</b><span class="cc-when" data-ts="${g.last}"></span></div>
      ${g.list.map(m => msgHTML(m, members)).join("")}
      ${decided ? "" : `<span class="cc-wait">Waiting for the chair's decision</span>`}
    </section>`;
  }

  function membersHTML(members) {
    const agent = councilAgent();
    const equity = agent ? ` · ${usd(agent.equity)} <span class="${agent.pnl_pct >= 0 ? "pos" : "neg"}">${pctText(agent.pnl_pct)}</span>` : "";
    return members.map(m => `<div class="cc-member ${m.role === "chair" ? "chair" : ""}" style="--c:${m.colour}">${sprite(m.avatar)}
        <div><b>${safe(m.name)}</b><small>${ROLE_NOTE[m.role] || safe(m.role || "")}</small></div></div>`).join("")
      + `<div class="cc-account" style="--c:${tintOf("council")}">${sprite("council")}
        <div><b>${safe((council && council.name) || "Claude Council")}</b><small id="cc-equity">One shared account${equity}</small></div></div>`;
  }

  function emptyText() {
    if (status === "loading") return "Loading the council's board…";
    if (status === "unreachable") return "Can't reach /api/council. Is main.py running?";
    if (status === "missing") return "The council hasn't met yet. Restart the arena to start the council: its board shows here once the three Claudes hold their first meeting.";
    return "The council hasn't met yet. The analysts post their first proposals on the first tick.";
  }

  function tickTimes() {
    const t = clockNow();
    boardEl.querySelectorAll(".cc-when[data-ts]").forEach(el => { el.textContent = agoText(t - Number(el.dataset.ts)); });
  }

  function paint() {
    const members = decorate(council && Array.isArray(council.members) && council.members.length ? council.members : DEFAULT_MEMBERS);
    setHTML(membersEl, membersHTML(members));
    const msgs = council && Array.isArray(council.messages) ? council.messages : [];
    const meetings = groupMeetings(msgs), shown = showOlder ? meetings : meetings.slice(0, VISIBLE);
    setHTML(boardEl, meetings.length ? shown.map(g => meetingHTML(g, members)).join("") : `<div class="cc-empty">${emptyText()}</div>`);
    tickTimes();
    for (const m of msgs) seen.add(m.id);
    first = false;

    const more = meetings.length - shown.length;
    footEl.hidden = meetings.length <= VISIBLE && status !== "stale";
    countEl.innerHTML = [
      meetings.length > VISIBLE ? `Showing ${shown.length} of ${meetings.length} meetings` : "",
      status === "stale" ? `<span class="cc-stale">Last refresh failed, showing the previous board.</span>` : "",
    ].filter(Boolean).join(" · ");
    toggleBtn.hidden = meetings.length <= VISIBLE;
    toggleBtn.textContent = showOlder ? `Show the latest ${VISIBLE} only` : `Show older meetings (${more} more)`;
    toggleBtn.setAttribute("aria-pressed", String(showOlder));
  }

  /* ---------- interaction and loop ---------- */
  toggleBtn.addEventListener("click", () => { showOlder = !showOlder; paint(); if (!showOlder) boardEl.scrollTop = 0; });
  paint();
  load();
  setInterval(load, POLL_MS);
  setInterval(tickTimes, 15000);
  let bump;
  document.addEventListener("arena:decision", () => { clearTimeout(bump); bump = setTimeout(load, 400); });
  document.addEventListener("arena:data", () => {   // the equity line follows the summary without redrawing the members row
    const el = document.getElementById("cc-equity"), agent = councilAgent();
    if (!el || !agent) return;
    el.innerHTML = `One shared account · ${usd(agent.equity)} <span class="${agent.pnl_pct >= 0 ? "pos" : "neg"}">${pctText(agent.pnl_pct)}</span>`;
    membersEl._html = null;   // the next full paint re-syncs this line instead of skipping as "unchanged"
  });
})();
