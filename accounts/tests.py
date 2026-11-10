import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import Company, ProjectReference, User

TMP_MEDIA = tempfile.mkdtemp()


def make(email, role, **company):
    u = User.objects.create_user(email=email, password="secret-pass-1", role=role)
    defaults = {"name": email.split("@")[0], "vat_number": "123456789", "region": "attiki"}
    defaults.update(company)
    Company.objects.create(user=u, **defaults)
    return u


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class DirectoryTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.gc = make("gc@t.gr", "contractor", name="Δομική ΑΤΕ")
        self.gc2 = make("gc2@t.gr", "contractor", name="Κρήτη Κατασκευές", region="kriti")
        self.s1 = make("s1@t.gr", "subcontractor", name="Volt", license_category="C",
                       specialties=["power", "pv"], service_regions=["attiki", "kriti"], verified=True)
        self.s2 = make("s2@t.gr", "subcontractor", name="Φως ΟΕ", license_category="A",
                       specialties=["lighting"], region="thessalia")
        ProjectReference.objects.create(company=self.s1.company, title="Φωτοβολταϊκό 500 kWp", year=2024)

    def names(self, url):
        return [c["name"] for c in self.client.get(url).data]

    def test_each_side_sees_the_other_by_default(self):
        self.client.force_authenticate(self.gc)
        self.assertEqual(self.names("/api/companies"), ["Volt", "Φως ΟΕ"])
        self.client.force_authenticate(self.s1)
        self.assertEqual(set(self.names("/api/companies")), {"Δομική ΑΤΕ", "Κρήτη Κατασκευές"})
        # και ο εργολάβος μπορεί να δει άλλους εργολάβους ρητά, χωρίς τον εαυτό του
        self.client.force_authenticate(self.gc)
        self.assertEqual(self.names("/api/companies?role=contractor"), ["Κρήτη Κατασκευές"])

    def test_filters(self):
        self.client.force_authenticate(self.gc)
        self.assertEqual(self.names("/api/companies?region=kriti"), ["Volt"])  # μέσω περιοχής δραστηριότητας
        self.assertEqual(self.names("/api/companies?specialty=lighting"), ["Φως ΟΕ"])
        self.assertEqual(self.names("/api/companies?license=B"), ["Volt"])
        self.assertEqual(self.names("/api/companies?verified=1"), ["Volt"])
        self.assertEqual(self.names("/api/companies?q=φωτοβολταϊκό"), ["Volt"])  # αναζήτηση σε έργα

    def test_profile_includes_projects_stats_and_open_jobs(self):
        self.client.force_authenticate(self.gc)
        r = self.client.get(f"/api/companies/{self.s1.company.id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["projects"][0]["title"], "Φωτοβολταϊκό 500 kWp")
        self.assertEqual(r.data["stats"], {"bids_submitted": 0, "jobs_won": 0})
        self.client.force_authenticate(self.s1)
        r = self.client.get(f"/api/companies/{self.gc.company.id}")
        self.assertIn("jobs_published", r.data["stats"])
        self.assertEqual(r.data["open_jobs"], [])

    def test_project_crud_with_photo_and_ownership(self):
        self.client.force_authenticate(self.s2)
        photo = SimpleUploadedFile("p.jpg", b"\xff\xd8\xff fake jpg", content_type="image/jpeg")
        r = self.client.post("/api/me/projects", {
            "title": "Φωτισμός πλατείας", "year": "2023", "category": "public",
            "specialties": "lighting", "photo": photo,
        }, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        pid = r.data["id"]
        self.assertTrue(r.data["has_photo"])
        self.assertEqual(r.data["specialties"], ["lighting"])
        self.assertEqual(self.client.get(f"/api/projects/{pid}/photo").status_code, 200)

        bad = SimpleUploadedFile("x.exe", b"MZ")
        r = self.client.patch(f"/api/me/projects/{pid}", {"photo": bad}, format="multipart")
        self.assertEqual(r.status_code, 400)

        # Άλλη εταιρεία δεν αλλάζει ούτε διαγράφει
        self.client.force_authenticate(self.s1)
        self.assertEqual(self.client.patch(f"/api/me/projects/{pid}", {"title": "x"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/me/projects/{pid}").status_code, 404)

        self.client.force_authenticate(self.s2)
        r = self.client.patch(f"/api/me/projects/{pid}", {"title": "Φωτισμός κεντρικής πλατείας"}, format="json")
        self.assertEqual(r.data["title"], "Φωτισμός κεντρικής πλατείας")
        self.assertEqual(self.client.delete(f"/api/me/projects/{pid}").status_code, 204)

    def test_invalid_year_rejected(self):
        self.client.force_authenticate(self.s2)
        r = self.client.post("/api/me/projects", {"title": "x", "year": 1800}, format="json")
        self.assertEqual(r.status_code, 400)
