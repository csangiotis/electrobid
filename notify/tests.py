import re
from datetime import timedelta

from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Company, User
from notify import scheduled
from notify.models import Notification
from tenders.models import Bid, BOQItem, Job


def make(email, role, **company):
    u = User.objects.create_user(email=email, password="secret-pass-1", role=role, email_verified=True)
    data = {"name": email.split("@")[0], "vat_number": "123456789", "region": "attiki"}
    data.update(company)
    Company.objects.create(user=u, **data)
    return u


def draft_job(gc, **kw):
    job = Job.objects.create(contractor=gc, title=kw.pop("title", "Υδραυλικά"), region=kw.pop("region", "attiki"),
                             trades=kw.pop("trades", ["plumbing"]),
                             bid_deadline=kw.pop("deadline", timezone.now() + timedelta(days=5)), **kw)
    BOQItem.objects.create(job=job, position=1, description="Σωλήνας", unit="m", quantity=10)
    return job


class AccountEmailTests(APITestCase):
    def register(self, **extra):
        body = {"email": "new@t.gr", "password": "kalos-kodikos-1", "first_name": "Α", "last_name": "Β",
                "role": "subcontractor", "accept_terms": True,
                "company": {"name": "Νέα", "vat_number": "099999999", "region": "attiki"}}
        body.update(extra)
        return self.client.post("/api/auth/register", body, format="json")

    def test_terms_must_be_accepted(self):
        r = self.register(accept_terms=False)
        self.assertEqual(r.status_code, 400)
        self.assertIn("accept_terms", r.data)

    def test_register_sends_verification_and_link_verifies(self):
        r = self.register()
        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.data["user"]["email_verified"])
        self.assertEqual(len(mail.outbox), 1)
        m = re.search(r"#/verify/([^/]+)/(\S+)", mail.outbox[0].body)
        r = self.client.post("/api/auth/verify-email", {"uid": m.group(1), "token": m.group(2)})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(User.objects.get(email="new@t.gr").email_verified)
        # Ο ίδιος σύνδεσμος δεν ξαναδουλεύει (το token εξαρτάται από την κατάσταση)
        r = self.client.post("/api/auth/verify-email", {"uid": m.group(1), "token": m.group(2)})
        self.assertEqual(r.status_code, 400)

    def test_password_reset_flow(self):
        u = make("x@t.gr", "contractor")
        r = self.client.post("/api/auth/password-reset", {"email": "nobody@t.gr"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)  # ίδια απάντηση, χωρίς email
        self.client.post("/api/auth/password-reset", {"email": "X@t.gr"})
        self.assertEqual(len(mail.outbox), 1)
        uid, token = re.search(r"#/reset/([^/]+)/(\S+)", mail.outbox[0].body).groups()
        r = self.client.post("/api/auth/password-reset/confirm", {"uid": uid, "token": token, "password": "123"})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/auth/password-reset/confirm", {"uid": uid, "token": token, "password": "neos-kodikos-99"})
        self.assertEqual(r.status_code, 200)
        u.refresh_from_db()
        self.assertTrue(u.check_password("neos-kodikos-99"))
        r = self.client.post("/api/auth/password-reset/confirm", {"uid": uid, "token": token, "password": "allos-kodikos-99"})
        self.assertEqual(r.status_code, 400)  # μίας χρήσης

    @override_settings(REQUIRE_EMAIL_VERIFICATION=True)
    def test_unverified_cannot_publish(self):
        gc = make("gc@t.gr", "contractor")
        gc.email_verified = False
        gc.save()
        job = draft_job(gc)
        self.client.force_authenticate(gc)
        r = self.client.post(f"/api/jobs/{job.id}/publish")
        self.assertEqual(r.status_code, 403)


class NotificationTests(APITestCase):
    def setUp(self):
        self.gc = make("gc@t.gr", "contractor")
        self.plumber = make("p@t.gr", "subcontractor", specialties=["plumbing"], service_regions=["attiki"])
        self.far = make("far@t.gr", "subcontractor", specialties=["plumbing"], region="kriti")
        self.painter = make("paint@t.gr", "subcontractor", specialties=["painting"])

    def test_publish_notifies_matching_trade_and_region(self):
        job = draft_job(self.gc)
        self.client.force_authenticate(self.gc)
        self.assertEqual(self.client.post(f"/api/jobs/{job.id}/publish").status_code, 200)
        notified = set(Notification.objects.filter(kind="new_job").values_list("user__email", flat=True))
        self.assertEqual(notified, {"p@t.gr"})
        self.assertEqual([m.to for m in mail.outbox], [["p@t.gr"]])
        self.assertIn(f"#/jobs/{job.id}", mail.outbox[0].body)

    def test_email_prefs_disable_email_but_keep_in_app(self):
        self.client.force_authenticate(self.plumber)
        r = self.client.put("/api/me/email-prefs", {"new_job": False, "bogus": False}, format="json")
        self.assertFalse(next(x for x in r.data if x["kind"] == "new_job")["enabled"])
        job = draft_job(self.gc)
        self.client.force_authenticate(self.gc)
        self.client.post(f"/api/jobs/{job.id}/publish")
        self.assertEqual(len(mail.outbox), 0)
        self.client.force_authenticate(self.plumber)
        data = self.client.get("/api/notifications").data
        self.assertEqual(data["unread"], 1)
        self.client.post("/api/notifications/read", {}, format="json")
        self.assertEqual(self.client.get("/api/notifications").data["unread"], 0)

    def test_questions_answers_and_award_notifications(self):
        job = draft_job(self.gc, status=Job.Status.OPEN)
        self.client.force_authenticate(self.plumber)
        q = self.client.post(f"/api/jobs/{job.id}/questions", {"text": "Περιλαμβάνεται ο έλεγχος πίεσης;"}).data
        self.assertTrue(Notification.objects.filter(user=self.gc, kind="qa").exists())
        self.client.force_authenticate(self.gc)
        self.client.post(f"/api/jobs/{job.id}/questions/{q['id']}/answer", {"answer": "Ναι."})
        self.assertTrue(Notification.objects.filter(user=self.plumber, kind="qa").exists())

        b1 = Bid.objects.create(job=job, subcontractor=self.plumber, status="submitted")
        Bid.objects.create(job=job, subcontractor=self.painter, status="submitted")
        Job.objects.filter(id=job.id).update(bid_deadline=timezone.now() - timedelta(minutes=1))
        self.client.post(f"/api/jobs/{job.id}/award", {"bid_id": b1.id}, format="json")
        titles = dict(Notification.objects.filter(kind="award").values_list("user__email", "title"))
        self.assertTrue(titles["p@t.gr"].startswith("Σας ανατέθηκε"))
        self.assertTrue(titles["paint@t.gr"].startswith("Αποτέλεσμα"))

    def test_scheduled_reminder_and_opened(self):
        now = timezone.now()
        job = draft_job(self.gc, status=Job.Status.OPEN, deadline=now + timedelta(hours=5))
        Bid.objects.create(job=job, subcontractor=self.plumber, status="draft")
        Bid.objects.create(job=job, subcontractor=self.painter, status="submitted")
        scheduled.run(now)
        self.assertEqual(list(Notification.objects.filter(kind="deadline").values_list("user__email", flat=True)), ["p@t.gr"])
        scheduled.run(now)  # όχι διπλή αποστολή
        self.assertEqual(Notification.objects.filter(kind="deadline").count(), 1)
        scheduled.run(now + timedelta(hours=6))
        n = Notification.objects.get(kind="bids")
        self.assertEqual(n.user, self.gc)
        self.assertIn("1 προσφορά", n.body)

    def test_tick_runs_at_most_every_10_minutes(self):
        job = draft_job(self.gc, status=Job.Status.OPEN, deadline=timezone.now() - timedelta(minutes=1))
        self.client.force_authenticate(self.gc)
        self.client.get("/api/notifications")  # το middleware τρέχει το tick
        self.assertEqual(Notification.objects.filter(kind="bids").count(), 1)
        job.opened_notified = False
        job.save()
        self.client.get("/api/notifications")
        self.assertEqual(Notification.objects.filter(kind="bids").count(), 1)  # δεν πέρασαν 10 λεπτά
