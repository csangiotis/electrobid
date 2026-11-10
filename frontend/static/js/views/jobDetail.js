import { api, download } from "../api.js";
import {
  bidBadge, busy, companyLink, confirmDialog, esc, fmt, fromLocalInput, options, parseNum, phaseBadge, state,
  timeLeft, toast, toLocalInput, verifiedMark,
} from "../ui.js";

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
  <dl class="facts wide">
    <div><dt>Τοποθεσία</dt><dd>${esc([job.location, job.region_display].filter(Boolean).join(", "))}</dd></div>
    <div><dt>Κατηγορία</dt><dd>${esc(job.category_display)}</dd></div>
    <div><dt>Προθεσμία</dt><dd>${fmt.datetime(job.bid_deadline)}<small>${esc(timeLeft(job.bid_deadline))}</small></dd></div>
    <div><dt>Έναρξη</dt><dd>${fmt.date(job.start_date)}${job.duration_text ? `<small>διάρκεια ${esc(job.duration_text)}</small>` : ""}</dd></div>
    <div><dt>Έγγραφα</dt><dd>${job.documents.length}</dd></div>
    <div><dt>Γραμμές BOQ</dt><dd>${lines.length}</dd></div>
  </dl>
  ${job.awarded ? awardedBanner(job) : ""}
  <nav class="tabs">${tabs.map(([k, t]) => `<a href="#/jobs/${id}?tab=${k}" class="${k === tab ? "active" : ""}">${esc(t)}</a>`).join("")}</nav>
  <section id="tab"></section>`;

  if (job.is_owner) ownerActions(main.querySelector("#owner-actions"), job);
  const el = main.querySelector("#tab");
  const views = { overview, boq: boqTab, qa: questions, bid: myBid, bids: compare };
  await views[tab](el, job, boq, stale);
}

function awardedBanner(job) {
  if (job.awarded.is_me) return `<div class="banner ok"><b>Συγχαρητήρια, η εργασία ανατέθηκε σε εσάς.</b> Ο εργολάβος θα επικοινωνήσει για τα επόμενα βήματα.</div>`;
  if (job.is_owner) return `<div class="banner ok">Ανατέθηκε σε <b>${companyLink(job.awarded.company)}</b> με ${fmt.money(job.awarded.total)}.</div>`;
  return `<div class="banner">Η εργασία έχει ανατεθεί.</div>`;
}

function ownerActions(box, job) {
  if (job.phase === "bidding") {
    box.innerHTML = `
      <button class="btn sm" data-a="extend">Παράταση προθεσμίας</button>
      <button class="btn sm" data-a="close">Λήξη υποβολής τώρα</button>
      <button class="btn sm ghost danger-text" data-a="cancel">Ακύρωση</button>`;
  } else if (job.phase === "evaluation") {
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

// --- Προσφορά υπεργολάβου --------------------------------------------------------
async function myBid(el, job, boq, stale) {
  let bid = await api(`jobs/${job.id}/my-bid`);
  if (stale()) return;
  const lines = boq.filter((r) => !r.is_section);
  const editable = job.phase === "bidding";
  const prices = new Map((bid?.lines || []).map((l) => [l.item, l.unit_price]));
  const notes = new Map((bid?.lines || []).map((l) => [l.item, l.note]));

  if (!bid && !editable) {
    el.innerHTML = `<div class="empty"><h2>Η υποβολή έχει κλείσει</h2><p>Δεν δώσατε προσφορά σε αυτή την εργασία.</p></div>`;
    return;
  }
  const ro = editable ? "" : "readonly";
  const val = (v) => (v === null || v === undefined ? "" : String(v).replace(".", ","));

  el.innerHTML = `
  ${bid?.outdated ? `<div class="banner warn"><b>Η εργασία έχει νέο συμπλήρωμα μετά την υποβολή σας.</b> Ελέγξτε τα έγγραφα και ενημερώστε την προσφορά.</div>` : ""}
  ${bid?.status === "submitted" && editable ? `<div class="banner ok">Η προσφορά σας υποβλήθηκε ${fmt.datetime(bid.submitted_at)}. Μπορείτε να την αλλάξετε μέχρι τη λήξη (${esc(timeLeft(job.bid_deadline))}). Ο εργολάβος βλέπει τις τιμές μόνο μετά τη λήξη.</div>` : ""}
  ${bid?.status === "withdrawn" ? `<div class="banner">Η προσφορά έχει αποσυρθεί. Αποθηκεύστε για να τη συνεχίσετε ως πρόχειρη.</div>` : ""}
  <form id="bid" class="bid-layout">
    <div class="panel">
      <div class="row wrap"><h2 class="grow">Τιμολόγηση προμέτρησης ${bid ? bidBadge(bid.status) : ""}</h2>
        ${editable ? `<button type="button" class="btn sm ghost" id="paste">Επικόλληση στήλης τιμών από Excel</button>` : ""}</div>
      <p class="muted small">Τιμές μονάδας χωρίς ΦΠΑ. Αφήστε κενό αν δεν τιμολογείτε μια γραμμή και εξηγήστε στη σημείωση.</p>
      <div class="table-wrap"><table class="tbl boq priced">
        <thead><tr><th>Α/Α</th><th>Περιγραφή</th><th>Μον.</th><th class="num">Ποσότητα</th><th class="num">Τιμή μον. (€)</th><th class="num">Σύνολο</th></tr></thead>
        <tbody>${boqRows(boq, (r) => `
          <td class="num"><input class="price" name="p-${r.id}" inputmode="decimal" value="${val(prices.get(r.id))}" ${ro}>
            ${notes.get(r.id) || editable ? `<input class="line-note" name="n-${r.id}" placeholder="σημείωση" value="${esc(notes.get(r.id) || "")}" ${ro}>` : ""}</td>
          <td class="num mono line-total">—</td>`)}</tbody>
      </table></div>
    </div>
    <aside class="panel sticky bid-side">
      <div class="total-box"><small>Σύνολο προσφοράς (χωρίς ΦΠΑ)</small><b id="total">—</b>
        <span id="missing" class="muted small"></span></div>
      <label>Χρόνος εκτέλεσης (ημέρες)<input name="duration_days" type="number" min="1" value="${esc(bid?.duration_days ?? "")}" ${ro}></label>
      <label>Ισχύς προσφοράς (ημέρες)<input name="validity_days" type="number" min="1" value="${esc(bid?.validity_days ?? 60)}" ${ro}></label>
      <label>Όροι πληρωμής<input name="payment_terms" value="${esc(bid?.payment_terms)}" placeholder="π.χ. 30% προκαταβολή, λογαριασμοί ανά μήνα" ${ro}></label>
      <label>Εξαιρέσεις / παραδοχές<textarea name="exclusions" rows="3" placeholder="π.χ. Δεν περιλαμβάνονται χωματουργικά" ${ro}>${esc(bid?.exclusions)}</textarea></label>
      <label>Σημειώσεις<textarea name="notes" rows="2" ${ro}>${esc(bid?.notes)}</textarea></label>
      ${editable ? `
        <button type="button" class="btn block" id="save">Αποθήκευση${bid?.status === "submitted" ? " αλλαγών" : " πρόχειρου"}</button>
        ${bid?.status !== "submitted" ? `<button type="button" class="btn primary block" id="submit">Υποβολή προσφοράς</button>` : ""}
        ${bid?.status === "submitted" ? `<button type="button" class="btn ghost block danger-text" id="withdraw">Απόσυρση</button>` : ""}`
      : `<p class="muted small">Η προθεσμία έληξε. Η προσφορά δεν αλλάζει πλέον.</p>`}
    </aside>
  </form>`;

  const form = el.querySelector("#bid");
  const recalc = () => {
    let total = 0;
    let missing = 0;
    let bad = 0;
    for (const r of lines) {
      const input = form.elements[`p-${r.id}`];
      const p = parseNum(input.value);
      const cell = input.closest("tr").querySelector(".line-total");
      input.classList.toggle("invalid", Number.isNaN(p) || p < 0);
      if (p === null) { missing++; cell.textContent = "—"; continue; }
      if (Number.isNaN(p) || p < 0) { bad++; cell.textContent = "!"; continue; }
      const lt = p * Number(r.quantity);
      total += lt;
      cell.textContent = fmt.money(lt);
    }
    el.querySelector("#total").textContent = fmt.money(total);
    el.querySelector("#missing").textContent = missing
      ? `${missing} από ${lines.length} γραμμές χωρίς τιμή` : `Όλες οι ${lines.length} γραμμές τιμολογήθηκαν`;
    return { missing, bad };
  };
  form.addEventListener("input", recalc);
  recalc();
  if (!editable) return;

  const payload = () => {
    const f = form.elements;
    return {
      duration_days: f.duration_days.value ? Number(f.duration_days.value) : null,
      validity_days: Number(f.validity_days.value || 60),
      payment_terms: f.payment_terms.value,
      exclusions: f.exclusions.value,
      notes: f.notes.value,
      lines: lines.map((r) => {
        const p = parseNum(f[`p-${r.id}`].value);
        return { item: r.id, unit_price: p === null ? null : Math.round(p * 100) / 100, note: f[`n-${r.id}`]?.value || "" };
      }),
    };
  };
  const save = async () => {
    if (recalc().bad) throw new Error("Διορθώστε τις τιμές που είναι σημειωμένες με κόκκινο.");
    bid = await api(`jobs/${job.id}/my-bid`, { method: "PUT", body: payload() });
    return bid;
  };
  const reload = () => dispatchEvent(new HashChangeEvent("hashchange"));

  el.querySelector("#save").onclick = (e) => busy(e.target, async () => { await save(); toast("Αποθηκεύτηκε.", "ok"); reload(); });
  el.querySelector("#submit")?.addEventListener("click", async (e) => {
    const { missing } = recalc();
    const msg = missing
      ? `${missing} γραμμές δεν έχουν τιμή. Θα φαίνονται ως «χωρίς τιμή» στη σύγκριση. Υποβολή;`
      : "Υποβολή της προσφοράς; Μπορείτε να την αλλάξετε μέχρι τη λήξη της προθεσμίας.";
    if (!(await confirmDialog(msg, { ok: "Υποβολή" }))) return;
    busy(e.target, async () => {
      await save();
      await api(`jobs/${job.id}/my-bid/submit`, { method: "POST" });
      toast("Η προσφορά υποβλήθηκε.", "ok");
      reload();
    });
  });
  el.querySelector("#withdraw")?.addEventListener("click", async (e) => {
    if (!(await confirmDialog("Απόσυρση της προσφοράς; Ο εργολάβος δεν θα τη δει.", { ok: "Απόσυρση", danger: true }))) return;
    busy(e.target, async () => { await api(`jobs/${job.id}/my-bid/withdraw`, { method: "POST" }); reload(); });
  });
  el.querySelector("#paste").onclick = () => {
    const dlg = document.createElement("dialog");
    dlg.className = "modal wide";
    dlg.innerHTML = `<form method="dialog" class="stack"><h3>Επικόλληση τιμών</h3>
      <p class="muted small">Αντιγράψτε από το Excel τη στήλη με τις τιμές μονάδας (μία τιμή ανά γραμμή, με τη σειρά της προμέτρησης, χωρίς τις επικεφαλίδες ενοτήτων). Αναμένονται ${lines.length} τιμές.</p>
      <textarea name="v" rows="10" class="mono"></textarea>
      <div class="row end"><button class="btn ghost" value="no">Άκυρο</button><button class="btn primary" value="ok">Συμπλήρωση</button></div></form>`;
    document.body.append(dlg);
    dlg.showModal();
    dlg.addEventListener("close", () => {
      if (dlg.returnValue === "ok") {
        const vals = dlg.querySelector("textarea").value.replace(/\r/g, "").split("\n");
        while (vals.length && !vals[vals.length - 1].trim()) vals.pop();
        lines.forEach((r, i) => { if (i < vals.length) form.elements[`p-${r.id}`].value = vals[i].split("\t").pop().replace(/[€\s]/g, ""); });
        recalc();
        toast(vals.length === lines.length ? `Συμπληρώθηκαν ${vals.length} τιμές.` : `Επικολλήθηκαν ${vals.length} τιμές για ${lines.length} γραμμές. Ελέγξτε την αντιστοίχιση.`, vals.length === lines.length ? "ok" : "warn");
      }
      dlg.remove();
    });
  };
}

// --- Σύγκριση προσφορών (εργολάβος) ---------------------------------------------------
async function compare(el, job, _boq, stale) {
  const data = await api(`jobs/${job.id}/comparison`);
  if (stale()) return;

  if (data.sealed) {
    el.innerHTML = `
    <div class="sealed panel">
      <div class="seal">🔒</div>
      <h2>Οι προσφορές είναι σφραγισμένες</h2>
      <p>Έχουν υποβληθεί <b>${data.submitted_count}</b> ${data.submitted_count === 1 ? "προσφορά" : "προσφορές"}${data.drafts_count ? ` και ${data.drafts_count} υπεργολάβοι ετοιμάζουν προσφορά` : ""}.</p>
      <p class="muted">Ανοίγουν στη λήξη της προθεσμίας, ${fmt.datetime(data.bid_deadline)} (${esc(timeLeft(data.bid_deadline))}). Έτσι όλοι οι υπεργολάβοι συμμετέχουν με τους ίδιους όρους.</p>
    </div>`;
    return;
  }
  if (!data.bidders.length) {
    el.innerHTML = `<div class="empty"><h2>Δεν υποβλήθηκαν προσφορές</h2><p>Μπορείτε να ακυρώσετε την εργασία και να τη δημοσιεύσετε ξανά με νέα προθεσμία.</p></div>`;
    return;
  }
  const B = data.bidders;
  const lowest = data.stats.lowest_total;
  const canAward = job.phase === "evaluation";
  const diff = (t) => (lowest && t > lowest ? `+${(((t - lowest) / lowest) * 100).toFixed(1)}%` : "");

  el.innerHTML = `
  <div class="row wrap"><p class="muted grow">${B.length} προσφορές · διάμεσος συνόλων ${fmt.money(data.stats.median_total)}</p>
    <button class="btn sm" id="xlsx">Εξαγωγή σύγκρισης σε Excel</button></div>
  <div class="bidder-cards">${B.map((b) => `
    <div class="bidder ${b.rank === 1 && !b.missing_count ? "best" : ""} ${data.awarded_bid_id === b.bid_id ? "awarded" : ""}">
      <div class="rank">#${b.rank}</div>
      <h3>${companyLink(b.company)} ${verifiedMark(b.company)}</h3>
      <p class="muted small">${esc(b.company.region_display || "")}</p>
      <div class="amount">${fmt.money(b.total)} <small>${diff(b.total)}</small></div>
      <ul class="bidder-facts">
        <li>${b.duration_days ? `${b.duration_days} ημέρες εκτέλεση` : "Χρόνος εκτέλεσης: —"}</li>
        <li>${esc(b.payment_terms || "Όροι πληρωμής: —")}</li>
        ${b.missing_count ? `<li class="bad">${b.missing_count} γραμμές χωρίς τιμή</li>` : ""}
        ${b.outdated ? `<li class="warn">Δόθηκε πριν το τελευταίο συμπλήρωμα</li>` : ""}
      </ul>
      ${b.exclusions ? `<details><summary>Εξαιρέσεις</summary><p>${esc(b.exclusions)}</p></details>` : ""}
      ${b.notes ? `<details><summary>Σημειώσεις</summary><p>${esc(b.notes)}</p></details>` : ""}
      ${data.awarded_bid_id === b.bid_id ? `<span class="badge ok">Ανάδοχος</span>` : canAward ? `<button class="btn sm primary block" data-award="${b.bid_id}" data-name="${esc(b.company.name)}">Ανάθεση</button>` : ""}
    </div>`).join("")}</div>

  <div class="panel">
    <div class="row wrap"><h2 class="grow">Σύγκριση ανά γραμμή</h2>
      <div class="legend"><span class="lg lowest">χαμηλότερη</span><span class="lg outlier">±30% από διάμεσο</span><span class="lg missing">χωρίς τιμή</span></div></div>
    <div class="table-wrap compare-wrap"><table class="tbl compare">
      <thead><tr><th class="sticky-col">Α/Α</th><th class="sticky-col2">Περιγραφή</th><th>Μον.</th><th class="num">Ποσ.</th>
        ${B.map((b) => `<th class="num bidder-col">${companyLink(b.company)}<small>τιμή μον. / σύνολο</small></th>`).join("")}
        <th class="num">Διάμεσος</th></tr></thead>
      <tbody>${data.rows.map((r) => r.is_section
        ? `<tr class="section-row"><td class="sticky-col">${esc(r.code)}</td><td class="sticky-col2" colspan="${3 + B.length + 1}">${esc(r.description)}</td></tr>`
        : `<tr><td class="sticky-col mono">${esc(r.code)}</td><td class="sticky-col2 desc">${esc(r.description)}</td><td>${esc(r.unit)}</td><td class="num mono">${fmt.num(r.quantity)}</td>
          ${B.map((b) => {
            const c = r.cells[b.bid_id] || r.cells[String(b.bid_id)] || {};
            const cls = { lowest: "c-lowest", missing: "c-missing", outlier_high: "c-outlier", outlier_low: "c-outlier" }[c.flag] || "";
            return `<td class="num mono ${cls}" ${c.note ? `title="${esc(c.note)}"` : ""}>${c.unit_price === null || c.unit_price === undefined ? "—" : `${fmt.money(c.unit_price)}<small>${fmt.money(c.line_total)}</small>`}${c.note ? " ✎" : ""}</td>`;
          }).join("")}
          <td class="num mono muted">${fmt.money(r.median)}</td></tr>`).join("")}
      </tbody>
      <tfoot><tr><td class="sticky-col"></td><td class="sticky-col2">Σύνολο</td><td></td><td></td>
        ${B.map((b) => `<td class="num mono"><b>${fmt.money(b.total)}</b></td>`).join("")}<td></td></tr></tfoot>
    </table></div>
  </div>`;

  el.querySelector("#xlsx").onclick = (e) => busy(e.target, () => download(`jobs/${job.id}/comparison/export`, `sygkrisi-${job.id}.xlsx`));
  el.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-award]");
    if (!btn) return;
    if (!(await confirmDialog(`Ανάθεση της εργασίας στην «${btn.dataset.name}»; Οι υπόλοιποι υπεργολάβοι θα ενημερωθούν ότι η εργασία ανατέθηκε.`, { ok: "Ανάθεση" }))) return;
    busy(btn, async () => {
      await api(`jobs/${job.id}/award`, { method: "POST", body: { bid_id: Number(btn.dataset.award) } });
      toast("Η εργασία ανατέθηκε.", "ok");
      dispatchEvent(new HashChangeEvent("hashchange"));
    });
  });
}
