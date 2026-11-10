// Ανώνυμοι δείκτες τιμών αγοράς.
import { api } from "../api.js";
import { esc, fmt, label, options } from "../ui.js";

const UNIT_SHORT = { m2: "m²", m3: "m³", "κατ": "κατ." };
const UNIT_LABEL = { m: "m (τρέχον μέτρο)", m2: "m² (τετραγωνικό)", m3: "m³ (κυβικό)", "τεμ": "τεμάχιο", kg: "kg", "κατ": "κατ' αποκοπή", kwp: "kWp" };

export async function pricesView(main) {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  main.innerHTML = `
  <div class="page-head"><div><h1>Δείκτες τιμών</h1>
    <p class="muted">Ανώνυμες τιμές μονάδας από υποβληθείσες προσφορές σε εργασίες της πλατφόρμας που έχουν κλείσει.
      Εμφανίζονται μόνο όταν βασίζονται σε τουλάχιστον τρεις διαφορετικές εταιρείες, και κάθε εταιρεία μετρά μία φορά.</p></div></div>
  <form class="filters prices" id="f">
    <input type="search" name="q" placeholder="π.χ. γυψοσανίδα πετροβάμβακα, καλώδιο NYM 3x1,5, πλακίδια δαπέδου" value="${esc(params.get("q") || "")}" autofocus>
    <select name="unit"><option value="">Μονάδα (αυτόματα)</option></select>
    <select name="region">${options("regions", params.get("region") || "", { empty: "Όλη η Ελλάδα" })}</select>
    <button class="btn primary">Αναζήτηση</button>
  </form>
  <div id="out"></div>`;
  const f = main.querySelector("#f");
  const out = main.querySelector("#out");
  const run = async () => {
    const q = f.q.value.trim();
    if (!q) { out.innerHTML = `<div class="empty"><p>Γράψτε ένα είδος εργασίας ή υλικού για να δείτε τις τιμές της αγοράς.</p></div>`; return; }
    out.innerHTML = `<div class="loading">Αναζήτηση…</div>`;
    const r = await api(`price-index?${new URLSearchParams({ q, unit: f.unit.value, region: f.region.value })}`);
    f.unit.innerHTML = `<option value="">Μονάδα (αυτόματα)</option>` + r.units.map((u) =>
      `<option value="${esc(u.unit)}" ${u.unit === r.unit ? "selected" : ""} ${u.available ? "" : "disabled"}>${esc(UNIT_LABEL[u.unit] || u.unit)}${u.available ? "" : " · λίγα δεδομένα"}</option>`).join("");
    if (!r.result) {
      out.innerHTML = `<div class="empty"><h2>Δεν υπάρχουν αρκετά δεδομένα</h2>
        <p>Για «${esc(q)}» δεν βρέθηκαν τιμές από τουλάχιστον ${r.min_companies ?? 3} εταιρείες${f.region.value ? " σε αυτή την περιοχή" : ""}. Δοκιμάστε πιο γενική περιγραφή${f.region.value ? " ή όλη την Ελλάδα" : ""}.</p></div>`;
      return;
    }
    const s = r.result;
    const pct = (v) => (s.max > s.min ? ((v - s.min) / (s.max - s.min)) * 100 : 50);
    out.innerHTML = `
      <div class="panel price-card">
        <div class="row wrap"><div class="grow"><span class="tag">${esc(UNIT_LABEL[r.unit] || r.unit)}</span>
          <h2>Διάμεσος: ${fmt.money(s.median)} / ${esc(UNIT_SHORT[r.unit] || r.unit)}</h2>
          <p class="muted">Από ${s.companies} εταιρείες. Οι μισές τιμές είναι μεταξύ ${fmt.money(s.p25)} και ${fmt.money(s.p75)}.</p></div></div>
        <div class="range-bar" aria-hidden="true">
          <span class="iqr" style="left:${pct(s.p25)}%;width:${pct(s.p75) - pct(s.p25)}%"></span>
          <span class="med" style="left:${pct(s.median)}%"></span></div>
        <div class="range-labels mono small"><span>${fmt.money(s.min)}</span><span>${fmt.money(s.max)}</span></div>
      </div>
      ${r.regions.length > 1 ? `<div class="panel"><h3>Ανά περιφέρεια</h3><div class="table-wrap"><table class="tbl">
        <thead><tr><th>Περιφέρεια</th><th class="num">Διάμεσος</th><th class="num">25%–75%</th><th class="num">Εταιρείες</th></tr></thead>
        <tbody>${r.regions.map((x) => `<tr><td>${esc(label("regions", x.region))}</td><td class="num mono">${fmt.money(x.stats.median)}</td>
          <td class="num mono">${fmt.money(x.stats.p25)} – ${fmt.money(x.stats.p75)}</td><td class="num">${x.stats.companies}</td></tr>`).join("")}</tbody></table></div></div>` : ""}
      ${r.examples.length ? `<div class="panel"><h3>Περιγραφές που περιλαμβάνονται</h3><ul class="examples">${r.examples.map((e) => `<li>${esc(e)}</li>`).join("")}</ul></div>` : ""}`;
  };
  f.onsubmit = (e) => { e.preventDefault(); history.replaceState(null, "", `#/prices?${new URLSearchParams({ q: f.q.value, region: f.region.value })}`); run(); };
  f.unit.onchange = run;
  f.region.onchange = run;
  run();
}
