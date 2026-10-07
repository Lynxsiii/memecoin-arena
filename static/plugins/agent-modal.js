/* Agent character sheet modal — click a mascot, label, standings row, bag or decision name. */
(() => {
  "use strict";
  const PREFIX = "am-";
  const TRIGGERS = ".lane[data-name], .label[data-name], #board tr[data-agent], .bag[data-agent] h3, article.decision[data-agent] .who, .mini-row[data-agent], .gl-agent[data-agent], .rm-who[data-agent], .sc-who[data-agent]";

  /* ---------- styles ---------- */
  const style = document.createElement("style");
  style.textContent = `
  ${TRIGGERS} { cursor: pointer; }
  .am-root { position: fixed; inset: 0; z-index: 900; display: none; }
  .am-root.open { display: block; }
  .am-back { position: absolute; inset: 0; background: rgba(10, 8, 24, .78); }
  .am-dlg { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
    width: min(720px, calc(100vw - 32px)); max-height: calc(100vh - 32px); overflow: auto; overscroll-behavior: contain;
    background: var(--dusk); color: var(--moon); border: 2px solid var(--c, var(--seam)); box-sizing: border-box;
    clip-path: polygon(0 8px, 4px 8px, 4px 4px, 8px 4px, 8px 0, calc(100% - 8px) 0, calc(100% - 8px) 4px, calc(100% - 4px) 4px, calc(100% - 4px) 8px, 100% 8px,
      100% calc(100% - 8px), calc(100% - 4px) calc(100% - 8px), calc(100% - 4px) calc(100% - 4px), calc(100% - 8px) calc(100% - 4px), calc(100% - 8px) 100%,
      8px 100%, 8px calc(100% - 4px), 4px calc(100% - 4px), 4px calc(100% - 8px), 0 calc(100% - 8px));
    outline: none; font: 14px/1.45 var(--body); }
  .am-root.open .am-dlg { animation: am-in .22s steps(4) both; }
  @keyframes am-in { from { opacity: 0; transform: translate(-50%, -50%) scale(.86); } to { opacity: 1; transform: translate(-50%, -50%) scale(1); } }
  .am-head { display: grid; grid-template-columns: 128px minmax(0, 1fr); gap: 14px 18px; padding: 18px 20px 12px; border-bottom: 1px solid var(--seam); align-items: center; }
  .am-sprite { width: 120px; height: 105px; image-rendering: pixelated; }
  .am-sprite svg { width: 100%; height: 100%; display: block; }
  .am-name { font: 400 40px/1 var(--pixel); color: var(--c); margin: 0; text-shadow: 2px 2px 0 var(--ink); }
  .am-desc { color: var(--haze); margin: 6px 0 0; font-size: 13px; }
  .am-quote { margin: 8px 0 0; font: 400 18px/1.2 var(--pixel); color: var(--c); }
  .am-quote::before { content: "\\201C"; } .am-quote::after { content: "\\201D"; }
  .am-bio { color: var(--moon); margin: 4px 0 0; font-size: 13px; font-style: italic; opacity: .9; }
  .am-journal { margin: 0; padding: 0 0 0 20px; font-size: 13px; color: var(--moon); }
  .am-journal li { margin: 3px 0; overflow-wrap: anywhere; }
  .am-journal li::marker { color: var(--c); font-variant-numeric: tabular-nums; }
  .am-rank { font: 400 20px/1 var(--pixel); color: var(--haze); margin-top: 8px; }
  .am-rank b { color: var(--gold); font-weight: 400; }
  .am-lives { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; margin-top: 6px; color: var(--haze); font-size: 13px; }
  .am-lives .am-lk { font: 400 20px/1 var(--pixel); }
  .am-lives .hearts { gap: 3px; }
  .am-lives .hearts svg { width: 14px; }
  .am-hearts-text { color: var(--loss); font-size: 16px; letter-spacing: 2px; line-height: 1; }
  .am-lives .am-gone { color: var(--loss); font-weight: 500; }
  .am-busts { margin: 4px 0 0; padding: 0 0 0 18px; color: var(--haze); font-size: 12px; }
  .am-busts li { margin: 1px 0; }
  .am-busts li::marker { color: var(--loss); }
  .am-busts b { color: var(--moon); font-weight: 500; font-variant-numeric: tabular-nums; }
  .am-hold { margin: 4px 0 0; color: var(--haze); font-size: 12px; }
  .am-tag.out { color: var(--loss); border-color: var(--loss); }
  .am-top { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 12px 20px 0; }
  .am-stat { background: var(--night); border: 1px solid var(--seam); padding: 8px 10px; }
  .am-stat small { display: block; color: var(--haze); font-size: 11px; }
  .am-stat span { font: 400 26px/1.05 var(--pixel); font-variant-numeric: tabular-nums; }
  .am-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 10px 20px 0; }
  .am-grid .am-stat span { font-size: 22px; }
  .am-xgrid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
  .am-xgrid .am-stat { cursor: help; }
  .am-xgrid .am-stat span { font-size: 22px; }
  .am-hot { color: var(--gold); }
  .am-xnote { margin: 6px 0 0; color: var(--haze); font-size: 12px; }
  .am-llm { margin: 10px 20px 0; padding: 8px 10px; border: 1px dashed var(--seam); color: var(--haze); font-size: 13px; display: flex; flex-wrap: wrap; gap: 6px 18px; }
  .am-llm code { font-family: ui-monospace, Consolas, monospace; font-size: 12px; color: var(--moon); }
  .am-err { color: var(--loss); }
  .am-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .am-tag { display: inline-block; font: 500 11px/1 var(--body); padding: 4px 7px; border: 1px solid var(--seam); color: var(--haze); background: var(--night); letter-spacing: .02em; }
  .am-tag.team { border-color: var(--c); color: var(--c); }
  .am-tag.persona { color: var(--moon); border-color: color-mix(in srgb, var(--c) 50%, var(--seam)); }
  .am-tag.mode-slow { color: var(--gold); border-color: var(--gold); }
  .am-tag.mode-paused { color: var(--loss); border-color: var(--loss); }
  .am-keys .am-k { color: var(--moon); }
  .am-sec { padding: 14px 20px 0; }
  .am-sec h4 { margin: 0 0 6px; font: 400 22px/1 var(--pixel); color: var(--haze); }
  .am-spark { display: block; width: 100%; height: 120px; background: var(--night); border: 1px solid var(--seam); }
  .am-tbl { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
  .am-tbl th { text-align: left; color: var(--haze); font-weight: 500; font-size: 11px; padding: 2px 6px; border-bottom: 1px solid var(--seam); }
  .am-tbl td { padding: 4px 6px; border-bottom: 1px solid rgba(52, 44, 99, .5); white-space: nowrap; }
  .am-tbl td.r, .am-tbl th.r { text-align: right; }
  .am-tbl td.why { white-space: normal; color: var(--haze); font-size: 12px; max-width: 260px; }
  .am-up { color: var(--profit); } .am-down { color: var(--loss); }
  .am-buy { color: var(--profit); } .am-sell { color: var(--gold); }
  .am-empty { color: var(--haze); font-size: 13px; padding: 6px 0; }
  .am-dec { border-left: 2px solid var(--seam); padding: 4px 10px; margin: 0 0 10px; }
  .am-dec .am-when { color: var(--haze); font-size: 11px; }
  .am-dec p { margin: 2px 0 4px; font-size: 13px; }
  .am-dec ul { margin: 0; padding: 0 0 0 14px; font-size: 12px; color: var(--haze); }
  .am-dec li.rej { text-decoration: line-through; opacity: .7; }
  .am-foot { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 14px 20px 18px; color: var(--haze); font-size: 12px; }
  .am-btn { font: 500 13px/1 var(--body); color: var(--moon); background: var(--night); border: 1px solid var(--seam); padding: 8px 12px; cursor: pointer; }
  .am-btn:hover, .am-btn:focus-visible { border-color: var(--c); outline: none; }
  .am-close { position: absolute; top: 12px; right: 14px; }
  .am-nav { display: flex; gap: 6px; }
  @media (max-width: 640px) {
    .am-dlg { left: 0; top: 0; transform: none; width: 100vw; max-width: 100vw; height: 100vh; max-height: 100vh; clip-path: none; border-width: 0; }
    @keyframes am-in { from { opacity: 0; transform: scale(.9); } to { opacity: 1; transform: none; } }
    .am-head { grid-template-columns: 80px minmax(0, 1fr); padding: 16px 16px 10px; }
    .am-sprite { width: 76px; height: 66px; }
    .am-name { font-size: 30px; }
    .am-top, .am-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); padding-left: 16px; padding-right: 16px; }
    .am-xgrid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .am-llm, .am-sec, .am-foot { padding-left: 16px; padding-right: 16px; }
    .am-sec { overflow-x: auto; }
    .am-close { top: 10px; right: 10px; }
  }
  @media (prefers-reduced-motion: reduce) { .am-root.open .am-dlg { animation: none; } }
  `;
  document.head.appendChild(style);

  /* ---------- DOM ---------- */
  const root = document.createElement("div");
  root.className = PREFIX + "root";
  root.innerHTML = `<div class="am-back"></div>
    <div class="am-dlg" role="dialog" aria-modal="true" aria-labelledby="am-title" tabindex="-1">
      <button class="am-btn am-close" type="button" aria-label="Close">Esc</button>
      <div class="am-body"></div>
      <div class="am-foot"><span class="am-keys">← → switch agent · 1–9, 0 jump · Esc close</span>
        <div class="am-nav"><button class="am-btn" type="button" data-nav="-1">← Prev</button><button class="am-btn" type="button" data-nav="1">Next →</button></div></div>
    </div>`;
  document.body.appendChild(root);
  const dlg = root.querySelector(".am-dlg"), body = root.querySelector(".am-body");

  let openName = null, trigger = null, series = null, seriesAt = 0, lastKey = "";

  const sorted = () => (data?.agents || []).slice().sort((a, b) => a.order - b.order);  // stage order
  const PERSONA_LABEL = { degen: "Degen: apes in", skeptic: "Skeptic: hard to convince", scalper: "Scalper: in and out",
                          twin: "Twin: identical copy, measures luck", triplet: "Triplet: a third identical copy",
                          copycat: "Copycat: follows the top traders", graduate: "Graduate: trades coins that left the bonding curve",
                          runner: "Runner: hunts early runners" };
  const agent = name => (data?.agents || []).find(a => a.name === name);
  // " · journal: 2 added, 1 removed (14 lessons)" from a decision's journal change (older records hold the whole list)
  const journalNote = j => {
    if (Array.isArray(j)) return ` · rewrote its journal (${j.length} lesson${j.length === 1 ? "" : "s"})`;
    if (!j || typeof j !== "object") return "";
    const n = (k, w) => (j[k] || []).length ? `${j[k].length} ${w}` : "";
    const parts = [n("added", "added"), n("removed", "removed"), n("reworded", "reworded")].filter(Boolean);
    return parts.length ? ` · journal: ${parts.join(", ")} (${j.total} lesson${j.total === 1 ? "" : "s"})` : "";
  };
  const rankOf = name => (data?.agents || []).findIndex(a => a.name === name) + 1;
  const cls = n => n >= 0 ? "am-up" : "am-down";
  const hasLives = a => typeof a.lives === "number" && isFinite(a.lives) && a.lives >= 1;   // Claudes; bots and older arenas send none
  const bustsOf = a => (Array.isArray(a.busts) ? a.busts : []).filter(b => b && typeof b === "object");
  // "14:05" today, "Oct 5, 14:05" on an earlier day
  const bustTime = ts => {
    const d = new Date(Number(ts) * 1000);
    if (isNaN(d)) return "an unknown time";
    const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return d.toDateString() === new Date().toDateString() ? time : `${d.toLocaleDateString([], { month: "short", day: "numeric" })}, ${time}`;
  };
  // "Lives: ♥♥♡ (2 of 3 left)", then every bust so far and what it trades with now
  function livesHTML(a) {
    if (!hasLives(a)) return "";
    const total = Math.min(9, Math.round(a.lives));
    const raw = a.out === true ? 0 : typeof a.lives_left === "number" && isFinite(a.lives_left) ? a.lives_left : total;
    const left = Math.max(0, Math.min(total, Math.round(raw)));
    const hearts = typeof heartsHTML === "function" ? heartsHTML(a) : `<span class="am-hearts-text">${"♥".repeat(left)}${"♡".repeat(total - left)}</span>`;
    const busts = bustsOf(a);
    const holding = busts.length && typeof a.trading_equity === "number" && isFinite(a.trading_equity)
      ? `<p class="am-hold">Trading with ${money(a.trading_equity)} right now; each fresh ${money(data?.start_cash || 1000, 0)} stake after a bust counts against its score.</p>` : "";
    return `<div class="am-lives"><span class="am-lk">Lives:</span><span aria-hidden="true">${hearts}</span>
        <span>${left ? `(${left} of ${total} left)` : `<span class="am-gone">(out of lives)</span>`}</span></div>
      ${busts.length ? `<ul class="am-busts">${busts.map(b => `<li>Went bust at ${esc(bustTime(b.ts))} with <b>${money(Number(b.equity) || 0, 0)}</b> left</li>`).join("")}</ul>` : ""}${holding}`;
  }

  // The "Who's really winning" report card (alpha vs each yardstick, fee drag, top-3 share, average win and loss). The
  // analytics plugin already polls /api/analytics and shares the payload as window.arenaAnalytics; older arenas send no
  // `extra`, and before the first poll there is nothing yet, so the section is simply left out.
  const ALPHA_ORDER = ["Hold SOL", "Random", "Graduates"];
  const extraOf = name => {
    const rows = window.arenaAnalytics && window.arenaAnalytics.agents;
    const row = Array.isArray(rows) ? rows.find(r => r && r.name === name) : null;
    return row && row.extra && typeof row.extra === "object" ? row.extra : null;
  };
  function extraHTML(a) {
    const x = extraOf(a.name);
    if (!x) return "";
    const n = v => typeof v === "number" && isFinite(v) ? v : null;
    const start = n(window.arenaAnalytics.start_cash) || data?.start_cash || 1000;
    const stat = (label, val, c, tip) => `<div class="am-stat" title="${esc(tip)}"><small>${label}</small><span class="${c}">${val}</span></div>`;
    const alpha = x.alpha && typeof x.alpha === "object" ? x.alpha : {};
    const rank = b => { const i = ALPHA_ORDER.indexOf(b); return i < 0 ? 99 : i; };
    const cells = Object.keys(alpha).sort((p, q) => rank(p) - rank(q) || p.localeCompare(q)).map(b => {
      const v = n(alpha[b]);
      return stat(`Alpha vs ${esc(b)}`, v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)} pts`, v == null ? "" : cls(v),
                  `How many percentage points better than ${b} over the same time`);
    });
    const fd = n(x.fee_drag_pct), fu = n(x.fees_usd), t3 = n(x.top3_share), w = n(x.avg_win_usd), l = n(x.avg_loss_usd);
    cells.push(stat("Fee drag", fd == null ? "—" : `${fd.toFixed(1)}%`, "",
                    `Fees paid as a share of the starting ${money(start, 0)}${fu != null ? ` (${money(fu)} so far)` : ""}`));
    cells.push(stat("Top-3 share", t3 == null ? "—" : `${Math.round(t3 * 100)}%`, t3 != null && t3 >= 0.8 ? "am-hot" : "",
                    t3 == null ? "No profit yet, so there is nothing to split"
                               : "How much of the profit came from just the 3 best trades (near 100% means it's mostly luck so far)"));
    if (w != null || l != null) cells.push(stat("Avg win / loss", `${w == null ? "—" : signed(w)} / ${l == null ? "—" : signed(l)}`, "",
                    `Average winning and losing trade${n(x.closed) != null ? `, over ${x.closed} closed trades` : ""}`));
    return `<div class="am-sec"><h4>Who's really winning</h4><div class="am-xgrid">${cells.join("")}</div>
      <p class="am-xnote">Alpha is how many percentage points better than each yardstick bot over the same time. Fee drag is the fees paid as a share of the starting ${money(start, 0)}. Top-3 share is how much of the profit came from just the 3 best trades: near 100% means it's mostly luck so far.</p></div>`;
  }

  /* ---------- rendering ---------- */
  function render() {
    const a = agent(openName);
    if (!a) return;
    const color = colorOf(a);
    dlg.style.setProperty("--c", color);
    const t = now();
    const sells = (data.trades || []).filter(x => x.agent === a.name && x.side === "sell" && typeof x.pnl === "number");
    const best = sells.length ? sells.reduce((m, x) => x.pnl > m.pnl ? x : m) : null;
    const worst = sells.length ? sells.reduce((m, x) => x.pnl < m.pnl ? x : m) : null;
    const trades = (data.trades || []).filter(x => x.agent === a.name).slice(0, 15);
    const decisions = a.kind === "llm" ? (data.decisions || []).filter(d => d.agent === a.name).slice(0, 10) : [];

    let llm = "";
    const mode = a.kind === "llm" ? String(a.mode || "normal") : "";
    if (a.kind === "llm") {
      let status;
      if (a.out === true) status = "Out of lives, not trading any more";
      else if (mode === "paused") status = "Paused, not trading";
      else if (a.thinking_since) status = `Thinking for ${span(t - a.thinking_since)}`;
      else if (a.next_run) status = `Looks again in ${span(Math.max(0, a.next_run - t))}`;
      else status = "Idle";
      llm = `<div class="am-llm"><span>${esc(status)}</span>${a.model ? `<span>Model <code>${esc(a.model)}</code></span>` : ""}
        <span>Mode <code>${esc(mode)}</code>${mode === "slow" ? " (looks less often)" : ""}</span>
        ${a.persona ? `<span>Persona <code>${esc(a.persona)}</code></span>` : ""}
        ${a.error ? `<span class="am-err">Last error: ${esc(a.error)}</span>` : ""}</div>`;
    }
    const teamTag = `<span class="am-tag team">${typeof teamOf === "function" ? teamName(teamOf(a)) : a.kind === "llm" ? "Team Claude" : "Team Bots"}</span>`;
    const personaTag = a.persona ? `<span class="am-tag persona">${esc(PERSONA_LABEL[a.persona] || a.persona)}</span>` : "";
    const modeTag = a.out === true ? `<span class="am-tag out">out of lives</span>`
                  : a.kind === "llm" && mode !== "normal" ? `<span class="am-tag mode-${esc(mode)}">${esc(mode)}</span>` : "";
    const slotIdx = sorted().findIndex(x => x.name === a.name);
    const keyTag = slotIdx >= 0 && slotIdx < 10 ? `<span class="am-tag" title="Press this key to open">key ${(slotIdx + 1) % 10}</span>` : "";

    const stat = (label, val, c = "") => `<div class="am-stat"><small>${label}</small><span class="${c}">${val}</span></div>`;
    const html = `
      <div class="am-head">
        <div class="am-sprite">${spriteSVG(a.avatar)}</div>
        <div><h3 class="am-name" id="am-title">${esc(a.name)}</h3>
          <p class="am-desc">${esc(a.description)}</p>
          ${a.catchphrase ? `<p class="am-quote">${esc(a.catchphrase)}</p>` : ""}
          ${a.bio ? `<p class="am-bio">${esc(a.bio)}</p>` : ""}
          <div class="am-rank">Rank <b>${ordinal(rankOf(a.name))}</b> of ${data.agents.length}</div>
          ${livesHTML(a)}
          <div class="am-tags">${teamTag}${personaTag}${modeTag}${keyTag}</div></div>
      </div>
      <div class="am-top">
        ${stat(hasLives(a) && bustsOf(a).length ? "Score equity" : "Equity", money(a.equity))}
        ${stat("P&amp;L", pct(a.pnl_pct), cls(a.pnl_pct))}
        ${hasLives(a) && typeof a.points === "number" ? stat("Points", (a.points >= 0 ? "+" : "") + a.points.toFixed(1), cls(a.points)) : stat("Cash", money(a.cash))}
      </div>
      ${llm}
      <div class="am-grid">
        ${stat("Trades", a.trades)}
        ${stat("Closed", a.closed)}
        ${stat("Win rate", a.win_rate == null ? "—" : Math.round(a.win_rate) + "%")}
        ${stat("Max drawdown", a.max_dd != null ? "-" + Number(a.max_dd).toFixed(1) + "%" : "—", a.max_dd > 0 ? "am-down" : "")}
        ${stat("Best trade", best ? signed(best.pnl) : "—", best ? cls(best.pnl) : "")}
        ${stat("Worst trade", worst ? signed(worst.pnl) : "—", worst ? cls(worst.pnl) : "")}
      </div>
      ${extraHTML(a)}
      <div class="am-sec"><h4>Equity</h4><canvas class="am-spark" aria-label="Equity over time"></canvas></div>
      <div class="am-sec"><h4>Open positions</h4>${a.positions?.length ? `<table class="am-tbl"><thead><tr><th>Token</th><th class="r">Cost</th><th class="r">Value</th><th class="r">P&amp;L</th><th class="r">Held</th><th>Rating</th></tr></thead><tbody>
        ${a.positions.map(p => `<tr><td>${esc(p.symbol)}</td><td class="r">${money(p.cost)}</td><td class="r">${money(p.value)}</td><td class="r ${cls(p.pnl_pct)}">${pct(p.pnl_pct)}</td><td class="r">${span(p.held_min * 60)}</td><td>${esc(p.rating)}</td></tr>`).join("")}
        </tbody></table>` : `<div class="am-empty">No open positions, sitting in cash.</div>`}</div>
      <div class="am-sec"><h4>Last trades</h4>${trades.length ? `<table class="am-tbl"><thead><tr><th>When</th><th>Side</th><th>Token</th><th class="r">Size</th><th class="r">P&amp;L</th><th>Reason</th></tr></thead><tbody>
        ${trades.map(x => `<tr><td>${esc(ago(t - x.ts))}</td><td class="am-${x.side}">${x.side}</td><td>${esc(x.symbol)}</td><td class="r">${money(x.usd)}</td><td class="r ${x.pnl == null ? "" : cls(x.pnl)}">${x.pnl == null ? "—" : signed(x.pnl)}</td><td class="why">${esc(x.reason || "")}</td></tr>`).join("")}
        </tbody></table>` : `<div class="am-empty">No trades yet.</div>`}</div>
      ${a.kind === "llm" ? `<div class="am-sec"><h4>Journal</h4>${Array.isArray(a.journal) && a.journal.length
          ? `<ol class="am-journal">${a.journal.map(l => `<li>${esc(String(l))}</li>`).join("")}</ol>`
          : `<div class="am-empty">No lessons written yet. The journal fills in as its trades close.</div>`}</div>` : ""}
      ${a.kind === "llm" ? `<div class="am-sec"><h4>Recent decisions</h4>${decisions.length ? decisions.map(d => `<div class="am-dec">
          <div class="am-when">${esc(ago(t - d.ts))}${d.secs ? ` · thought for ${span(d.secs)}` : ""}${journalNote(d.journal)}${d.error ? ` · <span class="am-err">${esc(d.error)}</span>` : ""}</div>
          ${d.note ? `<p>${esc(d.note)}</p>` : ""}
          ${d.orders?.length ? `<ul>${d.orders.map(o => `<li class="${o.rejected ? "rej" : ""}">${esc(o.action)} ${esc(o.symbol || "")}${o.usd ? ` ${money(o.usd, 0)}` : o.fraction ? ` ${Math.round(o.fraction * 100)}%` : ""}${o.reason ? ` — ${esc(o.reason)}` : ""}${o.rejected ? ` (rejected${typeof o.rejected === "string" ? ": " + esc(o.rejected) : ""})` : ""}</li>`).join("")}</ul>` : `<ul><li>No orders</li></ul>`}
        </div>`).join("") : `<div class="am-empty">No decisions yet.</div>`}</div>` : ""}`;
    body.innerHTML = html;
    drawSpark(a, color);
  }

  function drawSpark(a, color) {
    const cv = body.querySelector(".am-spark");
    if (!cv) return;
    const pts = series?.[a.name] || [];
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth || 600, H = cv.clientHeight || 120;
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    const ctx = cv.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);
    const start = data?.start_cash || 1000;
    if (pts.length < 2) {
      ctx.fillStyle = "#a39dcb"; ctx.font = "12px Rubik, sans-serif"; ctx.fillText("Collecting history...", 10, H / 2);
      return;
    }
    const ys = pts.map(p => p[1]).concat([start]);
    let lo = Math.min(...ys), hi = Math.max(...ys);
    if (hi - lo < 1) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.1; lo -= pad; hi += pad;
    const x0 = pts[0][0], x1 = pts[pts.length - 1][0] || x0 + 1;
    const X = ms => 2 + (W - 4) * ((ms - x0) / Math.max(1, x1 - x0));
    const Y = v => H - 4 - (H - 8) * ((v - lo) / (hi - lo));
    // start cash dashed
    ctx.setLineDash([4, 4]); ctx.strokeStyle = "#a39dcb"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, Math.round(Y(start)) + .5); ctx.lineTo(W, Math.round(Y(start)) + .5); ctx.stroke();
    ctx.setLineDash([]);
    // stepped equity line
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.lineJoin = "miter";
    ctx.beginPath();
    let py = Y(pts[0][1]);
    ctx.moveTo(X(pts[0][0]), py);
    for (let i = 1; i < pts.length; i++) {
      const x = X(pts[i][0]), y = Y(pts[i][1]);
      ctx.lineTo(x, py); ctx.lineTo(x, y); py = y;
    }
    ctx.stroke();
    ctx.fillStyle = color;
    const lx = X(pts[pts.length - 1][0]), ly = Y(pts[pts.length - 1][1]);
    ctx.fillRect(Math.round(lx) - 3, Math.round(ly) - 3, 6, 6);
    ctx.fillStyle = "#a39dcb"; ctx.font = "11px Rubik, sans-serif";
    ctx.fillText(money(hi + pad, 0), 6, 12); ctx.fillText(money(lo - pad, 0), 6, H - 6);
  }

  async function loadSeries(force) {
    if (!force && Date.now() - seriesAt < 12000) return;
    seriesAt = Date.now();
    try {
      const r = await fetch("/api/series", { cache: "no-store" });
      if (r.ok) { series = await r.json(); if (openName) { const a = agent(openName); if (a) drawSpark(a, colorOf(a)); } }
    } catch (e) { /* keep the previous series */ }
  }

  /* ---------- open / close ---------- */
  function open(name, from) {
    if (!agent(name)) return;
    if (!openName) trigger = from || document.activeElement;
    openName = name;
    root.classList.add("open");
    document.body.style.overflow = "hidden";
    render();
    loadSeries(false);
    dlg.scrollTop = 0;
    dlg.focus({ preventScroll: true });
  }
  function close() {
    if (!openName) return;
    openName = null;
    root.classList.remove("open");
    document.body.style.overflow = "";
    const t = trigger; trigger = null;
    if (t && document.contains(t) && typeof t.focus === "function") { t.setAttribute("tabindex", t.getAttribute("tabindex") ?? "-1"); t.focus({ preventScroll: true }); }
  }
  function cycle(dir) {
    const list = sorted(); if (!list.length) return;
    const i = list.findIndex(a => a.name === openName);
    open(list[(i + dir + list.length) % list.length].name);
  }

  /* ---------- events ---------- */
  document.addEventListener("click", e => {
    if (root.contains(e.target)) {
      if (e.target.closest(".am-back") || e.target.closest(".am-close")) close();
      const nav = e.target.closest("[data-nav]"); if (nav) cycle(+nav.dataset.nav);
      return;
    }
    const el = e.target.closest(TRIGGERS);
    if (!el) return;
    // decisions: only act on the .who text; bags: only the h3
    const holder = el.closest("[data-name], [data-agent]");
    const name = holder?.dataset.name || holder?.dataset.agent;
    if (name) { e.preventDefault(); open(name, el); }
  });
  document.addEventListener("keydown", e => {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (openName) {
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      if (e.key === "ArrowRight") { e.preventDefault(); cycle(1); return; }
      if (e.key === "ArrowLeft") { e.preventDefault(); cycle(-1); return; }
      if (e.key === "Tab") { // keep focus inside
        const f = [...dlg.querySelectorAll("button, [href], [tabindex]:not([tabindex='-1'])")].filter(x => !x.disabled);
        if (f.length) {
          const first = f[0], last = f[f.length - 1];
          if (e.shiftKey && (document.activeElement === first || document.activeElement === dlg)) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      }
    }
    if (/^[0-9]$/.test(e.key)) {  // 1-9 → stage slots 1-9, 0 → slot 10; arrows still cycle everyone
      const list = sorted(), a = list[e.key === "0" ? 9 : +e.key - 1];
      if (a) { e.preventDefault(); open(a.name); }
    }
  });
  document.addEventListener("arena:data", () => {
    if (!openName) return;
    const key = JSON.stringify([agent(openName), data?.trades?.[0]?.id, data?.decisions?.[0]?.id, Math.floor(now() / 5)]);
    if (key !== lastKey) { lastKey = key; render(); }
    loadSeries(false);
  });
  let lastExtra = "";
  document.addEventListener("arena:analytics", () => {   // fresh report card from the analytics plugin: redraw only if this agent's changed
    if (!openName) return;
    const key = JSON.stringify(extraOf(openName));
    if (key !== lastExtra) { lastExtra = key; render(); }
  });
  window.addEventListener("resize", () => { if (openName) { const a = agent(openName); if (a) drawSpark(a, colorOf(a)); } });
})();
