import { api, auth } from "./api.js";
import { esc, state, toast } from "./ui.js";
import { loginView, registerView } from "./views/auth.js";
import { marketView, myBidsView, myJobsView } from "./views/lists.js";
import { jobEditView } from "./views/jobEdit.js";
import { jobDetailView } from "./views/jobDetail.js";
import { profileView } from "./views/profile.js";
import { companyView, directoryView } from "./views/directory.js";

const routes = [
  [/^\/login$/, loginView, { public: true }],
  [/^\/register$/, registerView, { public: true }],
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

  if (!opts.public && !state.me) { location.hash = "#/login"; return; }
  if (opts.public && state.me) { location.hash = home(); return; }
  if (opts.role && state.me.role !== opts.role) { location.hash = home(); return; }

  if (opts.public) {
    root.innerHTML = `<main class="auth-wrap" id="view"></main>`;
  } else {
    root.innerHTML = `${nav(path)}<main class="page" id="view"><div class="loading">Φόρτωση…</div></main>`;
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

export function setSession(payload) {
  auth.token = payload.token;
  state.me = payload.user;
  location.hash = home();
}

export function rerender() { render(); }

window.addEventListener("hashchange", render);
window.addEventListener("unhandledrejection", (e) => toast(e.reason?.message || "Σφάλμα", "error"));
render();
