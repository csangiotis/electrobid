// Προσφορά υπεργολάβου (με ενότητες και BAFO) και σύγκριση/ανάθεση για τον εργολάβο.
import { api, download } from "../api.js";
import {
  bidBadge, busy, companyLink, confirmDialog, esc, fmt, fromLocalInput, parseNum, timeLeft, toast,
  toLocalInput, verifiedMark,
} from "../ui.js";

const reload = () => dispatchEvent(new HashChangeEvent("hashchange"));

// Ενότητα κάθε γραμμής: id της προηγούμενης επικεφαλίδας (0 αν δεν υπάρχει)
export function sectionsOf(boq) {
  const map = new Map();
  const sections = [];
  let cur = { id: 0, code: "", title: "Γενικά", items: [] };
  for (const r of boq) {
    if (r.is_section) {
      if (cur.items.length) sections.push(cur);
      cur = { id: r.id, code: r.code, title: r.description, items: [] };
    } else { cur.items.push(r); map.set(r.id, cur.id); }
  }
  if (cur.items.length) sections.push(cur);
  return { map, sections };
}

export function awardedBanner(job) {
  const a = job.awarded;
  if (a.is_me) {
    const parts = a.awards.map((x) => (x.sections.length ? `ενότητες ${x.sections.map(esc).join(", ")}` : "όλη η εργασία") + ` · ${fmt.money(x.amount)}`);
    return `<div class="banner ok"><b>Συγχαρητήρια, σας ανατέθηκε η εργασία</b> (${parts.join("; ")}). Επικοινωνήστε με τον εργολάβο από την καρτέλα «Συνεργασία».</div>`;
  }
  if (job.is_owner) {
    return `<div class="banner ok"><b>Ανάθεση:</b> ${a.awards.map((x) => `${companyLink(x.company)}${x.sections.length ? ` (${x.sections.map(esc).join(", ")})` : ""} · ${fmt.money(x.amount)}`).join(" · ")}</div>`;
  }
  return `<div class="banner">Η εργασία έχει ανατεθεί.</div>`;
}

// ---------------------------------------------------------------------------------------------
export async function myBid(el, job, boq, stale) {
  const bid = await api(`jobs/${job.id}/my-bid`);
  if (stale()) return;
  const { map: secOf, sections } = sectionsOf(boq);
  const lines = boq.filter((r) => !r.is_section);
  const inBafo = job.phase === "bafo" && bid?.bafo_invited;
  const editable = job.phase === "bidding" || (bid?.can_edit ?? false);
  const prices = new Map((bid?.lines || []).map((l) => [l.item, l]));
  const excluded = new Set(bid?.excluded_sections || []);

  if (!bid && !editable) {
    el.innerHTML = `<div class="empty"><h2>Η υποβολή έχει κλείσει</h2><p>Δεν δώσατε προσφορά σε αυτή την εργασία.</p></div>`;
    return;
  }
  const ro = editable ? "" : "readonly";
  const val = (v) => (v === null || v === undefined ? "" : String(v).replace(".", ","));
  const multi = sections.length > 1 || (sections[0] && sections[0].id !== 0);

  const rows = boq.map((r) => {
    if (r.is_section) {
      const ex = excluded.has(r.id);
      return `<tr class="section-row" data-sec="${r.id}"><td>${esc(r.code)}</td><td colspan="3">${esc(r.description)}</td>
        <td colspan="2" class="num">${editable ? `<label class="check sec-toggle"><input type="checkbox" data-exclude="${r.id}" ${ex ? "checked" : ""}> Δεν τιμολογώ αυτή την ενότητα</label>`
          : ex ? `<span class="muted small">εκτός προσφοράς</span>` : ""}<span class="sec-total mono" data-sectotal="${r.id}"></span></td></tr>`;
    }
    const l = prices.get(r.id);
    const ex = excluded.has(secOf.get(r.id));
    const orig = l?.original_unit_price != null && l.original_unit_price !== l.unit_price ? l.original_unit_price : null;
    return `<tr data-item="${r.id}" class="${ex ? "excluded" : ""}"><td class="mono">${esc(r.code)}</td><td>${esc(r.description)}</td><td>${esc(r.unit)}</td>
      <td class="num mono">${fmt.num(r.quantity)}</td>
      <td class="num"><input class="price" name="p-${r.id}" inputmode="decimal" value="${val(l?.unit_price)}" ${ro} ${ex ? "disabled" : ""}>
        ${orig !== null || inBafo && l?.original_unit_price != null ? `<small class="orig">αρχική ${fmt.money(l.original_unit_price)}</small>` : ""}
        ${l?.note || editable ? `<input class="line-note" name="n-${r.id}" placeholder="σημείωση" value="${esc(l?.note || "")}" ${ro} ${ex ? "disabled" : ""}>` : ""}</td>
      <td class="num mono line-total">—</td></tr>`;
  }).join("");

  el.innerHTML = `
  ${inBafo ? `<div class="banner live"><b>Ο εργολάβος ζητά βελτιωμένη τελική προσφορά</b> έως ${fmt.datetime(job.bafo_deadline)} (${esc(timeLeft(job.bafo_deadline))}).
     ${job.bafo_message ? `«${esc(job.bafo_message)}»` : ""} Αναθεωρήστε τις τιμές και πατήστε «Υποβολή βελτιωμένης προσφοράς».
     ${bid.bafo_submitted_at ? `<br><small>Υποβλήθηκε βελτιωμένη προσφορά ${fmt.datetime(bid.bafo_submitted_at)}.</small>` : ""}</div>` : ""}
  ${bid?.outdated ? `<div class="banner warn"><b>Η εργασία έχει νέο συμπλήρωμα μετά την υποβολή σας.</b> Ελέγξτε τα έγγραφα και ενημερώστε την προσφορά.</div>` : ""}
  ${bid?.status === "submitted" && job.phase === "bidding" ? `<div class="banner ok">Η προσφορά σας υποβλήθηκε ${fmt.datetime(bid.submitted_at)}. Μπορείτε να την αλλάξετε μέχρι τη λήξη (${esc(timeLeft(job.bid_deadline))}). Ο εργολάβος βλέπει τις τιμές μόνο μετά τη λήξη.</div>` : ""}
  ${bid?.status === "withdrawn" ? `<div class="banner">Η προσφορά έχει αποσυρθεί. Αποθηκεύστε για να τη συνεχίσετε ως πρόχειρη.</div>` : ""}
  <form id="bid" class="bid-layout">
    <div class="panel">
      <div class="row wrap"><h2 class="grow">Τιμολόγηση προμέτρησης ${bid ? bidBadge(bid.status) : ""}</h2>
        ${editable ? `<button type="button" class="btn sm ghost" id="paste">Επικόλληση στήλης τιμών από Excel</button>` : ""}</div>
      <p class="muted small">Τιμές μονάδας χωρίς ΦΠΑ. Αφήστε κενό αν δεν τιμολογείτε μια γραμμή και εξηγήστε στη σημείωση.
        ${multi && editable ? "Μπορείτε να δώσετε <b>μερική προσφορά</b>: σημειώστε τις ενότητες που δεν τιμολογείτε." : ""}</p>
      <div class="table-wrap"><table class="tbl boq priced">
        <thead><tr><th>Α/Α</th><th>Περιγραφή</th><th>Μον.</th><th class="num">Ποσότητα</th><th class="num">Τιμή μον. (€)</th><th class="num">Σύνολο</th></tr></thead>
        <tbody>${rows}</tbody></table></div>
    </div>
    <aside class="panel sticky bid-side">
      <div class="total-box"><small>Σύνολο προσφοράς (χωρίς ΦΠΑ)</small><b id="total">—</b>
        <span id="missing" class="muted small"></span></div>
      <label>Χρόνος εκτέλεσης (ημέρες)<input name="duration_days" type="number" min="1" value="${esc(bid?.duration_days ?? "")}" ${ro}></label>
      <label>Ισχύς προσφοράς (ημέρες)<input name="validity_days" type="number" min="1" value="${esc(bid?.validity_days ?? 60)}" ${ro}></label>
      <label>Όροι πληρωμής<input name="payment_terms" value="${esc(bid?.payment_terms)}" placeholder="π.χ. 30% προκαταβολή, λογαριασμοί ανά μήνα" ${ro}></label>
      <label>Εξαιρέσεις / παραδοχές<textarea name="exclusions" rows="3" placeholder="π.χ. Δεν περιλαμβάνονται χωματουργικά" ${ro}>${esc(bid?.exclusions)}</textarea></label>
      <label>Σημειώσεις<textarea name="notes" rows="2" ${ro}>${esc(bid?.notes)}</textarea></label>
      ${!editable ? `<p class="muted small">${job.phase === "bafo" ? "Ο εργολάβος αξιολογεί βελτιωμένες προσφορές από άλλους υπεργολάβους." : "Η προθεσμία έληξε. Η προσφορά δεν αλλάζει πλέον."}</p>`
        : inBafo ? `<button type="button" class="btn primary block" id="bafo-submit">Υποβολή βελτιωμένης προσφοράς</button>`
        : `<button type="button" class="btn block" id="save">Αποθήκευση${bid?.status === "submitted" ? " αλλαγών" : " πρόχειρου"}</button>
          ${bid?.status !== "submitted" ? `<button type="button" class="btn primary block" id="submit">Υποβολή προσφοράς</button>` : ""}
          ${bid?.status === "submitted" ? `<button type="button" class="btn ghost block danger-text" id="withdraw">Απόσυρση</button>` : ""}`}
    </aside>
  </form>`;

  const form = el.querySelector("#bid");
  const recalc = () => {
    let total = 0; let missing = 0; let bad = 0;
    const secTotals = new Map();
    for (const r of lines) {
      const input = form.elements[`p-${r.id}`];
      const cell = input.closest("tr").querySelector(".line-total");
      const sid = secOf.get(r.id);
      if (excluded.has(sid)) { cell.textContent = "εκτός"; input.classList.remove("invalid"); continue; }
      const p = parseNum(input.value);
      input.classList.toggle("invalid", Number.isNaN(p) || p < 0);
      if (p === null) { missing++; cell.textContent = "—"; continue; }
      if (Number.isNaN(p) || p < 0) { bad++; cell.textContent = "!"; continue; }
      const lt = p * Number(r.quantity);
      total += lt;
      secTotals.set(sid, (secTotals.get(sid) || 0) + lt);
      cell.textContent = fmt.money(lt);
    }
    for (const s of el.querySelectorAll("[data-sectotal]")) {
      const sid = Number(s.dataset.sectotal);
      s.textContent = excluded.has(sid) ? "" : fmt.money(secTotals.get(sid) || 0);
    }
    const active = lines.filter((r) => !excluded.has(secOf.get(r.id))).length;
    el.querySelector("#total").textContent = fmt.money(total);
    el.querySelector("#missing").textContent = (missing ? `${missing} από ${active} γραμμές χωρίς τιμή` : `Τιμολογήθηκαν όλες οι ${active} γραμμές`)
      + (excluded.size ? ` · μερική προσφορά (${excluded.size} ${excluded.size === 1 ? "ενότητα" : "ενότητες"} εκτός)` : "");
    return { missing, bad };
  };
  form.addEventListener("input", recalc);
  form.addEventListener("change", (e) => {
    const sid = e.target.dataset.exclude;
    if (sid === undefined) return;
    const id = Number(sid);
    if (e.target.checked) excluded.add(id); else excluded.delete(id);
    for (const r of lines) {
      if (secOf.get(r.id) !== id) continue;
      const tr = form.querySelector(`tr[data-item="${r.id}"]`);
      tr.classList.toggle("excluded", e.target.checked);
      tr.querySelectorAll("input").forEach((i) => { i.disabled = e.target.checked; });
    }
    recalc();
  });
  recalc();
  if (!editable) return;

  const payload = () => {
    const f = form.elements;
    return {
      duration_days: f.duration_days.value ? Number(f.duration_days.value) : null,
      validity_days: Number(f.validity_days.value || 60),
      payment_terms: f.payment_terms.value, exclusions: f.exclusions.value, notes: f.notes.value,
      excluded_sections: [...excluded],
      lines: lines.map((r) => {
        const ex = excluded.has(secOf.get(r.id));
        const p = ex ? null : parseNum(f[`p-${r.id}`].value);
        return { item: r.id, unit_price: p === null ? null : Math.round(p * 100) / 100, note: ex ? "" : f[`n-${r.id}`]?.value || "" };
      }),
    };
  };
  const save = async () => {
    if (recalc().bad) throw new Error("Διορθώστε τις τιμές που είναι σημειωμένες με κόκκινο.");
    return api(`jobs/${job.id}/my-bid`, { method: "PUT", body: payload() });
  };

  el.querySelector("#save")?.addEventListener("click", (e) => busy(e.target, async () => { await save(); toast("Αποθηκεύτηκε.", "ok"); reload(); }));
  el.querySelector("#bafo-submit")?.addEventListener("click", async (e) => {
    if (!(await confirmDialog("Υποβολή της βελτιωμένης προσφοράς; Μπορείτε να την αλλάξετε μέχρι τη λήξη του γύρου.", { ok: "Υποβολή" }))) return;
    busy(e.target, async () => { await save(); await api(`jobs/${job.id}/my-bid/submit`, { method: "POST" }); toast("Η βελτιωμένη προσφορά υποβλήθηκε.", "ok"); reload(); });
  });
  el.querySelector("#submit")?.addEventListener("click", async (e) => {
    const { missing } = recalc();
    const msg = missing
      ? `${missing} γραμμές δεν έχουν τιμή. Θα φαίνονται ως «χωρίς τιμή» στη σύγκριση. Υποβολή;`
      : "Υποβολή της προσφοράς; Μπορείτε να την αλλάξετε μέχρι τη λήξη της προθεσμίας.";
    if (!(await confirmDialog(msg, { ok: "Υποβολή" }))) return;
    busy(e.target, async () => { await save(); await api(`jobs/${job.id}/my-bid/submit`, { method: "POST" }); toast("Η προσφορά υποβλήθηκε.", "ok"); reload(); });
  });
  el.querySelector("#withdraw")?.addEventListener("click", async (e) => {
    if (!(await confirmDialog("Απόσυρση της προσφοράς; Ο εργολάβος δεν θα τη δει.", { ok: "Απόσυρση", danger: true }))) return;
    busy(e.target, async () => { await api(`jobs/${job.id}/my-bid/withdraw`, { method: "POST" }); reload(); });
  });
  el.querySelector("#paste")?.addEventListener("click", () => {
    const active = lines.filter((r) => !excluded.has(secOf.get(r.id)));
    const dlg = document.createElement("dialog");
    dlg.className = "modal wide";
    dlg.innerHTML = `<form method="dialog" class="stack"><h3>Επικόλληση τιμών</h3>
      <p class="muted small">Αντιγράψτε από το Excel τη στήλη με τις τιμές μονάδας (μία ανά γραμμή, με τη σειρά της προμέτρησης, χωρίς επικεφαλίδες και χωρίς τις ενότητες που δεν τιμολογείτε). Αναμένονται ${active.length} τιμές.</p>
      <textarea name="v" rows="10" class="mono"></textarea>
      <div class="row end"><button class="btn ghost" value="no">Άκυρο</button><button class="btn primary" value="ok">Συμπλήρωση</button></div></form>`;
    document.body.append(dlg);
    dlg.showModal();
    dlg.addEventListener("close", () => {
      if (dlg.returnValue === "ok") {
        const vals = dlg.querySelector("textarea").value.replace(/\r/g, "").split("\n");
        while (vals.length && !vals[vals.length - 1].trim()) vals.pop();
        active.forEach((r, i) => { if (i < vals.length) form.elements[`p-${r.id}`].value = vals[i].split("\t").pop().replace(/[€\s]/g, ""); });
        recalc();
        toast(vals.length === active.length ? `Συμπληρώθηκαν ${vals.length} τιμές.` : `Επικολλήθηκαν ${vals.length} τιμές για ${active.length} γραμμές. Ελέγξτε την αντιστοίχιση.`, vals.length === active.length ? "ok" : "warn");
      }
      dlg.remove();
    });
  });
}

// ---------------------------------------------------------------------------------------------
export async function compare(el, job, _boq, stale) {
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
  const byId = Object.fromEntries(B.map((b) => [b.bid_id, b]));
  const lowest = data.stats.lowest_total;
  const canAct = job.phase === "evaluation" && !data.awards.length;
  const awardedIds = new Set(data.awards.map((a) => a.bid_id));
  const diff = (t) => (lowest && t > lowest ? `+${(((t - lowest) / lowest) * 100).toFixed(1)}%` : "");
  const cell = (r, b) => r.cells[b.bid_id] || r.cells[String(b.bid_id)] || {};
  const multiSection = data.sections.length > 1;

  const card = (b) => {
    const complete = !b.partial && !b.missing_count;
    const change = b.original_total != null && b.original_total !== b.total
      ? `<div class="bafo-change">από ${fmt.money(b.original_total)} <b>${b.total < b.original_total ? "−" : "+"}${Math.abs(((b.total - b.original_total) / b.original_total) * 100).toFixed(1)}%</b></div>` : "";
    return `
    <div class="bidder ${b.rank === 1 && complete ? "best" : ""} ${awardedIds.has(b.bid_id) ? "awarded" : ""}">
      <div class="rank">#${b.rank}</div>
      <h3>${companyLink(b.company)} ${verifiedMark(b.company)}</h3>
      <p class="muted small">${esc(b.company.region_display || "")}</p>
      <div class="amount">${fmt.money(b.total)} <small>${complete ? diff(b.total) : ""}</small></div>
      ${change}
      <ul class="bidder-facts">
        ${b.partial ? `<li class="warn">Μερική προσφορά: ${b.sections_covered.length} από ${data.sections.length} ενότητες</li>` : ""}
        <li>${b.duration_days ? `${b.duration_days} ημέρες εκτέλεση` : "Χρόνος εκτέλεσης: —"}</li>
        <li>${esc(b.payment_terms || "Όροι πληρωμής: —")}</li>
        ${b.missing_count ? `<li class="bad">${b.missing_count} γραμμές χωρίς τιμή</li>` : ""}
        ${b.outdated ? `<li class="warn">Δόθηκε πριν το τελευταίο συμπλήρωμα</li>` : ""}
        ${b.bafo_invited ? `<li class="live">BAFO: ${b.bafo_submitted_at ? "υπέβαλε βελτιωμένη" : data.bafo_active ? "σε αναμονή" : "δεν αναθεώρησε"}</li>` : ""}
      </ul>
      ${b.exclusions ? `<details><summary>Εξαιρέσεις</summary><p>${esc(b.exclusions)}</p></details>` : ""}
      ${b.notes ? `<details><summary>Σημειώσεις</summary><p>${esc(b.notes)}</p></details>` : ""}
      ${awardedIds.has(b.bid_id) ? `<span class="badge ok">Ανάδοχος</span>`
        : canAct && complete ? `<button class="btn sm primary block" data-award="${b.bid_id}">Ανάθεση όλης της εργασίας</button>` : ""}
    </div>`;
  };

  el.innerHTML = `
  ${data.bafo_active ? `<div class="banner live"><b>Γύρος βελτιωμένων προσφορών σε εξέλιξη</b> έως ${fmt.datetime(data.bafo_deadline)} (${esc(timeLeft(data.bafo_deadline))}).
    Μέχρι τότε βλέπετε τις αρχικές τιμές· οι αναθεωρημένες ανοίγουν στη λήξη.</div>` : ""}
  <div class="row wrap"><p class="muted grow">${B.length} προσφορές · διάμεσος πλήρων προσφορών ${fmt.money(data.stats.median_total)}</p>
    ${canAct ? `<button class="btn sm" id="bafo">Ζητήστε βελτιωμένη προσφορά (BAFO)</button>` : ""}
    ${canAct && multiSection ? `<button class="btn sm primary" id="split">Ανάθεση ανά ενότητα</button>` : ""}
    <button class="btn sm" id="xlsx">Εξαγωγή σε Excel</button></div>
  <div class="bidder-cards">${B.map(card).join("")}</div>

  ${multiSection ? `
  <div class="panel">
    <h2>Σύνολα ανά ενότητα</h2>
    <div class="table-wrap"><table class="tbl sections-tbl">
      <thead><tr><th>Ενότητα</th>${B.map((b) => `<th class="num">${companyLink(b.company)}</th>`).join("")}</tr></thead>
      <tbody>${data.sections.map((s) => `<tr><td><b>${esc(s.code)} ${esc(s.title)}</b><div class="muted small">${s.lines} γραμμές</div></td>
        ${B.map((b) => {
          const t = s.totals[b.bid_id] ?? s.totals[String(b.bid_id)];
          return `<td class="num mono ${t == null ? "c-excluded" : s.best_bid_id === b.bid_id ? "c-lowest" : ""}">${t == null ? "—" : fmt.money(t)}</td>`;
        }).join("")}</tr>`).join("")}</tbody>
      <tfoot><tr><td>Βέλτιστος συνδυασμός ανά ενότητα</td><td colspan="${B.length}" class="num mono"><b>${data.best_combination.total != null ? fmt.money(data.best_combination.total) : "—"}</b>
        ${data.best_combination.total != null && lowest ? ` <span class="muted small">(${data.best_combination.total < lowest ? `${fmt.money(lowest - data.best_combination.total)} φθηνότερα από την καλύτερη πλήρη` : "όχι φθηνότερος από την καλύτερη πλήρη προσφορά"})</span>` : ""}</td></tr></tfoot>
    </table></div>
  </div>` : ""}

  <div class="panel">
    <div class="row wrap"><h2 class="grow">Σύγκριση ανά γραμμή</h2>
      <div class="legend"><span class="lg lowest">χαμηλότερη</span><span class="lg outlier">±30% από διάμεσο</span><span class="lg missing">χωρίς τιμή</span><span class="lg excl">εκτός προσφοράς</span></div></div>
    <div class="table-wrap compare-wrap"><table class="tbl compare">
      <thead><tr><th class="sticky-col">Α/Α</th><th class="sticky-col2">Περιγραφή</th><th>Μον.</th><th class="num">Ποσ.</th>
        ${B.map((b) => `<th class="num bidder-col">${companyLink(b.company)}<small>τιμή μον. / σύνολο</small></th>`).join("")}
        <th class="num">Διάμεσος</th></tr></thead>
      <tbody>${data.rows.map((r) => r.is_section
        ? `<tr class="section-row"><td class="sticky-col">${esc(r.code)}</td><td class="sticky-col2" colspan="${3 + B.length + 1}">${esc(r.description)}</td></tr>`
        : `<tr><td class="sticky-col mono">${esc(r.code)}</td><td class="sticky-col2 desc">${esc(r.description)}</td><td>${esc(r.unit)}</td><td class="num mono">${fmt.num(r.quantity)}</td>
          ${B.map((b) => {
            const c = cell(r, b);
            const cls = { lowest: "c-lowest", missing: "c-missing", outlier_high: "c-outlier", outlier_low: "c-outlier", excluded: "c-excluded" }[c.flag] || "";
            if (c.flag === "excluded") return `<td class="num ${cls}"><small>εκτός</small></td>`;
            return `<td class="num mono ${cls}" ${c.note ? `title="${esc(c.note)}"` : ""}>${c.unit_price == null ? "—" : `${fmt.money(c.unit_price)}${c.original_unit_price != null ? `<s class="orig">${fmt.money(c.original_unit_price)}</s>` : ""}<small>${fmt.money(c.line_total)}</small>`}${c.note ? " ✎" : ""}</td>`;
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
    if (btn) {
      const b = byId[btn.dataset.award];
      if (!(await confirmDialog(`Ανάθεση όλης της εργασίας στην «${b.company.name}» με ${fmt.money(b.total)}; Οι υπόλοιποι υπεργολάβοι θα ενημερωθούν.`, { ok: "Ανάθεση" }))) return;
      busy(btn, async () => { await api(`jobs/${job.id}/award`, { method: "POST", body: { bid_id: b.bid_id } }); toast("Η εργασία ανατέθηκε.", "ok"); reload(); });
    }
    if (e.target.id === "split") splitDialog(job, data, byId);
    if (e.target.id === "bafo") bafoDialog(job, B);
  });
}

function splitDialog(job, data, byId) {
  const dlg = document.createElement("dialog");
  dlg.className = "modal wide";
  dlg.innerHTML = `<form class="stack" id="f">
    <h3>Ανάθεση ανά ενότητα</h3>
    <p class="muted small">Για κάθε ενότητα επιλέξτε υπεργολάβο. Εμφανίζονται μόνο όσοι την τιμολόγησαν πλήρως· προεπιλεγμένος είναι ο φθηνότερος.</p>
    ${data.sections.map((s) => {
      const offers = Object.entries(s.totals).sort((a, b) => a[1] - b[1]);
      return `<label>${esc(s.code)} ${esc(s.title)}
        <select name="s-${s.id}">${offers.map(([bid, t]) => `<option value="${bid}" ${Number(bid) === s.best_bid_id ? "selected" : ""}>${esc(byId[bid].company.name)} · ${fmt.money(t)}</option>`).join("")}
          <option value="">Να μην ανατεθεί τώρα</option></select></label>`;
    }).join("")}
    <p class="total-line">Σύνολο: <b id="sum" class="mono"></b></p>
    <div class="row end"><button type="button" class="btn ghost" value="cancel">Άκυρο</button><button class="btn primary">Ανάθεση</button></div>
  </form>`;
  document.body.append(dlg);
  dlg.showModal();
  const f = dlg.querySelector("#f");
  const sum = () => {
    let t = 0;
    for (const s of data.sections) { const v = f[`s-${s.id}`].value; if (v) t += Number(s.totals[v]); }
    dlg.querySelector("#sum").textContent = fmt.money(t);
  };
  f.addEventListener("change", sum); sum();
  const close = () => { dlg.close(); dlg.remove(); };
  dlg.querySelector("[value=cancel]").onclick = close;
  dlg.addEventListener("cancel", () => dlg.remove());
  f.onsubmit = (e) => {
    e.preventDefault();
    const groups = {};
    for (const s of data.sections) { const v = f[`s-${s.id}`].value; if (v) (groups[v] ||= []).push(s.id); }
    const allocations = Object.entries(groups).map(([bid, sections]) => ({ bid_id: Number(bid), sections }));
    if (!allocations.length) { toast("Επιλέξτε τουλάχιστον μία ενότητα.", "error"); return; }
    busy(f.querySelector("button.primary"), async () => {
      await api(`jobs/${job.id}/award`, { method: "POST", body: { allocations } });
      toast("Η ανάθεση ολοκληρώθηκε.", "ok"); close(); reload();
    });
  };
}

function bafoDialog(job, bidders) {
  const dlg = document.createElement("dialog");
  dlg.className = "modal wide";
  const in3 = new Date(Date.now() + 3 * 864e5);
  in3.setHours(12, 0, 0, 0);
  dlg.innerHTML = `<form class="stack" id="f">
    <h3>Βελτιωμένη τελική προσφορά (BAFO)</h3>
    <p class="muted small">Οι επιλεγμένοι υπεργολάβοι μπορούν να αναθεωρήσουν τις τιμές τους μέχρι την προθεσμία. Οι νέες τιμές ανοίγουν όλες μαζί στη λήξη· βλέπετε και την αρχική τιμή για σύγκριση.</p>
    <div class="stack tight">${bidders.map((b, i) => `<label class="check"><input type="checkbox" name="b" value="${b.bid_id}" ${i < 3 ? "checked" : ""}>
      #${b.rank} ${esc(b.company.name)} · ${fmt.money(b.total)}${b.partial ? " (μερική)" : ""}</label>`).join("")}</div>
    <label>Προθεσμία<input type="datetime-local" name="deadline" required value="${toLocalInput(in3.toISOString())}"></label>
    <label>Μήνυμα <small>(προαιρετικό)</small><textarea name="message" rows="2" placeholder="π.χ. Παρακαλούμε την τελική σας τιμή και τον χρόνο εκτέλεσης."></textarea></label>
    <div class="row end"><button type="button" class="btn ghost" value="cancel">Άκυρο</button><button class="btn primary">Αποστολή αιτήματος</button></div>
  </form>`;
  document.body.append(dlg);
  dlg.showModal();
  const close = () => { dlg.close(); dlg.remove(); };
  dlg.querySelector("[value=cancel]").onclick = close;
  dlg.addEventListener("cancel", () => dlg.remove());
  const f = dlg.querySelector("#f");
  f.onsubmit = (e) => {
    e.preventDefault();
    const ids = [...f.querySelectorAll("input[name=b]:checked")].map((i) => Number(i.value));
    if (!ids.length) { toast("Επιλέξτε τουλάχιστον έναν υπεργολάβο.", "error"); return; }
    busy(f.querySelector("button.primary"), async () => {
      await api(`jobs/${job.id}/bafo`, { method: "POST", body: { bid_ids: ids, deadline: fromLocalInput(f.deadline.value), message: f.message.value } });
      toast("Στάλθηκε το αίτημα βελτιωμένης προσφοράς.", "ok"); close(); reload();
    });
  };
}
