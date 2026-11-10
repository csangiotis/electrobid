import { api } from "../api.js";
import { bidBadge, companyLink, esc, fmt, options, phaseBadge, state, timeLeft, verifiedMark } from "../ui.js";

function jobCard(j) {
  const me = state.me;
  const urgent = j.bid_deadline && new Date(j.bid_deadline) - Date.now() < 48 * 3.6e6;
  return `
  <a class="job-card" href="#/jobs/${j.id}">
    <div class="job-card-top">
      <span class="tag">${esc(j.category_display)}</span>
      ${j.my_bid_status ? bidBadge(j.my_bid_status) : ""}
      ${j.is_owner ? `<span class="badge muted">Δική σας</span>` : ""}
    </div>
    <h3>${esc(j.title)}</h3>
    <p class="by">${esc(j.contractor.name)} ${verifiedMark(j.contractor)}</p>
    <dl class="facts">
      <div><dt>Τοποθεσία</dt><dd>${esc(j.location || j.region_display)}</dd></div>
      <div><dt>Γραμμές BOQ</dt><dd>${j.boq_count}</dd></div>
      <div><dt>Σχέδια/έγγραφα</dt><dd>${j.documents_count}</dd></div>
      <div><dt>Έναρξη</dt><dd>${j.start_date ? fmt.date(j.start_date) : "—"}</dd></div>
    </dl>
    <div class="job-card-foot">
      <span class="deadline ${urgent ? "urgent" : ""}">Λήξη ${esc(timeLeft(j.bid_deadline))}</span>
      <span class="muted">${j.bids_count} ${j.bids_count === 1 ? "προσφορά" : "προσφορές"}</span>
    </div>
    ${me.role === "subcontractor" && !j.my_bid_status ? `<span class="cta">Δείτε & προσφέρετε →</span>` : ""}
  </a>`;
}

export async function marketView(main, _p, stale) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  main.innerHTML = `
  <div class="page-head">
    <div><h1>${state.me.role === "subcontractor" ? "Διαθέσιμες εργασίες" : "Αγορά εργασιών"}</h1>
    <p class="muted">Ανοιχτές εργασίες που δέχονται προσφορές, ταξινομημένες κατά προθεσμία.</p></div>
  </div>
  <form class="filters" id="flt">
    <input type="search" name="q" placeholder="Αναζήτηση σε τίτλο, περιγραφή, τοποθεσία" value="${esc(params.get("q") || "")}">
    <select name="region">${options("regions", params.get("region") || "", { empty: "Όλες οι περιφέρειες" })}</select>
    <select name="category">${options("job_categories", params.get("category") || "", { empty: "Όλες οι κατηγορίες" })}</select>
  </form>
  <div id="list" class="cards"><div class="loading">Φόρτωση…</div></div>`;

  const flt = main.querySelector("#flt");
  if (state.me.role === "subcontractor" && !params.toString() && state.me.company?.service_regions?.length === 1) {
    flt.region.value = state.me.company.service_regions[0];
  }
  let timer;
  const load = async () => {
    const qs = new URLSearchParams([...new FormData(flt)].filter(([, v]) => v)).toString();
    const jobs = await api(`jobs${qs ? "?" + qs : ""}`);
    if (stale()) return;
    const list = main.querySelector("#list");
    list.innerHTML = jobs.length
      ? jobs.map(jobCard).join("")
      : `<div class="empty"><h2>Καμία ανοιχτή εργασία</h2><p>Δοκιμάστε άλλα φίλτρα ή ελέγξτε ξανά αργότερα.</p></div>`;
  };
  flt.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 250); });
  flt.addEventListener("submit", (e) => e.preventDefault());
  await load();
}

export async function myJobsView(main, _p, stale) {
  const jobs = await api("jobs?scope=mine");
  if (stale()) return;
  const active = jobs.filter((j) => ["draft", "bidding", "evaluation"].includes(j.phase));
  const past = jobs.filter((j) => !active.includes(j));
  const count = (p) => jobs.filter((j) => j.phase === p).length;

  const table = (rows) => `
    <div class="table-wrap"><table class="tbl">
      <thead><tr><th>Εργασία</th><th>Κατάσταση</th><th>Προθεσμία</th><th class="num">Προσφορές</th><th></th></tr></thead>
      <tbody>${rows.map((j) => `
        <tr>
          <td><a href="#/jobs/${j.id}" class="strong">${esc(j.title)}</a><div class="muted small">${esc(j.location || j.region_display)} · ${j.boq_count} γραμμές BOQ · ${j.documents_count} έγγραφα</div></td>
          <td>${phaseBadge(j.phase)}</td>
          <td>${j.bid_deadline ? `${fmt.datetime(j.bid_deadline)}<div class="muted small">${esc(timeLeft(j.bid_deadline))}</div>` : "—"}</td>
          <td class="num">${j.phase === "draft" ? "—" : j.bids_count}</td>
          <td class="actions">${j.phase === "draft"
            ? `<a class="btn sm" href="#/jobs/${j.id}/edit">Συνέχεια</a>`
            : j.phase === "evaluation"
              ? `<a class="btn sm primary" href="#/jobs/${j.id}?tab=bids">Σύγκριση</a>`
              : `<a class="btn sm ghost" href="#/jobs/${j.id}">Άνοιγμα</a>`}</td>
        </tr>`).join("")}</tbody>
    </table></div>`;

  main.innerHTML = `
  <div class="page-head">
    <div><h1>Οι εργασίες μου</h1><p class="muted">Δημοσιεύστε εργασίες, απαντήστε σε ερωτήσεις και συγκρίνετε προσφορές.</p></div>
    <a class="btn primary" href="#/jobs/new">+ Νέα εργασία</a>
  </div>
  <div class="stats">
    <div class="stat"><span>${count("draft")}</span>Πρόχειρα</div>
    <div class="stat live"><span>${count("bidding")}</span>Σε διαγωνισμό</div>
    <div class="stat warn"><span>${count("evaluation")}</span>Προς αξιολόγηση</div>
    <div class="stat ok"><span>${count("awarded")}</span>Ανατέθηκαν</div>
  </div>
  ${jobs.length === 0 ? `
    <div class="empty"><h2>Δεν έχετε εργασίες ακόμα</h2>
    <p>Δημιουργήστε την πρώτη: ανεβάστε την προμέτρηση σε Excel και τα σχέδια, ορίστε προθεσμία και δημοσιεύστε.</p>
    <a class="btn primary" href="#/jobs/new">Νέα εργασία</a></div>` : ""}
  ${active.length ? `<h2 class="section">Ενεργές</h2>${table(active)}` : ""}
  ${past.length ? `<h2 class="section">Ολοκληρωμένες / ακυρωμένες</h2>${table(past)}` : ""}`;
}

export async function myBidsView(main, _p, stale) {
  const bids = await api("my-bids");
  if (stale()) return;
  const result = (b) => {
    if (b.won === true) return `<span class="badge ok">Κερδίσατε</span>`;
    if (b.won === false) return `<span class="badge muted">Ανατέθηκε αλλού</span>`;
    if (b.job.phase === "evaluation") return `<span class="badge warn">Σε αξιολόγηση</span>`;
    if (b.job.phase === "cancelled") return `<span class="badge muted">Ακυρώθηκε</span>`;
    return `<span class="muted small">Λήξη ${esc(timeLeft(b.job.bid_deadline))}</span>`;
  };
  main.innerHTML = `
  <div class="page-head"><div><h1>Οι προσφορές μου</h1>
  <p class="muted">Πρόχειρες και υποβληθείσες προσφορές. Μέχρι τη λήξη μπορείτε να τις αλλάξετε ή να τις αποσύρετε.</p></div></div>
  ${bids.length ? `
  <div class="table-wrap"><table class="tbl">
    <thead><tr><th>Εργασία</th><th>Προσφορά</th><th class="num">Σύνολο</th><th>Αποτέλεσμα</th></tr></thead>
    <tbody>${bids.map((b) => `
      <tr>
        <td><a class="strong" href="#/jobs/${b.job.id}">${esc(b.job.title)}</a>
          <div class="muted small">${companyLink(b.job.contractor)} · ${esc(b.job.location || b.job.region_display)}</div></td>
        <td>${bidBadge(b.status)}<div class="muted small">${b.submitted_at ? fmt.datetime(b.submitted_at) : "ενημ. " + fmt.datetime(b.updated_at)}</div></td>
        <td class="num mono">${fmt.money(b.total)}</td>
        <td>${result(b)}</td>
      </tr>`).join("")}</tbody>
  </table></div>` : `
  <div class="empty"><h2>Δεν έχετε προσφορές ακόμα</h2><p>Βρείτε εργασίες στην περιοχή σας και τιμολογήστε την προμέτρηση.</p>
  <a class="btn primary" href="#/jobs">Διαθέσιμες εργασίες</a></div>`}`;
}
