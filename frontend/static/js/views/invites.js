// Προσκλήσεις υπεργολάβων σε εργασία (πάνελ για επεξεργασία και σελίδα εργασίας).
import { api } from "../api.js";
import { busy, confirmDialog, esc, options, toast, tradeTags, verifiedMark } from "../ui.js";

const STATUS = {
  pending: ["Σε αναμονή", "muted"], declined: ["Απέρριψε", "warn"],
};
const BID = { draft: ["Ετοιμάζει προσφορά", "live"], submitted: ["Υπέβαλε προσφορά", "ok"], withdrawn: ["Απέσυρε", "muted"] };

export async function invitesPanel(el, job, { onChange } = {}) {
  let list = await api(`jobs/${job.id}/invitations`);
  const canInvite = job.status === "draft" || job.phase === "bidding";
  const draft = job.status === "draft";

  const render = () => {
    el.innerHTML = `
      ${job.visibility === "private"
        ? `<p class="banner small">Ιδιωτική εργασία: τη βλέπουν μόνο οι υπεργολάβοι που προσκαλείτε.</p>`
        : `<p class="muted small">Η εργασία είναι δημόσια. Με την πρόσκληση ειδοποιείτε απευθείας υπεργολάβους που θέλετε οπωσδήποτε να δώσουν προσφορά.</p>`}
      ${list.length ? `<ul class="inv-list">${list.map((i) => {
        const [st, cls] = i.bid_status ? BID[i.bid_status] : STATUS[i.status];
        return `<li><a class="co-link" href="#/companies/${i.company.id}">${esc(i.company.name)}</a> ${verifiedMark(i.company)}
          <span class="muted small">${esc(i.company.region_display || "")}</span><span class="grow"></span>
          <span class="badge ${cls}">${esc(st)}</span>
          ${draft ? `<span class="muted small">θα σταλεί με τη δημοσίευση</span>` : ""}
          ${!i.bid_status && canInvite ? `<button class="icon-btn" data-rm="${i.id}" title="Αφαίρεση">×</button>` : ""}</li>`;
      }).join("")}</ul>` : `<p class="muted small">Δεν έχετε στείλει προσκλήσεις.</p>`}
      ${canInvite ? `
      <div class="inv-search">
        <div class="row wrap">
          <input type="search" id="inv-q" placeholder="Αναζήτηση υπεργολάβου (όνομα, πόλη, έργο)" class="grow">
          <select id="inv-trade">${options("specialties", job.trades?.[0] || "", { empty: "Όλες οι ειδικότητες" })}</select>
          <select id="inv-region">${options("regions", job.region || "", { empty: "Όλες οι περιοχές" })}</select>
        </div>
        <div id="inv-results" class="inv-results"></div>
        <textarea id="inv-msg" rows="2" placeholder="Προαιρετικό μήνυμα προς τους προσκεκλημένους"></textarea>
        <div class="row end"><button class="btn primary sm" id="inv-send" disabled>Πρόσκληση επιλεγμένων</button></div>
      </div>` : ""}`;
    if (canInvite) search();
  };

  let timer;
  const search = async () => {
    const q = el.querySelector("#inv-q")?.value || "";
    const qs = new URLSearchParams({ role: "subcontractor" });
    const trade = el.querySelector("#inv-trade").value;
    const region = el.querySelector("#inv-region").value;
    if (q) qs.set("q", q);
    if (trade) qs.set("specialty", trade);
    if (region) qs.set("region", region);
    const res = await api(`companies?${qs}`);
    const invited = new Set(list.map((i) => i.company.id));
    const box = el.querySelector("#inv-results");
    if (!box) return;
    box.innerHTML = res.length ? res.slice(0, 30).map((c) => `
      <label class="inv-row ${invited.has(c.id) ? "done" : ""}">
        <input type="checkbox" value="${c.id}" ${invited.has(c.id) ? "checked disabled" : ""}>
        <span class="grow"><b>${esc(c.name)}</b> ${verifiedMark(c)} <span class="muted small">${esc([c.city, c.region_display].filter(Boolean).join(", "))} · ${c.projects_count} έργα</span>
          <span class="chips static">${tradeTags(c.specialties, 3)}</span></span>
        ${invited.has(c.id) ? `<span class="muted small">προσκεκλημένος</span>` : ""}
      </label>`).join("") : `<p class="muted small pad">Δεν βρέθηκαν υπεργολάβοι με αυτά τα φίλτρα.</p>`;
  };

  el.addEventListener("input", (e) => {
    if (e.target.id === "inv-q") { clearTimeout(timer); timer = setTimeout(search, 250); }
  });
  el.addEventListener("change", (e) => {
    if (e.target.id === "inv-trade" || e.target.id === "inv-region") search();
    const n = el.querySelectorAll("#inv-results input:checked:not(:disabled)").length;
    const btn = el.querySelector("#inv-send");
    if (btn) { btn.disabled = !n; btn.textContent = n ? `Πρόσκληση ${n} ${n === 1 ? "υπεργολάβου" : "υπεργολάβων"}` : "Πρόσκληση επιλεγμένων"; }
  });
  el.addEventListener("click", async (e) => {
    if (e.target.id === "inv-send") {
      const ids = [...el.querySelectorAll("#inv-results input:checked:not(:disabled)")].map((i) => Number(i.value));
      busy(e.target, async () => {
        list = await api(`jobs/${job.id}/invitations`, { method: "POST", body: { company_ids: ids, message: el.querySelector("#inv-msg").value } });
        toast(draft ? "Οι προσκλήσεις θα σταλούν με τη δημοσίευση." : "Οι προσκλήσεις στάλθηκαν.", "ok");
        render(); onChange?.(list);
      });
    }
    const rm = e.target.closest("[data-rm]");
    if (rm && await confirmDialog("Αφαίρεση της πρόσκλησης;", { ok: "Αφαίρεση" })) {
      busy(rm, async () => {
        await api(`jobs/${job.id}/invitations/${rm.dataset.rm}`, { method: "DELETE" });
        list = list.filter((i) => i.id !== Number(rm.dataset.rm));
        render(); onChange?.(list);
      });
    }
  });
  render();
  return list;
}

// Από το προφίλ υπεργολάβου: επιλογή εργασίας και αποστολή πρόσκλησης
export async function inviteToJobDialog(company) {
  const jobs = (await api("jobs?scope=mine")).filter((j) => j.phase === "draft" || j.phase === "bidding");
  const dlg = document.createElement("dialog");
  dlg.className = "modal wide";
  dlg.innerHTML = jobs.length ? `
    <form class="stack" id="f">
      <h3>Πρόσκληση της «${esc(company.name)}»</h3>
      <label>Εργασία<select name="job">${jobs.map((j) => `<option value="${j.id}">${esc(j.title)}${j.phase === "draft" ? " (πρόχειρο)" : ""}</option>`).join("")}</select></label>
      <label>Μήνυμα <small>(προαιρετικό)</small><textarea name="message" rows="3"></textarea></label>
      <div class="row end"><button type="button" class="btn ghost" value="cancel">Άκυρο</button><button class="btn primary">Αποστολή πρόσκλησης</button></div>
    </form>` : `
    <div class="stack"><h3>Δεν έχετε ανοιχτή εργασία</h3>
      <p class="muted">Δημιουργήστε πρώτα μια εργασία και μετά προσκαλέστε την εταιρεία.</p>
      <div class="row end"><button type="button" class="btn ghost" value="cancel">Κλείσιμο</button><a class="btn primary" href="#/jobs/new">Νέα εργασία</a></div></div>`;
  document.body.append(dlg);
  dlg.showModal();
  const close = () => { dlg.close(); dlg.remove(); };
  dlg.querySelector("[value=cancel]").onclick = close;
  dlg.querySelector("a")?.addEventListener("click", close);
  dlg.addEventListener("cancel", () => dlg.remove());
  const f = dlg.querySelector("#f");
  if (f) f.onsubmit = (e) => {
    e.preventDefault();
    busy(f.querySelector("button.primary"), async () => {
      const job = jobs.find((j) => j.id === Number(f.job.value));
      await api(`jobs/${job.id}/invitations`, { method: "POST", body: { company_ids: [company.id], message: f.message.value } });
      toast(job.phase === "draft" ? "Η πρόσκληση θα σταλεί με τη δημοσίευση της εργασίας." : "Η πρόσκληση στάλθηκε.", "ok");
      close();
    });
  };
}
