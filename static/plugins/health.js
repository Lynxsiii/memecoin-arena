// health plugin: toolbar status light + dropdown with arena health, Claude status and CSV exports
(function () {
  const POLL_MS = 5000, STALL_S = 120;
  const toolbar = document.getElementById("toolbar"), wrap = document.querySelector(".wrap");
  if (!toolbar || !wrap) return;

  const style = document.createElement("style");
  style.textContent = `
  .hl-btn { display: inline-flex; align-items: center; gap: 7px; position: relative; }
  .hl-dot { width: 8px; height: 8px; background: var(--haze); flex: none;
            box-shadow: 0 0 0 1px var(--night), 0 0 6px currentColor; }
  .hl-dot.ok { background: var(--profit); color: var(--profit); }
  .hl-dot.warn { background: var(--gold); color: var(--gold); }
  .hl-dot.bad { background: var(--loss); color: var(--loss); animation: hl-blink 1s steps(2) infinite; }
  @keyframes hl-blink { 50% { opacity: .35; } }
  .hl-anchor { position: relative; display: inline-block; }
  .hl-panel { position: absolute; top: calc(100% + 6px); right: 0; z-index: 60; width: min(340px, calc(100vw - 32px));
              max-height: min(72vh, 640px); overflow: auto; overscroll-behavior: contain;
              background: var(--dusk); border: 1px solid var(--seam); border-radius: 3px; padding: 12px;
              font: 400 13px/1.45 var(--body); color: var(--moon); text-align: left;
              box-shadow: 0 8px 24px rgba(0,0,0,.45); }
  .hl-tag { display: inline-block; font-size: 10px; line-height: 1; padding: 2px 4px; border: 1px solid var(--seam); color: var(--haze); margin-left: 5px; vertical-align: 1px; }
  .hl-tag.slow { color: var(--gold); border-color: var(--gold); } .hl-tag.paused { color: var(--loss); border-color: var(--loss); }
  .hl-sum { color: var(--haze); font-size: 12px; margin: -4px 0 6px; }
  .hl-panel[hidden] { display: none; }
  .hl-h { font: 400 22px/1 var(--pixel); color: var(--moon); margin: 0 0 8px; letter-spacing: .5px; }
  .hl-h + .hl-h, .hl-sec { margin-top: 12px; }
  .hl-row { display: flex; justify-content: space-between; gap: 10px; padding: 3px 0; border-bottom: 1px dashed var(--seam); }
  .hl-row:last-child { border-bottom: 0; }
  .hl-k { color: var(--haze); }
  .hl-v { text-align: right; font-variant-numeric: tabular-nums; }
  .hl-v.ok { color: var(--profit); } .hl-v.warn { color: var(--gold); } .hl-v.bad { color: var(--loss); }
  .hl-agent { padding: 5px 0; border-bottom: 1px dashed var(--seam); }
  .hl-agent:last-child { border-bottom: 0; }
  .hl-agent b { font-weight: 500; }
  .hl-err { color: var(--loss); word-break: break-word; margin-top: 2px; }
  .hl-hint { color: var(--gold); margin-top: 2px; }
  .hl-hint code { font-family: ui-monospace, Consolas, monospace; background: var(--night); padding: 1px 4px; }
  .hl-links { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .hl-links a { color: var(--moon); text-decoration: none; border: 1px solid var(--seam); background: var(--night);
                padding: 5px 8px; border-radius: 3px; font-size: 12px; }
  .hl-links a:hover { border-color: var(--gold); color: var(--gold); }
  .hl-muted { color: var(--haze); }
  .hl-strip { display: flex; align-items: center; gap: 10px; padding: 9px 12px; margin-bottom: 12px;
              background: #3a1a2a; border: 1px solid var(--loss); border-left: 4px solid var(--loss); border-radius: 3px;
              color: var(--moon); font: 400 13px/1.4 var(--body); }
  .hl-strip[hidden] { display: none; }
  .hl-strip .hl-dot { width: 10px; height: 10px; }
  .hl-strip b { font: 400 20px/1 var(--pixel); color: var(--loss); }
  @media (max-width: 480px) { .hl-panel { position: fixed; top: auto; right: 16px; left: 16px; width: auto; margin-top: 6px; } }
  `;
  document.head.appendChild(style);

  // elements
  const anchor = document.createElement("span");
  anchor.className = "hl-anchor";
  const btn = document.createElement("button");
  btn.className = "tb-btn hl-btn";
  btn.type = "button";
  btn.setAttribute("aria-haspopup", "true");
  btn.setAttribute("aria-expanded", "false");
  btn.title = "Arena health";
  btn.innerHTML = '<i class="hl-dot" aria-hidden="true"></i><span class="hl-txt">Health…</span>';
  const panel = document.createElement("div");
  panel.className = "hl-panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Arena health");
  anchor.append(btn, panel);
  (document.getElementById("statusbar") || toolbar).appendChild(anchor);   // the header's status spot; older pages: the toolbar

  const strip = document.createElement("div");
  strip.className = "hl-strip";
  strip.setAttribute("role", "alert");
  strip.hidden = true;
  wrap.insertBefore(strip, wrap.firstChild);

  const dot = btn.querySelector(".hl-dot"), txt = btn.querySelector(".hl-txt");
  let health = null, unreachable = false, unavailable = false, fetchedAt = 0, open = false;

  const safe = typeof esc === "function" ? esc : s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtAgo = s => (typeof ago === "function" ? ago(s) : fmtSpan(s) + " ago");
  function fmtSpan(s) {
    if (typeof span === "function") return span(s);
    s = Math.max(0, Math.round(s));
    if (s < 60) return s + "s";
    if (s < 3600) return Math.round(s / 60) + " min";
    return (s / 3600).toFixed(1) + " h";
  }
  const clockNow = () => (typeof now === "function" ? now() : Date.now() / 1000);

  function age() {
    if (!health || health.last_tick_age == null) return null;
    return health.last_tick_age + (clockNow() - fetchedAt);  // keep counting between polls
  }
  function level(a) {
    const tick = (health && health.tick) || 30;
    if (a == null) return "warn";
    if (a < 2 * tick) return "ok";
    if (a < 5 * tick) return "warn";
    return "bad";
  }

  function renderButton() {
    if (unavailable) { dot.className = "hl-dot"; txt.textContent = "Health unavailable"; return; }
    if (unreachable) { dot.className = "hl-dot bad"; txt.textContent = "Arena unreachable"; return; }
    const a = age();
    if (a == null) { dot.className = "hl-dot warn"; txt.textContent = "No ticks yet"; return; }
    const lv = level(a);
    dot.className = "hl-dot " + lv;
    txt.textContent = lv === "bad" ? "Arena stalled? Last tick " + fmtAgo(a) : "Tick " + fmtAgo(a);
  }

  function renderStrip() {
    const a = age();
    if (unreachable) {
      strip.hidden = false;
      strip.innerHTML = '<i class="hl-dot bad"></i><div><b>Can\'t reach the arena.</b> Is main.py still running?</div>';
    } else if (!unavailable && a != null && a > STALL_S) {
      strip.hidden = false;
      strip.innerHTML = `<i class="hl-dot bad"></i><div><b>Arena looks stalled.</b> No tick for ${safe(fmtSpan(a))}` +
        ` (expected every ${safe(fmtSpan(health.tick || 30))}). Check the terminal running main.py.</div>`;
    } else {
      strip.hidden = true;
    }
  }

  function row(k, v, cls) {
    return `<div class="hl-row"><span class="hl-k">${safe(k)}</span><span class="hl-v ${cls || ""}">${v}</span></div>`;
  }

  function renderPanel() {
    if (!open) return;
    if (unavailable) {
      panel.innerHTML = '<div class="hl-h">Health</div><div class="hl-muted">Health endpoint unavailable. Restart main.py to load extras.py.</div>';
      return;
    }
    if (!health) {
      panel.innerHTML = '<div class="hl-h">Health</div><div class="hl-muted">' +
        (unreachable ? "Can't reach the arena. Is main.py still running?" : "Loading…") + "</div>";
      return;
    }
    const a = age(), lv = level(a), t = clockNow();
    let html = '<div class="hl-h">Arena</div>';
    html += row("Last tick", a == null ? "none yet" : safe(fmtAgo(a)), lv);
    html += row("Ticks", safe(String(health.ticks ?? "–")));
    html += row("Tick interval", safe(fmtSpan(health.tick || 0)));
    html += row("Tokens tracked", safe(String(health.tracked ?? "–")));
    html += row("Market", health.mock ? "Mock (offline)" : "Live prices", health.mock ? "warn" : "ok");
    html += row("Database", health.db_size_mb == null ? "–" : safe(health.db_size_mb + " MB"));
    if (unreachable) html += row("Dashboard", "disconnected", "bad");

    const cl = health.claude || [];
    // mode / persona live on the summary payload, not the health one; cross-reference by name when available
    const info = n => { try { return typeof agentByName === "function" ? agentByName(n) : null; } catch (e) { return null; } };
    const nThinking = cl.filter(c => c.thinking_since).length, nErr = cl.filter(c => c.error).length;
    const nPaused = cl.filter(c => (info(c.name) || {}).mode === "paused").length;
    html += `<div class="hl-h hl-sec">Claude agents</div>`;
    if (!cl.length) html += '<div class="hl-muted">No Claude agents running.</div>';
    else html += `<div class="hl-sum">${cl.length} agents · ${nThinking} thinking${nPaused ? ` · ${nPaused} paused` : ""}${nErr ? ` · <span class="hl-v bad">${nErr} with errors</span>` : ""}</div>`;
    for (const c of cl) {
      const a = info(c.name) || {}, mode = a.mode || "normal";
      let status, cls = "";
      if (mode === "paused") { status = "paused"; cls = "bad"; }
      else if (c.thinking_since) { status = "thinking for " + fmtSpan(t - c.thinking_since); cls = "warn"; }
      else if (c.next_run && c.next_run > t) status = "next look in " + fmtSpan(c.next_run - t);
      else status = "due on next tick";
      const tags = (a.persona ? `<span class="hl-tag">${safe(a.persona)}</span>` : "") + (mode !== "normal" ? `<span class="hl-tag ${safe(mode)}">${safe(mode)}</span>` : "");
      html += `<div class="hl-agent"><div class="hl-row"><span><b>${safe(c.name)}</b>${tags}</span><span class="hl-v ${cls}">${safe(status)}</span></div>`;
      if (c.model) html += `<div class="hl-muted">${safe(c.model)}</div>`;
      if (c.error) {
        html += `<div class="hl-err">${safe(c.error)}</div>`;
        const e = c.error.toLowerCase();
        if (/log ?in|auth|not authenticated|unauthori|api key|credential/.test(e))
          html += '<div class="hl-hint">Fix: run <code>claude auth login</code> in a terminal.</div>';
        else if (/limit/.test(e)) html += '<div class="hl-hint">Usage limit hit, it will retry in 30 min.</div>';
      }
      html += "</div>";
    }

    html += '<div class="hl-h hl-sec">Export</div><div class="hl-links">' +
      '<a href="/api/export/trades.csv" download>Trades CSV</a>' +
      '<a href="/api/export/decisions.csv" download>Decisions CSV</a>' +
      '<a href="/api/export/equity.csv" download>Equity CSV</a></div>';
    panel.innerHTML = html;
  }

  function renderAll() { renderButton(); renderStrip(); renderPanel(); }

  async function poll() {
    try {
      const r = await fetch("/api/health", { cache: "no-store" });
      if (r.status === 404) { unavailable = true; unreachable = false; }
      else if (!r.ok) { unreachable = true; }
      else {
        const j = await r.json();
        if (j && !j.error) { health = j; fetchedAt = clockNow(); unreachable = false; unavailable = false; }
        else unreachable = true;
      }
    } catch (e) {
      unreachable = true;
    }
    renderAll();
  }

  function setOpen(v) {
    open = v;
    panel.hidden = !v;
    btn.setAttribute("aria-expanded", String(v));
    btn.setAttribute("aria-pressed", String(v));
    if (v) renderPanel();
  }
  btn.addEventListener("click", e => { e.stopPropagation(); setOpen(!open); });
  document.addEventListener("click", e => { if (open && !anchor.contains(e.target)) setOpen(false); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && open) { setOpen(false); btn.focus(); } });

  poll();
  setInterval(poll, POLL_MS);
  setInterval(() => { renderButton(); renderStrip(); if (open) renderPanel(); }, 1000);
})();
