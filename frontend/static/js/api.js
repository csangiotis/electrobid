// Επικοινωνία με το Django REST API.
const TOKEN_KEY = "electrobid.token";

export const auth = {
  get token() { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set token(v) {
    try { v ? localStorage.setItem(TOKEN_KEY, v) : localStorage.removeItem(TOKEN_KEY); } catch { /* */ }
  },
};

export class ApiError extends Error {
  constructor(status, data) {
    super(flattenErrors(data) || `Σφάλμα ${status}`);
    this.status = status;
    this.data = data;
  }
}

// Μετατρέπει τα σφάλματα του DRF ({field: ["..."]}) σε ένα κείμενο.
function flattenErrors(data, prefix = "") {
  if (!data) return "";
  if (typeof data === "string") return data;
  if (Array.isArray(data)) return data.map((d) => flattenErrors(d, prefix)).filter(Boolean).join(" ");
  if (data.detail) return flattenErrors(data.detail);
  return Object.entries(data)
    .map(([k, v]) => {
      const msg = flattenErrors(v);
      return k === "non_field_errors" || k === "detail" ? msg : `${FIELD_LABELS[k] || k}: ${msg}`;
    })
    .join(" · ");
}

const FIELD_LABELS = {
  email: "Email", password: "Κωδικός", vat_number: "ΑΦΜ", name: "Επωνυμία", region: "Περιφέρεια",
  title: "Τίτλος", bid_deadline: "Προθεσμία", company: "Εταιρεία", first_name: "Όνομα",
  last_name: "Επώνυμο", role: "Ρόλος", lines: "Γραμμές",
};

export async function api(path, { method = "GET", body, raw = false } = {}) {
  const headers = {};
  if (auth.token) headers.Authorization = `Token ${auth.token}`;
  let payload = body;
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api/${path}`, { method, headers, body: payload });
  if (res.status === 401) {
    auth.token = null;
    location.hash = "#/login";
    throw new ApiError(401, { detail: "Η σύνδεση έληξε. Συνδεθείτε ξανά." });
  }
  if (raw) {
    if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
    return res;
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

// Λήψη αρχείου μέσω fetch (χρειάζεται το token στο header).
export async function download(path, fallbackName) {
  const res = await api(path, { raw: true });
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const name = m ? decodeURIComponent(m[1]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
