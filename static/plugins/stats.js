/* Head to head plugin: the three-team standing (Team Claude, Team Bots, Team Copy), achievement badges, per-agent sparklines. */
(() => {
  "use strict";
  const slot = document.getElementById("slot-after-standings");
  if (!slot) return;

  /* ---------- styles ---------- */
  const css = `
  .st-wrap { margin-top: 36px; min-width: 0; }   /* h2 and .sub inherit the dashboard's heading style */
  .st-versus { padding: 14px 16px 16px; }
  .st-stand { display: grid; gap: 10px; }
  .st-row { display: grid; grid-template-columns: minmax(0, 230px) minmax(0, 1fr) 84px; gap: 6px 14px; align-items: center; }
  .st-row .st-place { font: 400 18px/1 var(--pixel); color: var(--haze); }
  .st-row:first-child .st-place { color: var(--gold); }
  .st-team { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .st-team .st-tsprites { display: flex; flex-wrap: wrap; gap: 2px; width: 92px; max-width: 100%; flex: none; }
  .st-team svg { width: 20px; height: 18px; flex: none; }
  .st-team .st-tname { font: 400 20px/1 var(--pixel); white-space: nowrap; display: flex; align-items: center; gap: 6px; }
  .st-team .st-tavg { font-size: 12px; color: var(--haze); font-variant-numeric: tabular-nums; white-space: nowrap; }
  .st-row .st-tot { font: 400 22px/1 var(--pixel); font-variant-numeric: tabular-nums; text-align: right; }
  .st-break { display: flex; justify-content: space-between; gap: 8px 16px; flex-wrap: wrap; margin-top: 8px; font-size: 12px; color: var(--haze); font-variant-numeric: tabular-nums; }
  .st-break b { font-weight: 500; }
  .st-break .st-bl { display: inline-flex; align-items: center; gap: 5px; }
  .st-break svg { width: 16px; height: 14px; }

  .st-pers { margin-top: 16px; padding: 12px 14px; }
  .st-pers h3 { margin: 0; font: 400 22px/1 var(--pixel); color: var(--moon); }
  .st-pers .sub { margin: 2px 0 8px; }
  .st-pers table { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
  .st-pers th { text-align: right; font-weight: 500; font-size: 11px; color: var(--haze); padding: 2px 6px; border-bottom: 1px solid var(--seam); }
  .st-pers th:first-child, .st-pers td:first-child { text-align: left; }
  .st-pers td { text-align: right; padding: 5px 6px; border-bottom: 1px solid rgba(52, 44, 99, .5); white-space: nowrap; }
  .st-pers tr.base td { background: rgba(255,255,255,.03); }
  .st-pers tr:last-child td { border-bottom: 0; }
  .st-pers .st-pname { display: inline-flex; align-items: center; gap: 6px; font: 400 17px/1 var(--pixel); }
  .st-pers .st-pname svg { width: 18px; height: 16px; }
  .st-pers .st-ptag { font: 400 10px/1 var(--body); color: var(--haze); border: 1px solid var(--seam); padding: 2px 4px; }
  .st-pers .st-pverdict { margin-top: 8px; font-size: 12px; color: var(--haze); }
  /* one bar per team: the start line sits in the middle, profit fills to the right, loss to the left */
  .st-bar { position: relative; height: 22px; background: var(--night); border: 2px solid var(--moon); overflow: hidden; min-width: 0; }
  .st-bar .st-fill { position: absolute; top: 0; bottom: 0; transition: width .7s steps(7), left .7s steps(7); }
  .st-bar .st-fill.claude { background: repeating-linear-gradient(90deg, #f7c548 0 10px, #62c6ff 10px 20px); }
  .st-bar .st-fill.bots { background: repeating-linear-gradient(90deg, #c8d0e8 0 7px, #ff82b8 7px 14px, #b488ff 14px 21px); }
  .st-bar .st-fill.copy { background: repeating-linear-gradient(90deg, #ff5fd2 0 7px, #3d8bff 7px 14px, #ffa132 14px 21px); }
  .st-bar .st-fill.neg { background: repeating-linear-gradient(90deg, var(--loss) 0 10px, #b04050 10px 20px); }
  .st-bar .st-mid { position: absolute; left: calc(50% - 1px); top: -2px; bottom: -2px; width: 2px; background: var(--moon); opacity: .5; }
  .st-bar .st-shine { position: absolute; left: 0; right: 0; top: 2px; height: 4px; background: rgba(255,255,255,.22); pointer-events: none; }
  .st-verdict { margin-top: 12px; text-align: center; font: 400 22px/1.1 var(--pixel); color: var(--gold); }
  .st-verdict.bots { color: #c8d0e8; } .st-verdict.copy { color: #ff5fd2; } .st-verdict.even { color: var(--haze); }

  .st-badges { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin-top: 16px; }
  .st-badge { padding: 10px 10px 10px; display: grid; grid-template-columns: 26px minmax(0, 1fr); gap: 2px 8px; align-items: center;
              box-shadow: inset 0 0 0 1px var(--night), inset 0 0 0 2px var(--seam); position: relative; }
  .st-badge::before { content: ""; position: absolute; top: -1px; left: -1px; width: 6px; height: 6px; background: var(--gold); }
  .st-badge .st-btitle { grid-column: 1 / -1; font-size: 11px; color: var(--haze); letter-spacing: .02em; }
  .st-badge svg { width: 24px; height: 21px; }
  .st-badge .st-bname { font: 400 18px/1 var(--pixel); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .st-badge .st-bstat { grid-column: 1 / -1; font-size: 12px; font-variant-numeric: tabular-nums; color: var(--moon); }
  .st-badge.none { opacity: .55; } .st-badge.none::before { background: var(--seam); }
  .st-badge.none .st-bname { color: var(--haze); font: 400 14px/1.3 var(--body); }

  .st-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin-top: 16px; }
  .st-cards .st-cteam { grid-column: 1 / -1; font: 400 18px/1 var(--pixel); color: var(--haze); margin: 6px 0 -2px; display: flex; align-items: center; gap: 8px; }
  .st-cards .st-cteam::after { content: ""; flex: 1; height: 1px; background: var(--seam); }
  .st-cards .st-cteam:first-child { margin-top: 0; }
  .st-card { padding: 8px 10px 6px; min-width: 0; box-shadow: inset 3px 0 0 var(--c, var(--seam)); }
  .st-card .st-chead { display: flex; align-items: center; gap: 6px; }
  .st-card .st-chead svg { width: 18px; height: 16px; flex: none; }
  .st-card .st-cname { font: 400 16px/1 var(--pixel); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .st-card canvas { display: block; width: 100%; height: 44px; margin-top: 5px; image-rendering: pixelated; }
  .st-card .st-cfoot { display: flex; justify-content: space-between; align-items: baseline; gap: 6px; margin-top: 4px; font-variant-numeric: tabular-nums; min-width: 0; }
  .st-card .st-ceq { font: 400 19px/1 var(--pixel); }
  .st-card .st-cpnl { font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .st-pos { color: var(--profit); } .st-neg { color: var(--loss); }
  @media (max-width: 640px) {
    .st-row { grid-template-columns: minmax(0, 1fr) 76px; }
    .st-row .st-tot { grid-column: 2; grid-row: 1; }
    .st-row .st-bar { grid-column: 1 / -1; grid-row: 2; height: 16px; }
    .st-team .st-tsprites { width: 72px; } .st-team svg { width: 16px; height: 14px; }
    .st-row .st-tot { font-size: 19px; }
  }
  @media (max-width: 480px) {
    .st-badges { grid-template-columns: repeat(2, minmax(0, 1fr)); } .st-cards { grid-template-columns: 1fr 1fr; }
    .st-pers { overflow-x: auto; }
  }
  @media (prefers-reduced-motion: reduce) { .st-bar .st-fill { transition: none; } }
  `;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  /* ---------- skeleton ---------- */
  slot.innerHTML = `<section class="st-wrap block">
    <h2>Head to head</h2>
    <p class="sub">Team Claude vs Team Bots vs Team Copy, bragging rights, a personality check, and every agent's equity path.</p>
    <div class="panel st-versus" id="st-versus"></div>
    <div class="st-badges" id="st-badges"></div>
    <div class="panel st-pers" id="st-pers" hidden></div>
    <div class="st-cards" id="st-cards"></div>
  </section>`;
  const versusEl = document.getElementById("st-versus");
  const badgesEl = document.getElementById("st-badges");
  const persEl = document.getElementById("st-pers");
  const cardsEl = document.getElementById("st-cards");
  const byOrder = xs => xs.slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0));  // stage order
  const setHTML = (el, html) => { if (el._stHtml !== html) { el.innerHTML = html; el._stHtml = html; } };
  const cls = n => n >= 0 ? "st-pos" : "st-neg";
  const col = a => (typeof colorOf === "function" ? colorOf(a) : "#c8d0e8");
  const sprite = a => (typeof spriteSVG === "function" ? spriteSVG(a.avatar) : "");
  /* teams: the dashboard's helpers when present, else the same fallback (team key, or llm → claude / bot → bots) */
  const ORDER = typeof TEAM_ORDER !== "undefined" ? TEAM_ORDER : ["claude", "bots", "copy"];
  const NAMES = typeof TEAM_INFO !== "undefined" ? TEAM_INFO : { claude: "Team Claude", bots: "Team Bots", copy: "Team Copy" };
  const teamKey = a => (typeof teamOf === "function" ? teamOf(a) : (NAMES[a.team] ? a.team : a.kind === "llm" ? "claude" : "bots"));
  const tName = k => NAMES[k] || ("Team " + k);
  const SHORT = { claude: ["Claude", "Claudes"], bots: ["bot", "bots"], copy: ["copier", "copiers"] };
  const teamsOf = agents => ORDER.map(key => ({ key, list: byOrder(agents.filter(a => teamKey(a) === key)) })).filter(t => t.list.length);

  /* ---------- leader time tracking (per browser session) ---------- */
  const LKEY = "st-leader-time";
  let leaderTime = {};
  try { leaderTime = JSON.parse(sessionStorage.getItem(LKEY) || "{}") || {}; } catch { leaderTime = {}; }
  let lastLeader = null, lastStamp = Date.now();
  function trackLeader(d) {
    const t = Date.now();
    if (lastLeader) leaderTime[lastLeader] = (leaderTime[lastLeader] || 0) + (t - lastStamp) / 1000;
    lastLeader = d.agents[0] ? d.agents[0].name : null;
    lastStamp = t;
    try { sessionStorage.setItem(LKEY, JSON.stringify(leaderTime)); } catch {}
  }

  /* ---------- the standing: one bar per team, best average first ---------- */
  function renderVersus(d) {
    const avg = xs => xs.length ? xs.reduce((s, a) => s + a.pnl_pct, 0) / xs.length : 0;
    const start = d.start_cash || 0;
    const teams = teamsOf(d.agents).map(t => ({ ...t, avg: avg(t.list), total: t.list.reduce((s, a) => s + a.equity - start, 0) }))
      .sort((a, b) => b.avg - a.avg);
    if (!teams.length) return;
    // every 1% of average P&L is 6% of the bar, measured from the start line in the middle
    const geom = t => { const w = Math.min(50, Math.abs(t.avg) * 6); return t.avg >= 0 ? [50, w] : [50 - w, w]; };
    const diff = teams.length > 1 ? teams[0].avg - teams[1].avg : 0;
    const verdict = teams.length < 2 ? [teams[0].key, `${tName(teams[0].key)} on its own`]
      : Math.abs(diff) < 0.05 ? ["even", `Dead even: ${tName(teams[0].key)} and ${tName(teams[1].key)}`]
      : [teams[0].key, `${tName(teams[0].key)} ahead of ${tName(teams[1].key)} by ${Math.abs(diff).toFixed(1)}%`];
    const teamCell = (t, i) => `<span class="st-place">${ordinal(i + 1)}</span>
          <div class="st-tsprites">${t.list.map(a => `<span style="color:${col(a)}" title="${esc(a.name)}">${sprite(a)}</span>`).join("")}</div>
          <div><div class="st-tname">${tName(t.key)}</div><div class="st-tavg">${t.list.length} agent${t.list.length === 1 ? "" : "s"}, avg <span class="${cls(t.avg)}">${pct(t.avg)}</span></div></div>`;
    const row = (t, i) => {
      const [left, width] = geom(t);
      return `<div class="st-row" data-team="${t.key}">
        <div class="st-team">${teamCell(t, i)}</div>
        <div class="st-bar" role="img" aria-label="${tName(t.key)}: average ${pct(t.avg)}, ${signed(t.total, 0)} total">
          <div class="st-fill ${t.key}${t.avg < -0.5 ? " neg" : ""}" style="left:${left.toFixed(1)}%;width:${width.toFixed(1)}%"></div>
          <div class="st-mid"></div><div class="st-shine"></div></div>
        <div class="st-tot ${cls(t.total)}">${signed(t.total, 0)}</div></div>`;
    };
    // breakdown: the best agent of each team, and how many of each sit in the top half of the board
    const top = xs => xs.length ? xs.reduce((m, a) => a.pnl_pct > m.pnl_pct ? a : m) : null;
    const half = Math.ceil(d.agents.length / 2), topHalf = d.agents.slice(0, half);
    const who = a => a ? `<span class="st-bl" style="color:${col(a)}">${sprite(a)}<b>${esc(a.name)}</b> <span class="${cls(a.pnl_pct)}">${pct(a.pnl_pct)}</span></span>` : "—";
    const label = (k, n) => (SHORT[k] || [k, k])[n === 1 ? 0 : 1];
    const counts = ORDER.filter(k => teams.some(t => t.key === k)).map(k => { const n = topHalf.filter(a => teamKey(a) === k).length; return `<b>${n}</b> ${label(k, n)}`; }).join(", ");
    const breakdown = ORDER.filter(k => teams.some(t => t.key === k)).map(k => `<span>Best ${label(k, 1)} ${who(top(teams.find(t => t.key === k).list))}</span>`).join("")
      + `<span>Top ${half}: ${counts}</span>`;
    const key = teams.map(t => t.key).join("|");
    if (versusEl._stBuilt === key) {  // same order: move the bars in place so the stepped transition plays
      for (const t of teams) {
        const [left, width] = geom(t), rowEl = versusEl.querySelector(`.st-row[data-team="${t.key}"]`);
        if (!rowEl) continue;
        const fill = rowEl.querySelector(".st-fill");
        fill.style.left = left.toFixed(1) + "%"; fill.style.width = width.toFixed(1) + "%";
        fill.className = `st-fill ${t.key}${t.avg < -0.5 ? " neg" : ""}`;
        rowEl.querySelector(".st-bar").setAttribute("aria-label", `${tName(t.key)}: average ${pct(t.avg)}, ${signed(t.total, 0)} total`);
        setHTML(rowEl.querySelector(".st-team"), teamCell(t, teams.indexOf(t)));
        const tot = rowEl.querySelector(".st-tot"); tot.textContent = signed(t.total, 0); tot.className = "st-tot " + cls(t.total);
      }
      const v = versusEl.querySelector(".st-verdict"); v.className = "st-verdict " + verdict[0]; v.textContent = verdict[1];
      setHTML(versusEl.querySelector(".st-break"), breakdown);
    } else {
      versusEl.innerHTML = `<div class="st-stand">${teams.map(row).join("")}</div>
        <div class="st-verdict ${verdict[0]}">${verdict[1]}</div>
        <div class="st-break">${breakdown}</div>`;
      versusEl._stBuilt = key;
    }
  }

  /* ---------- personality check: same model, different prompts ---------- */
  function renderPersonality(d) {
    const llm = d.agents.filter(a => a.kind === "llm" && a.model);
    const groups = new Map();
    for (const a of llm) { const k = a.model; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(a); }
    // twin and triplet are noise checks and the copycat has a different brief: they're listed, but only style personas decide the verdict
    const isStyle = a => a.persona && !["twin", "triplet", "copycat"].includes(String(a.persona));
    const sets = [...groups.values()].filter(xs => xs.length > 1 && xs.some(isStyle));
    if (!sets.length) { if (!persEl.hidden) { persEl.hidden = true; persEl._stHtml = ""; } return; }
    persEl.hidden = false;
    const html = sets.map(xs => {
      const rows = xs.slice().sort((a, b) => (a.persona ? 1 : 0) - (b.persona ? 1 : 0) || (a.order ?? 0) - (b.order ?? 0));
      const base = rows.find(a => !a.persona) || rows[0];
      const lead = rows.filter(a => a === base || isStyle(a)).reduce((m, a) => a.pnl_pct > m.pnl_pct ? a : m);
      const verdict = lead === base
        ? `${esc(base.name)} without a persona is ahead so far. The prompts cost money.`
        : `${esc(lead.name)} (${esc(lead.persona)}) is ahead of plain ${esc(base.name)} by ${(lead.pnl_pct - base.pnl_pct).toFixed(1)}%. The prompt matters.`;
      return `<h3>Personality check</h3><p class="sub">${esc(base.model)} · one model, ${rows.length} prompts</p>
        <table><thead><tr><th>Agent</th><th>P&amp;L</th><th>Equity</th><th>Trades</th><th>Win rate</th><th>Max DD</th></tr></thead><tbody>
        ${rows.map(a => `<tr class="${a.persona ? "" : "base"}"><td><span class="st-pname" style="color:${col(a)}">${sprite(a)}${esc(a.name)}</span>
            <span class="st-ptag">${a.persona ? esc(a.persona) : "base"}</span>${a.mode && a.mode !== "normal" ? ` <span class="st-ptag">${esc(a.mode)}</span>` : ""}</td>
          <td class="${cls(a.pnl_pct)}">${pct(a.pnl_pct)}</td><td>${money(a.equity, 0)}</td><td>${a.trades}</td>
          <td>${a.win_rate == null ? "—" : Math.round(a.win_rate) + "%"}${a.closed ? ` <span class="sub">of ${a.closed}</span>` : ""}</td>
          <td>${a.max_dd != null ? "-" + Number(a.max_dd).toFixed(1) + "%" : "—"}</td></tr>`).join("")}
        </tbody></table><div class="st-pverdict">${verdict}</div>`;
    }).join("");
    setHTML(persEl, html);
  }

  /* ---------- badges ---------- */
  function renderBadges(d) {
    const byName = n => d.agents.find(a => a.name === n);
    const sells = (d.trades || []).filter(t => t.side === "sell" && typeof t.pnl === "number");
    const best = (xs, score) => { let w = null, ws = -Infinity; for (const x of xs) { const s = score(x); if (s != null && s > ws) { ws = s; w = x; } } return w; };
    const out = [];
    const win = best(sells.filter(t => t.pnl > 0), t => t.pnl);
    out.push(["Biggest win", win && byName(win.agent), win && `${esc(win.symbol)} ${signed(win.pnl)}`]);
    const loss = best(sells.filter(t => t.pnl < 0), t => -t.pnl);
    out.push(["Worst loss", loss && byName(loss.agent), loss && `${esc(loss.symbol)} ${signed(loss.pnl)}`]);
    const active = best(d.agents.filter(a => a.trades > 0), a => a.trades);
    out.push(["Most active", active, active && `${active.trades} trades`]);
    const wr = best(d.agents.filter(a => a.closed >= 3 && a.win_rate != null), a => a.win_rate);
    out.push(["Best win rate", wr, wr && `${wr.win_rate}% of ${wr.closed} closed`]);
    let dh = null;
    for (const a of d.agents) for (const p of a.positions || []) if (!dh || p.held_min > dh.p.held_min) dh = {a, p};
    out.push(["Diamond hands", dh && dh.a, dh && `${esc(dh.p.symbol)} held ${span(dh.p.held_min * 60)}`]);
    const hoard = best(d.agents.filter(a => a.equity > 0), a => a.cash / a.equity);
    out.push(["Cash hoarder", hoard, hoard && `${Math.round(hoard.cash / hoard.equity * 100)}% in cash`]);
    const lead = best(Object.keys(leaderTime).filter(n => byName(n) && leaderTime[n] > 0), n => leaderTime[n]);
    out.push(["Longest in 1st", lead && byName(lead), lead && `${span(leaderTime[lead])} this session`]);
    setHTML(badgesEl, out.map(([title, a, stat]) => a
      ? `<div class="panel st-badge"><div class="st-btitle">${title}</div><span style="color:${col(a)}">${sprite(a)}</span>
           <div class="st-bname" style="color:${col(a)}">${esc(a.name)}</div><div class="st-bstat">${stat}</div></div>`
      : `<div class="panel st-badge none"><div class="st-btitle">${title}</div><span></span><div class="st-bname">Nobody yet</div><div class="st-bstat">&nbsp;</div></div>`
    ).join(""));
  }

  /* ---------- sparkline cards ---------- */
  let series = null;
  function ensureCards(d) {
    // Stage order grouped by team: stable across rank changes, so canvases are not rebuilt every tick.
    const teams = teamsOf(d.agents);
    const want = teams.map(t => t.key + "=" + t.list.map(a => a.name + ":" + a.avatar).join(",")).join("|");
    if (cardsEl._stKey === want) return;
    cardsEl._stKey = want;
    const card = a => `<div class="panel st-card" data-agent="${esc(a.name)}" style="--c:${col(a)}">
        <div class="st-chead"><span style="color:${col(a)}">${sprite(a)}</span><div class="st-cname" style="color:${col(a)}">${esc(a.name)}</div></div>
        <canvas></canvas>
        <div class="st-cfoot"><span class="st-ceq"></span><span class="st-cpnl"></span></div></div>`;
    const group = t => `<div class="st-cteam">${tName(t.key)}</div>${t.list.map(card).join("")}`;
    cardsEl.innerHTML = teams.length > 1 ? teams.map(group).join("") : byOrder(d.agents).map(card).join("");
    drawAll();
  }
  function updateFoot(d) {
    for (const a of d.agents) {
      const card = cardsEl.querySelector(`[data-agent="${a.name.replace(/"/g, '\\"')}"]`);
      if (!card) continue;
      card.querySelector(".st-ceq").textContent = money(a.equity, 0);
      const p = card.querySelector(".st-cpnl");
      p.textContent = `${pct(a.pnl_pct)} · ${signed(a.equity - (d.start_cash || 0))}`;
      p.className = "st-cpnl " + cls(a.pnl_pct);
    }
  }
  function draw(canvas, pts, color, start) {
    const w = canvas.clientWidth || 160, h = canvas.clientHeight || 56, dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr); ctx.clearRect(0, 0, w, h);
    if (!pts || pts.length < 1) return;
    const ys = pts.map(p => p[1]).concat(start ? [start] : []);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    if (hi - lo < 1e-9) { lo -= 1; hi += 1; } else { const pad = (hi - lo) * .12; lo -= pad; hi += pad; }
    const t0 = pts[0][0], t1 = pts[pts.length - 1][0] || t0 + 1;
    const X = t => 2 + (t1 === t0 ? 0 : (t - t0) / (t1 - t0)) * (w - 4);
    const Y = v => Math.round(h - 2 - (v - lo) / (hi - lo) * (h - 4)) + .5;
    if (start) {  // dashed start line
      ctx.strokeStyle = "rgba(163,157,203,.6)"; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(0, Y(start)); ctx.lineTo(w, Y(start)); ctx.stroke(); ctx.setLineDash([]);
    }
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.lineJoin = "miter";
    ctx.beginPath();
    let px = X(pts[0][0]), py = Y(pts[0][1]); ctx.moveTo(px, py);
    for (let i = 1; i < pts.length; i++) { const x = X(pts[i][0]), y = Y(pts[i][1]); ctx.lineTo(x, py); ctx.lineTo(x, y); py = y; }
    ctx.lineTo(w, py); ctx.stroke();
    ctx.fillStyle = color; ctx.fillRect(w - 4, py - 2, 4, 4);  // final pixel marker
  }
  function drawAll() {
    if (!series || !data) return;
    for (const a of data.agents) {
      const card = cardsEl.querySelector(`[data-agent="${a.name.replace(/"/g, '\\"')}"]`);
      if (card) draw(card.querySelector("canvas"), series[a.name] || [], col(a), data.start_cash);
    }
  }
  async function refreshSeries() {
    try {
      const r = await fetch("/api/series", {cache: "no-store"});
      if (!r.ok) return;
      series = await r.json();
      drawAll();
    } catch {}
  }
  let resizeTimer = 0;
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(drawAll, 200); });

  /* ---------- wiring ---------- */
  function render(d) {
    if (!d || !Array.isArray(d.agents)) return;
    trackLeader(d);
    renderVersus(d);
    renderBadges(d);
    renderPersonality(d);
    ensureCards(d);
    updateFoot(d);
  }
  if (typeof data !== "undefined" && data) render(data);
  document.addEventListener("arena:data", e => render(e.detail));
  refreshSeries();
  setInterval(refreshSeries, 30000);
})();
