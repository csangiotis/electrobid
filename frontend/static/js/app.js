import { api, auth } from "./api.js";
import { esc, state, toast } from "./ui.js";
import { loginView, registerView } from "./views/auth.js";
import { marketView, myBidsView, myJobsView } from "./views/lists.js";
import { jobEditView } from "./views/jobEdit.js";
import { jobDetailView } from "./views/jobDetail.js";
import { profileView } from "./views/profile.js";
import { companyView, directoryView } from "./views/directory.js";
import { forgotView, notifItem, notificationsView, resetView, verifyView } from "./views/account.js";
import { privacyView, termsView } from "./views/legal.js";

const routes = [
  [/^\/login$/, loginView, { public: true }],
  [/^\/register$/, registerView, { public: true }],
  [/^\/forgot$/, forgotView, { public: true }],
  [/^\/reset\/([^/]+)\/([^/]+)$/, resetView, { public: true }],
  [/^\/verify\/([^/]+)\/([^/]+)$/, verifyView, { any: true }],
  [/^\/terms$/, termsView, { any: true }],
  [/^\/privacy$/, privacyView, { any: true }],
  [/^\/notifications$/, notificationsView],
  [/^\/jobs$/, marketView],
  [/^\/jobs\/new$/, jobEditView, { role: "contractor" }],
  [/^\/jobs\/(\d+)\/edit$/, jobEditView, { role: "contractor" }],
  [/^\/jobs\/(\d+)$/, jobDetailView],
  [/^\/my-jobs$/, myJobsView, { role: "contractor" }],
  [/^\/my-bids$/, myBidsView, { role: "subcontractor" }],
  [/^\/profile$/, profileView],
  [/^\/directory$/, directoryView],
  [/^\/companies\/(\d+)$/, companyView],
];

export function home() {
  return state.me?.role === "contractor" ? "#/my-jobs" : "#/jobs";
}

function nav(path) {
  const me = state.me;
  const links = me.role === "contractor"
    ? [["#/my-jobs", "Οι εργασίες μου"], ["#/jobs", "Αγορά εργασιών"], ["#/directory", "Υπεργολάβοι"]]
    : [["#/jobs", "Διαθέσιμες εργασίες"], ["#/my-bids", "Οι προσφορές μου"], ["#/directory", "Εργολάβοι"]];
  const active = (href) => {
    const h = href.slice(1);
    if (path === h) return "active";
    if (h === "/directory" && path.startsWith("/companies/")) return "active";
    return "";
  };
  return `
  <header class="topbar">
    <a class="brand" href="${home()}">
      <svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7"/><path d="M6 20h9v6H6zM17 20h9v6h-9zM11.5 12h9v6h-9zM14 5.5h4v4.5h-4z"/></svg>
      <span>subcontractor<b>.gr</b></span>
    </a>
    <nav>${links.map(([h, t]) => `<a href="${h}" class="${active(h)}">${t}</a>`).join("")}</nav>
    <div class="who">
      <div class="bell-wrap">
        <button class="bell" id="bell" title="Ειδοποιήσεις" aria-label="Ειδοποιήσεις">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-6V11a7 7 0 0 0-5.5-6.84V3a1.5 1.5 0 0 0-3 0v1.16A7 7 0 0 0 5 11v5l-2 2v1h18v-1l-2-2Z"/></svg>
          <span class="count" id="bell-count" hidden></span>
        </button>
        <div class="bell-pop" id="bell-pop" hidden></div>
      </div>
      ${me.role === "contractor" ? `<a class="btn primary sm" href="#/jobs/new">+ Νέα εργασία</a>` : ""}
      <a href="#/profile" class="me" title="Προφίλ">
        <span class="avatar">${esc((me.company?.name || me.email).slice(0, 1))}</span>
        <span class="me-text"><b>${esc(me.company?.name || "")}</b><small>${me.role === "contractor" ? "Εργολάβος" : "Υπεργολάβος"}</small></span>
      </a>
      <button class="btn ghost sm" id="logout">Έξοδος</button>
    </div>
  </header>`;
}

let renderSeq = 0;

async function render() {
  const seq = ++renderSeq;
  const path = (location.hash || "#/").slice(1).split("?")[0] || "/";
  const root = document.getElementById("app");

  if (!state.choices) state.choices = await api("choices");
  if (auth.token && !state.me) {
    try { state.me = await api("me"); } catch { auth.token = null; }
  }

  const match = routes.map(([re, view, opts = {}]) => [re.exec(path), view, opts]).find(([m]) => m);
  if (!match) { location.hash = state.me ? home() : "#/login"; return; }
  const [m, view, opts] = match;

  if (!opts.public && !opts.any && !state.me) { location.hash = "#/login"; return; }
  if (opts.public && state.me) { location.hash = home(); return; }
  if (opts.role && state.me.role !== opts.role) { location.hash = home(); return; }

  if (opts.public || (opts.any && !state.me)) {
    root.innerHTML = `<main class="auth-wrap" id="view"></main>`;
  } else {
    root.innerHTML = `${nav(path)}${verifyBanner()}<main class="page" id="view"><div class="loading">Φόρτωση…</div></main>`;
    setupBell(root);
    root.querySelector("#resend")?.addEventListener("click", async (e) => {
      e.target.disabled = true;
      try { await api("auth/resend-verification", { method: "POST" }); toast("Στάλθηκε νέο email επιβεβαίωσης.", "ok"); }
      catch (err) { toast(err.message, "error"); e.target.disabled = false; }
    });
    root.querySelector("#logout").onclick = async () => {
      try { await api("auth/logout", { method: "POST" }); } catch { /* */ }
      auth.token = null; state.me = null; location.hash = "#/login";
    };
  }
  const main = root.querySelector("#view");
  try {
    await view(main, m.slice(1), () => seq !== renderSeq);
  } catch (err) {
    if (seq !== renderSeq) return;
    main.innerHTML = `<div class="empty"><h2>Δεν ήταν δυνατή η φόρτωση</h2><p>${esc(err.message)}</p>
      <a class="btn" href="${home()}">Επιστροφή</a></div>`;
  }
  window.scrollTo(0, 0);
}

function verifyBanner() {
  if (!state.me || state.me.email_verified) return "";
  return `<div class="verify-bar">Επιβεβαιώστε το email σας (${esc(state.me.email)}) από τον σύνδεσμο που σας στείλαμε${
    state.me.needs_verification ? ", για να μπορείτε να δημοσιεύετε εργασίες και να υποβάλλετε προσφορές" : ""}.
    <button class="btn sm ghost" id="resend">Αποστολή ξανά</button></div>`;
}

// ---- Ειδοποιήσεις (καμπανάκι) ----
let bellTimer;
async function refreshBell(root) {
  try {
    const data = await api("notifications");
    const count = root.querySelector("#bell-count");
    if (!count) return null;
    count.hidden = !data.unread;
    count.textContent = data.unread > 9 ? "9+" : data.unread;
    return data;
  } catch { return null; }
}
function setupBell(root) {
  clearInterval(bellTimer);
  refreshBell(root);
  bellTimer = setInterval(() => refreshBell(root), 60000);
  const pop = root.querySelector("#bell-pop");
  root.querySelector("#bell").onclick = async (e) => {
    e.stopPropagation();
    if (!pop.hidden) { pop.hidden = true; return; }
    pop.hidden = false;
    pop.innerHTML = `<div class="loading">Φόρτωση…</div>`;
    const data = await refreshBell(root);
    if (!data) return;
    pop.innerHTML = `<div class="bell-head"><b>Ειδοποιήσεις</b>${data.unread ? `<button class="link-btn" id="read-all">Όλες αναγνωσμένες</button>` : ""}</div>
      ${data.items.length ? `<ul class="notif-list">${data.items.slice(0, 8).map(notifItem).join("")}</ul>`
        : `<p class="muted small pad">Δεν υπάρχουν ειδοποιήσεις.</p>`}
      <a class="bell-all" href="#/notifications">Όλες οι ειδοποιήσεις</a>`;
    pop.querySelector("#read-all")?.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      await api("notifications/read", { method: "POST", body: {} });
      refreshBell(root); pop.hidden = true;
    });
  };
  pop.addEventListener("click", (e) => {
    const a = e.target.closest("[data-notif]");
    if (a) { api("notifications/read", { method: "POST", body: { ids: [a.dataset.notif] } }).catch(() => {}); pop.hidden = true; }
  });
}
document.addEventListener("click", (e) => {
  const pop = document.getElementById("bell-pop");
  if (pop && !e.target.closest(".bell-wrap")) pop.hidden = true;
});

export function setSession(payload) {
  auth.token = payload.token;
  state.me = payload.user;
  location.hash = home();
}

export function rerender() { render(); }

window.addEventListener("hashchange", render);
window.addEventListener("unhandledrejection", (e) => toast(e.reason?.message || "Σφάλμα", "error"));
render();
