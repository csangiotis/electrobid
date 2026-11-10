import { api } from "../api.js";
import { setSession } from "../app.js";
import { busy, esc, formData, options, state } from "../ui.js";

const brand = `
  <div class="auth-brand">
    <svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7"/><path d="M18 4 8 18h7l-2 10 11-15h-7z"/></svg>
    <div><div class="auth-title">Electro<b>Bid</b></div>
    <p>Προσφορές ηλεκτρολογικών έργων: ο εργολάβος ανεβάζει προμέτρηση και σχέδια, οι υπεργολάβοι τιμολογούν γραμμή-γραμμή.</p></div>
  </div>`;

export async function loginView(main) {
  main.innerHTML = `
  <section class="auth-card">
    ${brand}
    <form id="f" class="stack">
      <label>Email<input name="email" type="email" required autocomplete="username"></label>
      <label>Κωδικός<input name="password" type="password" required autocomplete="current-password"></label>
      <button class="btn primary block">Σύνδεση</button>
      <p class="muted center">Νέος χρήστης; <a href="#/register">Δημιουργία λογαριασμού</a></p>
    </form>
  </section>`;
  const f = main.querySelector("#f");
  f.onsubmit = (e) => {
    e.preventDefault();
    busy(f.querySelector("button"), async () => setSession(await api("auth/login", { method: "POST", body: formData(f) })));
  };
}

export async function registerView(main) {
  main.innerHTML = `
  <section class="auth-card wide">
    ${brand}
    <form id="f" class="stack">
      <fieldset class="role-pick">
        <legend>Ποιος είστε;</legend>
        <label class="role-opt"><input type="radio" name="role" value="contractor" required>
          <span><b>Εργολάβος</b><small>Δημοσιεύω εργασίες και ζητάω προσφορές</small></span></label>
        <label class="role-opt"><input type="radio" name="role" value="subcontractor" required checked>
          <span><b>Υπεργολάβος</b><small>Βρίσκω εργασίες και δίνω προσφορές</small></span></label>
      </fieldset>
      <div class="grid2">
        <label>Όνομα<input name="first_name" required></label>
        <label>Επώνυμο<input name="last_name" required></label>
        <label>Email<input name="email" type="email" required autocomplete="username"></label>
        <label>Κωδικός <small>(τουλάχιστον 8 χαρακτήρες)</small><input name="password" type="password" minlength="8" required autocomplete="new-password"></label>
      </div>
      <h3>Στοιχεία εταιρείας</h3>
      <div class="grid2">
        <label>Επωνυμία<input name="c_name" required></label>
        <label>ΑΦΜ<input name="c_vat_number" required pattern="\\d{9}" inputmode="numeric" maxlength="9"></label>
        <label>Έδρα (περιφέρεια)<select name="c_region" required>${options("regions", "attiki")}</select></label>
        <label>Πόλη<input name="c_city"></label>
        <label>Τηλέφωνο<input name="c_phone" type="tel"></label>
        <label>Κατηγορία άδειας ηλεκτρολόγου<select name="c_license_category">${options("licenses", "", { empty: "—" })}</select></label>
      </div>
      <div class="sub-only">
        <label>Ειδικότητες</label>
        <div class="chips">${state.choices.specialties.map((s) =>
          `<label class="chip"><input type="checkbox" name="c_specialties" value="${esc(s.value)}"><span>${esc(s.label)}</span></label>`).join("")}</div>
        <label>Περιοχές δραστηριότητας</label>
        <div class="chips">${state.choices.regions.map((s) =>
          `<label class="chip"><input type="checkbox" name="c_service_regions" value="${esc(s.value)}"><span>${esc(s.label)}</span></label>`).join("")}</div>
      </div>
      <button class="btn primary block">Δημιουργία λογαριασμού</button>
      <p class="muted center">Έχετε ήδη λογαριασμό; <a href="#/login">Σύνδεση</a></p>
    </form>
  </section>`;
  const f = main.querySelector("#f");
  const toggle = () => {
    main.querySelector(".sub-only").hidden = f.role.value !== "subcontractor";
  };
  f.addEventListener("change", toggle);
  toggle();
  f.onsubmit = (e) => {
    e.preventDefault();
    const fd = new FormData(f);
    const body = { company: {} };
    for (const [k, v] of fd.entries()) {
      if (k.startsWith("c_")) {
        const key = k.slice(2);
        if (key === "specialties" || key === "service_regions") (body.company[key] ||= []).push(v);
        else body.company[key] = v;
      } else body[k] = v;
    }
    busy(f.querySelector("button.primary"), async () =>
      setSession(await api("auth/register", { method: "POST", body })));
  };
}
