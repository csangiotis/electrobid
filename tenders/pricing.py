"""
Τιμές από το ιστορικό της πλατφόρμας.

- Τιμοκατάλογος υπεργολάβου: για κάθε γραμμή μιας νέας προμέτρησης προτείνεται η τιμή που
  έδωσε ο ίδιος σε παρόμοια γραμμή παλαιότερα.
- Δείκτες αγοράς: ανώνυμα στατιστικά (διάμεσος, εύρος) από υποβληθείσες προσφορές σε δημόσιες
  εργασίες που έχουν λήξει. Εμφανίζονται μόνο αν βασίζονται σε τουλάχιστον MIN_COMPANIES
  διαφορετικές εταιρείες, ώστε να μη φαίνεται ποιος έδωσε ποια τιμή.

Η ομοιότητα υπολογίζεται με λέξεις (χωρίς τόνους/κεφαλαία) και απαιτεί ίδια μονάδα μέτρησης.
"""
import re
from decimal import Decimal
from statistics import median

from django.utils import timezone

from accounts.textsearch import fold

from .models import Bid, BidLine, Job

MIN_COMPANIES = 3
MIN_SCORE = 0.5
HISTORY_LIMIT = 5000
STOPWORDS = {"και", "με", "για", "του", "της", "των", "τον", "την", "το", "τα", "σε", "απο", "στο", "στη", "στην",
             "ή", "η", "ο", "οι", "ενα", "μια", "εως", "ανα", "πλήρης", "πληρης", "πληρως", "τυπου", "ειδους"}
UNIT_ALIASES = {
    "m": {"m", "μ", "μμ", "μ.μ", "μ.μ.", "τρμ", "τ.μ.μ", "lm", "μετρα", "m1"},
    "m2": {"m2", "m²", "μ2", "μ²", "τμ", "τ.μ", "τ.μ.", "sqm"},
    "m3": {"m3", "m³", "μ3", "μ³", "κμ", "κ.μ", "κ.μ."},
    "τεμ": {"τεμ", "τεμ.", "τμχ", "τεμαχιο", "τεμάχιο", "pcs", "τεμ/κα", "τεμαχια"},
    "kg": {"kg", "κιλα", "χλγ", "χγρ"},
    "κατ": {"κατ", "κατ.", "κομπλε", "αποκοπη", "κατ/ση", "σετ", "ls"},
    "kwp": {"kwp"},
}
_UNIT_LOOKUP = {fold(alias).replace(" ", ""): key for key, aliases in UNIT_ALIASES.items() for alias in aliases}


def norm_unit(unit):
    u = fold(unit).replace(" ", "")
    return _UNIT_LOOKUP.get(u, u)


# Απλή αφαίρεση ελληνικών καταλήξεων, ώστε «γυψοσανίδα», «γυψοσανίδας», «γυψοσανίδες» να ταιριάζουν
GREEK_ENDINGS = sorted(["ιων", "εων", "ους", "ων", "ου", "ης", "ας", "ες", "ος", "οι", "εσ", "ασ", "οσ", "ησ",
                        "α", "η", "ο", "ε", "ι", "υ", "σ"], key=len, reverse=True)


def stem(word):
    if len(word) <= 4 or not re.search("[α-ω]", word):
        return word
    for end in GREEK_ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 3:
            return word[: -len(end)]
    return word


# Σύντομοι κωδικοί γραμμένοι με ελληνικά γράμματα που μοιάζουν με λατινικά (ΝΥΜ → nym, ΡVC → pvc)
LOOKALIKE = str.maketrans("αβεηικμνορτυχζ", "abehikmnoptyxz")


def latinize(word):
    if len(word) <= 4 and all(ch in "αβεηικμνορτυχζ" or ch.isascii() for ch in word):
        return word.translate(LOOKALIKE)
    return word


def tokens(text):
    t = fold(text)
    t = re.sub(r"(\d)([a-wyzα-ω])", r"\1 \2", t)  # «10cm» → «10 cm» (όχι το «3x1,5»)
    words = re.findall(r"[0-9a-zα-ω]+(?:[.,x×/][0-9a-zα-ω]+)*", t)
    return frozenset(stem(latinize(w)) for w in words if len(w) > 1 and w not in STOPWORDS)


def similarity(a, b):
    """Jaccard λέξεων. Αν και οι δύο περιγραφές έχουν αριθμούς/διαστάσεις (π.χ. 3x1,5, Φ20, 10 cm),
    πρέπει να ταυτίζονται: διαφορετική διατομή ή διάσταση σημαίνει διαφορετικό είδος και τιμή."""
    if not a or not b:
        return 0.0
    na = {w for w in a if any(ch.isdigit() for ch in w)}
    nb = {w for w in b if any(ch.isdigit() for ch in w)}
    if na and nb and na != nb:
        return 0.0
    return len(a & b) / len(a | b)


def _stats(values):
    vals = sorted(values)
    n = len(vals)

    def q(p):
        k = (n - 1) * p
        lo, hi = int(k), min(int(k) + 1, n - 1)
        return vals[lo] + (vals[hi] - vals[lo]) * Decimal(str(k - lo))

    return {"median": Decimal(str(median(vals))).quantize(Decimal("0.01")),
            "p25": q(0.25).quantize(Decimal("0.01")), "p75": q(0.75).quantize(Decimal("0.01")),
            "min": vals[0], "max": vals[-1], "n": n}


# ---- Τιμοκατάλογος υπεργολάβου --------------------------------------------------------------
def own_history(user, exclude_job=None):
    qs = (BidLine.objects.filter(bid__subcontractor=user, unit_price__isnull=False)
          .exclude(bid__status=Bid.Status.WITHDRAWN)
          .select_related("item", "bid__job").order_by("-bid__updated_at"))
    if exclude_job is not None:
        qs = qs.exclude(bid__job=exclude_job)
    return [(tokens(ln.item.description), norm_unit(ln.item.unit), ln) for ln in qs[:HISTORY_LIMIT]]


def suggestions_for(job, user):
    history = own_history(user, exclude_job=job)
    out = {}
    if not history:
        return out
    for item in job.boq_items.exclude(quantity=None):
        t, u = tokens(item.description), norm_unit(item.unit)
        best, best_score = None, 0.0
        for ht, hu, ln in history:
            if hu != u:
                continue
            sc = similarity(t, ht)
            if sc > best_score:  # το ιστορικό είναι ταξινομημένο από το νεότερο: σε ισοβαθμία κρατά το νεότερο
                best, best_score = ln, sc
        if best is not None and best_score >= MIN_SCORE:
            out[item.id] = {"unit_price": best.unit_price, "description": best.item.description,
                            "job": best.bid.job.title, "date": best.bid.updated_at, "score": round(best_score, 2)}
    return out


# ---- Δείκτες αγοράς -------------------------------------------------------------------------
def market_history(exclude_job=None):
    """Υποβληθείσες τιμές σε δημόσιες εργασίες με λήξη προθεσμίας στο παρελθόν."""
    qs = (BidLine.objects.filter(unit_price__isnull=False, bid__status=Bid.Status.SUBMITTED,
                                 bid__job__visibility=Job.Visibility.PUBLIC,
                                 bid__job__bid_deadline__lte=timezone.now())
          .exclude(bid__job__status=Job.Status.DRAFT)
          .select_related("item", "bid__job").order_by("-bid__job__bid_deadline"))
    if exclude_job is not None:
        qs = qs.exclude(bid__job=exclude_job)
    return [(tokens(ln.item.description), norm_unit(ln.item.unit), ln.unit_price, ln.bid.subcontractor_id,
             ln.bid.job.region, ln.item.description) for ln in qs[:HISTORY_LIMIT * 4]]


def _aggregate(matches):
    companies = {m[3] for m in matches}
    if len(companies) < MIN_COMPANIES:
        return None
    # Μία τιμή ανά εταιρεία (ο διάμεσος των τιμών της), για να μη βαραίνει όποιος δίνει πολλές προσφορές
    per_company = {}
    for m in matches:
        per_company.setdefault(m[3], []).append(m[2])
    values = [Decimal(str(median(v))) for v in per_company.values()]
    stats = _stats(values)
    stats["companies"] = len(companies)
    stats.pop("n")
    return stats


def market_for_job(job):
    """{item_id: stats} για τη στήλη «Αγορά» της σύγκρισης."""
    history = market_history(exclude_job=job)
    out = {}
    for item in job.boq_items.exclude(quantity=None):
        t, u = tokens(item.description), norm_unit(item.unit)
        matches = [h for h in history if h[1] == u and similarity(t, h[0]) >= MIN_SCORE]
        agg = _aggregate(matches)
        if agg:
            out[item.id] = agg
    return out


def price_index(query, unit="", region=""):
    t = tokens(query)
    if not t:
        return {"query": query, "result": None, "units": [], "regions": [], "examples": []}
    history = market_history()
    # Στην αναζήτηση η φράση είναι σύντομη: μετρά πόσες από τις λέξεις της περιέχει η περιγραφή
    need = 1.0 if len(t) <= 2 else 0.75
    matches = [h for h in history if len(t & h[0]) / len(t) >= need]
    units = {}
    for h in matches:
        units.setdefault(h[1], []).append(h)
    unit = norm_unit(unit) if unit else (max(units, key=lambda k: len(units[k])) if units else "")
    selected = units.get(unit, [])
    if region:
        selected = [h for h in selected if h[4] == region]
    by_region = {}
    for h in units.get(unit, []):
        by_region.setdefault(h[4], []).append(h)
    examples = list(dict.fromkeys(h[5] for h in selected))[:6] if _aggregate(selected) else []
    return {
        "query": query, "unit": unit,
        "result": _aggregate(selected),
        "units": [{"unit": k, "available": _aggregate(v) is not None} for k, v in sorted(units.items(), key=lambda x: -len(x[1]))],
        "regions": [{"region": r, "stats": _aggregate(v)} for r, v in by_region.items() if _aggregate(v)],
        "examples": examples,
        "min_companies": MIN_COMPANIES,
    }
