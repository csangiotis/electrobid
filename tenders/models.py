import os
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from accounts.models import LICENSE_CATEGORIES, REGIONS


class Job(models.Model):
    """Μια εργασία (διαγωνισμός) που δημοσιεύει ο εργολάβος."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Πρόχειρο"
        OPEN = "open", "Δημοσιευμένο"
        AWARDED = "awarded", "Ανατέθηκε"
        CANCELLED = "cancelled", "Ακυρώθηκε"

    class Category(models.TextChoices):
        RESIDENTIAL = "residential", "Κατοικίες"
        COMMERCIAL = "commercial", "Εμπορικό / γραφεία"
        INDUSTRIAL = "industrial", "Βιομηχανικό"
        PUBLIC = "public", "Δημόσιο έργο"
        HOSPITALITY = "hospitality", "Ξενοδοχειακό"
        ENERGY = "energy", "Ενέργεια / ΦΒ"

    contractor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jobs"
    )
    title = models.CharField("τίτλος", max_length=200)
    description = models.TextField("περιγραφή", blank=True)
    category = models.CharField(
        "κατηγορία", max_length=20, choices=Category.choices, default=Category.COMMERCIAL
    )
    region = models.CharField("περιφέρεια", max_length=40, choices=REGIONS)
    location = models.CharField("τοποθεσία", max_length=200, blank=True)
    required_license = models.CharField(
        "ελάχιστη άδεια", max_length=1, choices=LICENSE_CATEGORIES, blank=True
    )
    bid_deadline = models.DateTimeField("προθεσμία προσφορών", null=True, blank=True)
    start_date = models.DateField("επιθυμητή έναρξη", null=True, blank=True)
    duration_text = models.CharField("εκτιμώμενη διάρκεια", max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    # Αυξάνεται κάθε φορά που προστίθεται συμπλήρωμα μετά τη δημοσίευση,
    # ώστε να φαίνεται αν μια προσφορά δόθηκε σε παλιότερη έκδοση.
    revision = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    awarded_bid = models.OneToOneField(
        "Bid", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "εργασία"
        verbose_name_plural = "εργασίες"

    def __str__(self):
        return self.title

    @property
    def deadline_passed(self):
        return bool(self.bid_deadline and timezone.now() >= self.bid_deadline)

    @property
    def phase(self):
        """Φάση όπως τη βλέπει ο χρήστης: draft / bidding / evaluation / awarded / cancelled."""
        if self.status == self.Status.OPEN:
            return "evaluation" if self.deadline_passed else "bidding"
        if self.status == self.Status.DRAFT:
            return "draft"
        return self.status

    @property
    def accepts_bids(self):
        return self.status == self.Status.OPEN and not self.deadline_passed


def document_upload_to(instance, filename):
    return f"jobs/{instance.job_id}/{filename}"


class JobDocument(models.Model):
    class Kind(models.TextChoices):
        DRAWING = "drawing", "Σχέδιο"
        SPEC = "spec", "Τεχνική περιγραφή / προδιαγραφές"
        BOQ = "boq", "Προμέτρηση (αρχικό αρχείο)"
        OTHER = "other", "Άλλο"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(upload_to=document_upload_to)
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.DRAWING)
    # Αριθμός έκδοσης για έγγραφα με τον ίδιο τίτλο (π.χ. "Κάτοψη ισογείου" rev 0, 1, 2)
    version = models.PositiveIntegerField(default=0)
    is_addendum = models.BooleanField(default=False)
    job_revision = models.PositiveIntegerField(default=0)
    size = models.PositiveBigIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "title", "-version"]

    @property
    def filename(self):
        return os.path.basename(self.file.name)


class BOQItem(models.Model):
    """Γραμμή προμέτρησης. Αν quantity είναι κενό, η γραμμή είναι επικεφαλίδα ενότητας."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="boq_items")
    position = models.PositiveIntegerField()
    code = models.CharField("α/α - κωδικός", max_length=50, blank=True)
    description = models.TextField("περιγραφή")
    unit = models.CharField("μονάδα", max_length=20, blank=True)
    quantity = models.DecimalField(
        "ποσότητα", max_digits=14, decimal_places=3, null=True, blank=True
    )

    class Meta:
        ordering = ["position"]

    @property
    def is_section(self):
        return self.quantity is None


class JobQuestion(models.Model):
    """Ερώτηση διευκρίνισης. Οι απαντήσεις είναι ορατές σε όλους, ανώνυμα."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="questions")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.TextField()
    answer = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]


class Bid(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Πρόχειρη"
        SUBMITTED = "submitted", "Υποβλήθηκε"
        WITHDRAWN = "withdrawn", "Αποσύρθηκε"

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="bids")
    subcontractor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bids"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField("σημειώσεις", blank=True)
    exclusions = models.TextField("εξαιρέσεις / παραδοχές", blank=True)
    payment_terms = models.CharField("όροι πληρωμής", max_length=300, blank=True)
    duration_days = models.PositiveIntegerField("χρόνος εκτέλεσης (ημέρες)", null=True, blank=True)
    validity_days = models.PositiveIntegerField("ισχύς προσφοράς (ημέρες)", default=60)
    job_revision = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("job", "subcontractor")]
        ordering = ["-updated_at"]

    def total(self):
        total = Decimal("0")
        for line in self.lines.select_related("item"):
            if line.unit_price is not None and line.item.quantity is not None:
                total += line.unit_price * line.item.quantity
        return total.quantize(Decimal("0.01"))


class BidLine(models.Model):
    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(BOQItem, on_delete=models.CASCADE, related_name="bid_lines")
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        unique_together = [("bid", "item")]
