import { api } from "../api.js";
import { esc, fmt, label, options, state, timeLeft, verifiedMark } from "../ui.js";

// Φωτογραφίες έργων: χρειάζονται το token, οπότε φορτώνονται με fetch ως blob.
const photoCache = new Map();
export async function loadPhotos(root) {
  for (const img of root.querySelectorAll("img[data-photo]")) {
    const id = img.dataset.photo;
    try {
      if (!photoCache.has(id)) {
        const res = await api(`projects/${id}/photo`, { raw: true });
        photoCache.set(id, URL.createObjectURL(await res.blob()));
      }
      img.src = photoCache.get(id);
      img.classList.add("loaded");
    } catch { img.remove(); }
  }
}
export function forgetPhoto(id) { photoCache.delete(String(id)); }

const roleWord = (role, plural) => (role === "contractor"
  ? (plural ? "Εργολάβοι" : "Εργολάβος") : (plural ? "Υπεργολάβοι" : "Υπεργολάβος"));

function initials(name) {
  return esc(name.split(/\s+/).filter((w) => /\p{L}/u.test(w[0] || "")).slice(0, 2).map((w) => w[0]).join("").toUpperCase());
}

function companyCard(c) {
  const years = c.founded_year ? new Date().getFullYear() - c.founded_year : null;
  return `
  <a class="company-card" href="#/companies/${c.id}">
    <div class="company-head">
      <span class="logo">${initials(c.name)}</span>
      <div><h3>${esc(c.name)} ${verifiedMark(c)}</h3>
      <p class="muted small">${esc([c.city, c.region_display].filter(Boolean).join(", "))}</p></div>
    </div>
    ${c.description ? `<p class="clamp">${esc(c.description)}</p>` : ""}
    <div class="chips static">${c.specialties.slice(0, 4).map((s) => `<span class="chip-s">${esc(label("specialties", s))}</span>`).join("")}
      ${c.specialties.length > 4 ? `<span class="chip-s more">+${c.specialties.length - 4}</span>` : ""}</div>
    <dl class="facts mini">
      <div><dt>Έργα</dt><dd>${c.projects_count}</dd></div>
      <div><dt>Άδεια</dt><dd>${c.license_category ? esc(c.license_display) : "—"}</dd></div>
      <div><dt>Προσωπικό</dt><dd>${c.employees ?? "—"}</dd></div>
      <div><dt>Εμπειρία</dt><dd>${years !== null ? `${years} έτη` : "—"}</dd></div>
    </dl>
  </a>`;
}

export async function directoryView(main, _p, stale) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const other = state.me.role === "contractor" ? "subcontractor" : "contractor";
  const role = params.get("role") || other;
  const lookingForSubs = role === "subcontractor";

  main.innerHTML = `
  <div class="page-head">
    <div><h1>${roleWord(role, true)}</h1>
    <p class="muted">${lookingForSubs
      ? "Βρείτε υπεργολάβους με βάση την περιοχή, την ειδικότητα, την άδεια και τα έργα τους."
      : "Δείτε εργολάβους, τα έργα τους και τις ανοιχτές εργασίες τους."}</p></div>
    <div class="seg">
      <a href="#/directory?role=subcontractor" class="${lookingForSubs ? "on" : ""}">Υπεργολάβοι</a>
      <a href="#/directory?role=contractor" class="${!lookingForSubs ? "on" : ""}">Εργολάβοι</a>
    </div>
  </div>
  <form class="filters dir" id="flt">
    <input type="search" name="q" placeholder="Όνομα, πόλη, έργο ή πελάτης" value="${esc(params.get("q") || "")}">
    <select name="region">${options("regions", params.get("region") || "", { empty: "Όλες οι περιοχές" })}</select>
    <select name="specialty">${options("specialties", params.get("specialty") || "", { empty: "Όλες οι ειδικότητες" })}</select>
    <select name="license">${options("licenses", params.get("license") || "", { empty: "Οποιαδήποτε άδεια" })}</select>
    <label class="check"><input type="checkbox" name="verified" value="1" ${params.get("verified") ? "checked" : ""}> Μόνο επαληθευμένες</label>
  </form>
  <p class="muted small" id="count"></p>
  <div id="list" class="cards"><div class="loading">Φόρτωση…</div></div>`;

  const flt = main.querySelector("#flt");
  let timer;
  const load = async () => {
    const qs = new URLSearchParams([["role", role], ...[...new FormData(flt)].filter(([, v]) => v)]);
    const list = await api(`companies?${qs}`);
    if (stale()) return;
    main.querySelector("#count").textContent = `${list.length} ${list.length === 1 ? "εταιρεία" : "εταιρείες"}`;
    main.querySelector("#list").innerHTML = list.length ? list.map(companyCard).join("")
      : `<div class="empty"><h2>Δεν βρέθηκαν εταιρείες</h2><p>Δοκιμάστε λιγότερα φίλτρα.</p></div>`;
  };
  flt.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 250); });
  flt.addEventListener("submit", (e) => e.preventDefault());
  await load();
}

export function projectCard(p, { editable = false } = {}) {
  return `
  <article class="project" data-id="${p.id}">
    ${p.has_photo ? `<div class="project-photo"><img data-photo="${p.id}" alt=""></div>` : ""}
    <div class="project-body">
      <div class="row wrap tight">${p.year ? `<span class="year">${p.year}</span>` : ""}
        ${p.category ? `<span class="tag">${esc(p.category_display)}</span>` : ""}
        ${p.value_range ? `<span class="badge muted">${esc(p.value_display)}</span>` : ""}</div>
      <h3>${esc(p.title)}</h3>
      <p class="muted small">${esc([p.client, p.location || p.region_display].filter(Boolean).join(" · "))}</p>
      ${p.description ? `<p class="small">${esc(p.description).replace(/\n/g, "<br>")}</p>` : ""}
      ${p.specialties.length ? `<div class="chips static">${p.specialties.map((s) => `<span class="chip-s">${esc(label("specialties", s))}</span>`).join("")}</div>` : ""}
      ${editable ? `<div class="row end tight"><button type="button" class="btn sm ghost" data-edit="${p.id}">Επεξεργασία</button>
        <button type="button" class="btn sm ghost danger-text" data-remove="${p.id}">Διαγραφή</button></div>` : ""}
    </div>
  </article>`;
}

export async function companyView(main, [id], stale) {
  const c = await api(`companies/${id}`);
  if (stale()) return;
  const isContractor = c.role === "contractor";
  const s = c.stats;
  const years = c.founded_year ? new Date().getFullYear() - c.founded_year : null;
  const website = c.website && /^https?:\/\//i.test(c.website) ? c.website : "";

  main.innerHTML = `
  <a class="back" href="#/directory?role=${c.role}">← ${roleWord(c.role, true)}</a>
  <section class="profile-hero panel">
    <span class="logo big">${initials(c.name)}</span>
    <div class="grow">
      <div class="row wrap tight"><span class="tag">${roleWord(c.role)}</span>
        ${c.verified ? `<span class="badge ok">✓ Επαληθευμένη</span>` : `<span class="badge muted">Μη επαληθευμένη</span>`}</div>
      <h1>${esc(c.name)}</h1>
      <p class="muted">${esc([c.city, c.region_display].filter(Boolean).join(", "))}${c.founded_year ? ` · από το ${c.founded_year}` : ""} · μέλος από ${fmt.date(c.member_since)}</p>
      <div class="row wrap contact">
        ${c.phone ? `<a class="btn sm" href="tel:${esc(c.phone.replace(/\s/g, ""))}">☎ ${esc(c.phone)}</a>` : ""}
        ${website ? `<a class="btn sm ghost" href="${esc(website)}" target="_blank" rel="noopener noreferrer">${esc(website.replace(/^https?:\/\//, ""))} ↗</a>` : ""}
        <span class="muted small">ΑΦΜ ${esc(c.vat_number)}</span>
      </div>
    </div>
    ${c.is_me ? `<a class="btn" href="#/profile">Επεξεργασία προφίλ</a>` : ""}
  </section>

  <div class="stats">
    ${isContractor ? `
      <div class="stat"><span>${s.jobs_published}</span>Εργασίες στην πλατφόρμα</div>
      <div class="stat live"><span>${s.jobs_open}</span>Ανοιχτές τώρα</div>
      <div class="stat ok"><span>${s.jobs_awarded}</span>Αναθέσεις</div>` : `
      <div class="stat"><span>${s.bids_submitted}</span>Προσφορές στην πλατφόρμα</div>
      <div class="stat ok"><span>${s.jobs_won}</span>Αναθέσεις που κέρδισε</div>`}
    <div class="stat warn"><span>${c.projects.length}</span>Έργα στο ιστορικό</div>
  </div>

  <div class="profile-layout">
    <div>
      ${c.description ? `<div class="panel"><h2>Η εταιρεία</h2><p>${esc(c.description).replace(/\n/g, "<br>")}</p></div>` : ""}
      ${isContractor && c.open_jobs.length ? `
        <div class="panel"><h2>Ανοιχτές εργασίες</h2>
          <ul class="link-list">${c.open_jobs.map((j) => `<li><a href="#/jobs/${j.id}"><b>${esc(j.title)}</b></a>
            <span class="muted small">${esc(j.location)} · λήξη ${esc(timeLeft(j.bid_deadline))}</span></li>`).join("")}</ul></div>` : ""}
      <h2 class="section">Έργα και εμπειρία</h2>
      ${c.projects.length ? `<div class="projects">${c.projects.map((p) => projectCard(p)).join("")}</div>`
        : `<div class="empty small-empty"><p>${c.is_me ? "Δεν έχετε προσθέσει έργα. Τα έργα είναι ο πιο πειστικός λόγος για να σας επιλέξουν." : "Η εταιρεία δεν έχει προσθέσει έργα ακόμα."}</p>
          ${c.is_me ? `<a class="btn primary" href="#/profile">Προσθήκη έργων</a>` : ""}</div>`}
    </div>
    <aside class="panel">
      <h3>Στοιχεία</h3>
      <dl class="kv">
        <dt>Άδεια ηλεκτρολόγου</dt><dd>${c.license_category ? esc(c.license_display) : "—"}</dd>
        <dt>Προσωπικό</dt><dd>${c.employees ?? "—"}</dd>
        <dt>Εμπειρία</dt><dd>${years !== null ? `${years} έτη` : "—"}</dd>
      </dl>
      ${c.specialties.length ? `<h3>Ειδικότητες</h3><div class="chips static">${c.specialties.map((x) => `<span class="chip-s">${esc(label("specialties", x))}</span>`).join("")}</div>` : ""}
      ${c.service_regions.length ? `<h3>Περιοχές δραστηριότητας</h3><div class="chips static">${c.service_regions.map((x) => `<span class="chip-s">${esc(label("regions", x))}</span>`).join("")}</div>` : ""}
    </aside>
  </div>`;
  loadPhotos(main);
}
