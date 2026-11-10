from decimal import Decimal
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
from tenders.models import Bid, Job

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



def sectioned_job(gc):
    job = Job.objects.create(contractor=gc, title="Η/Μ", region="attiki", trades=["plumbing", "power"],
                             status=Job.Status.OPEN, bid_deadline=timezone.now() + timedelta(days=2))
    rows = [("1", "ΗΛΕΚΤΡΟΛΟΓΙΚΑ", None), ("1.1", "Καλώδιο", 100), ("1.2", "Πρίζα", 10),
            ("2", "ΥΔΡΑΥΛΙΚΑ", None), ("2.1", "Σωλήνας", 50)]
    from tenders.models import BOQItem
    items = [BOQItem.objects.create(job=job, position=i, code=c, description=d, unit="τεμ", quantity=q)
             for i, (c, d, q) in enumerate(rows, 1)]
    return job, items


class SectionAwardBafoTests(APITestCase):
    def setUp(self):
        self.gc = make_user("gc@t.gr", User.Role.CONTRACTOR)
        self.el = make_user("el@t.gr", User.Role.SUBCONTRACTOR)
        self.pl = make_user("pl@t.gr", User.Role.SUBCONTRACTOR)
        self.full = make_user("full@t.gr", User.Role.SUBCONTRACTOR)
        self.job, items = sectioned_job(self.gc)
        self.sec_el, self.sec_pl = items[0].id, items[3].id
        self.cable, self.socket, self.pipe = items[1].id, items[2].id, items[4].id

    def put(self, user, prices, excluded=()):
        self.client.force_authenticate(user)
        lines = [{"item": i, "unit_price": p} for i, p in prices.items()]
        r = self.client.put(f"/api/jobs/{self.job.id}/my-bid",
                            {"lines": lines, "excluded_sections": list(excluded) + [999]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertNotIn(999, r.data["excluded_sections"])
        return self.client.post(f"/api/jobs/{self.job.id}/my-bid/submit")

    def close(self):
        Job.objects.filter(id=self.job.id).update(bid_deadline=timezone.now() - timedelta(minutes=1))

    def test_partial_bids_section_summary_and_split_award(self):
        self.put(self.el, {self.cable: 2, self.socket: 10}, excluded=[self.sec_pl])      # 300 ηλεκτρ.
        self.put(self.pl, {self.pipe: 5}, excluded=[self.sec_el])                         # 250 υδραυλ.
        self.put(self.full, {self.cable: 3, self.socket: 12, self.pipe: 6})              # 420 + 300 = 720
        self.close()
        self.client.force_authenticate(self.gc)
        data = self.client.get(f"/api/jobs/{self.job.id}/comparison").data
        by = {b["company"]["name"]: b for b in data["bidders"]}
        self.assertTrue(by["el"]["partial"])
        self.assertEqual(by["el"]["missing_count"], 0)  # η εξαιρεμένη ενότητα δεν μετρά ως «χωρίς τιμή»
        self.assertEqual(data["bidders"][0]["company"]["name"], "full")  # οι πλήρεις πρώτα
        self.assertEqual(data["best_combination"]["total"], 550)
        sec = {s["title"]: s for s in data["sections"]}
        self.assertEqual(sec["ΗΛΕΚΤΡΟΛΟΓΙΚΑ"]["best_bid_id"], by["el"]["bid_id"])

        # Δεν γίνεται να ανατεθεί ενότητα που δεν καλύπτεται, ούτε διπλή ενότητα
        bad = self.client.post(f"/api/jobs/{self.job.id}/award", {"allocations": [
            {"bid_id": by["el"]["bid_id"], "sections": [self.sec_pl]}]}, format="json")
        self.assertEqual(bad.status_code, 400)
        r = self.client.post(f"/api/jobs/{self.job.id}/award", {"allocations": [
            {"bid_id": by["el"]["bid_id"], "sections": [self.sec_el]},
            {"bid_id": by["pl"]["bid_id"], "sections": [self.sec_pl]}]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "awarded")
        self.assertEqual(sorted(a["amount"] for a in r.data["awarded"]["awards"]), [250, 300])
        self.client.force_authenticate(self.el)
        mine = self.client.get(f"/api/jobs/{self.job.id}").data["awarded"]
        self.assertEqual(len(mine["awards"]), 1)  # βλέπει μόνο τη δική του ανάθεση
        self.assertTrue(self.client.get("/api/my-bids").data[0]["won"])
        self.client.force_authenticate(self.full)
        self.assertFalse(self.client.get("/api/my-bids").data[0]["won"])

    def test_bafo_round(self):
        self.put(self.el, {self.cable: 2, self.socket: 10, self.pipe: 5})
        self.put(self.full, {self.cable: 3, self.socket: 12, self.pipe: 6})
        self.close()
        self.client.force_authenticate(self.gc)
        full_bid = Bid.objects.get(subcontractor=self.full).id
        r = self.client.post(f"/api/jobs/{self.job.id}/bafo", {
            "bid_ids": [full_bid], "message": "Τελική τιμή παρακαλώ",
            "deadline": (timezone.now() + timedelta(days=1)).isoformat()}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["phase"], "bafo")
        self.assertEqual(self.client.post(f"/api/jobs/{self.job.id}/award", {"bid_id": full_bid}, format="json").status_code, 400)

        # Ο μη προσκεκλημένος δεν αλλάζει τίποτα· ο προσκεκλημένος αναθεωρεί
        self.client.force_authenticate(self.el)
        self.assertEqual(self.client.put(f"/api/jobs/{self.job.id}/my-bid", {"notes": "x"}, format="json").status_code, 400)
        self.client.force_authenticate(self.full)
        mine = self.client.get(f"/api/jobs/{self.job.id}/my-bid").data
        self.assertTrue(mine["can_edit"])
        self.put(self.full, {self.cable: 1.5, self.socket: 10, self.pipe: 5})
        # Σφραγισμένο μέχρι τη λήξη του BAFO: ο εργολάβος βλέπει την αρχική τιμή
        self.client.force_authenticate(self.gc)
        data = self.client.get(f"/api/jobs/{self.job.id}/comparison").data
        self.assertEqual({b["company"]["name"]: b["total"] for b in data["bidders"]}["full"], 720)
        Job.objects.filter(id=self.job.id).update(bafo_deadline=timezone.now() - timedelta(minutes=1))
        data = self.client.get(f"/api/jobs/{self.job.id}/comparison").data
        full = next(b for b in data["bidders"] if b["company"]["name"] == "full")
        self.assertEqual((full["total"], full["original_total"]), (500, 720))
        self.assertEqual(data["bidders"][0]["company"]["name"], "full")
        self.assertEqual(self.client.post(f"/api/jobs/{self.job.id}/award", {"bid_id": full_bid}, format="json").status_code, 200)


class CollaborationTests(APITestCase):
    def setUp(self):
        from django.core import mail
        self.mail = mail
        self.gc = make_user("gc@t.gr", User.Role.CONTRACTOR)
        self.el = make_user("el@t.gr", User.Role.SUBCONTRACTOR)
        self.pl = make_user("pl@t.gr", User.Role.SUBCONTRACTOR)
        self.other = make_user("o@t.gr", User.Role.SUBCONTRACTOR)
        self.job, items = sectioned_job(self.gc)
        for u, prices in [(self.el, {items[1].id: 2, items[2].id: 10, items[4].id: 9}),
                          (self.pl, {items[1].id: 9, items[2].id: 90, items[4].id: 5})]:
            b = Bid.objects.create(job=self.job, subcontractor=u, status="submitted")
            for i, p in prices.items():
                b.lines.create(item_id=i, unit_price=p)
        Job.objects.filter(id=self.job.id).update(bid_deadline=timezone.now() - timedelta(minutes=1))
        self.client.force_authenticate(self.gc)
        r = self.client.post(f"/api/jobs/{self.job.id}/award", {"allocations": [
            {"bid_id": Bid.objects.get(subcontractor=self.el).id, "sections": [items[0].id]},
            {"bid_id": Bid.objects.get(subcontractor=self.pl).id, "sections": [items[3].id]}]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_messages_threads_and_notification_throttle(self):
        url = f"/api/jobs/{self.job.id}/messages"
        self.client.force_authenticate(self.gc)
        self.assertEqual(self.client.post(url, {"text": "Γεια"}, format="json").status_code, 400)  # χωρίς «with»
        self.client.post(url, {"with": self.el.id, "text": "Πότε ξεκινάτε;"}, format="json")
        self.client.post(url, {"with": self.el.id, "text": "Και κάτι ακόμα"}, format="json")
        from notify.models import Notification
        self.assertEqual(Notification.objects.filter(user=self.el, kind="message").count(), 1)  # μία ειδοποίηση
        self.client.force_authenticate(self.el)
        threads = self.client.get(f"/api/jobs/{self.job.id}/threads").data
        self.assertEqual(threads[0]["unread"], 2)
        msgs = self.client.get(url).data
        self.assertEqual([m["mine"] for m in msgs], [False, False])
        self.client.post(url, {"text": "Δευτέρα"}, format="json")
        self.client.force_authenticate(self.gc)
        threads = {t["with"]: t for t in self.client.get(f"/api/jobs/{self.job.id}/threads").data}
        self.assertEqual(threads[self.el.id]["unread"], 1)
        self.assertEqual(threads[self.pl.id]["last"], None)
        # Τρίτος δεν έχει πρόσβαση, ούτε ο ένας ανάδοχος στη συνομιλία του άλλου
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.pl)
        self.assertEqual(len(self.client.get(url).data), 0)

    def test_reviews_both_ways_and_profile_average(self):
        url = f"/api/jobs/{self.job.id}/reviews"
        self.client.force_authenticate(self.gc)
        data = self.client.get(url).data
        self.assertEqual({t["company"]["name"] for t in data["targets"]}, {"el", "pl"})
        crit = {c["key"]: 5 for c in data["criteria"]}
        r = self.client.post(url, {"target": self.el.company.id, "criteria": crit, "comment": "Άψογοι"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        bad = self.client.post(url, {"target": self.other.company.id, "criteria": crit}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.client.post(url, {"target": self.el.company.id, "criteria": {**crit, "quality": 2}}, format="json")  # ενημέρωση
        self.client.force_authenticate(self.el)
        crit2 = {c["key"]: 4 for c in self.client.get(url).data["criteria"]}
        self.assertIn("payments", crit2)
        self.client.post(url, {"target": self.gc.company.id, "criteria": crit2}, format="json")
        prof = self.client.get(f"/api/companies/{self.el.company.id}").data["reviews"]
        self.assertEqual((prof["count"], prof["average"]), (1, 4))
        listing = {c["name"]: c["rating"] for c in self.client.get("/api/companies", {"role": "contractor"}).data}
        self.assertEqual(listing["gc"], {"average": 4.0, "count": 1})
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_contract_data(self):
        self.client.force_authenticate(self.el)
        c = self.client.get(f"/api/jobs/{self.job.id}/contract").data
        self.assertEqual(c["amount"], 300)
        self.assertEqual(c["scope"], ["ΗΛΕΚΤΡΟΛΟΓΙΚΑ"])
        self.assertEqual(len(c["appendix"]), 1)
        self.assertEqual(c["vat_24"], 72)
        self.client.force_authenticate(self.gc)
        self.assertEqual(self.client.get(f"/api/jobs/{self.job.id}/contract").status_code, 400)
        pl_bid = Bid.objects.get(subcontractor=self.pl).id
        self.assertEqual(self.client.get(f"/api/jobs/{self.job.id}/contract", {"bid": pl_bid}).data["amount"], 250)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f"/api/jobs/{self.job.id}/contract").status_code, 403)


class PricingTests(APITestCase):
    def setUp(self):
        from accounts.models import Company
        self.gc = make_user("gc@t.gr", User.Role.CONTRACTOR)
        self.subs = [make_user(f"s{i}@t.gr", User.Role.SUBCONTRACTOR) for i in range(4)]
        # Παλιά, κλειστή δημόσια εργασία με τιμές από 4 εταιρείες
        self.old = Job.objects.create(contractor=self.gc, title="Παλιά", region="attiki", status=Job.Status.AWARDED,
                                      bid_deadline=timezone.now() - timedelta(days=30))
        from tenders.models import BOQItem
        it = BOQItem.objects.create(job=self.old, position=1, description="Χώρισμα γυψοσανίδας 10 cm με πετροβάμβακα",
                                    unit="τ.μ.", quantity=100)
        for i, (u, p) in enumerate(zip(self.subs, [20, 22, 25, 40])):
            b = Bid.objects.create(job=self.old, subcontractor=u, status="submitted")
            b.lines.create(item=it, unit_price=p)
        # Νέα εργασία με παρόμοια γραμμή
        self.new = Job.objects.create(contractor=self.gc, title="Νέα", region="attiki", status=Job.Status.OPEN,
                                      bid_deadline=timezone.now() + timedelta(days=3))
        self.item = BOQItem.objects.create(job=self.new, position=1, description="Χώρισμα από γυψοσανίδα 10cm, με πετροβάμβακα",
                                           unit="m²", quantity=50)
        self.other = BOQItem.objects.create(job=self.new, position=2, description="Χώρισμα γυψοσανίδας 10 cm",
                                            unit="m", quantity=5)  # άλλη μονάδα

    def test_own_price_suggestions(self):
        self.client.force_authenticate(self.subs[1])
        s = self.client.get(f"/api/jobs/{self.new.id}/my-bid/suggestions").data
        self.assertEqual(list(s), [self.item.id])  # η γραμμή με άλλη μονάδα δεν ταιριάζει
        self.assertEqual(s[self.item.id]["unit_price"], 22)
        self.client.force_authenticate(make_user("new@t.gr", User.Role.SUBCONTRACTOR))
        self.assertEqual(self.client.get(f"/api/jobs/{self.new.id}/my-bid/suggestions").data, {})

    def test_market_stats_need_three_companies(self):
        Job.objects.filter(id=self.new.id).update(bid_deadline=timezone.now() - timedelta(minutes=1))
        self.client.force_authenticate(self.gc)
        rows = {r["item_id"]: r for r in self.client.get(f"/api/jobs/{self.new.id}/comparison").data["rows"]}
        m = rows[self.item.id]["market"]
        self.assertEqual((m["companies"], m["median"]), (4, 23.5))
        self.assertIsNone(rows[self.other.id]["market"])
        # Με δύο εταιρείες δεν εμφανίζεται τίποτα
        Bid.objects.filter(subcontractor__in=self.subs[2:]).delete()
        rows = {r["item_id"]: r for r in self.client.get(f"/api/jobs/{self.new.id}/comparison").data["rows"]}
        self.assertIsNone(rows[self.item.id]["market"])

    def test_price_index_search_and_private_jobs_excluded(self):
        self.client.force_authenticate(self.subs[0])
        r = self.client.get("/api/price-index", {"q": "γυψοσανιδα πετροβαμβακα"}).data
        self.assertEqual(r["unit"], "m2")
        self.assertEqual(r["result"]["companies"], 4)
        self.assertEqual(r["result"]["p25"], Decimal("21.50"))
        Job.objects.filter(id=self.old.id).update(visibility="private")
        self.assertIsNone(self.client.get("/api/price-index", {"q": "γυψοσανιδα"}).data["result"])
