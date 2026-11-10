import { api } from "../api.js";
import { busy, confirmDialog, esc, options, state, toast, tradeChips } from "../ui.js";
import { forgetPhoto, loadPhotos, projectCard } from "./directory.js";

const chipBoxes = (list, name, selected) => state.choices[list].map((s) =>
  `<label class="chip"><input type="checkbox" name="${name}" value="${esc(s.value)}" ${selected.includes(s.value) ? "checked" : ""}><span>${esc(s.label)}</span></label>`).join("");

export async function profileView(main, _p, stale) {
  const [me, projects, prefs] = await Promise.all([api("me"), api("me/projects"), api("me/email-prefs")]);
  if (stale()) return;
  state.me = me;
  let list = projects;
  const c = me.company;
  const isSub = me.role === "subcontractor";

  main.innerHTML = `
  <div class="page-head"><div><h1>Το προφίλ μου</h1>
    <p class="muted">${esc(me.email)} · ${isSub ? "Υπεργολάβος" : "Εργολάβος"} ${c.verified ? `<span class="badge ok">Επαληθευμένη</span>` : `<span class="badge muted">Μη επαληθευμένη</span>`}</p></div>
    <a class="btn" href="#/companies/${me.company_id}">Δείτε το δημόσιο προφίλ →</a></div>
  <div class="profile-edit">
    <form id="f" class="panel stack">
      <h2>Στοιχεία εταιρείας</h2>
      <div class="grid2">
        <label>Όνομα<input name="first_name" value="${esc(me.first_name)}"></label>
        <label>Επώνυμο<input name="last_name" value="${esc(me.last_name)}"></label>
        <label>Επωνυμία<input name="name" required value="${esc(c.name)}"></label>
        <label>ΑΦΜ<input name="vat_number" required pattern="\\d{9}" value="${esc(c.vat_number)}"></label>
        <label>Έδρα<select name="region">${options("regions", c.region)}</select></label>
        <label>Πόλη<input name="city" value="${esc(c.city)}"></label>
        <label>Διεύθυνση έδρας<input name="address" value="${esc(c.address)}"></label>
        <label>ΔΟΥ<input name="tax_office" value="${esc(c.tax_office)}"></label>
        <label>Τηλέφωνο<input name="phone" value="${esc(c.phone)}"></label>
        <label>Ιστοσελίδα<input name="website" type="url" placeholder="https://" value="${esc(c.website)}"></label>
        <label>Έτος ίδρυσης<input name="founded_year" type="number" min="1900" max="2100" value="${esc(c.founded_year ?? "")}"></label>
        <label>Προσωπικό (άτομα)<input name="employees" type="number" min="0" value="${esc(c.employees ?? "")}"></label>
      </div>
      <label>Παρουσίαση εταιρείας<textarea name="description" rows="4" placeholder="Τι κάνετε, σε τι είστε δυνατοί, εξοπλισμός, πιστοποιήσεις…">${esc(c.description)}</textarea></label>
      <label>Ειδικότητες</label><div class="chip-groups">${tradeChips("specialties", c.specialties)}</div>
      <label>Περιοχές δραστηριότητας</label><div class="chips">${chipBoxes("regions", "service_regions", c.service_regions)}</div>
      <p class="muted small">Η επαλήθευση (σήμα ✓) γίνεται από τη διαχείριση της πλατφόρμας μετά από έλεγχο των στοιχείων της εταιρείας.</p>
      <div class="row end"><button class="btn primary">Αποθήκευση</button></div>
    </form>
    <section class="panel" id="prefs">
      <h2>Ειδοποιήσεις με email</h2>
      <p class="muted small">Οι ειδοποιήσεις εμφανίζονται πάντα στο καμπανάκι. Εδώ επιλέγετε ποιες έρχονται και με email στο ${esc(me.email)}.
        Τα email λογαριασμού (επιβεβαίωση, κωδικός) στέλνονται πάντα.</p>
      <div class="prefs">${prefs.map((p) => `<label class="check"><input type="checkbox" data-kind="${esc(p.kind)}" ${p.enabled ? "checked" : ""}> ${esc(p.label)}</label>`).join("")}</div>
    </section>
    <section class="panel">
      <div class="row wrap"><h2 class="grow">Έργα και εμπειρία <span class="muted">(${list.length})</span></h2>
        <button class="btn primary sm" id="add">+ Προσθήκη έργου</button></div>
      <p class="muted small">${isSub
        ? "Έργα που έχετε εκτελέσει. Οι εργολάβοι τα βλέπουν στο προφίλ σας και στον κατάλογο υπεργολάβων."
        : "Έργα που έχετε αναλάβει. Οι υπεργολάβοι τα βλέπουν όταν αποφασίζουν αν θα δώσουν προσφορά."}</p>
      <div class="projects" id="projects"></div>
    </section>
  </div>`;

  const f = main.querySelector("#f");
  f.onsubmit = (e) => {
    e.preventDefault();
    const fd = new FormData(f);
    const num = (k) => (fd.get(k) ? Number(fd.get(k)) : null);
    const company = {
      name: fd.get("name"), vat_number: fd.get("vat_number"), region: fd.get("region"), city: fd.get("city"),
      phone: fd.get("phone"), website: fd.get("website"), address: fd.get("address"), tax_office: fd.get("tax_office"),
      description: fd.get("description"), employees: num("employees"), founded_year: num("founded_year"),
      specialties: fd.getAll("specialties"), service_regions: fd.getAll("service_regions"),
    };
    busy(f.querySelector("button.primary"), async () => {
      state.me = await api("me", { method: "PATCH", body: { first_name: fd.get("first_name"), last_name: fd.get("last_name"), company } });
      toast("Το προφίλ αποθηκεύτηκε.", "ok");
      const nameEl = document.querySelector(".me-text b");
      if (nameEl) nameEl.textContent = state.me.company.name;
    });
  };

  main.querySelector("#prefs").addEventListener("change", async (e) => {
    const k = e.target.dataset.kind;
    if (!k) return;
    try {
      await api("me/email-prefs", { method: "PUT", body: { [k]: e.target.checked } });
      toast(e.target.checked ? "Θα λαμβάνετε email." : "Δεν θα λαμβάνετε email για αυτό.", "ok");
    } catch (err) { toast(err.message, "error"); e.target.checked = !e.target.checked; }
  });

  const box = main.querySelector("#projects");
  const render = () => {
    main.querySelector("h2 .muted").textContent = `(${list.length})`;
    box.innerHTML = list.length ? list.map((p) => projectCard(p, { editable: true })).join("")
      : `<div class="empty small-empty"><p>Προσθέστε 3 με 5 χαρακτηριστικά έργα, με έτος, πελάτη και ύψος εργασιών. Μια φωτογραφία κάνει μεγάλη διαφορά.</p></div>`;
    loadPhotos(box);
  };
  render();

  main.querySelector("#add").onclick = () => openProjectDialog(null, (p) => { list = [p, ...list].sort(byYear); render(); });
  box.addEventListener("click", async (e) => {
    const ed = e.target.closest("[data-edit]");
    const rm = e.target.closest("[data-remove]");
    if (ed) {
      const p = list.find((x) => x.id === Number(ed.dataset.edit));
      openProjectDialog(p, (upd) => { forgetPhoto(upd.id); list = list.map((x) => (x.id === upd.id ? upd : x)).sort(byYear); render(); });
    }
    if (rm && await confirmDialog("Να διαγραφεί το έργο από το προφίλ;", { ok: "Διαγραφή", danger: true })) {
      busy(rm, async () => {
        await api(`me/projects/${rm.dataset.remove}`, { method: "DELETE" });
        list = list.filter((x) => x.id !== Number(rm.dataset.remove));
        render();
      });
    }
  });
}

const byYear = (a, b) => (b.year || 0) - (a.year || 0);

function openProjectDialog(p, onSaved) {
  const dlg = document.createElement("dialog");
  dlg.className = "modal wide";
  dlg.innerHTML = `
  <form class="stack" id="pf">
    <h3>${p ? "Επεξεργασία έργου" : "Νέο έργο"}</h3>
    <label>Τίτλος έργου<input name="title" required maxlength="200" value="${esc(p?.title)}" placeholder="π.χ. Γυψοσανίδες και ψευδοροφές εμπορικού κέντρου 12.000 m²"></label>
    <div class="grid2">
      <label>Πελάτης / κύριος έργου<input name="client" value="${esc(p?.client)}"></label>
      <label>Τοποθεσία<input name="location" value="${esc(p?.location)}"></label>
      <label>Περιφέρεια<select name="region">${options("regions", p?.region || "", { empty: "—" })}</select></label>
      <label>Έτος ολοκλήρωσης<input name="year" type="number" min="1950" max="${new Date().getFullYear() + 1}" value="${esc(p?.year ?? "")}"></label>
      <label>Κατηγορία<select name="category">${options("project_categories", p?.category || "", { empty: "—" })}</select></label>
      <label>Ύψος εργασιών<select name="value_range">${options("value_ranges", p?.value_range || "", { empty: "Δεν αναφέρεται" })}</select></label>
    </div>
    <label>Ειδικότητες έργου</label>
    <div class="chip-groups compact">${tradeChips("specialties", p?.specialties || [])}</div>
    <label>Περιγραφή<textarea name="description" rows="3" placeholder="Τι περιλάμβανε, ιδιαιτερότητες, χρόνος εκτέλεσης…">${esc(p?.description)}</textarea></label>
    <label>Φωτογραφία <small>(JPG, PNG ή WEBP, έως 8 MB)</small><input type="file" name="photo" accept=".jpg,.jpeg,.png,.webp"></label>
    ${p?.has_photo ? `<label class="check"><input type="checkbox" name="remove_photo" value="1"> Αφαίρεση υπάρχουσας φωτογραφίας</label>` : ""}
    <div class="row end"><button type="button" class="btn ghost" value="cancel">Άκυρο</button><button class="btn primary">Αποθήκευση</button></div>
  </form>`;
  document.body.append(dlg);
  dlg.showModal();
  const close = () => { dlg.close(); dlg.remove(); };
  dlg.querySelector("[value=cancel]").onclick = close;
  dlg.addEventListener("cancel", () => dlg.remove());
  const form = dlg.querySelector("#pf");
  form.onsubmit = (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const specs = fd.getAll("specialties");
    fd.delete("specialties");
    fd.append("specialties", specs.join(","));
    if (!fd.get("photo")?.size) fd.delete("photo");
    busy(form.querySelector("button.primary"), async () => {
      const saved = await api(p ? `me/projects/${p.id}` : "me/projects", { method: p ? "PATCH" : "POST", body: fd });
      toast(p ? "Το έργο ενημερώθηκε." : "Το έργο προστέθηκε.", "ok");
      close();
      onSaved(saved);
    });
  };
}
