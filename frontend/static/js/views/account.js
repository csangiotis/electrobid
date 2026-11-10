import { api } from "../api.js";
import { busy, esc, formData, fmt, state, toast } from "../ui.js";

const card = (inner) => `<section class="auth-card">${inner}</section>`;
const brandMini = `<div class="auth-title mini">subcontractor<b>.gr</b></div>`;

export async function forgotView(main) {
  main.innerHTML = card(`${brandMini}
    <h2>Ξεχάσατε τον κωδικό;</h2>
    <p class="muted">Γράψτε το email του λογαριασμού σας και θα σας στείλουμε σύνδεσμο για νέο κωδικό.</p>
    <form id="f" class="stack">
      <label>Email<input name="email" type="email" required autocomplete="username"></label>
      <button class="btn primary block">Αποστολή συνδέσμου</button>
      <p class="muted center"><a href="#/login">Πίσω στη σύνδεση</a></p>
    </form>`);
  const f = main.querySelector("#f");
  f.onsubmit = (e) => {
    e.preventDefault();
    busy(f.querySelector("button"), async () => {
      const r = await api("auth/password-reset", { method: "POST", body: formData(f) });
      f.innerHTML = `<div class="banner ok">${esc(r.detail)}</div><p class="muted">Ελέγξτε και τα ανεπιθύμητα (spam).</p>
        <p class="center"><a href="#/login">Πίσω στη σύνδεση</a></p>`;
    });
  };
}

export async function resetView(main, [uid, token]) {
  main.innerHTML = card(`${brandMini}
    <h2>Νέος κωδικός</h2>
    <form id="f" class="stack">
      <label>Νέος κωδικός <small>(τουλάχιστον 8 χαρακτήρες)</small><input name="password" type="password" minlength="8" required autocomplete="new-password"></label>
      <label>Επανάληψη<input name="password2" type="password" minlength="8" required autocomplete="new-password"></label>
      <button class="btn primary block">Αποθήκευση κωδικού</button>
    </form>`);
  const f = main.querySelector("#f");
  f.onsubmit = (e) => {
    e.preventDefault();
    if (f.password.value !== f.password2.value) { toast("Οι κωδικοί δεν ταιριάζουν.", "error"); return; }
    busy(f.querySelector("button"), async () => {
      await api("auth/password-reset/confirm", { method: "POST", body: { uid, token, password: f.password.value } });
      toast("Ο κωδικός άλλαξε. Συνδεθείτε με τον νέο κωδικό.", "ok");
      location.hash = "#/login";
    });
  };
}

export async function verifyView(main, [uid, token]) {
  main.innerHTML = card(`${brandMini}<h2>Επιβεβαίωση email</h2><p class="muted" id="msg">Έλεγχος…</p>`);
  const msg = main.querySelector("#msg");
  try {
    await api("auth/verify-email", { method: "POST", body: { uid, token } });
    if (state.me) { state.me.email_verified = true; state.me.needs_verification = false; }
    msg.outerHTML = `<div class="banner ok">Το email σας επιβεβαιώθηκε.</div>
      <a class="btn primary block" href="${state.me ? "#/" : "#/login"}">Συνέχεια</a>`;
  } catch (err) {
    msg.outerHTML = `<div class="banner warn">${esc(err.message)}</div>
      <p class="muted">Συνδεθείτε και πατήστε «Αποστολή ξανά» στην ειδοποίηση στο πάνω μέρος της σελίδας.</p>
      <a class="btn block" href="${state.me ? "#/" : "#/login"}">Συνέχεια</a>`;
  }
}

export async function notificationsView(main, _p, stale) {
  const data = await api("notifications");
  if (stale()) return;
  main.innerHTML = `
  <div class="page-head"><div><h1>Ειδοποιήσεις</h1>
    <p class="muted">Οι τελευταίες 50. Ποια λαμβάνετε και με email το ρυθμίζετε στο <a href="#/profile">προφίλ</a>.</p></div>
    ${data.unread ? `<button class="btn" id="all">Σήμανση όλων ως αναγνωσμένων</button>` : ""}</div>
  <div class="panel narrow">${data.items.length ? `<ul class="notif-list full">${data.items.map(notifItem).join("")}</ul>`
    : `<p class="muted">Δεν υπάρχουν ειδοποιήσεις.</p>`}</div>`;
  main.addEventListener("click", (e) => {
    const a = e.target.closest("[data-notif]");
    if (a) api("notifications/read", { method: "POST", body: { ids: [a.dataset.notif] } }).catch(() => {});
  });
  main.querySelector("#all")?.addEventListener("click", async () => {
    await api("notifications/read", { method: "POST", body: {} });
    dispatchEvent(new HashChangeEvent("hashchange"));
  });
}

export function notifItem(n) {
  return `<li class="${n.read ? "" : "unread"}"><a href="${esc(n.url || "#/notifications")}" data-notif="${n.id}">
    <b>${esc(n.title)}</b>${n.body ? `<span class="nb">${esc(n.body.split("\n")[0])}</span>` : ""}
    <small class="muted">${fmt.datetime(n.created_at)}</small></a></li>`;
}
