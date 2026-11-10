import io
import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APITestCase

from accounts.models import Company, User
from tenders.models import Job

TMP_MEDIA = tempfile.mkdtemp()


def make_user(email, role, license="C"):
    u = User.objects.create_user(email=email, password="secret-pass-1", role=role)
    Company.objects.create(user=u, name=email.split("@")[0], vat_number="123456789",
                           region="attiki", license_category=license)
    return u


def boq_xlsx():
    wb = Workbook()
    ws = wb.active
    ws.append(["ΠΡΟΜΕΤΡΗΣΗ ΗΛΕΚΤΡΟΛΟΓΙΚΩΝ"])
    ws.append([])
    ws.append(["Α/Α", "Περιγραφή", "Μονάδα", "Ποσότητα", "Τιμή μονάδας"])
    ws.append(["1", "ΙΣΧΥΡΑ ΡΕΥΜΑΤΑ", None, None])
    ws.append(["1.1", "Καλώδιο NYM 3x1,5", "m", 1200])
    ws.append(["1.2", "Πρίζα σούκο", "τεμ", "85"])
    ws.append(["1.3", "Πίνακας διανομής", "τεμ", "2,5"])
    ws.append([None, "ΣΥΝΟΛΟ", None, None])
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile("boq.xlsx", buf.getvalue())


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class TenderFlowTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.gc = make_user("gc@test.gr", User.Role.CONTRACTOR)
        self.sub1 = make_user("sub1@test.gr", User.Role.SUBCONTRACTOR, "C")
        self.sub2 = make_user("sub2@test.gr", User.Role.SUBCONTRACTOR, "D")
        self.sub_low = make_user("sub3@test.gr", User.Role.SUBCONTRACTOR, "A")

    def as_(self, user):
        self.client.force_authenticate(user)

    def create_published_job(self, required_license="B"):
        self.as_(self.gc)
        r = self.client.post("/api/jobs", {
            "title": "Ηλεκτρολογικά κτιρίου γραφείων", "region": "attiki",
            "category": "commercial", "required_license": required_license, "trades": ["power", "low_voltage"],
            "bid_deadline": (timezone.now() + timedelta(days=7)).isoformat(),
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        job_id = r.data["id"]
        r = self.client.post(f"/api/jobs/{job_id}/boq/import", {"file": boq_xlsx()}, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        r = self.client.post(f"/api/jobs/{job_id}/publish")
        self.assertEqual(r.status_code, 200, r.data)
        return job_id

    def items(self, job_id):
        return [i for i in self.client.get(f"/api/jobs/{job_id}/boq").data if not i["is_section"]]

    def bid(self, user, job_id, prices):
        self.as_(user)
        items = self.items(job_id)
        lines = [{"item": it["id"], "unit_price": p} for it, p in zip(items, prices)]
        r = self.client.put(f"/api/jobs/{job_id}/my-bid", {"lines": lines, "duration_days": 30}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        return self.client.post(f"/api/jobs/{job_id}/my-bid/submit")

    def test_boq_import_detects_header_sections_and_greek_numbers(self):
        job_id = self.create_published_job()
        boq = self.client.get(f"/api/jobs/{job_id}/boq").data
        self.assertEqual(len(boq), 4)  # ενότητα + 3 γραμμές, χωρίς το «ΣΥΝΟΛΟ»
        self.assertTrue(boq[0]["is_section"])
        self.assertEqual(boq[3]["quantity"], 2.5)
        self.assertEqual(boq[1]["unit"], "m")

    def test_full_flow_sealed_until_deadline_then_compare_and_award(self):
        job_id = self.create_published_job()
        self.assertEqual(self.bid(self.sub1, job_id, ["1.20", "8.00", "450"]).status_code, 200)
        self.assertEqual(self.bid(self.sub2, job_id, ["1.00", "9.50", "500"]).status_code, 200)

        # Ο εργολάβος δεν βλέπει τιμές πριν τη λήξη
        self.as_(self.gc)
        r = self.client.get(f"/api/jobs/{job_id}/comparison")
        self.assertTrue(r.data["sealed"])
        self.assertEqual(r.data["submitted_count"], 2)
        self.assertNotIn("bidders", r.data)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}/comparison/export").status_code, 403)
        self.assertEqual(self.client.post(f"/api/jobs/{job_id}/award", {"bid_id": 1}).status_code, 400)

        # Λήξη και σύγκριση
        self.client.post(f"/api/jobs/{job_id}/close_bidding")
        r = self.client.get(f"/api/jobs/{job_id}/comparison")
        self.assertFalse(r.data["sealed"])
        totals = {b["company"]["name"]: b["total"] for b in r.data["bidders"]}
        self.assertEqual(totals["sub1"], 1200 * 1.2 + 85 * 8 + 2.5 * 450)  # 3245
        self.assertEqual(totals["sub2"], 1200 * 1.0 + 85 * 9.5 + 2.5 * 500)  # 3257.5
        self.assertEqual(r.data["bidders"][0]["company"]["name"], "sub1")
        export = self.client.get(f"/api/jobs/{job_id}/comparison/export")
        self.assertEqual(export.status_code, 200)

        # Δεν δέχεται νέες προσφορές
        self.as_(self.sub1)
        self.assertEqual(self.client.post(f"/api/jobs/{job_id}/my-bid/submit").status_code, 400)

        # Ανάθεση
        self.as_(self.gc)
        winner = r.data["bidders"][0]["bid_id"]
        r = self.client.post(f"/api/jobs/{job_id}/award", {"bid_id": winner}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "awarded")
        self.as_(self.sub1)
        mine = self.client.get("/api/my-bids").data
        self.assertTrue(mine[0]["won"])
        self.as_(self.sub2)
        self.assertFalse(self.client.get("/api/my-bids").data[0]["won"])

    def test_any_subcontractor_can_bid_license_not_checked(self):
        job_id = self.create_published_job(required_license="D")
        self.assertEqual(self.bid(self.sub_low, job_id, ["1", "1", "1"]).status_code, 200)

    def test_permissions(self):
        job_id = self.create_published_job()
        # Υπεργολάβος δεν δημιουργεί εργασίες
        self.as_(self.sub1)
        r = self.client.post("/api/jobs", {"title": "x", "region": "attiki"}, format="json")
        self.assertEqual(r.status_code, 403)
        # Ούτε βλέπει τη σύγκριση
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}/comparison").status_code, 403)
        # Άλλος εργολάβος δεν βλέπει πρόχειρο
        self.as_(self.gc)
        draft = self.client.post("/api/jobs", {"title": "Πρόχειρο", "region": "attiki"}, format="json").data
        other = make_user("gc2@test.gr", User.Role.CONTRACTOR)
        self.as_(other)
        self.assertEqual(self.client.get(f"/api/jobs/{draft['id']}").status_code, 404)
        # Μετά τη δημοσίευση η προμέτρηση κλειδώνει
        self.as_(self.gc)
        r = self.client.put(f"/api/jobs/{job_id}/boq", [{"description": "x", "quantity": 1}], format="json")
        self.assertEqual(r.status_code, 400)

    def test_addendum_marks_earlier_bids_outdated(self):
        job_id = self.create_published_job()
        self.bid(self.sub1, job_id, ["1", "1", "1"])
        self.as_(self.gc)
        f = SimpleUploadedFile("kat-isogeiou-rev1.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.client.post(f"/api/jobs/{job_id}/documents", {"files": [f], "kind": "drawing"}, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data[0]["is_addendum"])
        self.as_(self.sub1)
        self.assertTrue(self.client.get(f"/api/jobs/{job_id}/my-bid").data["outdated"])
        # Λήψη εγγράφου από υπεργολάβο
        dl = self.client.get(f"/api/documents/{r.data[0]['id']}/download")
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(b"".join(dl.streaming_content), b"%PDF-1.4 test")

    def test_questions_are_anonymous_and_public_once_answered(self):
        job_id = self.create_published_job()
        self.as_(self.sub1)
        q = self.client.post(f"/api/jobs/{job_id}/questions", {"text": "Τα φωτιστικά περιλαμβάνονται;"}).data
        self.as_(self.sub2)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}/questions").data, [])
        self.as_(self.gc)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}/questions").data[0]["asked_by"], "sub1")
        self.client.post(f"/api/jobs/{job_id}/questions/{q['id']}/answer", {"answer": "Όχι, μόνο η εγκατάσταση."})
        self.as_(self.sub2)
        data = self.client.get(f"/api/jobs/{job_id}/questions").data
        self.assertEqual(len(data), 1)
        self.assertIsNone(data[0]["asked_by"])

    def test_marketplace_lists_only_open_jobs(self):
        job_id = self.create_published_job()
        self.client.post("/api/jobs", {"title": "Πρόχειρο", "region": "attiki"}, format="json")
        self.as_(self.sub1)
        ids = [j["id"] for j in self.client.get("/api/jobs").data]
        self.assertEqual(ids, [job_id])
        self.assertEqual(self.client.get("/api/jobs?region=kriti").data, [])

    def test_trades_required_to_publish_and_filterable(self):
        self.as_(self.gc)
        r = self.client.post("/api/jobs", {"title": "Γυψοσανίδες", "region": "attiki", "trades": ["drywall"],
                                           "bid_deadline": (timezone.now() + timedelta(days=3)).isoformat()}, format="json")
        drywall = r.data["id"]
        self.client.put(f"/api/jobs/{drywall}/boq", [{"description": "Χώρισμα", "unit": "m²", "quantity": 100}], format="json")
        self.assertEqual(self.client.post(f"/api/jobs/{drywall}/publish").status_code, 200)
        no_trade = self.client.post("/api/jobs", {"title": "Χωρίς ειδικότητα", "region": "attiki",
                                                  "bid_deadline": (timezone.now() + timedelta(days=3)).isoformat()}, format="json").data["id"]
        self.client.put(f"/api/jobs/{no_trade}/boq", [{"description": "x", "quantity": 1}], format="json")
        r = self.client.post(f"/api/jobs/{no_trade}/publish")
        self.assertEqual(r.status_code, 400)
        self.assertIn("ειδικότητα", str(r.data))
        bad = self.client.post("/api/jobs", {"title": "x", "region": "attiki", "trades": ["juggling"]}, format="json")
        self.assertEqual(bad.status_code, 400)

        electrical = self.create_published_job()
        self.as_(self.sub1)
        ids = lambda q: [j["id"] for j in self.client.get("/api/jobs", q).data]
        self.assertEqual(ids({"trade": "drywall"}), [drywall])
        self.assertEqual(set(ids({})), {drywall, electrical})
        self.sub1.company.specialties = ["power"]
        self.sub1.company.save()
        self.assertEqual(ids({"mine": "1"}), [electrical])
        Job.objects.filter(id=drywall).update(trades=[])  # χωρίς ειδικότητα: φαίνεται σε όλους
        self.assertEqual(set(ids({"mine": "1"})), {electrical, drywall})

    def test_marketplace_search_ignores_case_and_accents(self):
        job_id = self.create_published_job()
        self.as_(self.sub1)
        self.assertEqual([j["id"] for j in self.client.get("/api/jobs", {"q": "ΗΛΕΚΤΡΟΛΟΓΙΚΑ κτιριου"}).data], [job_id])
        self.assertEqual(self.client.get("/api/jobs", {"q": "ξενοδοχείο"}).data, [])


class AuthTests(APITestCase):
    def test_register_and_login(self):
        r = self.client.post("/api/auth/register", {
            "email": "New@Test.gr", "password": "kalos-kodikos-1", "first_name": "Νίκος",
            "last_name": "Π.", "role": "subcontractor", "accept_terms": True,
            "company": {"name": "Ηλεκτρική ΑΕ", "vat_number": "099999999", "region": "kriti",
                        "license_category": "C", "specialties": ["power", "pv"]},
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        r = self.client.post("/api/auth/login", {"email": "new@test.gr", "password": "kalos-kodikos-1"})
        self.assertEqual(r.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {r.data['token']}")
        self.assertEqual(self.client.get("/api/me").data["company"]["name"], "Ηλεκτρική ΑΕ")

    def test_bad_vat_rejected(self):
        r = self.client.post("/api/auth/register", {
            "email": "x@test.gr", "password": "kalos-kodikos-1", "first_name": "a", "last_name": "b",
            "role": "contractor", "company": {"name": "X", "vat_number": "12", "region": "attiki"},
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("company", r.data)

