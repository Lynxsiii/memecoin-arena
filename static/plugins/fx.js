/* fx.js — arcade effects for the pixel stage: coin bursts, smoke, shakes, rank banners, sparkles, shooting stars, day/night sky. */
(() => {
  const STAGE = document.getElementById("stage");
  if (!STAGE || typeof arenaPrefs === "undefined") return;

  const css = `
  .fx-layer { position: absolute; inset: 0; pointer-events: none; z-index: 20; overflow: hidden; }
  .fx-sky { position: absolute; left: 0; right: 0; top: 0; height: 62%; pointer-events: none; z-index: 1;
            background: linear-gradient(180deg, var(--fx-tint-a, transparent) 0%, var(--fx-tint-b, transparent) 70%, transparent 100%);
            transition: background 2s linear; }
  .fx-p { position: absolute; width: var(--s, 6px); height: var(--s, 6px); background: var(--col, var(--gold)); left: 0; top: 0;
          image-rendering: pixelated; animation: fx-burst var(--dur, 1.1s) steps(12) forwards; box-shadow: inset -2px -2px 0 rgba(0,0,0,.25); }
  @keyframes fx-burst {
    0%   { transform: translate(0, 0) rotate(0deg); opacity: 1; }
    40%  { transform: translate(calc(var(--dx) * .6), var(--up)) rotate(var(--rot)); opacity: 1; }
    100% { transform: translate(var(--dx), var(--fall)) rotate(calc(var(--rot) * 2)); opacity: 0; }
  }
  .fx-smoke { position: absolute; width: var(--s, 8px); height: var(--s, 8px); background: #8a86a6; opacity: .85; left: 0; top: 0;
              animation: fx-smoke var(--dur, 1.4s) steps(9) forwards; }
  @keyframes fx-smoke {
    0%   { transform: translate(0, 0) scale(1); opacity: .85; }
    100% { transform: translate(var(--dx), var(--up)) scale(2.2); opacity: 0; }
  }
  .fx-flash { position: absolute; inset: 0; background: var(--moon); opacity: 0; animation: fx-flash .42s steps(4) forwards; }
  @keyframes fx-flash { 0% { opacity: .75; } 100% { opacity: 0; } }
  .fx-shake { animation: fx-shake .45s steps(9) !important; }
  @keyframes fx-shake {
    0% { transform: translate(0, 0); } 20% { transform: translate(-6px, 2px); } 40% { transform: translate(5px, -3px); }
    60% { transform: translate(-4px, 3px); } 80% { transform: translate(3px, -2px); } 100% { transform: translate(0, 0); }
  }
  .fx-win { position: absolute; left: 50%; top: 34%; transform: translateX(-50%); white-space: nowrap; text-align: center;
            font: 400 clamp(34px, 9vw, 64px)/1 var(--pixel); color: var(--gold); text-shadow: 3px 3px 0 var(--ink), -2px -2px 0 var(--ink), 6px 6px 0 rgba(0,0,0,.35);
            animation: fx-win 2.1s steps(14) forwards; }
  .fx-win small { display: block; font: 400 .55em/1 var(--pixel); color: var(--profit); letter-spacing: .02em; }
  @keyframes fx-win {
    0% { opacity: 0; transform: translateX(-50%) scale(.3); } 12% { opacity: 1; transform: translateX(-50%) scale(1.15); }
    22% { transform: translateX(-50%) scale(1); } 80% { opacity: 1; transform: translateX(-50%) scale(1) translateY(0); }
    100% { opacity: 0; transform: translateX(-50%) scale(1) translateY(-30px); }
  }
  .fx-banner { position: absolute; left: 0; right: 0; top: 38%; padding: 10px 16px; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
               background: var(--ink); color: var(--fx-c, var(--gold)); border-top: 4px solid var(--fx-c, var(--gold)); border-bottom: 4px solid var(--fx-c, var(--gold));
               box-shadow: 0 0 0 4px var(--night); font: 400 clamp(28px, 7vw, 46px)/1 var(--pixel); text-shadow: 2px 2px 0 rgba(0,0,0,.6);
               animation: fx-slide 2.6s forwards; }
  .fx-banner::before, .fx-banner::after { content: ""; position: absolute; top: 50%; width: 10px; height: 10px; margin-top: -5px; background: var(--fx-c, var(--gold)); }
  .fx-banner::before { left: 10px; } .fx-banner::after { right: 10px; }
  @keyframes fx-slide {
    0% { transform: translateX(-100%); animation-timing-function: steps(7, end); }
    16% { transform: translateX(0); animation-timing-function: steps(1, end); }
    84% { transform: translateX(0); animation-timing-function: steps(7, end); }
    100% { transform: translateX(100%); }
  }
  .fx-crown { position: absolute; width: 28px; height: 22px; left: 0; top: 0; transform: translate(-50%, -100%);
              animation: fx-crown 2.6s steps(2) forwards; }
  .fx-crown svg { width: 100%; height: 100%; display: block; }
  @keyframes fx-crown { 0% { opacity: 0; translate: 0 8px; } 10% { opacity: 1; translate: 0 0; } 50% { translate: 0 -4px; } 90% { opacity: 1; translate: 0 0; } 100% { opacity: 0; } }
  .fx-bulb { position: absolute; width: 22px; height: 26px; left: 0; top: 0; transform: translate(-50%, -100%); animation: fx-bulb 1.3s steps(6) forwards; }
  .fx-bulb svg { width: 100%; height: 100%; display: block; }
  @keyframes fx-bulb { 0% { opacity: 0; translate: 0 6px; } 15% { opacity: 1; translate: 0 0; } 75% { opacity: 1; } 100% { opacity: 0; translate: 0 -10px; } }
  .fx-spark { position: absolute; width: 4px; height: 4px; left: 0; top: 0; background: var(--col, var(--moon));
              animation: fx-spark var(--dur, 1s) steps(5) forwards; }
  @keyframes fx-spark { 0% { opacity: 0; transform: translate(0,0) scale(1); } 20% { opacity: 1; transform: translate(0,0) scale(1.8); }
                        100% { opacity: 0; transform: translate(var(--dx), var(--up)) scale(.5); } }
  .fx-star { position: absolute; width: 4px; height: 4px; background: var(--moon); left: 0; top: 0;
             box-shadow: -4px 2px 0 rgba(238,234,251,.85), -8px 4px 0 rgba(238,234,251,.65), -12px 6px 0 rgba(238,234,251,.45),
                         -16px 8px 0 rgba(238,234,251,.3), -20px 10px 0 rgba(238,234,251,.15);
             animation: fx-star var(--dur, 1.3s) steps(16) forwards; }
  @keyframes fx-star { 0% { transform: translate(0,0); opacity: 1; } 85% { opacity: 1; } 100% { transform: translate(var(--dx), var(--dy)); opacity: 0; } }
  .fx-btn.tb-btn { font: 500 13px/1 var(--body); color: var(--moon); background: var(--dusk); border: 1px solid var(--seam); padding: 6px 10px; border-radius: 3px; cursor: pointer; }
  .fx-btn.tb-btn[aria-pressed="true"] { border-color: var(--gold); background: #2a2350; }
  @media (prefers-reduced-motion: reduce) {
    .fx-banner, .fx-win, .fx-crown, .fx-bulb { animation: none !important; transform: none; }
    .fx-win { transform: translateX(-50%); }
    .fx-crown, .fx-bulb { transform: translate(-50%, -100%); }
    .fx-p, .fx-smoke, .fx-star, .fx-spark, .fx-flash { display: none !important; }
    .fx-shake { animation: none !important; }
  }
  @media (max-width: 480px) { .fx-banner { padding: 8px 10px; } }`;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  /* layers */
  const layer = document.createElement("div");
  layer.className = "fx-layer";
  layer.setAttribute("aria-hidden", "true");
  STAGE.appendChild(layer);
  const sky = document.createElement("div");
  sky.className = "fx-sky";
  sky.setAttribute("aria-hidden", "true");
  const lanes = document.getElementById("lanes");
  if (lanes) STAGE.insertBefore(sky, lanes); else STAGE.appendChild(sky);

  let enabled = arenaPrefs.get("fx", true) !== false;
  const reduce = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : {matches: false};
  const motion = () => enabled && !reduce.matches;
  const rnd = (a, b) => a + Math.random() * (b - a);
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const laneOf = name => document.querySelector(`.lane[data-name="${CSS.escape(name)}"]`);
  const agentColor = name => {
    try { const a = agentByName(name); if (a) return colorOf(a); } catch {}
    const l = laneOf(name);
    return (l && l.style.getPropertyValue("--c")) || "var(--gold)";
  };
  // Where on the stage (in layer px) a lane's sprite sits. `k` scales effects to the lane width
  // (1 at a roomy ~130px lane, down to .4 when 14 lanes squeeze onto a phone), read at runtime.
  function anchor(name) {
    const lane = laneOf(name);
    if (!lane) return null;
    const sp = lane.querySelector(".sprite") || lane;
    const r = sp.getBoundingClientRect(), s = STAGE.getBoundingClientRect(), lw = lane.getBoundingClientRect().width || r.width;
    const k = clamp(lw / 130, .4, 1);
    return {x: r.left - s.left + r.width / 2, y: r.top - s.top + r.height / 2, top: r.top - s.top, w: r.width, lw, k};
  }
  function spawn(cls, vars, life) {
    const el = document.createElement("div");
    el.className = cls;
    for (const k in vars) el.style.setProperty(k, vars[k]);
    layer.appendChild(el);
    setTimeout(() => el.remove(), life);
    return el;
  }

  /* toolbar toggle */
  const tb = document.getElementById("toolbar");
  let btn;
  if (tb) {
    btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tb-btn fx-btn";
    btn.textContent = "Effects";
    btn.title = "Arcade effects on the stage";
    btn.setAttribute("aria-pressed", String(enabled));
    btn.addEventListener("click", () => { enabled = !enabled; arenaPrefs.set("fx", enabled); sync(); });
    tb.appendChild(btn);
  }
  function sync() {
    if (btn) btn.setAttribute("aria-pressed", String(enabled));
    if (!enabled) { layer.replaceChildren(); clearTimeout(starTimer); starTimer = 0; STAGE.classList.remove("fx-shake"); }
    else scheduleStar();
    tintSky();
  }
  document.addEventListener("arena:prefs", e => {
    if (e.detail && e.detail.key === "fx") { enabled = e.detail.value !== false; sync(); }
  });

  /* 1. profitable sell: coin burst, big win flash + banner */
  function coinBurst(name, pnl) {
    const a = anchor(name);
    if (!a) return;
    const col = agentColor(name), k = a.k;
    const n = Math.round(clamp(10 + pnl * 1.6, 10, 70) * (0.5 + k * 0.5));
    const spread = clamp(40 + pnl * 2, 40, 140) * k;
    for (let i = 0; i < n; i++) {
      const gold = Math.random() < .55, size = Math.random() < .3 ? 8 : 5;
      spawn("fx-p", {
        "--dx": `${rnd(-spread, spread)}px`, "--up": `${-rnd(30, 60 + spread * .6) * (0.7 + k * 0.3)}px`, "--fall": `${rnd(40, 110) * k}px`,
        "--rot": `${rnd(-180, 180)}deg`, "--dur": `${rnd(.9, 1.5)}s`, "--s": `${Math.max(3, Math.round(size * (0.6 + k * 0.4)))}px`,
        "--col": gold ? (Math.random() < .5 ? "var(--gold)" : "#ffe08a") : (Math.random() < .5 ? col : "var(--profit)"),
        left: `${a.x + rnd(-10, 10) * k}px`, top: `${a.y + rnd(-10, 10) * k}px`,
      }, 1600);
    }
  }
  function bigWin(pnl) {
    if (motion()) spawn("fx-flash", {}, 500);
    const el = spawn("fx-win", {}, 2200);
    el.textContent = "Big win ";
    const s = document.createElement("small");
    s.textContent = signed(pnl);
    el.appendChild(s);
  }

  /* 2. losing sell: smoke + shake */
  function smoke(name) {
    const a = anchor(name);
    if (!a) return;
    const k = a.k, n = Math.round(9 * (0.5 + k * 0.5));
    for (let i = 0; i < n; i++) {
      spawn("fx-smoke", {
        "--dx": `${rnd(-26, 26) * k}px`, "--up": `${-rnd(30, 70) * (0.7 + k * 0.3)}px`, "--dur": `${rnd(1, 1.6)}s`, "--s": `${Math.round((Math.random() < .4 ? 10 : 7) * (0.6 + k * 0.4))}px`,
        left: `${a.x + rnd(-16, 16) * k}px`, top: `${a.y + rnd(-6, 14) * k}px`,
      }, 1700);
    }
  }
  let shakeTimer = 0;
  function shake() {
    STAGE.classList.remove("fx-shake"); void STAGE.offsetWidth; STAGE.classList.add("fx-shake");
    clearTimeout(shakeTimer);
    shakeTimer = setTimeout(() => STAGE.classList.remove("fx-shake"), 500);
  }

  /* 3. leader change: full-width banner + crown */
  function crown(name) {
    const a = anchor(name);
    if (!a) return;
    const k = a.k;
    const el = spawn("fx-crown", {left: `${a.x}px`, top: `${a.top - 2}px`, width: `${Math.round(28 * (0.6 + k * 0.4))}px`, height: `${Math.round(22 * (0.6 + k * 0.4))}px`}, 2700);
    el.innerHTML = `<svg viewBox="0 0 7 5" shape-rendering="crispEdges" aria-hidden="true">
      <path fill="#f7c548" d="M0 1h1v1h1v1h1V1h1v2h1V2h1V1h1v4H0z"/>
      <path fill="#ff6b7a" d="M1 4h1v1H1zM3 4h1v1H3zM5 4h1v1H5z"/></svg>`;
    if (!motion()) return;
    for (let i = 0; i < Math.round(10 * (0.5 + k * 0.5)); i++) {
      spawn("fx-spark", {
        "--dx": `${rnd(-30, 30) * k}px`, "--up": `${-rnd(10, 40)}px`, "--dur": `${rnd(.8, 1.6)}s`, "--col": Math.random() < .5 ? "var(--gold)" : "var(--moon)",
        left: `${a.x + rnd(-24, 24) * k}px`, top: `${a.top - 14 + rnd(-10, 10)}px`,
      }, 1700);
    }
  }
  function takesFirst(name) {
    const el = spawn("fx-banner", {"--fx-c": agentColor(name)}, 2700);
    const ag = (() => { try { return agentByName(name); } catch { return null; } })();
    const team = ag ? (typeof teamOf === "function" ? teamName(teamOf(ag)) : ag.kind === "llm" ? "Team Claude" : "Team Bots") : "";
    el.textContent = `${name} takes 1st`;
    if (team && STAGE.clientWidth >= 560) {  // room for the team tag on wider stages only
      const s = document.createElement("small");
      s.textContent = ` · ${team}`;
      s.style.cssText = "font-size:.55em;color:var(--moon);opacity:.8";
      el.appendChild(s);
    }
    crown(name);
  }

  /* 4. Claude decision: lightbulb sparkle */
  function lightbulb(name) {
    const a = anchor(name);
    if (!a) return;
    const k = a.k;
    const el = spawn("fx-bulb", {left: `${a.x + a.w * .38}px`, top: `${a.top + 2}px`, width: `${Math.round(22 * (0.6 + k * 0.4))}px`, height: `${Math.round(26 * (0.6 + k * 0.4))}px`}, 1400);
    el.innerHTML = `<svg viewBox="0 0 6 7" shape-rendering="crispEdges" aria-hidden="true">
      <path fill="#ffe08a" d="M1 0h4v1h1v3H5v1H1V4H0V1h1z"/><path fill="#f7c548" d="M2 1h1v2H2z"/>
      <path fill="#a39dcb" d="M2 5h2v1H2zM2 6h2v1H2z"/></svg>`;
    if (!motion()) return;
    for (let i = 0; i < Math.round(6 * (0.5 + k * 0.5)); i++) {
      spawn("fx-spark", {
        "--dx": `${rnd(-22, 22) * k}px`, "--up": `${-rnd(8, 28)}px`, "--dur": `${rnd(.7, 1.2)}s`, "--col": "#ffe08a",
        left: `${a.x + a.w * .38 + rnd(-14, 14) * k}px`, top: `${a.top - 10 + rnd(-8, 8)}px`,
      }, 1300);
    }
  }

  /* 5. ambient: shooting star + day/night tint */
  let starTimer = 0;
  function shootingStar() {
    if (!motion()) return;
    const W = STAGE.clientWidth, H = STAGE.clientHeight;
    const x0 = rnd(0, W * .6), y0 = rnd(10, H * .25), len = rnd(W * .3, W * .55);
    spawn("fx-star", {left: `${x0}px`, top: `${y0}px`, "--dx": `${len}px`, "--dy": `${len * .5}px`, "--dur": `${rnd(1, 1.6)}s`}, 1800);
  }
  function scheduleStar() {
    clearTimeout(starTimer);
    if (!motion()) { starTimer = 0; return; }
    starTimer = setTimeout(() => { shootingStar(); scheduleStar(); }, rnd(20000, 40000));
  }
  function tintSky() {
    let a = "transparent", b = "transparent";
    if (enabled) {
      const h = new Date().getHours();
      if (h >= 5 && h < 8) { a = "rgba(255, 128, 170, .16)"; b = "rgba(255, 160, 120, .08)"; }          // dawn
      else if (h >= 8 && h < 17) { a = "rgba(130, 120, 230, .18)"; b = "rgba(120, 140, 240, .08)"; }   // day
      else if (h >= 17 && h < 20) { a = "rgba(255, 140, 60, .16)"; b = "rgba(150, 70, 190, .12)"; }    // dusk
    }
    sky.style.setProperty("--fx-tint-a", a);
    sky.style.setProperty("--fx-tint-b", b);
  }

  /* wiring */
  let leader = null;
  function onData(d) {
    const top = d && d.agents && d.agents[0] && d.agents[0].name;
    if (!top) return;
    if (leader !== null && top !== leader && enabled) takesFirst(top);
    leader = top;
  }
  function onTrade(t) {
    if (!enabled || !t || t.side !== "sell") return;
    const pnl = Number(t.pnl ?? 0);
    if (pnl > 0) {
      if (motion()) coinBurst(t.agent, pnl);
      if (pnl > 20) bigWin(pnl);
    } else if (pnl < -5) {
      if (motion()) { smoke(t.agent); shake(); }
    }
  }
  function onDecision(d) {
    if (!enabled || !d || !d.agent) return;
    lightbulb(d.agent);
  }

  if (typeof data !== "undefined" && data) onData(data);
  document.addEventListener("arena:data", e => onData(e.detail));
  document.addEventListener("arena:trade", e => onTrade(e.detail));
  document.addEventListener("arena:decision", e => onDecision(e.detail));
  if (reduce.addEventListener) reduce.addEventListener("change", sync);
  tintSky();
  setInterval(tintSky, 60000);
  scheduleStar();
})();
