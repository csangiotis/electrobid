// Βοηθητικά για εμφάνιση και μορφοποίηση.
export const state = { me: null, choices: null };

export function esc(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

const money = new Intl.NumberFormat("el-GR", { style: "currency", currency: "EUR" });
const num = new Intl.NumberFormat("el-GR", { maximumFractionDigits: 3 });
const dt = new Intl.DateTimeFormat("el-GR", { dateStyle: "medium", timeStyle: "short" });
const d = new Intl.DateTimeFormat("el-GR", { dateStyle: "medium" });

export const fmt = {
  money: (v) => (v === null || v === undefined || v === "" ? "—" : money.format(Number(v))),
  num: (v) => (v === null || v === undefined || v === "" ? "—" : num.format(Number(v))),
  datetime: (v) => (v ? dt.format(new Date(v)) : "—"),
  date: (v) => (v ? d.format(new Date(v)) : "—"),
  size: (b) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`),
};

// «σε 3 ημέρες», «σε 5 ώρες», «έληξε»
export function timeLeft(iso) {
  if (!iso) return "χωρίς προθεσμία";
  const ms = new Date(iso) - Date.now();
  if (ms <= 0) return "έληξε";
  const h = Math.floor(ms / 3.6e6);
  if (h < 1) return `σε ${Math.max(1, Math.round(ms / 6e4))} λεπτά`;
  if (h < 48) return `σε ${h} ${h === 1 ? "ώρα" : "ώρες"}`;
  return `σε ${Math.floor(h / 24)} ημέρες`;
}

// Είσοδος αριθμού: δέχεται «1.234,50» ή «1234.5»
export function parseNum(v) {
  if (v === null || v === undefined) return null;
  let t = String(v).trim().replace(/\s/g, "");
  if (!t) return null;
  if (t.includes(",") && t.includes(".")) {
    t = t.lastIndexOf(",") > t.lastIndexOf(".") ? t.replace(/\./g, "").replace(",", ".") : t.replace(/,/g, "");
  } else if (t.includes(",")) t = t.replace(",", ".");
  const n = Number(t);
  return Number.isFinite(n) ? n : NaN;
}

export function label(listName, value) {
  const item = state.choices?.[listName]?.find((c) => c.value === value);
  return item ? item.label : value || "";
}

export function options(listName, selected, { empty } = {}) {
  const sel = Array.isArray(selected) ? selected : [selected];
  const opt = (c) => `<option value="${esc(c.value)}" ${sel.includes(c.value) ? "selected" : ""}>${esc(c.label)}</option>`;
  const items = state.choices?.[listName] || [];
  let opts;
  if (items.some((c) => c.group)) {
    const groups = [...new Set(items.map((c) => c.group))];
    opts = groups.map((g) => `<optgroup label="${esc(g)}">${items.filter((c) => c.group === g).map(opt).join("")}</optgroup>`).join("");
  } else {
    opts = items.map(opt).join("");
  }
  return (empty !== undefined ? `<option value="">${esc(empty)}</option>` : "") + opts;
}

const PHASES = {
  draft: ["Πρόχειρο", "muted"],
  bidding: ["Δέχεται προσφορές", "live"],
  evaluation: ["Αξιολόγηση", "warn"],
  awarded: ["Ανατέθηκε", "ok"],
  cancelled: ["Ακυρώθηκε", "muted"],
};
export function phaseBadge(phase) {
  const [t, cls] = PHASES[phase] || [phase, "muted"];
  return `<span class="badge ${cls}">${esc(t)}</span>`;
}

const BID_STATUS = { draft: ["Πρόχειρη", "muted"], submitted: ["Υποβλήθηκε", "ok"], withdrawn: ["Αποσύρθηκε", "muted"] };
export function bidBadge(status) {
  if (!status) return "";
  const [t, cls] = BID_STATUS[status] || [status, "muted"];
  return `<span class="badge ${cls}">${esc(t)}</span>`;
}

export function companyLink(company) {
  if (!company?.id) return esc(company?.name || "");
  return `<a class="co-link" href="#/companies/${company.id}">${esc(company.name)}</a>`;
}

export function verifiedMark(company) {
  return company?.verified ? `<span class="verified" title="Επαληθευμένη εταιρεία">✓</span>` : "";
}

export function toast(msg, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  document.getElementById("toasts").append(el);
  setTimeout(() => el.classList.add("out"), 3800);
  setTimeout(() => el.remove(), 4300);
}

export function confirmDialog(message, { ok = "Επιβεβαίωση", danger = false } = {}) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "modal";
    dlg.innerHTML = `<p>${esc(message)}</p>
      <div class="row end"><button class="btn ghost" value="no">Άκυρο</button>
      <button class="btn ${danger ? "danger" : "primary"}" value="yes">${esc(ok)}</button></div>`;
    document.body.append(dlg);
    dlg.addEventListener("click", (e) => {
      const v = e.target.closest("button")?.value;
      if (v) { dlg.close(); dlg.remove(); resolve(v === "yes"); }
    });
    dlg.addEventListener("cancel", () => { dlg.remove(); resolve(false); });
    dlg.showModal();
  });
}

// Εκτελεί ενέργεια με κουμπί σε κατάσταση φόρτωσης και εμφανίζει τα σφάλματα.
export async function busy(btn, fn) {
  const prev = btn?.innerHTML;
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spin"></span>${prev}`; }
  try {
    return await fn();
  } catch (err) {
    toast(err.message || "Κάτι πήγε στραβά.", "error");
    return undefined;
  } finally {
    if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = prev; }
  }
}

export function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

// datetime-local ⇄ ISO
export function toLocalInput(iso) {
  if (!iso) return "";
  const dte = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${dte.getFullYear()}-${p(dte.getMonth() + 1)}-${p(dte.getDate())}T${p(dte.getHours())}:${p(dte.getMinutes())}`;
}
export function fromLocalInput(v) {
  return v ? new Date(v).toISOString() : null;
}

// Ειδικότητες ως επιλέξιμα chips, ομαδοποιημένα (Η/Μ, οικοδομικά κ.λπ.)
export function tradeChips(name, selected = []) {
  const items = state.choices?.specialties || [];
  const groups = [...new Set(items.map((c) => c.group))];
  return groups.map((g) => `
    <div class="chip-group"><span class="chip-group-title">${esc(g)}</span>
      <div class="chips">${items.filter((c) => c.group === g).map((c) =>
        `<label class="chip"><input type="checkbox" name="${name}" value="${esc(c.value)}" ${selected.includes(c.value) ? "checked" : ""}><span>${esc(c.label)}</span></label>`).join("")}</div>
    </div>`).join("");
}

export function tradeTags(keys = [], max = 99) {
  const shown = keys.slice(0, max).map((k) => `<span class="chip-s">${esc(label("specialties", k))}</span>`).join("");
  return shown + (keys.length > max ? `<span class="chip-s more">+${keys.length - max}</span>` : "");
}
