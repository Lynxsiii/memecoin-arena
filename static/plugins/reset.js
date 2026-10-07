/* Reset money: a toolbar button that puts every agent back to the starting cash after asking whether the Claudes
   keep their journals (they're backed up to a file either way). Calls POST /api/reset-money. */
(() => {
  "use strict";
  const toolbar = document.getElementById("toolbar");
  if (!toolbar || document.getElementById("rs-btn")) return;

  const style = document.createElement("style");
  style.textContent = `
  .rs-back { position: fixed; inset: 0; background: rgba(10, 8, 26, .72); display: grid; place-items: center; z-index: 60; padding: 16px; }
  .rs-dlg { background: var(--dusk); border: 2px solid var(--loss); max-width: 440px; width: 100%; padding: 20px 20px 16px; color: var(--moon);
            clip-path: polygon(0 6px, 6px 6px, 6px 0, calc(100% - 6px) 0, calc(100% - 6px) 6px, 100% 6px, 100% calc(100% - 6px),
                               calc(100% - 6px) calc(100% - 6px), calc(100% - 6px) 100%, 6px 100%, 6px calc(100% - 6px), 0 calc(100% - 6px)); }
  .rs-dlg h3 { margin: 0 0 8px; font: 400 28px/1 var(--pixel); color: var(--loss); }
  .rs-dlg p { margin: 0 0 10px; font-size: 14px; color: var(--haze); }
  .rs-dlg p b { color: var(--moon); font-weight: 500; }
  .rs-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  .rs-row button { font: 500 14px var(--body); padding: 8px 12px; border-radius: 3px; cursor: pointer; border: 1px solid var(--seam);
                   background: var(--night); color: var(--moon); }
  .rs-row button.rs-keep { border-color: var(--gold); }
  .rs-row button.rs-wipe { border-color: var(--loss); color: var(--loss); }
  .rs-row button:disabled { opacity: .5; cursor: wait; }
  .rs-msg { font-size: 13px; margin-top: 10px; min-height: 1em; }
  .rs-msg.err { color: var(--loss); }
  `;
  document.head.appendChild(style);

  const btn = document.createElement("button");
  btn.type = "button"; btn.id = "rs-btn"; btn.className = "tb-btn"; btn.textContent = "Reset money";
  btn.title = "Put every agent back to the starting cash";
  toolbar.appendChild(btn);

  let open = null;
  function close() { if (open) { open.remove(); open = null; btn.focus(); } }

  btn.addEventListener("click", () => {
    if (open) return;
    const cash = (typeof data !== "undefined" && data && data.start_cash) || 1000;
    open = document.createElement("div");
    open.className = "rs-back";
    open.innerHTML = `
      <div class="rs-dlg" role="dialog" aria-modal="true" aria-labelledby="rs-title">
        <h3 id="rs-title">Reset money?</h3>
        <p>Every agent goes back to <b>$${Number(cash).toLocaleString()}</b> with no open positions. This run's trades are archived
          as a season (still in <b>python days.py</b>); usage history, recordings and checks are kept.</p>
        <p>Should the Claudes keep the lessons in their journals? Every journal is <b>backed up to a file</b> in
          journal_backups either way.</p>
        <div class="rs-row">
          <button type="button" class="rs-keep" data-j="keep">Reset, keep journals</button>
          <button type="button" class="rs-wipe" data-j="wipe">Reset, wipe journals</button>
          <button type="button" class="rs-cancel">Cancel</button>
        </div>
        <div class="rs-msg" role="status"></div>
      </div>`;
    document.body.appendChild(open);
    const dlg = open.querySelector(".rs-dlg"), msg = open.querySelector(".rs-msg");
    open.querySelector(".rs-cancel").focus();
    open.addEventListener("click", e => { if (e.target === open) close(); });
    open.addEventListener("keydown", e => {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {  // keep focus inside the dialog
        const b = [...dlg.querySelectorAll("button")], i = b.indexOf(document.activeElement);
        e.preventDefault(); b[(i + (e.shiftKey ? b.length - 1 : 1)) % b.length].focus();
      }
    });
    open.querySelector(".rs-cancel").addEventListener("click", close);
    dlg.querySelectorAll("button[data-j]").forEach(b => b.addEventListener("click", async () => {
      dlg.querySelectorAll("button").forEach(x => x.disabled = true);
      msg.className = "rs-msg"; msg.textContent = "Resetting…";
      try {
        const r = await fetch("/api/reset-money", {method: "POST", headers: {"Content-Type": "application/json"},
                                                    body: JSON.stringify({journals: b.dataset.j})});
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
        msg.textContent = `Done. Season ${j.season} archived, journals ${j.journals}${j.backup ? ", backup saved" : ""}. Reloading…`;
        setTimeout(() => location.reload(), 1200);
      } catch (e) {
        msg.className = "rs-msg err"; msg.textContent = `Reset failed: ${e.message}`;
        dlg.querySelectorAll("button").forEach(x => x.disabled = false);
      }
    }));
  });
})();
