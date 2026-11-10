import { api, download } from "../api.js";
import {
  bidBadge, busy, companyLink, confirmDialog, esc, fmt, fromLocalInput, options, parseNum, phaseBadge, state, tradeTags,
  timeLeft, toast, toLocalInput, verifiedMark,
} from "../ui.js";
import { invitesPanel } from "./invites.js";
import { awardedBanner, compare, myBid } from "./bidding.js";

export async function jobDetailView(main, [id], stale) {
  const [job, boq] = await Promise.all([api(`jobs/${id}`), api(`jobs/${id}/boq`)]);
  if (stale()) return;
  if (job.is_owner && job.status === "draft") { location.hash = `#/jobs/${id}/edit`; return; }

  const me = state.me;
  const isSub = me.role === "subcontractor";
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const tabs = [["overview", "Επισκόπηση"], ["boq", "Προμέτρηση"], ["qa", "Ερωτήσεις"]];
  if (isSub) tabs.push(["bid", "Η προσφορά μου"]);
  if (job.is_owner) tabs.push(["bids", `Προσφορές (${job.bids_count})`]);
  if (job.is_owner && job.phase === "bidding") tabs.push(["invites", "Προσκλήσεις"]);
  let tab = params.get("tab") || (job.is_owner && job.phase !== "bidding" ? "bids" : "overview");
  if (!tabs.some(([k]) => k === tab)) tab = "overview";

  const lines = boq.filter((r) => !r.is_section);

  main.innerHTML = `
  <div class="page-head">
    <div>
      <a class="back" href="${job.is_owner ? "#/my-jobs" : isSub ? "#/jobs" : "#/jobs"}">← ${job.is_owner ? "Οι εργασίες μου" : "Εργασίες"}</a>
      <h1>${esc(job.title)}</h1>
      <p class="by">${phaseBadge(job.phase)} ${companyLink(job.contractor)} ${verifiedMark(job.contractor)}
        ${job.revision ? `<span class="badge warn">${job.revision} ${job.revision === 1 ? "συμπλήρωμα" : "συμπληρώματα"}</span>` : ""}</p>
    </div>
    <div class="row wrap" id="owner-actions"></div>
  </div>
  ${job.trades?.length ? `<div class="chips static job-trades">${tradeTags(job.trades)}</div>` : ""}
  <dl class="facts wide">
    <div><dt>Τοποθεσία</dt><dd>${esc([job.location, job.region_display].filter(Boolean).join(", "))}</dd></div>
    <div><dt>Κατηγορία</dt><dd>${esc(job.category_display)}</dd></div>
    <div><dt>Προθεσμία</dt><dd>${fmt.datetime(job.bid_deadline)}<small>${esc(timeLeft(job.bid_deadline))}</small></dd></div>
    <div><dt>Έναρξη</dt><dd>${fmt.date(job.start_date)}${job.duration_text ? `<small>διάρκεια ${esc(job.duration_text)}</small>` : ""}</dd></div>
    <div><dt>Έγγραφα</dt><dd>${job.documents.length}</dd></div>
    <div><dt>Γραμμές BOQ</dt><dd>${lines.length}</dd></div>
  </dl>
  ${job.awarded ? awardedBanner(job) : ""}
  ${job.invitation && !job.my_bid_status && job.phase === "bidding" ? `
    <div class="banner live" id="inv-banner">${job.invitation.status === "declined"
      ? "Έχετε απορρίψει την πρόσκληση. Μπορείτε ακόμα να δώσετε προσφορά."
      : `<b>Ο εργολάβος σας προσκάλεσε να δώσετε προσφορά.</b>${job.invitation.message ? ` «${esc(job.invitation.message)}»` : ""}
        <span class="row tight" style="margin-top:8px"><a class="btn sm primary" href="#/jobs/${job.id}?tab=bid">Δίνω προσφορά</a>
        <button class="btn sm ghost" id="decline">Δεν ενδιαφέρομαι</button></span>`}</div>` : ""}
  ${job.visibility === "private" ? `<p class="muted small">🔒 Ιδιωτική εργασία: τη βλέπουν μόνο οι προσκεκλημένοι.</p>` : ""}
  <nav class="tabs">${tabs.map(([k, t]) => `<a href="#/jobs/${id}?tab=${k}" class="${k === tab ? "active" : ""}">${esc(t)}</a>`).join("")}</nav>
  <section id="tab"></section>`;

  if (job.is_owner) ownerActions(main.querySelector("#owner-actions"), job);
  main.querySelector("#decline")?.addEventListener("click", async (e) => {
    if (!(await confirmDialog("Να ενημερωθεί ο εργολάβος ότι δεν θα δώσετε προσφορά;", { ok: "Δεν ενδιαφέρομαι" }))) return;
    busy(e.target, async () => { await api(`jobs/${id}/decline`, { method: "POST" }); dispatchEvent(new HashChangeEvent("hashchange")); });
  });
  const el = main.querySelector("#tab");
  const views = { overview, boq: boqTab, qa: questions, bid: myBid, bids: compare,
    invites: (box) => { box.innerHTML = `<div class="panel narrow" id="inv"></div>`; return invitesPanel(box.querySelector("#inv"), job); } };
  await views[tab](el, job, boq, stale);
}

function ownerActions(box, job) {
  if (job.phase === "bidding") {
    box.innerHTML = `
      <button class="btn sm" data-a="extend">Παράταση προθεσμίας</button>
      <button class="btn sm" data-a="close">Λήξη υποβολής τώρα</button>
      <button class="btn sm ghost danger-text" data-a="cancel">Ακύρωση</button>`;
  } else if (job.phase === "evaluation" || job.phase === "bafo") {
    box.innerHTML = `<button class="btn sm ghost danger-text" data-a="cancel">Ακύρωση εργασίας</button>`;
  }
  box.onclick = async (e) => {
    const a = e.target.closest("[data-a]")?.dataset.a;
    if (!a) return;
    if (a === "close" && await confirmDialog("Να λήξει τώρα η υποβολή; Οι προσφορές θα ανοίξουν και δεν θα γίνονται δεκτές νέες.", { ok: "Λήξη τώρα" })) {
      busy(e.target, async () => { await api(`jobs/${job.id}/close_bidding`, { method: "POST" }); location.hash = `#/jobs/${job.id}?tab=bids`; });
    }
    if (a === "cancel" && await confirmDialog("Ακύρωση της εργασίας; Οι υπεργολάβοι θα τη βλέπουν ως ακυρωμένη.", { ok: "Ακύρωση εργασίας", danger: true })) {
      busy(e.target, async () => { await api(`jobs/${job.id}/cancel`, { method: "POST" }); dispatchEvent(new HashChangeEvent("hashchange")); });
    }
    if (a === "extend") {
      const dlg = document.createElement("dialog");
      dlg.className = "modal";
      dlg.innerHTML = `<form method="dialog" class="stack"><h3>Παράταση προθεσμίας</h3>
        <label>Νέα προθεσμία<input type="datetime-local" name="d" required value="${toLocalInput(job.bid_deadline)}"></label>
        <div class="row end"><button class="btn ghost" value="no" formnovalidate>Άκυρο</button><button class="btn primary" value="ok">Αποθήκευση</button></div></form>`;
      document.body.append(dlg);
      dlg.showModal();
      dlg.addEventListener("close", async () => {
        const v = dlg.querySelector("[name=d]").value;
        if (dlg.returnValue === "ok" && v) {
          await busy(null, async () => {
            await api(`jobs/${job.id}`, { method: "PATCH", body: { bid_deadline: fromLocalInput(v) } });
            toast("Η προθεσμία παρατάθηκε.", "ok");
            dispatchEvent(new HashChangeEvent("hashchange"));
          });
        }
        dlg.remove();
      });
    }
  };
}

// --- Επισκόπηση -------------------------------------------------------------
async function overview(el, job) {
  const docs = job.documents;
  const addenda = docs.filter((d) => d.is_addendum);
  const canAddendum = job.is_owner && job.phase === "bidding";
  el.innerHTML = `
  <div class="two-col">
    <div class="panel">
      <h2>Περιγραφή</h2>
      <div class="prose">${job.description ? esc(job.description).replace(/\n/g, "<br>") : `<p class="muted">Χωρίς περιγραφή.</p>`}</div>
    </div>
    <div class="panel">
      <h2>Σχέδια και έγγραφα <span class="muted">(${docs.length})</span></h2>
      ${addenda.length ? `<p class="banner warn small">Έχουν προστεθεί ${addenda.length} αρχεία ως συμπληρώματα μετά τη δημοσίευση.</p>` : ""}
      ${docs.length ? `<ul class="doc-list">${docs.map((d) => `
        <li><span class="doc-ico">${esc(d.filename.split(".").pop().toUpperCase().slice(0, 4))}</span>
          <div class="grow"><b>${esc(d.title)}</b> ${d.version ? `<span class="badge muted">έκδ. ${d.version}</span>` : ""} ${d.is_addendum ? `<span class="badge warn">Συμπλήρωμα ${d.job_revision}</span>` : ""}
          <div class="muted small">${esc(d.kind_display)} · ${fmt.size(d.size)} · ${fmt.date(d.uploaded_at)}</div></div>
          ${/\.pdf$/i.test(d.filename) ? `<button class="btn ghost sm" data-view="${d.id}">Προβολή</button>` : ""}
          <button class="btn sm" data-dl="${d.id}" data-name="${esc(d.filename)}">Λήψη</button></li>`).join("")}</ul>`
        : `<p class="muted">Δεν υπάρχουν έγγραφα.</p>`}
      ${canAddendum ? `
        <form id="add-form" class="addendum">
          <b>Νέο συμπλήρωμα</b>
          <p class="muted small">Οι υπεργολάβοι που έχουν ήδη υποβάλει θα δουν ότι η προσφορά τους αφορά παλαιότερη έκδοση.</p>
          <div class="row wrap"><select name="kind">${options("document_kinds", "drawing")}</select>
          <label class="btn sm file">Ανέβασμα αρχείων<input type="file" name="files" multiple hidden></label></div>
        </form>` : ""}
    </div>
  </div>`;
  el.addEventListener("click", async (e) => {
    const dl = e.target.closest("[data-dl]");
    const vw = e.target.closest("[data-view]");
    if (dl) busy(dl, () => download(`documents/${dl.dataset.dl}/download`, dl.dataset.name));
    if (vw) {
      const win = window.open("", "_blank");
      await busy(vw, async () => {
        const res = await api(`documents/${vw.dataset.view}/download?inline=1`, { raw: true });
        const url = URL.createObjectURL(new Blob([await res.blob()], { type: "application/pdf" }));
        if (win) win.location = url; else location.href = url;
      });
    }
  });
  const form = el.querySelector("#add-form");
  if (form) {
    form.files.onchange = () => busy(form.querySelector("label.btn"), async () => {
      await api(`jobs/${job.id}/documents`, { method: "POST", body: new FormData(form) });
      toast("Το συμπλήρωμα δημοσιεύτηκε.", "ok");
      dispatchEvent(new HashChangeEvent("hashchange"));
    });
  }
}

// --- Προμέτρηση -------------------------------------------------------------
function boqRows(boq, cell = () => "") {
  return boq.map((r) => r.is_section
    ? `<tr class="section-row"><td>${esc(r.code)}</td><td colspan="99">${esc(r.description)}</td></tr>`
    : `<tr data-item="${r.id}"><td class="mono">${esc(r.code)}</td><td>${esc(r.description)}</td><td>${esc(r.unit)}</td>
        <td class="num mono">${fmt.num(r.quantity)}</td>${cell(r)}</tr>`).join("");
}

async function boqTab(el, job, boq) {
  el.innerHTML = `
  <div class="panel">
    <div class="row wrap"><h2 class="grow">Προμέτρηση</h2>
    <button class="btn sm" id="csv">Λήψη σε CSV (Excel)</button></div>
    <div class="table-wrap"><table class="tbl boq">
      <thead><tr><th>Α/Α</th><th>Περιγραφή</th><th>Μον.</th><th class="num">Ποσότητα</th></tr></thead>
      <tbody>${boqRows(boq)}</tbody></table></div>
  </div>`;
  el.querySelector("#csv").onclick = () => {
    const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const rows = [["Α/Α", "Περιγραφή", "Μονάδα", "Ποσότητα", "Τιμή μονάδας", "Σύνολο"].map(q).join(";")];
    for (const r of boq) rows.push([r.code, r.description, r.unit, r.quantity === null ? "" : String(r.quantity).replace(".", ","), "", ""].map(q).join(";"));
    const blob = new Blob(["﻿" + rows.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `promertrisi-${job.id}.csv` });
    a.click();
  };
}

// --- Ερωτήσεις ---------------------------------------------------------------
async function questions(el, job, _boq, stale) {
  const qs = await api(`jobs/${job.id}/questions`);
  if (stale()) return;
  const canAsk = !job.is_owner && job.phase === "bidding";
  el.innerHTML = `
  <div class="panel narrow">
    <h2>Ερωτήσεις διευκρινίσεων</h2>
    <p class="muted small">${job.is_owner
      ? "Οι απαντήσεις σας δημοσιεύονται σε όλους τους υπεργολάβους. Η ταυτότητα όποιου ρώτησε δεν εμφανίζεται."
      : "Οι ερωτήσεις είναι ανώνυμες. Όταν απαντηθούν, η απάντηση εμφανίζεται σε όλους."}</p>
    ${canAsk ? `<form id="ask" class="stack"><textarea name="text" rows="3" required placeholder="π.χ. Τα φωτιστικά σώματα τα προμηθεύει ο εργολάβος;"></textarea>
      <div class="row end"><button class="btn primary sm">Υποβολή ερώτησης</button></div></form>` : ""}
    <ol class="qa">${qs.map((q) => `
      <li class="${q.answer ? "" : "pending"}">
        <div class="q"><span class="qa-tag">Ε</span><div>${esc(q.text)}
          <div class="muted small">${fmt.datetime(q.created_at)}${q.asked_by ? ` · ${esc(q.asked_by)}` : ""}${q.is_mine ? " · δική σας" : ""}</div></div></div>
        ${q.answer ? `<div class="a"><span class="qa-tag a">Α</span><div>${esc(q.answer).replace(/\n/g, "<br>")}<div class="muted small">${fmt.datetime(q.answered_at)}</div></div></div>`
          : job.is_owner ? `<form class="answer stack" data-q="${q.id}"><textarea name="answer" rows="2" required placeholder="Απάντηση…"></textarea>
              <div class="row end"><button class="btn sm primary">Δημοσίευση απάντησης</button></div></form>`
          : `<div class="muted small">Αναμένεται απάντηση</div>`}
      </li>`).join("") || `<li class="muted">Δεν υπάρχουν ερωτήσεις ακόμα.</li>`}</ol>
  </div>`;
  el.addEventListener("submit", (e) => {
    e.preventDefault();
    const f = e.target;
    const reload = () => dispatchEvent(new HashChangeEvent("hashchange"));
    if (f.id === "ask") busy(f.querySelector("button"), async () => { await api(`jobs/${job.id}/questions`, { method: "POST", body: { text: f.text.value } }); toast("Η ερώτηση στάλθηκε.", "ok"); reload(); });
    if (f.dataset.q) busy(f.querySelector("button"), async () => { await api(`jobs/${job.id}/questions/${f.dataset.q}/answer`, { method: "POST", body: { answer: f.answer.value } }); reload(); });
  });
}
