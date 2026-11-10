"""
Εισαγωγή προμέτρησης (BOQ) από Excel ή CSV.

Εντοπίζει αυτόματα τη γραμμή επικεφαλίδων ψάχνοντας λέξεις όπως
«Α/Α», «Περιγραφή», «Μονάδα», «Ποσότητα» (ελληνικά ή αγγλικά).
Γραμμές με περιγραφή αλλά χωρίς ποσότητα γίνονται επικεφαλίδες ενοτήτων.
"""
import csv
import io
import unicodedata
from decimal import Decimal, InvalidOperation

HEADER_KEYWORDS = {
    "code": ["α/α", "αα", "κωδ", "αρθρο", "code", "item no", "no.", "a/a", "κωδικος"],
    "description": ["περιγραφ", "description", "ειδος", "εργασια"],
    "unit": ["μον", "μ.μ", "unit", "uom"],
    "quantity": ["ποσοτ", "ποσ.", "qty", "quantity", "τεμ/ποσ"],
}
SKIP_PREFIXES = ("συνολο", "γενικο συνολο", "total", "subtotal", "φπα", "vat")
MAX_HEADER_SCAN = 20
MAX_ROWS = 5000


class BOQImportError(ValueError):
    pass


def _norm(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def parse_decimal(value):
    """Δέχεται 1234.5, '1.234,50', '1,5', '12 τεμ' κ.λπ. Επιστρέφει Decimal ή None."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    text = str(value).strip().replace(" ", "").replace(" ", "")
    text = "".join(ch for ch in text if ch.isdigit() or ch in ",.-")
    if not text or not any(ch.isdigit() for ch in text):
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _read_rows(uploaded_file):
    name = (uploaded_file.name or "").lower()
    data = uploaded_file.read()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:  # αρχείο κατεστραμμένο ή μη έγκυρο
            raise BOQImportError("Δεν ήταν δυνατό να διαβαστεί το αρχείο Excel.") from exc
        ws = wb.worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    if name.endswith(".csv"):
        for encoding in ("utf-8-sig", "cp1253", "latin-1"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
        return [row for row in csv.reader(io.StringIO(text), dialect)]
    raise BOQImportError("Υποστηρίζονται αρχεία .xlsx και .csv (τα .xls αποθηκεύστε ως .xlsx).")


def _find_header(rows):
    for idx, row in enumerate(rows[:MAX_HEADER_SCAN]):
        mapping = {}
        for col, cell in enumerate(row):
            cell_n = _norm(cell)
            if not cell_n:
                continue
            for field, keywords in HEADER_KEYWORDS.items():
                if field in mapping:
                    continue
                if any(cell_n.startswith(k) or k in cell_n for k in keywords):
                    # «Τιμή μονάδας» δεν είναι στήλη μονάδας μέτρησης
                    if field == "unit" and ("τιμ" in cell_n or "price" in cell_n):
                        continue
                    mapping[field] = col
                    break
        if "description" in mapping and "quantity" in mapping:
            return idx, mapping
    raise BOQImportError(
        "Δεν βρέθηκαν επικεφαλίδες. Το αρχείο χρειάζεται τουλάχιστον στήλες "
        "«Περιγραφή» και «Ποσότητα» (προαιρετικά «Α/Α» και «Μονάδα»)."
    )


def parse_boq(uploaded_file):
    """Επιστρέφει λίστα dict: code, description, unit, quantity (Decimal ή None)."""
    rows = _read_rows(uploaded_file)
    header_idx, cols = _find_header(rows)

    def cell(row, field):
        col = cols.get(field)
        if col is None or col >= len(row):
            return None
        return row[col]

    items = []
    for row in rows[header_idx + 1:]:
        if len(items) >= MAX_ROWS:
            raise BOQImportError(f"Η προμέτρηση ξεπερνά τις {MAX_ROWS} γραμμές.")
        description = cell(row, "description")
        description = str(description).strip() if description is not None else ""
        if not description:
            continue
        if _norm(description).startswith(SKIP_PREFIXES):
            continue
        code = cell(row, "code")
        code = "" if code is None else str(code).strip()
        if code.endswith(".0") and code[:-2].isdigit():
            code = code[:-2]
        quantity = parse_decimal(cell(row, "quantity"))
        unit = cell(row, "unit")
        unit = str(unit).strip() if unit is not None and quantity is not None else ""
        items.append({
            "code": code[:50],
            "description": description,
            "unit": unit[:20],
            "quantity": quantity,
        })

    if not any(i["quantity"] is not None for i in items):
        raise BOQImportError("Δεν βρέθηκε καμία γραμμή με ποσότητα.")
    return items
