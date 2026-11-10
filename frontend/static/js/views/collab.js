// Συνεργασία μετά την ανάθεση: μηνύματα, συμφωνητικό, αξιολόγηση.
import { api, download } from "../api.js";
import { busy, companyLink, esc, fmt, toast } from "../ui.js";

export function starsOnly(n) {
  const full = Math.round(n || 0);
  return `<span class="stars" title="${n} από 5">${"★".repeat(full)}<span class="off">${"★".repeat(5 - full)}</span></span>`;
}

export function stars(avg, count) {
  if (!count) return `<span class="muted small">Χωρίς αξιολογήσεις</span>`;
  const full = Math.round(avg);
  return `<span class="stars" title="${avg} από 5">${"★".repeat(full)}<span class="off">${"★".repeat(5 - full)}</span></span>
    <span class="small"><b>${String(avg).replace(".", ",")}</b> <span class="muted">(${count})</span></span>`;
}

export async function collabTab(el, job) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const threads = await api(`jobs/${job.id}/threads`);
  const owner = job.is_owner;
  let current = owner ? Number(params.get("with")) || threads[0]?.with : threads[0]?.with;

  el.innerHTML = `
  <div class="collab ${owner && threads.length > 1 ? "with-threads" : ""}">
    ${owner && threads.length > 1 ? `<aside class="panel threads">${threads.map((t) => `
      <button class="thread ${t.with === current ? "on" : ""}" data-with="${t.with}">
        <b>${esc(t.company.name)}</b>${t.unread ? `<span class="badge live">${t.unread}</span>` : ""}
        <small class="muted">${t.last ? esc((t.last.mine ? "Εσείς: " : "") + (t.last.text || "συνημμένο")).slice(0, 60) : "Χωρίς μηνύματα"}</small>
      </button>`).join("")}</aside>` : ""}
    <section class="panel chat-panel">
      <div class="row wrap"><h2 class="grow" id="chat-title"></h2>
        <a class="btn sm" id="contract-btn">Συμφωνητικό</a></div>
      <div class="chat" id="chat"><div class="loading">Φόρτωση…</div></div>
      <form id="send" class="chat-form">
        <textarea name="text" rows="2" placeholder="Γράψτε μήνυμα… (Enter για αποστολή, Shift+Enter για νέα γραμμή)"></textarea>
        <div class="row wrap"><label class="btn sm ghost file">📎 Αρχείο<input type="file" name="attachment" hidden></label>
          <span class="muted small grow" id="file-name"></span><button class="btn primary sm">Αποστολή</button></div>
      </form>
    </section>
    <section class="panel" id="review"></section>
  </div>`;

  const chat = el.querySelector("#chat");
  const title = el.querySelector("#chat-title");
  const form = el.querySelector("#send");

  const load = async (scroll = true) => {
    if (!current) { chat.innerHTML = `<p class="muted">Δεν υπάρχει συνομιλία.</p>`; return; }
    const t = threads.find((x) => x.with === current);
    title.innerHTML = `Συνομιλία με ${companyLink(t.company)}`;
    el.querySelector("#contract-btn").href = `#/jobs/${job.id}/contract${owner ? `?bid=${job.awarded.awards.find((a) => a.company.id === t.company.id)?.bid_id}` : ""}`;
    const msgs = await api(`jobs/${job.id}/messages${owner ? `?with=${current}` : ""}`);
    const atBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 40;
    chat.innerHTML = msgs.length ? msgs.map((m) => `
      <div class="msg ${m.mine ? "mine" : ""}">
        ${m.text ? `<div class="bubble">${esc(m.text).replace(/\n/g, "<br>")}</div>` : ""}
        ${m.attachment ? `<button class="attach" data-att="${m.id}" data-name="${esc(m.attachment)}">📎 ${esc(m.attachment)}</button>` : ""}
        <small class="muted">${fmt.datetime(m.created_at)}${m.mine && m.read ? " · διαβάστηκε" : ""}</small>
      </div>`).join("") : `<p class="muted center">Ξεκινήστε τη συζήτηση: χρονοδιάγραμμα, πρόσβαση στο εργοτάξιο, παραδόσεις υλικών.</p>`;
    if (scroll || atBottom) chat.scrollTop = chat.scrollHeight;
    const btn = el.querySelector(`.thread[data-with="${current}"] .badge`);
    if (btn) btn.remove();
  };

  el.querySelector(".threads")?.addEventListener("click", (e) => {
    const b = e.target.closest("[data-with]");
    if (!b) return;
    current = Number(b.dataset.with);
    el.querySelectorAll(".thread").forEach((x) => x.classList.toggle("on", x === b));
    load(); renderReview();
  });
  chat.addEventListener("click", (e) => {
    const a = e.target.closest("[data-att]");
    if (a) busy(a, () => download(`jobs/${job.id}/messages/${a.dataset.att}/attachment`, a.dataset.name));
  });
  form.attachment.onchange = () => { el.querySelector("#file-name").textContent = form.attachment.files[0]?.name || ""; };
  form.text.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  form.onsubmit = (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    if (!fd.get("attachment")?.size) fd.delete("attachment");
    if (!fd.get("text").trim() && !fd.get("attachment")) return;
    if (owner) fd.append("with", current);
    busy(form.querySelector("button.primary"), async () => {
      await api(`jobs/${job.id}/messages`, { method: "POST", body: fd });
      form.reset(); el.querySelector("#file-name").textContent = "";
      load();
    });
  };

  // Αξιολόγηση
  const reviewBox = el.querySelector("#review");
  const renderReview = async () => {
    const data = await api(`jobs/${job.id}/reviews`);
    const t = owner ? data.targets.find((x) => threads.find((th) => th.with === current)?.company.id === x.company.id) : data.targets[0];
    if (!t) { reviewBox.innerHTML = ""; return; }
    const r = t.review;
    reviewBox.innerHTML = `
      <h2>Αξιολόγηση: ${esc(t.company.name)}</h2>
      <p class="muted small">Η αξιολόγηση εμφανίζεται στο δημόσιο προφίλ της εταιρείας. ${r ? "Μπορείτε να την αλλάξετε." : ""}</p>
      <form id="rv" class="stack">
        <div class="criteria">${data.criteria.map((c) => `
          <div class="crit"><span>${esc(c.label)}</span>
            <span class="rate" data-key="${c.key}">${[1, 2, 3, 4, 5].map((n) => `<button type="button" data-n="${n}" class="${(r?.criteria[c.key] || 0) >= n ? "on" : ""}" aria-label="${n}">★</button>`).join("")}</span></div>`).join("")}</div>
        <textarea name="comment" rows="3" placeholder="Σχόλιο (προαιρετικό)">${esc(r?.comment || "")}</textarea>
        <div class="row end"><button class="btn primary sm">${r ? "Ενημέρωση αξιολόγησης" : "Υποβολή αξιολόγησης"}</button></div>
      </form>`;
    const values = { ...(r?.criteria || {}) };
    reviewBox.querySelectorAll(".rate").forEach((box) => {
      box.addEventListener("click", (e) => {
        const n = Number(e.target.dataset.n);
        if (!n) return;
        values[box.dataset.key] = n;
        box.querySelectorAll("button").forEach((b) => b.classList.toggle("on", Number(b.dataset.n) <= n));
      });
    });
    reviewBox.querySelector("#rv").onsubmit = (e) => {
      e.preventDefault();
      if (data.criteria.some((c) => !values[c.key])) { toast("Βαθμολογήστε όλα τα κριτήρια.", "error"); return; }
      busy(e.target.querySelector("button.primary"), async () => {
        await api(`jobs/${job.id}/reviews`, { method: "POST", body: { target: t.company.id, criteria: values, comment: e.target.comment.value } });
        toast("Η αξιολόγηση αποθηκεύτηκε.", "ok");
        renderReview();
      });
    };
  };

  await load();
  renderReview();
  const timer = setInterval(() => { if (!chat.isConnected) clearInterval(timer); else load(false).catch(() => {}); }, 15000);
}

// ---------------------------------------------------------------------------------------------
export async function contractView(main, [id]) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const c = await api(`jobs/${id}/contract${params.get("bid") ? `?bid=${params.get("bid")}` : ""}`);
  const p = (x) => `<b>${esc(x.name)}</b>, ΑΦΜ ${esc(x.vat_number)}${x.tax_office ? `, ΔΟΥ ${esc(x.tax_office)}` : ", ΔΟΥ ______"},
    με έδρα ${x.address ? esc([x.address, x.city].filter(Boolean).join(", ")) : "________________"}, που εκπροσωπείται από ${x.representative ? esc(x.representative) : "________________"}`;
  main.innerHTML = `
  <div class="no-print row wrap contract-bar">
    <a class="back grow" href="#/jobs/${id}?tab=collab">← Πίσω στην εργασία</a>
    <button class="btn" id="print">Εκτύπωση / PDF</button>
  </div>
  <p class="no-print banner small">Πρότυπο συμφωνητικού προς έλεγχο από τα μέρη ή νομικό σύμβουλο. Μετά την υπογραφή, το συμφωνητικό
    υποβάλλεται για ψηφιακή θεώρηση στην ΑΑΔΕ (άρθρο 19 Ν. 820/1978) μέσω <a href="https://www.gov.gr/en/org/aade/adeiodoteseis-kai-summorphose/psephiake-bebaiose-sumphonetikon-analepses-tekhnikon-ergon-apo-ergolabo-upergolabo" target="_blank" rel="noopener">gov.gr</a>.
    Συμπληρώστε τα κενά (ΔΟΥ, διεύθυνση) στο προφίλ της εταιρείας για να εμφανίζονται αυτόματα.</p>
  <article class="contract">
    <h1>ΙΔΙΩΤΙΚΟ ΣΥΜΦΩΝΗΤΙΚΟ ΑΝΑΘΕΣΗΣ ΥΠΕΡΓΟΛΑΒΙΑΣ</h1>
    <p>Στην/Στο ______________ σήμερα ____/____/______ οι παρακάτω συμβαλλόμενοι:</p>
    <ol>
      <li>${p(c.contractor)}, εφεξής «<b>Εργολάβος</b>», και</li>
      <li>${p(c.subcontractor)}, εφεξής «<b>Υπεργολάβος</b>»,</li>
    </ol>
    <p>συμφώνησαν και συναποδέχθηκαν τα ακόλουθα:</p>
    <h2>Άρθρο 1. Αντικείμενο</h2>
    <p>Ο Εργολάβος αναθέτει στον Υπεργολάβο και ο Υπεργολάβος αναλαμβάνει την εκτέλεση των εργασιών
      «<b>${esc(c.job.title)}</b>»${c.scope.length ? `, και συγκεκριμένα των ενοτήτων: <b>${c.scope.map(esc).join(", ")}</b>` : ""},
      στο έργο που βρίσκεται ${c.job.location ? `στην περιοχή ${esc(c.job.location)}, ` : ""}${esc(c.job.region)},
      σύμφωνα με την προμέτρηση και τις τιμές του Παραρτήματος, τα σχέδια και τα έγγραφα της εργασίας όπως δημοσιεύτηκαν στην πλατφόρμα subcontractor.gr.</p>
    <h2>Άρθρο 2. Τίμημα</h2>
    <p>Το συνολικό συμφωνηθέν τίμημα ανέρχεται σε <b>${fmt.money(c.amount)}</b> πλέον ΦΠΑ 24% (${fmt.money(c.vat_24)}), ήτοι συνολικά
      <b>${fmt.money(c.amount_with_vat)}</b>, και προκύπτει από τις τιμές μονάδας του Παραρτήματος επί τις ποσότητες. Οι τελικές ποσότητες
      επιμετρώνται επί τόπου και το τίμημα προσαρμόζεται με βάση τις τιμές μονάδας.</p>
    <h2>Άρθρο 3. Τρόπος πληρωμής</h2>
    <p>${c.payment_terms ? esc(c.payment_terms) : "______________________________________________"}.</p>
    <h2>Άρθρο 4. Χρόνος εκτέλεσης</h2>
    <p>Οι εργασίες ξεκινούν ${c.job.start_date ? `στις ${fmt.date(c.job.start_date)}` : "στις ____/____/______"} και ολοκληρώνονται εντός
      ${c.duration_days ? `<b>${c.duration_days}</b> ημερών` : "______ ημερών"} από την έναρξη${c.job.duration_text ? ` (εκτίμηση εργοδότη: ${esc(c.job.duration_text)})` : ""}.</p>
    ${c.exclusions ? `<h2>Άρθρο 5. Εξαιρέσεις και παραδοχές της προσφοράς</h2><p>${esc(c.exclusions).replace(/\n/g, "<br>")}</p>` : ""}
    <h2>Άρθρο ${c.exclusions ? 6 : 5}. Υποχρεώσεις του Υπεργολάβου</h2>
    <p>Ο Υπεργολάβος εκτελεί τις εργασίες έντεχνα, σύμφωνα με τους κανόνες της τέχνης, τις ισχύουσες προδιαγραφές και τη νομοθεσία
      για την υγεία και ασφάλεια στην εργασία. Απασχολεί δικό του, νόμιμα ασφαλισμένο προσωπικό και ευθύνεται για τις ασφαλιστικές
      εισφορές του. Διαθέτει τις άδειες και τα προσόντα που απαιτούνται για τις εργασίες.</p>
    <h2>Άρθρο ${c.exclusions ? 7 : 6}. Ψηφιακή θεώρηση</h2>
    <p>Το παρόν υποβάλλεται για ψηφιακή βεβαίωση στην ΑΑΔΕ σύμφωνα με το άρθρο 19 του Ν. 820/1978, όπως ισχύει.</p>
    <h2>Άρθρο ${c.exclusions ? 8 : 7}. Λοιποί όροι</h2>
    <p>______________________________________________________________________________</p>
    <p>Το παρόν συντάχθηκε σε δύο όμοια πρωτότυπα και κάθε συμβαλλόμενος έλαβε από ένα.</p>
    <div class="signatures"><div>Ο ΕΡΓΟΛΑΒΟΣ<br><br><br>${esc(c.contractor.name)}</div><div>Ο ΥΠΕΡΓΟΛΑΒΟΣ<br><br><br>${esc(c.subcontractor.name)}</div></div>

    <h2 class="page-break">Παράρτημα: Προμέτρηση και τιμές</h2>
    <table class="tbl">
      <thead><tr><th>Α/Α</th><th>Περιγραφή</th><th>Μον.</th><th class="num">Ποσότητα</th><th class="num">Τιμή μον.</th><th class="num">Σύνολο</th></tr></thead>
      <tbody>${c.appendix.map((s) => `
        ${c.appendix.length > 1 || s.code ? `<tr class="section-row"><td>${esc(s.code)}</td><td colspan="5">${esc(s.title)}</td></tr>` : ""}
        ${s.rows.map((r) => `<tr><td>${esc(r.code)}</td><td>${esc(r.description)}</td><td>${esc(r.unit)}</td>
          <td class="num">${fmt.num(r.quantity)}</td><td class="num">${fmt.money(r.unit_price)}</td><td class="num">${fmt.money(r.total)}</td></tr>`).join("")}`).join("")}</tbody>
      <tfoot><tr><td></td><td>Σύνολο χωρίς ΦΠΑ</td><td></td><td></td><td></td><td class="num">${fmt.money(c.amount)}</td></tr></tfoot>
    </table>
    <p class="muted small">Ανάθεση μέσω subcontractor.gr στις ${fmt.date(c.awarded_at)}.</p>
  </article>`;
  main.querySelector("#print").onclick = () => window.print();
}
