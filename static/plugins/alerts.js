/* alerts.js — background-tab quality of life: 8-bit sounds, desktop notifications,
   unseen-count tab title and a leader-mascot favicon. Classic script plugin, IIFE. */
(function () {
  "use strict";

  /* ---------- styles ---------- */
  const style = document.createElement("style");
  style.textContent = `
    .al-btn { font: 500 13px/1 var(--body, Rubik, sans-serif); color: var(--moon, #eeeafb); background: var(--dusk, #1f1a40);
      border: 1px solid var(--seam, #342c63); border-radius: 3px; padding: 5px 9px; cursor: pointer; display: inline-flex;
      align-items: center; gap: 6px; }
    .al-btn:hover { border-color: var(--haze, #a39dcb); }
    .al-btn[aria-pressed="true"] { border-color: var(--gold, #f7c548); background: #2a2350; }
    .al-btn[disabled] { opacity: .55; cursor: not-allowed; }
    .al-dot { width: 7px; height: 7px; background: var(--seam, #342c63); border-radius: 1px; }
    .al-btn[aria-pressed="true"] .al-dot { background: var(--gold, #f7c548); }
  `;
  document.head.appendChild(style);

  /* ---------- helpers / guards ---------- */
  const prefs = (typeof arenaPrefs === "object" && arenaPrefs) || {
    get: (k, d) => { try { const v = localStorage.getItem("arena:" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set: (k, v) => { try { localStorage.setItem("arena:" + k, JSON.stringify(v)); } catch {} },
  };
  const fmtMoney = n => (typeof money === "function" ? money(n, 0) : "$" + Math.round(n).toLocaleString());
  const fmtSigned = n => (typeof signed === "function" ? signed(n) : (n >= 0 ? "+" : "") + n.toFixed(2));
  const BASE_TITLE = "Memecoin Arena";

  let soundOn = !!prefs.get("sound", false);
  let notifyOn = !!prefs.get("notify", false);

  /* ---------- 8-bit sound (WebAudio, no files) ---------- */
  let ctx = null;
  function unlockAudio() {
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      if (!ctx) ctx = new AC();
      if (ctx.state === "suspended") ctx.resume();
    } catch { ctx = null; }
    return ctx;
  }
  // Oscillator note with a tiny attack and exponential release. `to` slides the pitch.
  function note(freq, at, dur, opts) {
    const o = opts || {};
    const osc = ctx.createOscillator(), g = ctx.createGain();
    const gain = o.gain == null ? 0.06 : o.gain;
    osc.type = o.type || "square";
    osc.frequency.setValueAtTime(freq, at);
    if (o.to) osc.frequency.exponentialRampToValueAtTime(o.to, at + dur);
    g.gain.setValueAtTime(0.0001, at);
    g.gain.linearRampToValueAtTime(gain, at + 0.006);
    g.gain.setValueAtTime(gain, at + Math.max(0.006, dur * 0.6));
    g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    osc.connect(g).connect(ctx.destination);
    osc.start(at); osc.stop(at + dur + 0.03);
  }
  const SFX = {
    buy() {        // short rising blip
      const t = ctx.currentTime; note(520, t, 0.09, { to: 1040 });
    },
    sellWin() {    // coin "ba-ding"
      const t = ctx.currentTime; note(988, t, 0.07); note(1319, t + 0.08, 0.28);
    },
    sellLose() {   // descending womp
      const t = ctx.currentTime; note(320, t, 0.38, { type: "triangle", to: 110, gain: 0.07 });
    },
    decision() {   // soft two-note chime
      const t = ctx.currentTime; note(660, t, 0.13, { type: "triangle", gain: 0.05 }); note(880, t + 0.14, 0.2, { type: "triangle", gain: 0.05 });
    },
    error() {      // low buzz (two detuned squares beat against each other)
      const t = ctx.currentTime; note(92, t, 0.36, { gain: 0.045 }); note(97, t, 0.36, { gain: 0.035 });
    },
    lead() {       // little fanfare
      const t = ctx.currentTime; [523, 659, 784].forEach((f, i) => note(f, t + i * 0.085, 0.08)); note(1046, t + 0.26, 0.32);
    },
  };
  function play(name) {
    if (!soundOn || !ctx || ctx.state !== "running") return;
    try { SFX[name](); } catch {}
  }
  // If sound was left on last session, the first click anywhere unlocks the context (autoplay rules).
  if (soundOn) document.addEventListener("pointerdown", unlockAudio, { once: true, capture: true });

  /* ---------- desktop notifications ---------- */
  let lastNotif = 0;
  function notify(title, body, tag) {
    if (!notifyOn || !document.hidden) return;
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const t = Date.now();
    if (t - lastNotif < 20000) return;          // max 1 per 20s
    lastNotif = t;
    try {
      const n = new Notification(title, { body, tag: "arena-" + tag, silent: true });
      n.onclick = () => { try { window.focus(); } catch {} n.close(); };
    } catch {}
  }

  /* ---------- tab title ---------- */
  let unseen = 0, leaderName = null, leaderEquity = 0;
  function updateTitle() {
    const count = document.hidden && unseen ? `(${unseen}) ` : "";
    const lead = leaderName ? `${leaderName} leads ${fmtMoney(leaderEquity)} · ` : "";
    const title = count + lead + BASE_TITLE;
    if (document.title !== title) document.title = title;
  }
  function bump() { if (document.hidden) { unseen++; updateTitle(); } }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) { unseen = 0; }
    updateTitle();
  });

  /* ---------- favicon = leader's mascot ---------- */
  let iconLink = document.querySelector('link[rel="icon"]');
  if (!iconLink) { iconLink = document.createElement("link"); iconLink.rel = "icon"; document.head.appendChild(iconLink); }
  let faviconFor = null;
  function setFavicon(agent) {
    if (!agent || typeof spriteSVG !== "function" || faviconFor === agent.avatar) return;
    faviconFor = agent.avatar;
    try {
      const svg = spriteSVG(agent.avatar).replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="28" ');
      const img = new Image();
      img.onload = () => {
        try {
          const c = document.createElement("canvas"); c.width = 32; c.height = 32;
          const g = c.getContext("2d"); g.imageSmoothingEnabled = false;
          g.drawImage(img, 0, 2, 32, 28);
          iconLink.type = "image/png";
          iconLink.href = c.toDataURL("image/png");
        } catch {}
      };
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    } catch {}
  }

  /* ---------- toolbar toggles ---------- */
  function makeBtn(label, title) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "tb-btn al-btn"; b.title = title;
    b.setAttribute("aria-pressed", "false");
    b.innerHTML = `<span class="al-dot" aria-hidden="true"></span>${label}`;
    return b;
  }
  const soundBtn = makeBtn("Sound", "8-bit sound effects for trades, decisions and lead changes");
  const notifyBtn = makeBtn("Notify", "Desktop notifications while this tab is in the background");
  const toolbar = document.getElementById("toolbar");
  if (toolbar) { toolbar.appendChild(soundBtn); toolbar.appendChild(notifyBtn); }

  function syncButtons() {
    soundBtn.setAttribute("aria-pressed", String(soundOn));
    notifyBtn.setAttribute("aria-pressed", String(notifyOn));
    if ("Notification" in window && Notification.permission === "denied") {
      notifyBtn.title = "Notifications are blocked for this site in your browser settings";
    }
  }
  soundBtn.addEventListener("click", () => {
    soundOn = !soundOn;
    if (soundOn) { unlockAudio(); setTimeout(() => play("buy"), 30); }   // audible confirmation on the user's gesture
    prefs.set("sound", soundOn); syncButtons();
  });
  notifyBtn.addEventListener("click", async () => {
    if (!("Notification" in window)) { notifyBtn.title = "This browser does not support notifications"; notifyBtn.disabled = true; return; }
    if (notifyOn) { notifyOn = false; prefs.set("notify", false); syncButtons(); return; }
    let perm = Notification.permission;
    if (perm === "default") { try { perm = await Notification.requestPermission(); } catch { perm = Notification.permission; } }
    notifyOn = perm === "granted";
    prefs.set("notify", notifyOn); syncButtons();
  });
  document.addEventListener("arena:prefs", e => {
    const d = e.detail || {};
    if (d.key === "sound") soundOn = !!d.value;
    if (d.key === "notify") notifyOn = !!d.value;
    syncButtons();
  });
  syncButtons();

  /* ---------- events ---------- */
  function onData(summary) {
    const agents = summary && summary.agents;
    if (!agents || !agents.length) return;
    const top = agents[0];
    const first = leaderName === null;
    if (!first && top.name !== leaderName) {
      const prev = leaderName;
      leaderName = top.name; leaderEquity = top.equity;
      play("lead"); bump();
      notify(`${top.name} takes the lead`, `Now ahead of ${prev} with ${fmtMoney(top.equity)}`, "lead");
    } else {
      leaderName = top.name; leaderEquity = top.equity;
    }
    setFavicon(top);
    updateTitle();
  }
  function onTrade(t) {
    if (!t) return;
    if (t.side === "buy") { play("buy"); bump(); return; }
    const pnl = Number(t.pnl) || 0;
    play(pnl >= 0 ? "sellWin" : "sellLose"); bump();
    if (Math.abs(pnl) > 10) {
      notify(`${t.agent} sold ${t.symbol || t.token || ""}`.trim(),
             `${pnl >= 0 ? "Profit" : "Loss"} ${fmtSigned(pnl)} on ${fmtMoney(t.usd || 0)}`, "sell");
    }
  }
  function onDecision(d) {
    if (!d) return;
    if (d.error) {
      play("error"); bump();
      notify(`${d.agent} hit an error`, String(d.error).slice(0, 120), "error");
      return;
    }
    play("decision"); bump();
    const orders = Array.isArray(d.orders) ? d.orders : [];
    if (orders.length) {
      const text = (d.note && String(d.note).slice(0, 110)) || `${orders.length} order${orders.length === 1 ? "" : "s"}`;
      notify(`${d.agent} decided to trade`, text, "decision");
    }
  }

  document.addEventListener("arena:data", e => onData(e.detail));
  document.addEventListener("arena:trade", e => onTrade(e.detail));
  document.addEventListener("arena:decision", e => onDecision(e.detail));

  // First load: establish the leader without firing a lead-change event.
  if (typeof data !== "undefined" && data) onData(data);
  else updateTitle();
})();
