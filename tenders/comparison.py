"""Σύγκριση προσφορών γραμμή-προς-γραμμή (bid leveling) και εξαγωγή σε Excel."""
import io
from decimal import Decimal
from statistics import median

from .models import Bid, boq_sections
from .serializers import company_brief

OUTLIER_THRESHOLD = Decimal("0.30")  # ±30% από τη διάμεσο


def build_comparison(job):
    """
    Πίνακας σύγκρισης. Κατά τη διάρκεια BAFO οι αναθεωρημένες τιμές μένουν σφραγισμένες:
    για όσους έχουν προσκληθεί φαίνονται οι τιμές του αρχικού γύρου.
    """
    bids = list(
        job.bids.filter(status=Bid.Status.SUBMITTED)
        .select_related("subcontractor__company")
        .prefetch_related("lines")
    )
    items = list(job.boq_items.all())
    sections = boq_sections(items)
    section_of = {it.id: sid for sid, _, _, its in sections for it in its}
    sealed_bafo = job.bafo_active

    def price(bid, line):
        if line is None:
            return None
        if sealed_bafo and bid.bafo_invited and line.original_unit_price is not None:
            return line.original_unit_price
        return line.unit_price

    lines = {b.id: {ln.item_id: ln for ln in b.lines.all()} for b in bids}
    excluded = {b.id: set(b.excluded_sections or []) for b in bids}
    totals = {b.id: Decimal("0") for b in bids}
    original = {b.id: Decimal("0") for b in bids}
    has_original = {b.id: False for b in bids}
    missing = {b.id: 0 for b in bids}
    sec_totals = {sid: {b.id: Decimal("0") for b in bids} for sid, *_ in sections}
    sec_complete = {sid: {b.id: True for b in bids} for sid, *_ in sections}
    rows = []

    for item in items:
        row = {
            "item_id": item.id, "code": item.code, "description": item.description,
            "unit": item.unit, "quantity": item.quantity, "is_section": item.is_section,
            "section_id": item.id if item.is_section else section_of.get(item.id, 0),
            "cells": {}, "min": None, "median": None, "max": None,
        }
        if item.is_section:
            rows.append(row)
            continue
        sid = row["section_id"]
        valid = []
        for b in bids:
            line = lines[b.id].get(item.id)
            up = price(b, line)
            if sid in excluded[b.id]:
                sec_complete[sid][b.id] = False
                row["cells"][b.id] = {"unit_price": None, "line_total": None, "flag": "excluded", "note": ""}
                continue
            if up is None:
                missing[b.id] += 1
                sec_complete[sid][b.id] = False
                row["cells"][b.id] = {"unit_price": None, "line_total": None,
                                      "flag": "missing", "note": line.note if line else ""}
                continue
            lt = (up * item.quantity).quantize(Decimal("0.01"))
            totals[b.id] += lt
            sec_totals[sid][b.id] += lt
            orig = line.original_unit_price if line.original_unit_price is not None else up
            has_original[b.id] |= line.original_unit_price is not None and not sealed_bafo
            original[b.id] += (orig * item.quantity).quantize(Decimal("0.01"))
            valid.append(up)
            cell = {"unit_price": up, "line_total": lt, "flag": None, "note": line.note}
            if not sealed_bafo and line.original_unit_price is not None and line.original_unit_price != up:
                cell["original_unit_price"] = line.original_unit_price
            row["cells"][b.id] = cell
        if valid:
            lo, hi, med = min(valid), max(valid), Decimal(str(median(valid)))
            row.update({"min": lo, "max": hi, "median": med.quantize(Decimal("0.01"))})
            for cell in row["cells"].values():
                up = cell["unit_price"]
                if up is None:
                    continue
                if len(valid) > 1 and up == lo:
                    cell["flag"] = "lowest"
                if med > 0 and len(valid) >= 3 and abs(up - med) / med > OUTLIER_THRESHOLD:
                    cell["flag"] = "outlier_high" if up > med else "outlier_low"
        rows.append(row)

    def complete(b):
        return missing[b.id] == 0 and not excluded[b.id]

    ranked = sorted(bids, key=lambda b: (not complete(b), totals[b.id]))
    bidders = []
    for rank, b in enumerate(ranked, start=1):
        covered = [sid for sid, *_ in sections if sec_complete[sid][b.id]]
        bidders.append({
            "bid_id": b.id,
            "company": company_brief(b.subcontractor),
            "total": totals[b.id].quantize(Decimal("0.01")),
            "original_total": original[b.id] if has_original[b.id] else None,
            "rank": rank,
            "missing_count": missing[b.id],
            "partial": bool(excluded[b.id]),
            "sections_covered": covered,
            "duration_days": b.duration_days,
            "validity_days": b.validity_days,
            "payment_terms": b.payment_terms,
            "notes": b.notes,
            "exclusions": b.exclusions,
            "outdated": b.job_revision < job.revision,
            "submitted_at": b.submitted_at,
            "bafo_invited": b.bafo_invited,
            "bafo_submitted_at": b.bafo_submitted_at,
        })

    section_summary, combo_total, combo_ok = [], Decimal("0"), bool(sections)
    for sid, code, title, its in sections:
        offers = {b.id: sec_totals[sid][b.id] for b in bids if sec_complete[sid][b.id]}
        best = min(offers, key=offers.get) if offers else None
        if best is None:
            combo_ok = False
        else:
            combo_total += offers[best]
        section_summary.append({
            "id": sid, "code": code, "title": title, "lines": len(its),
            "totals": {bid_id: total for bid_id, total in offers.items()},
            "best_bid_id": best, "best_total": offers.get(best),
        })

    complete_totals = [x["total"] for x in bidders if x["missing_count"] == 0 and not x["partial"]]
    return {
        "sealed": False,
        "bafo_active": sealed_bafo,
        "bafo_deadline": job.bafo_deadline,
        "bidders": bidders,
        "rows": rows,
        "sections": section_summary,
        "best_combination": {"total": combo_total if combo_ok else None,
                             "picks": {s["id"]: s["best_bid_id"] for s in section_summary}},
        "awards": [{"bid_id": a.bid_id, "sections": a.sections, "amount": a.amount} for a in job.awards.all()],
        "stats": {
            "count": len(bidders),
            "lowest_total": min(complete_totals) if complete_totals else None,
            "median_total": Decimal(str(median(complete_totals))).quantize(Decimal("0.01"))
            if complete_totals else None,
        },
    }


def comparison_xlsx(job):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    data = build_comparison(job)
    bidders = data["bidders"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Σύγκριση"
    bold = Font(bold=True)
    green = PatternFill("solid", fgColor="D9F2E3")
    amber = PatternFill("solid", fgColor="FCE8C3")
    red = PatternFill("solid", fgColor="F8D7D7")
    head = PatternFill("solid", fgColor="1F2A44")
    grey = PatternFill("solid", fgColor="E7E9EF")

    ws["A1"] = f"Σύγκριση προσφορών: {job.title}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"{job.location or job.get_region_display()} · {len(bidders)} προσφορές"

    header = ["Α/Α", "Περιγραφή", "Μον.", "Ποσότητα"]
    for b in bidders:
        header += [f"{b['company']['name']}\nΤιμή μον.", "Σύνολο"]
    ws.append([])
    ws.append(header)
    hr = ws.max_row
    for c in ws[hr]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head
        c.alignment = Alignment(wrap_text=True, vertical="center")

    for row in data["rows"]:
        if row["is_section"]:
            ws.append([row["code"], row["description"]])
            for c in ws[ws.max_row]:
                c.font = bold
            continue
        values = [row["code"], row["description"], row["unit"], float(row["quantity"])]
        for b in bidders:
            cell = row["cells"].get(b["bid_id"], {})
            up, lt = cell.get("unit_price"), cell.get("line_total")
            values += [float(up) if up is not None else None, float(lt) if lt is not None else None]
        ws.append(values)
        r = ws.max_row
        for i, b in enumerate(bidders):
            flag = row["cells"].get(b["bid_id"], {}).get("flag")
            fill = {"lowest": green, "missing": red, "outlier_high": amber,
                    "outlier_low": amber, "excluded": grey}.get(flag)
            if fill:
                ws.cell(row=r, column=5 + i * 2).fill = fill

    total_row = ["", "ΣΥΝΟΛΟ", "", ""]
    for b in bidders:
        total_row += ["", float(b["total"])]
    ws.append(total_row)
    for c in ws[ws.max_row]:
        c.font = bold
    for label, key in [("Χρόνος εκτέλεσης (ημ.)", "duration_days"),
                       ("Όροι πληρωμής", "payment_terms"),
                       ("Χωρίς τιμή (γραμμές)", "missing_count")]:
        r = ["", label, "", ""]
        for b in bidders:
            r += ["", b[key]]
        ws.append(r)

    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 8
    ws.column_dimensions["D"].width = 11
    for i in range(len(bidders) * 2):
        ws.column_dimensions[get_column_letter(5 + i)].width = 15
    for row in ws.iter_rows(min_row=hr + 1, min_col=4):
        for c in row:
            if isinstance(c.value, float):
                c.number_format = "#,##0.00"
    ws.row_dimensions[hr].height = 32
    ws.freeze_panes = ws.cell(row=hr + 1, column=5)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
