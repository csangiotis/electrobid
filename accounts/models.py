from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

# Οι 13 περιφέρειες της Ελλάδας
REGIONS = [
    ("attiki", "Αττική"),
    ("kentriki_makedonia", "Κεντρική Μακεδονία"),
    ("dytiki_makedonia", "Δυτική Μακεδονία"),
    ("anatoliki_makedonia_thraki", "Ανατολική Μακεδονία & Θράκη"),
    ("thessalia", "Θεσσαλία"),
    ("ipeiros", "Ήπειρος"),
    ("ionia_nisia", "Ιόνια Νησιά"),
    ("dytiki_ellada", "Δυτική Ελλάδα"),
    ("sterea_ellada", "Στερεά Ελλάδα"),
    ("peloponnisos", "Πελοπόννησος"),
    ("voreio_aigaio", "Βόρειο Αιγαίο"),
    ("notio_aigaio", "Νότιο Αιγαίο"),
    ("kriti", "Κρήτη"),
]

# Κατηγορίες άδειας (δεν εμφανίζονται πλέον στο UI· κρατιούνται για συμβατότητα)
LICENSE_CATEGORIES = [
    ("A", "Α' τάξη"),
    ("B", "Β' τάξη"),
    ("C", "Γ' τάξη"),
    ("D", "Δ' τάξη"),
]

# Ειδικότητες της οικοδομής, σε ομάδες. Τα κλειδιά των ηλεκτρολογικών
# (power, low_voltage, fire, pv, bms, mv, lighting, ev) διατηρούνται για συμβατότητα.
TRADE_GROUPS = [
    ("Η/Μ εγκαταστάσεις", [
        ("power", "Ηλεκτρολογικά (ισχυρά)"),
        ("low_voltage", "Ασθενή ρεύματα / δίκτυα"),
        ("mv", "Μέση τάση / υποσταθμοί"),
        ("lighting", "Φωτισμός"),
        ("bms", "BMS / αυτοματισμοί"),
        ("ev", "Φόρτιση ηλεκτρικών οχημάτων"),
        ("pv", "Φωτοβολταϊκά / ΑΠΕ"),
        ("plumbing", "Υδραυλικά / αποχέτευση"),
        ("heating", "Θέρμανση"),
        ("hvac", "Κλιματισμός / αερισμός"),
        ("fire", "Πυρανίχνευση"),
        ("fire_suppression", "Πυρόσβεση"),
        ("gas", "Φυσικό αέριο"),
        ("elevators", "Ανελκυστήρες"),
    ]),
    ("Χωματουργικά και φέρων οργανισμός", [
        ("demolition", "Κατεδαφίσεις / αποξηλώσεις"),
        ("earthworks", "Χωματουργικά / εκσκαφές"),
        ("concrete", "Σκυροδέματα / ξυλότυποι"),
        ("rebar", "Σιδηρός οπλισμός"),
        ("steel", "Μεταλλικές κατασκευές"),
    ]),
    ("Οικοδομικά και φινιρίσματα", [
        ("masonry", "Τοιχοποιίες"),
        ("plaster", "Επιχρίσματα"),
        ("drywall", "Γυψοσανίδες / ψευδοροφές"),
        ("insulation", "Μονώσεις / στεγανώσεις"),
        ("facades", "Θερμοπρόσοψη / όψεις"),
        ("tiling", "Πλακίδια"),
        ("marble", "Μάρμαρα"),
        ("flooring", "Δάπεδα (ξύλινα / βιομηχανικά / ρητίνες)"),
        ("painting", "Χρωματισμοί"),
        ("aluminium", "Κουφώματα αλουμινίου / PVC"),
        ("glazing", "Υαλοπίνακες / υαλοπετάσματα"),
        ("carpentry", "Ξυλουργικά / επιπλοποιία"),
        ("metalwork", "Σιδηρικά / κάγκελα"),
        ("roofing", "Στέγες / επικαλύψεις"),
    ]),
    ("Περιβάλλων χώρος και υποδομές", [
        ("landscaping", "Πράσινο / άρδευση"),
        ("paving", "Οδοποιία / ασφαλτικά / πλακοστρώσεις"),
        ("networks", "Δίκτυα ύδρευσης / αποχέτευσης"),
        ("pools", "Πισίνες"),
    ]),
]
SPECIALTIES = [item for _, items in TRADE_GROUPS for item in items]
SPECIALTY_GROUP = {key: group for group, items in TRADE_GROUPS for key, _ in items}



class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Το email είναι υποχρεωτικό")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.CONTRACTOR)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    class Role(models.TextChoices):
        CONTRACTOR = "contractor", "Εργολάβος"
        SUBCONTRACTOR = "subcontractor", "Υπεργολάβος"

    username = None
    email = models.EmailField("email", unique=True)
    role = models.CharField("ρόλος", max_length=20, choices=Role.choices)
    email_verified = models.BooleanField("email επιβεβαιωμένο", default=False)
    terms_accepted_at = models.DateTimeField("αποδοχή όρων", null=True, blank=True)
    # Προτιμήσεις email ανά είδος ειδοποίησης: {"new_job": false, ...}· ό,τι λείπει = ενεργό
    email_prefs = models.JSONField("προτιμήσεις email", default=dict, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    @property
    def is_contractor(self):
        return self.role == self.Role.CONTRACTOR

    @property
    def is_subcontractor(self):
        return self.role == self.Role.SUBCONTRACTOR

    def __str__(self):
        return self.email


class Company(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="company")
    name = models.CharField("επωνυμία", max_length=200)
    vat_number = models.CharField("ΑΦΜ", max_length=9)
    phone = models.CharField("τηλέφωνο", max_length=30, blank=True)
    city = models.CharField("πόλη", max_length=100, blank=True)
    address = models.CharField("διεύθυνση έδρας", max_length=200, blank=True)
    tax_office = models.CharField("ΔΟΥ", max_length=100, blank=True)
    region = models.CharField("έδρα (περιφέρεια)", max_length=40, choices=REGIONS)
    # Περιοχές όπου αναλαμβάνει εργασίες (λίστα κωδικών περιφέρειας)
    service_regions = models.JSONField("περιοχές δραστηριότητας", default=list, blank=True)
    license_category = models.CharField(
        "κατηγορία άδειας", max_length=1, choices=LICENSE_CATEGORIES, blank=True
    )
    specialties = models.JSONField("ειδικότητες", default=list, blank=True)
    employees = models.PositiveIntegerField("προσωπικό", null=True, blank=True)
    founded_year = models.PositiveIntegerField("έτος ίδρυσης", null=True, blank=True)
    website = models.URLField("ιστοσελίδα", blank=True)
    description = models.TextField("περιγραφή", blank=True)
    verified = models.BooleanField("επαληθευμένη", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "εταιρεία"
        verbose_name_plural = "εταιρείες"

    def __str__(self):
        return self.name


PROJECT_CATEGORIES = [
    ("residential", "Κατοικίες"),
    ("commercial", "Εμπορικό / γραφεία"),
    ("industrial", "Βιομηχανικό"),
    ("public", "Δημόσιο έργο"),
    ("hospitality", "Ξενοδοχειακό"),
    ("energy", "Ενέργεια / ΦΒ"),
]

VALUE_RANGES = [
    ("lt50", "έως 50.000 €"),
    ("50_200", "50.000 – 200.000 €"),
    ("200_1m", "200.000 – 1.000.000 €"),
    ("gt1m", "πάνω από 1.000.000 €"),
]


def project_photo_upload_to(instance, filename):
    return f"companies/{instance.company_id}/projects/{filename}"


class ProjectReference(models.Model):
    """Έργο που έχει εκτελέσει η εταιρεία (εμπειρία / portfolio)."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField("τίτλος", max_length=200)
    client = models.CharField("πελάτης / κύριος έργου", max_length=200, blank=True)
    location = models.CharField("τοποθεσία", max_length=200, blank=True)
    region = models.CharField("περιφέρεια", max_length=40, choices=REGIONS, blank=True)
    year = models.PositiveIntegerField("έτος ολοκλήρωσης", null=True, blank=True)
    category = models.CharField("κατηγορία", max_length=20, choices=PROJECT_CATEGORIES, blank=True)
    value_range = models.CharField("ύψος εργασιών", max_length=10, choices=VALUE_RANGES, blank=True)
    specialties = models.JSONField("αντικείμενο", default=list, blank=True)
    description = models.TextField("περιγραφή", blank=True)
    photo = models.FileField("φωτογραφία", upload_to=project_photo_upload_to, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "-created_at"]
        verbose_name = "έργο εταιρείας"
        verbose_name_plural = "έργα εταιρειών"

    def __str__(self):
        return self.title
