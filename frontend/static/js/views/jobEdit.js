import { api, download } from "../api.js";
import {
  busy, confirmDialog, esc, fmt, formData, fromLocalInput, options, parseNum, toast, toLocalInput, tradeChips,
} from "../ui.js";

export async function jobEditView(main, [id], stale) {
  const job = id ? await api(`jobs/${id}`) : null;
  if (stale()) return;
  if (job && job.status !== "draft") { location.hash = `#/jobs/${job.id}`; return; }

  main.innerHTML = `
  <div class="page-head">
    <div><a class="back" href="#/my-jobs">← Οι εργασίες μου</a>
    <h1>${job ? esc(job.title) : "Νέα εργασία"}</h1>
    <p class="muted">${job ? "Πρόχειρο · ορατό μόνο σε εσάς μέχρι τη δημοσίευση" : "Βήμα 1 από 3: βασικά στοιχεία. Μετά ανεβάζετε προμέτρηση και σχέδια."}</p></div>
    ${job ? `<button class="btn ghost danger-text" id="del">Διαγραφή πρόχειρου</button>` : ""}
  </div>
  <div class="edit-layout">
    <div class="edit-main">
      <section class="panel" id="s-info">
        <h2><span class="step">1</span> Στοιχεία εργασίας</h2>
        <form id="info" class="stack">
          <label>Τίτλος<input name="title" required maxlength="200" value="${esc(job?.title)}" placeholder="π.χ. Υδραυλικά και κλιματισμός κτιρίου γραφείων 4 ορόφων"></label>
          <label>Περιγραφή εργασιών<textarea name="description" rows="5" placeholder="Αντικείμενο, τι περιλαμβάνεται, τι προμηθεύει ο εργολάβος, ιδιαιτερότητες εργοταξίου…">${esc(job?.description)}</textarea></label>
          <div><label>Ειδικότητες που αφορά η εργασία</label>
            <p class="muted small">Οι υπεργολάβοι των ειδικοτήτων αυτών βλέπουν την εργασία στις «δικές τους».</p>
            <div class="chip-groups compact">${tradeChips("trades", job?.trades || [])}</div></div>
          <div class="grid3">
            <label>Κατηγορία<select name="category">${options("job_categories", job?.category || "commercial")}</select></label>
            <label>Περιφέρεια<select name="region" required>${options("regions", job?.region || "attiki")}</select></label>
            <label>Τοποθεσία<input name="location" value="${esc(job?.location)}" placeholder="π.χ. Μαρούσι"></label>
            <label>Προθεσμία προσφορών<input type="datetime-local" name="bid_deadline" value="${toLocalInput(job?.bid_deadline)}"></label>
            <label>Επιθυμητή έναρξη<input type="date" name="start_date" value="${esc(job?.start_date || "")}"></label>
            <label>Εκτιμώμενη διάρκεια<input name="duration_text" value="${esc(job?.duration_text)}" placeholder="π.χ. 4 μήνες"></label>
          </div>
          <div class="row end"><button class="btn primary">${job ? "Αποθήκευση στοιχείων" : "Συνέχεια →"}</button></div>
        </form>
      </section>
      ${job ? `
      <section class="panel" id="s-boq">
        <h2><span class="step">2</span> Προμέτρηση (BOQ)</h2>
        <p class="muted">Εισάγετε το Excel σας: εντοπίζουμε αυτόματα τις στήλες «Α/Α», «Περιγραφή», «Μονάδα», «Ποσότητα». Γραμμές χωρίς ποσότητα γίνονται επικεφαλίδες ενοτήτων. Οι υπεργολάβοι θα τιμολογήσουν ακριβώς αυτές τις γραμμές.</p>
        <div class="row wrap">
          <label class="btn file">Εισαγωγή από Excel / CSV<input type="file" id="boq-file" accept=".xlsx,.xlsm,.csv" hidden></label>
          <label class="check"><input type="checkbox" id="keep-file" checked> Κράτα και το αρχικό αρχείο στα έγγραφα</label>
          <a class="link" href="/static/templates/protypo-promertrisis.xlsx" download>Κατέβασμα προτύπου Excel</a>
        </div>
        <div id="boq-editor"></div>
      </section>
      <section class="panel" id="s-docs">
        <h2><span class="step">3</span> Σχέδια και έγγραφα</h2>
        <p class="muted">PDF, DWG/DXF, Excel, Word, εικόνες ή ZIP, έως 50 MB το καθένα. Αν ανεβάσετε αρχείο με τον ίδιο τίτλο, αποθηκεύεται ως νέα έκδοση.</p>
        <form id="docs-form" class="row wrap">
          <select name="kind">${options("document_kinds", "drawing")}</select>
          <label class="btn file">Επιλογή αρχείων<input type="file" name="files" multiple hidden></label>
        </form>
        <div id="docs"></div>
      </section>` : ""}
    </div>
    ${job ? `<aside class="edit-side"><div class="panel sticky" id="publish"></div></aside>` : ""}
  </div>`;

  const info = main.querySelector("#info");
  info.onsubmit = (e) => {
    e.preventDefault();
    const body = formData(info);
    body.trades = new FormData(info).getAll("trades");
    body.bid_deadline = fromLocalInput(body.bid_deadline);
    body.start_date = body.start_date || null;
    busy(info.querySelector("button"), async () => {
      if (!job) {
        const created = await api("jobs", { method: "POST", body });
        location.hash = `#/jobs/${created.id}/edit`;
        return;
      }
      Object.assign(job, await api(`jobs/${job.id}`, { method: "PUT", body }));
      toast("Τα στοιχεία αποθηκεύτηκαν.", "ok");
      main.querySelector("h1").textContent = job.title;
      renderPublish();
    });
  };
  if (!job) return;

  main.querySelector("#del").onclick = async () => {
    if (!(await confirmDialog("Να διαγραφεί οριστικά το πρόχειρο;", { ok: "Διαγραφή", danger: true }))) return;
    await busy(null, async () => { await api(`jobs/${job.id}`, { method: "DELETE" }); location.hash = "#/my-jobs"; });
  };

  // --- Προμέτρηση ---------------------------------------------------------
  let boq = await api(`jobs/${job.id}/boq`);
  let dirty = false;
  const editor = main.querySelector("#boq-editor");

  const renderBoq = () => {
    const priced = boq.filter((r) => r.quantity !== null && r.quantity !== "").length;
    editor.innerHTML = `
      <div class="boq-meta"><b>${priced}</b> γραμμές προς τιμολόγηση · ${boq.length - priced} ενότητες
        ${dirty ? `<span class="badge warn">Μη αποθηκευμένες αλλαγές</span>` : ""}</div>
      <div class="table-wrap"><table class="tbl boq-edit">
        <thead><tr><th style="width:90px">Α/Α</th><th>Περιγραφή</th><th style="width:80px">Μον.</th><th style="width:120px" class="num">Ποσότητα</th><th style="width:40px"></th></tr></thead>
        <tbody>${boq.map((r, i) => `
          <tr class="${r.quantity === null || r.quantity === "" ? "section-row" : ""}" data-i="${i}">
            <td><input data-f="code" value="${esc(r.code)}"></td>
            <td><textarea data-f="description" rows="1">${esc(r.description)}</textarea></td>
            <td><input data-f="unit" value="${esc(r.unit)}"></td>
            <td><input data-f="quantity" class="num" value="${r.quantity === null ? "" : esc(String(r.quantity).replace(".", ","))}" placeholder="ενότητα"></td>
            <td><button class="icon-btn" data-del="${i}" title="Διαγραφή γραμμής">×</button></td>
          </tr>`).join("") || `<tr><td colspan="5" class="muted center">Δεν υπάρχουν γραμμές. Εισάγετε Excel ή προσθέστε χειροκίνητα.</td></tr>`}
        </tbody>
      </table></div>
      <div class="row wrap">
        <button class="btn sm" data-add="item">+ Γραμμή</button>
        <button class="btn sm" data-add="section">+ Ενότητα</button>
        <span class="grow"></span>
        <button class="btn primary sm" id="boq-save" ${dirty ? "" : "disabled"}>Αποθήκευση προμέτρησης</button>
      </div>`;
  };

  editor.addEventListener("input", (e) => {
    const tr = e.target.closest("tr[data-i]");
    if (!tr) return;
    const row = boq[+tr.dataset.i];
    const f = e.target.dataset.f;
    row[f] = f === "quantity" ? e.target.value : e.target.value;
    tr.classList.toggle("section-row", f === "quantity" ? !e.target.value.trim() : tr.classList.contains("section-row"));
    if (!dirty) { dirty = true; editor.querySelector("#boq-save").disabled = false;
      editor.querySelector(".boq-meta").insertAdjacentHTML("beforeend", `<span class="badge warn">Μη αποθηκευμένες αλλαγές</span>`); }
  });
  editor.addEventListener("click", (e) => {
    const del = e.target.closest("[data-del]");
    const add = e.target.closest("[data-add]");
    if (del) { boq.splice(+del.dataset.del, 1); dirty = true; renderBoq(); }
    if (add) {
      boq.push({ code: "", description: "", unit: add.dataset.add === "item" ? "τεμ" : "", quantity: add.dataset.add === "item" ? "1" : null });
      dirty = true; renderBoq();
      editor.querySelector("tbody tr:last-child textarea")?.focus();
    }
    if (e.target.id === "boq-save") {
      const body = [];
      for (const r of boq) {
        const q = r.quantity === null || String(r.quantity).trim() === "" ? null : parseNum(r.quantity);
        if (Number.isNaN(q)) { toast(`Μη έγκυρη ποσότητα στη γραμμή «${r.description.slice(0, 40)}».`, "error"); return; }
        if (!r.description.trim()) continue;
        body.push({ code: r.code || "", description: r.description.trim(), unit: q === null ? "" : r.unit || "", quantity: q });
      }
      busy(e.target, async () => {
        boq = await api(`jobs/${job.id}/boq`, { method: "PUT", body });
        dirty = false; renderBoq(); renderPublish();
        toast("Η προμέτρηση αποθηκεύτηκε.", "ok");
      });
    }
  });

  main.querySelector("#boq-file").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (boq.length && !(await confirmDialog(`Η εισαγωγή θα αντικαταστήσει τις ${boq.length} υπάρχουσες γραμμές. Συνέχεια;`))) { e.target.value = ""; return; }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("keep_file", main.querySelector("#keep-file").checked ? "1" : "0");
    await busy(e.target.closest("label"), async () => {
      boq = await api(`jobs/${job.id}/boq/import`, { method: "POST", body: fd });
      dirty = false; renderBoq(); await loadDocs(); renderPublish();
      toast(`Εισήχθησαν ${boq.filter((r) => !r.is_section).length} γραμμές από το ${file.name}.`, "ok");
    });
    e.target.value = "";
  };

  // --- Έγγραφα ------------------------------------------------------------
  let docs = job.documents;
  const docsEl = main.querySelector("#docs");
  const renderDocs = () => {
    docsEl.innerHTML = docs.length ? `<ul class="doc-list">${docs.map((d) => `
      <li><span class="doc-ico">${esc(d.filename.split(".").pop().toUpperCase().slice(0, 4))}</span>
        <div class="grow"><b>${esc(d.title)}</b>${d.version ? ` <span class="badge muted">έκδ. ${d.version}</span>` : ""}
        <div class="muted small">${esc(d.kind_display)} · ${esc(d.filename)} · ${fmt.size(d.size)}</div></div>
        <button class="btn ghost sm" data-dl="${d.id}" data-name="${esc(d.filename)}">Λήψη</button>
        <button class="icon-btn" data-rm="${d.id}" title="Διαγραφή">×</button></li>`).join("")}</ul>`
      : `<p class="muted small">Δεν έχουν ανέβει έγγραφα. Τα σχέδια βοηθούν τους υπεργολάβους να τιμολογήσουν σωστά.</p>`;
  };
  const loadDocs = async () => { docs = await api(`jobs/${job.id}/documents`); renderDocs(); };
  docsEl.addEventListener("click", async (e) => {
    const dl = e.target.closest("[data-dl]");
    const rm = e.target.closest("[data-rm]");
    if (dl) busy(dl, () => download(`documents/${dl.dataset.dl}/download`, dl.dataset.name));
    if (rm && (await confirmDialog("Να διαγραφεί το έγγραφο;", { ok: "Διαγραφή", danger: true }))) {
      busy(rm, async () => { await api(`documents/${rm.dataset.rm}`, { method: "DELETE" }); await loadDocs(); renderPublish(); });
    }
  });
  const docsForm = main.querySelector("#docs-form");
  docsForm.files.onchange = () => {
    if (!docsForm.files.files.length) return;
    const fd = new FormData(docsForm);
    busy(docsForm.querySelector("label.btn"), async () => {
      const created = await api(`jobs/${job.id}/documents`, { method: "POST", body: fd });
      toast(`Ανέβηκαν ${created.length} αρχεία.`, "ok");
      await loadDocs(); renderPublish();
    }).finally(() => { docsForm.files.value = ""; });
  };

  // --- Δημοσίευση ---------------------------------------------------------
  const renderPublish = () => {
    const lines = boq.filter((r) => r.quantity !== null && r.quantity !== "").length;
    const deadlineOk = job.bid_deadline && new Date(job.bid_deadline) - Date.now() > 3.6e6;
    const checks = [
      [!!job.title, "Τίτλος και περιοχή"],
      [job.trades?.length > 0, job.trades?.length ? `Ειδικότητες: ${job.trades.length}` : "Τουλάχιστον μία ειδικότητα"],
      [deadlineOk, job.bid_deadline ? `Προθεσμία: ${fmt.datetime(job.bid_deadline)}` : "Προθεσμία προσφορών (τουλάχιστον 1 ώρα από τώρα)"],
      [lines > 0 && !dirty, lines ? `Προμέτρηση: ${lines} γραμμές${dirty ? " (μη αποθηκευμένη)" : ""}` : "Προμέτρηση με ποσότητες"],
      [docs.length > 0, docs.length ? `${docs.length} έγγραφα` : "Σχέδια (προαιρετικά, συνιστώνται)", true],
    ];
    const ready = checks.every(([ok, , optional]) => ok || optional);
    main.querySelector("#publish").innerHTML = `
      <h3>Έτοιμο για δημοσίευση;</h3>
      <ul class="checklist">${checks.map(([ok, t, opt]) => `<li class="${ok ? "ok" : opt ? "opt" : ""}">${esc(t)}</li>`).join("")}</ul>
      <p class="muted small">Μετά τη δημοσίευση η εργασία εμφανίζεται σε όλους τους υπεργολάβους. Η προμέτρηση κλειδώνει· αλλαγές γίνονται με συμπληρώματα.</p>
      <button class="btn primary block" id="pub" ${ready ? "" : "disabled"}>Δημοσίευση</button>`;
    main.querySelector("#pub").onclick = async (e) => {
      if (!(await confirmDialog("Δημοσίευση της εργασίας; Η προμέτρηση δεν θα μπορεί πλέον να αλλάξει.", { ok: "Δημοσίευση" }))) return;
      busy(e.target, async () => {
        await api(`jobs/${job.id}/publish`, { method: "POST" });
        toast("Η εργασία δημοσιεύτηκε.", "ok");
        location.hash = `#/jobs/${job.id}`;
      });
    };
  };

  renderBoq();
  renderDocs();
  renderPublish();
}
