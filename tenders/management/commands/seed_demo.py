"""
Δημιουργεί demo δεδομένα: έναν εργολάβο, τρεις υπεργολάβους και τέσσερις εργασίες
σε διαφορετικές φάσεις. Κωδικός για όλους: demo1234

    python manage.py seed_demo          # προσθέτει (αν δεν υπάρχουν)
    python manage.py seed_demo --reset  # σβήνει πρώτα τους demo χρήστες
"""
from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Company, ProjectReference, User
from tenders.models import Award, Bid, BidLine, BOQItem, Job, JobDocument, JobQuestion, Message, Review

PASSWORD = "demo1234"

OFFICE_BOQ = [
    ("1", "ΙΣΧΥΡΑ ΡΕΥΜΑΤΑ", None, None),
    ("1.1", "Γενικός πίνακας χαμηλής τάσης (ΓΠΧΤ) 630Α, πλήρως εξοπλισμένος", "τεμ", 1),
    ("1.2", "Υποπίνακας ορόφου 63Α τύπου στεγανού", "τεμ", 4),
    ("1.3", "Καλώδιο J1VV-U 5x16 mm² για τροφοδοσία υποπινάκων", "m", 320),
    ("1.4", "Καλώδιο NYM 3x1,5 mm² για κυκλώματα φωτισμού", "m", 4800),
    ("1.5", "Καλώδιο NYM 3x2,5 mm² για κυκλώματα ρευματοδοτών", "m", 6200),
    ("1.6", "Ρευματοδότης σούκο χωνευτός, πλήρης", "τεμ", 410),
    ("1.7", "Διακόπτης φωτισμού απλός χωνευτός", "τεμ", 140),
    ("1.8", "Σχάρα καλωδίων γαλβανιζέ 300x60 mm με στηρίγματα", "m", 260),
    ("2", "ΦΩΤΙΣΜΟΣ", None, None),
    ("2.1", "Εγκατάσταση φωτιστικού LED panel 60x60 (προμήθεια εργοδότη)", "τεμ", 380),
    ("2.2", "Φωτιστικό ασφαλείας LED αυτονομίας 3h", "τεμ", 64),
    ("3", "ΑΣΘΕΝΗ ΡΕΥΜΑΤΑ", None, None),
    ("3.1", "Καλώδιο δομημένης καλωδίωσης Cat6 U/UTP", "m", 9500),
    ("3.2", "Πρίζα δικτύου RJ45 Cat6 διπλή", "τεμ", 240),
    ("3.3", "Rack 42U με patch panels και οργάνωση καλωδίων", "τεμ", 1),
    ("4", "ΠΥΡΑΝΙΧΝΕΥΣΗ", None, None),
    ("4.1", "Πίνακας πυρανίχνευσης διευθυνσιοδοτούμενος 2 βρόχων", "τεμ", 1),
    ("4.2", "Ανιχνευτής καπνού διευθυνσιοδοτούμενος", "τεμ", 150),
    ("4.3", "Κομβίο συναγερμού και φαροσειρήνα", "τεμ", 24),
]
# Τιμές μονάδας ανά υπεργολάβο (με τη σειρά των γραμμών με ποσότητα)
OFFICE_PRICES = {
    "sub1": [14500, 1650, 34, "1.15", "1.45", 9.5, 7.8, 26, 9, 85, "1.25", 26, 2950, 2100, 38, 55],
    "sub2": [13800, 1520, 31, "1.05", "1.30", 8.9, 7.2, 23, 8, 78, "1.10", 22, 2700, 2050, 41, 60],
    "sub3": [15900, 1800, 37, "1.10", "1.40", 10.5, 8.5, 29, 12, 99, None, 24, 3300, 2300, 45, 72],
}

PV_BOQ = [
    ("1", "Βάσεις στήριξης αλουμινίου για τραπεζοειδές πάνελ", "kWp", 100),
    ("2", "Τοποθέτηση φωτοβολταϊκών πλαισίων (προμήθεια εργοδότη)", "τεμ", 182),
    ("3", "Αντιστροφέας 100 kW: τοποθέτηση και σύνδεση", "τεμ", 1),
    ("4", "Καλώδιο DC solar 6 mm²", "m", 1400),
    ("5", "Καλώδιο AC NYY 4x95 mm²", "m", 60),
    ("6", "Πίνακας AC με διακόπτη και αντικεραυνική προστασία", "τεμ", 1),
    ("7", "Γείωση και ισοδυναμικές συνδέσεις", "κατ", 1),
]

HVAC_BOQ = [
    ("1", "ΥΔΡΕΥΣΗ - ΑΠΟΧΕΤΕΥΣΗ", None, None),
    ("1.1", "Σωλήνας πολυστρωματικός PEX-AL-PEX Φ20 με μόνωση", "m", 850),
    ("1.2", "Σωλήνας αποχέτευσης PP Φ110", "m", 240),
    ("1.3", "Συλλέκτης ύδρευσης 6 κυκλωμάτων", "τεμ", 8),
    ("1.4", "Εγκατάσταση ειδών υγιεινής (προμήθεια εργοδότη)", "τεμ", 46),
    ("2", "ΚΛΙΜΑΤΙΣΜΟΣ - ΑΕΡΙΣΜΟΣ", None, None),
    ("2.1", "Σύστημα VRF: εσωτερική μονάδα κασέτας, εγκατάσταση", "τεμ", 38),
    ("2.2", "Ψυκτικές σωληνώσεις χαλκού με μόνωση", "m", 1100),
    ("2.3", "Αεραγωγοί γαλβανιζέ με μόνωση", "m²", 420),
    ("2.4", "Μονάδα ανάκτησης θερμότητας 3.000 m³/h", "τεμ", 2),
]

DRYWALL_BOQ = [
    ("1", "Χώρισμα γυψοσανίδας 10 cm με ηχομόνωση πετροβάμβακα", "m²", 1350),
    ("2", "Επένδυση τοίχου με γυψοσανίδα σε μεταλλικό σκελετό", "m²", 600),
    ("3", "Ψευδοροφή ορυκτών ινών 60x60 με σκελετό", "m²", 2400),
    ("4", "Ψευδοροφή γυψοσανίδας με περιμετρική σκοτία", "m²", 380),
    ("5", "Θυρίδα επίσκεψης 60x60", "τεμ", 45),
]

HOTEL_BOQ = [
    ("Α", "ΔΩΜΑΤΙΑ (48)", None, None),
    ("Α.1", "Αποξήλωση παλαιάς ηλεκτρολογικής εγκατάστασης δωματίου", "τεμ", 48),
    ("Α.2", "Νέα εγκατάσταση δωματίου με πινακίδιο και σύστημα κάρτας", "τεμ", 48),
    ("Β", "ΚΟΙΝΟΧΡΗΣΤΟΙ ΧΩΡΟΙ", None, None),
    ("Β.1", "Φωτισμός διαδρόμων με αισθητήρες παρουσίας", "m", 420),
    ("Β.2", "Αντικατάσταση πίνακα κουζίνας", "τεμ", 1),
]


def demo_png(seed, w=480, h=270):
    """Δείγμα «φωτογραφίας» έργου (PNG χωρίς εξωτερικές βιβλιοθήκες)."""
    import struct
    import zlib

    palettes = [((20, 33, 61), (242, 169, 0)), ((31, 58, 96), (90, 170, 220)), ((40, 54, 44), (140, 200, 120)),
                ((60, 40, 30), (230, 140, 70)), ((30, 30, 50), (180, 160, 240))]
    (r1, g1, b1), (r2, g2, b2) = palettes[seed % len(palettes)]
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            t = (x / w * 0.6 + y / h * 0.4)
            band = ((x + y * 2 + seed * 37) // 40) % 2
            k = t * (0.85 if band else 1.0)
            rows += bytes((int(r1 + (r2 - r1) * k), int(g1 + (g2 - g1) * k), int(b1 + (b2 - b1) * k)))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b""))


def tiny_pdf(title):
    """Ελάχιστο έγκυρο PDF μιας σελίδας (δείγμα σχεδίου)."""
    text = title.encode("latin-1", "replace")
    content = b"BT /F1 24 Tf 72 720 Td (" + text + b") Tj ET 0.5 w 72 100 468 580 re S"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


class Command(BaseCommand):
    help = "Δημιουργεί demo χρήστες και εργασίες"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true")

    @transaction.atomic
    def handle(self, *args, reset=False, **opts):
        if reset:
            User.objects.filter(email__endswith="@demo.gr").delete()
        if User.objects.filter(email="ergolavos@demo.gr").exists():
            self.stdout.write("Τα demo δεδομένα υπάρχουν ήδη (χρησιμοποιήστε --reset).")
            return

        now = timezone.now()
        gc = self.user("ergolavos@demo.gr", "contractor", "Γιώργος", "Αντωνίου",
                       name="ΤΕΧΝΟΔΟΜΙΚΗ ΑΤΕ", vat_number="094512367", region="attiki", city="Αθήνα",
                       license_category="D", verified=True, employees=85, founded_year=1998,
                       address="Λ. Κηφισίας 120", tax_office="ΦΑΕ Αθηνών",
                       website="https://technodomiki.example.gr", phone="210 6100 200",
                       description=("Τεχνική εταιρεία με 25+ χρόνια σε κτίρια γραφείων, εμπορικά κέντρα και "
                                    "ξενοδοχεία. Αναλαμβάνουμε έργα ως γενικός εργολάβος και συνεργαζόμαστε "
                                    "με σταθερή ομάδα υπεργολάβων για τα Η/Μ."))
        gc2 = self.user("kritikataskeves@demo.gr", "contractor", "Ελένη", "Μαυράκη",
                        name="Κρητικές Κατασκευές ΑΕ", vat_number="096677881", region="kriti", city="Ηράκλειο",
                        license_category="C", employees=32, founded_year=2009, phone="2810 300 400",
                        description="Ξενοδοχειακά και τουριστικά έργα σε Κρήτη και Νότιο Αιγαίο.")
        subs = {
            "sub1": self.user("hlektrotexniki@demo.gr", "subcontractor", "Μαρία", "Κωνσταντίνου",
                              name="Ηλεκτροτεχνική Αττικής ΕΠΕ", vat_number="800123456", region="attiki",
                              city="Περιστέρι", license_category="D", verified=True, employees=24, founded_year=2004,
                              phone="210 5700 123", website="https://hlektrotexniki.example.gr",
                              specialties=["power", "low_voltage", "fire", "mv"], service_regions=["attiki", "sterea_ellada"],
                              description=("Ισχυρά, ασθενή και πυρανίχνευση σε κτίρια γραφείων και βιομηχανίες. "
                                           "Συνεργείο 24 ατόμων, ιδιόκτητο ανυψωτικό, πιστοποίηση ISO 9001.")),
            "sub2": self.user("volt@demo.gr", "subcontractor", "Νίκος", "Παππάς",
                              name="Volt Εγκαταστάσεις ΙΚΕ", vat_number="801987654", region="attiki",
                              city="Χαλάνδρι", license_category="C", verified=True, employees=11, founded_year=2016,
                              address="Αγ. Παρασκευής 45", tax_office="Χαλανδρίου",
                              phone="694 000 1122",
                              specialties=["power", "lighting", "pv", "ev"], service_regions=["attiki", "notio_aigaio"],
                              description="Φωτοβολταϊκά, φόρτιση ΗΟ και φωτισμός LED για επαγγελματικούς χώρους."),
            "sub3": self.user("papadopoulos@demo.gr", "subcontractor", "Κώστας", "Παπαδόπουλος",
                              name="Παπαδόπουλος & Σια ΟΕ", vat_number="099887766", region="attiki",
                              city="Πειραιάς", license_category="C", employees=6, founded_year=1991,
                              specialties=["power", "low_voltage"], service_regions=["attiki", "peloponnisos"],
                              description="Οικογενειακή επιχείρηση, τρίτη γενιά ηλεκτρολόγων. Κατοικίες και καταστήματα."),
            "sub4": self.user("thessaliko@demo.gr", "subcontractor", "Δημήτρης", "Ζήσης",
                              name="Θεσσαλικά Ηλεκτρικά ΑΕ", vat_number="802345678", region="thessalia",
                              city="Λάρισα", license_category="D", verified=True, employees=40, founded_year=2001,
                              specialties=["power", "mv", "pv", "bms"], service_regions=["thessalia", "kentriki_makedonia", "sterea_ellada"],
                              description="Βιομηχανικές εγκαταστάσεις, υποσταθμοί μέσης τάσης και φωτοβολταϊκά πάρκα."),
            "sub5": self.user("kritiled@demo.gr", "subcontractor", "Γιάννης", "Σφακιανάκης",
                              name="Kriti Lighting & Power", vat_number="803456789", region="kriti",
                              city="Χανιά", license_category="B", employees=8, founded_year=2012,
                              specialties=["power", "lighting", "low_voltage"], service_regions=["kriti"],
                              description="Ανακαινίσεις ξενοδοχείων και συστήματα κάρτας δωματίων."),
        }
        subs.update({
            "plumb": self.user("ydrothermiki@demo.gr", "subcontractor", "Σπύρος", "Αλεξίου",
                               name="Υδροθερμική ΕΠΕ", vat_number="804567890", region="attiki", city="Μαρούσι",
                               verified=True, employees=18, founded_year=2007, phone="210 8000 456",
                               specialties=["plumbing", "heating", "hvac", "gas", "fire_suppression"],
                               service_regions=["attiki", "sterea_ellada"],
                               description="Υδραυλικά, θέρμανση, κλιματισμός VRF και πυρόσβεση για κτίρια γραφείων και ξενοδοχεία."),
            "cool": self.user("klimatiki@demo.gr", "subcontractor", "Άννα", "Ρήγα",
                              name="Κλιματική Βορείου Ελλάδος", vat_number="805678901", region="kentriki_makedonia",
                              city="Θεσσαλονίκη", employees=9, founded_year=2014,
                              specialties=["hvac", "heating"], service_regions=["kentriki_makedonia", "thessalia"],
                              description="Κλιματισμός, αντλίες θερμότητας και αεραγωγοί."),
            "dry": self.user("gypsotechniki@demo.gr", "subcontractor", "Παύλος", "Μιχαήλ",
                             name="Γυψοτεχνική ΙΚΕ", vat_number="806789012", region="attiki", city="Αχαρνές",
                             verified=True, employees=22, founded_year=2010,
                             specialties=["drywall", "insulation", "painting", "plaster"], service_regions=["attiki", "peloponnisos"],
                             description="Γυψοσανίδες, ψευδοροφές, μονώσεις και χρωματισμοί. Συνεργεία έως 20 ατόμων."),
            "alu": self.user("aluminia@demo.gr", "subcontractor", "Θανάσης", "Νικολάου",
                             name="Αλουμίνια Νικολάου ΑΕ", vat_number="807890123", region="attiki", city="Κορωπί",
                             employees=30, founded_year=1996,
                             specialties=["aluminium", "glazing", "metalwork"], service_regions=["attiki", "notio_aigaio", "kriti"],
                             description="Κουφώματα αλουμινίου και υαλοπετάσματα για επαγγελματικά κτίρια και ξενοδοχεία."),
        })
        self.projects(subs["plumb"].company, [
            ("Υδραυλικά και VRF ξενοδοχείου 90 δωματίων", "ΤΕΧΝΟΔΟΜΙΚΗ ΑΤΕ", "Βουλιαγμένη", "attiki", 2024, "hospitality",
             "200_1m", ["plumbing", "hvac"], "Πλήρης υδραυλική εγκατάσταση και VRF 180 kW.", True),
            ("Καταιονισμός υπόγειου σταθμού στάθμευσης", "Εμπορικό κέντρο", "Μαρούσι", "attiki", 2023, "commercial",
             "50_200", ["fire_suppression"], "", False),
        ])
        self.projects(subs["dry"].company, [
            ("Ψευδοροφές και χωρίσματα γραφείων 6.000 m²", "Ασφαλιστική εταιρεία", "Αθήνα", "attiki", 2025, "commercial",
             "200_1m", ["drywall", "insulation"], "Ηχομονωτικά χωρίσματα και ψευδοροφές ορυκτών ινών σε 4 ορόφους.", True),
        ])
        self.projects(subs["alu"].company, [
            ("Υαλοπέτασμα κτιρίου γραφείων", "Κατασκευαστική", "Κηφισιά", "attiki", 2024, "commercial", "gt1m",
             ["glazing", "aluminium"], "Structural glazing 1.800 m².", True),
        ])
        self.projects(gc.company, [
            ("Κτίριο γραφείων Κηφισίας 9.000 m²", "Ιδιώτης επενδυτής", "Κηφισιά", "attiki", 2025, "commercial", "gt1m",
             ["power", "low_voltage", "fire"], "Γενική εργολαβία με πλήρη Η/Μ, LEED Gold.", True),
            ("Ξενοδοχείο 5* 120 δωματίων", "Όμιλος ξενοδοχείων", "Ρόδος", "notio_aigaio", 2023, "hospitality", "gt1m",
             [], "Ολική ανακατασκευή σε 7 μήνες, εκτός τουριστικής περιόδου.", True),
            ("Εμπορικό κατάστημα 2.500 m²", "Αλυσίδα λιανικής", "Γλυφάδα", "attiki", 2022, "commercial", "200_1m", [], "", False),
        ])
        self.projects(gc2.company, [
            ("Boutique hotel 40 δωματίων", "Ιδιώτης", "Ρέθυμνο", "kriti", 2024, "hospitality", "200_1m", [], "", True),
        ])
        self.projects(subs["sub1"].company, [
            ("Ηλεκτρολογικά κτιρίου γραφείων 6 ορόφων", "ΤΕΧΝΟΔΟΜΙΚΗ ΑΤΕ", "Κηφισιά", "attiki", 2025, "commercial", "200_1m",
             ["power", "low_voltage", "fire"], "Ισχυρά, δομημένη καλωδίωση 1.200 θέσεων, πυρανίχνευση 2 βρόχων.", True),
            ("Υποσταθμός 1.000 kVA σε βιομηχανία τροφίμων", "Βιομηχανία τροφίμων", "Σχηματάρι", "sterea_ellada", 2024,
             "industrial", "200_1m", ["mv", "power"], "Υποσταθμός, ΓΠΧΤ και αντιστάθμιση.", True),
            ("Πυρανίχνευση νοσοκομειακής πτέρυγας", "Δημόσιο νοσοκομείο", "Αθήνα", "attiki", 2022, "public", "50_200",
             ["fire"], "", False),
        ])
        self.projects(subs["sub2"].company, [
            ("Φωτοβολταϊκό 250 kWp σε κέντρο logistics", "Εταιρεία logistics", "Μαγούλα", "attiki", 2025, "energy",
             "200_1m", ["pv"], "Net-billing με αντιστροφείς 2x125 kW, ολοκλήρωση σε 5 εβδομάδες.", True),
            ("12 σταθμοί φόρτισης ΗΟ σε εμπορικό πάρκινγκ", "Εμπορικό κέντρο", "Μαρούσι", "attiki", 2024, "commercial",
             "50_200", ["ev", "power"], "", True),
        ])
        self.projects(subs["sub4"].company, [
            ("Φωτοβολταϊκό πάρκο 5 MWp", "Εταιρεία ΑΠΕ", "Φάρσαλα", "thessalia", 2024, "energy", "gt1m",
             ["pv", "mv"], "Ηλεκτρολογικά DC/AC και υποσταθμός ανύψωσης.", True),
            ("BMS εργοστασίου 20.000 m²", "Βιομηχανία", "Βόλος", "thessalia", 2023, "industrial", "200_1m", ["bms"], "", False),
        ])
        self.projects(subs["sub5"].company, [
            ("Σύστημα κάρτας και φωτισμός 80 δωματίων", "Ξενοδοχείο 4*", "Χερσόνησος", "kriti", 2025, "hospitality",
             "50_200", ["lighting", "low_voltage"], "", True),
        ])

        # 1) Γραφεία Μαρούσι: η προθεσμία έληξε, 3 προσφορές για σύγκριση
        office = self.job(gc, "Ηλεκτρολογικά νέου κτιρίου γραφείων 4 ορόφων", OFFICE_BOQ,
                          description=("Πλήρης ηλεκτρολογική εγκατάσταση νέου κτιρίου γραφείων 4 ορόφων "
                                       "(περίπου 3.200 m²): ισχυρά, ασθενή, πυρανίχνευση.\n\n"
                                       "Τα φωτιστικά σώματα τα προμηθεύει ο εργοδότης· ο υπεργολάβος "
                                       "αναλαμβάνει την εγκατάσταση. Εργοτάξιο με γερανό και ανυψωτικό."),
                          category="commercial", location="Μαρούσι", trades=["power", "low_voltage", "fire"],
                          deadline=now + timedelta(days=1), start=now.date() + timedelta(days=30),
                          duration="5 μήνες", docs=["Κάτοψη ισογείου", "Κάτοψη τυπικού ορόφου", "Μονογραμμικό ΓΠΧΤ"])
        for key, terms, days in [("sub1", "30% προκαταβολή, μηνιαίοι λογαριασμοί", 140),
                                 ("sub2", "Μηνιαίοι λογαριασμοί, εξόφληση σε 60 ημέρες", 150),
                                 ("sub3", "40% προκαταβολή, υπόλοιπο τμηματικά", 120)]:
            self.bid(office, subs[key], OFFICE_PRICES[key], payment_terms=terms, duration_days=days,
                     exclusions="Δεν περιλαμβάνονται οικοδομικές εργασίες (μερεμέτια)." if key == "sub3" else "",
                     notes="Η τιμή του ΓΠΧΤ ισχύει για παραγγελία εντός 30 ημερών." if key == "sub1" else "")
        q = JobQuestion.objects.create(job=office, author=subs["sub2"],
                                       text="Η σύνδεση με τον ΔΕΔΔΗΕ και η μελέτη περιλαμβάνονται;")
        q.answer, q.answered_at = "Όχι. Τη σύνδεση και τη μελέτη τις αναλαμβάνει ο εργοδότης.", now
        q.save()
        office.bid_deadline = now - timedelta(hours=2)
        office.save()

        # 2) Φωτοβολταϊκό: ανοιχτό, 1 υποβληθείσα προσφορά, 1 ερώτηση
        pv = self.job(gc, "Φωτοβολταϊκό 100 kWp σε στέγη αποθήκης", PV_BOQ,
                      description="Εγκατάσταση φωτοβολταϊκού σταθμού net-billing σε μεταλλική στέγη αποθήκης.",
                      category="energy", location="Ασπρόπυργος", trades=["pv", "power"],
                      deadline=now + timedelta(days=5), start=now.date() + timedelta(days=21),
                      duration="6 εβδομάδες", docs=["Διάταξη πλαισίων στέγης"])
        self.bid(pv, subs["sub2"], [52, 18, 900, "1.35", 38, 2400, 1600], duration_days=35)
        JobQuestion.objects.create(job=pv, author=subs["sub1"],
                                   text="Υπάρχει πρόσβαση στη στέγη με καλαθοφόρο ή χρειάζεται ικρίωμα;")

        # 3) Ξενοδοχείο Κρήτη: ανοιχτό, καμία προσφορά
        self.job(gc, "Ανακαίνιση ηλεκτρολογικών ξενοδοχείου 48 δωματίων", HOTEL_BOQ,
                 description="Εργασίες κατά τη χειμερινή περίοδο, με το ξενοδοχείο κλειστό.",
                 category="hospitality", location="Ηράκλειο", region="kriti", trades=["power", "lighting"],
                 deadline=now + timedelta(days=12), start=now.date() + timedelta(days=40), duration="3 μήνες")

        # 4) Υδραυλικά και κλιματισμός: ανοιχτό, 1 προσφορά
        hvac = self.job(gc, "Υδραυλικά και κλιματισμός VRF κτιρίου γραφείων", HVAC_BOQ,
                        description=("Ύδρευση, αποχέτευση και κλιματισμός VRF στο νέο κτίριο γραφείων στο Μαρούσι. "
                                     "Οι εξωτερικές μονάδες VRF και τα είδη υγιεινής είναι προμήθεια εργοδότη."),
                        category="commercial", location="Μαρούσι", trades=["plumbing", "hvac"],
                        deadline=now + timedelta(days=8), start=now.date() + timedelta(days=35),
                        duration="4 μήνες", docs=["Κάτοψη Η/Μ τυπικού ορόφου"])
        self.bid(hvac, subs["plumb"], ["7.2", "11", 280, 45, 160, 38, 42, 6800], duration_days=110,
                 payment_terms="Μηνιαίοι λογαριασμοί")

        # 5) Γυψοσανίδες: ανοιχτό, χωρίς προσφορές
        self.job(gc, "Γυψοσανίδες και ψευδοροφές γραφείων", DRYWALL_BOQ,
                 description="Εσωτερικά χωρίσματα και ψευδοροφές 4 ορόφων γραφείων.",
                 category="commercial", location="Μαρούσι", trades=["drywall", "insulation"],
                 deadline=now + timedelta(days=10), start=now.date() + timedelta(days=70), duration="10 εβδομάδες")

        # 6) Ολοκληρωμένη ανάθεση με συνομιλία και αξιολογήσεις
        shop = self.job(gc, "Ηλεκτρολογικά καταστήματος 2.500 m²", [
            ("1", "Γενικός πίνακας καταστήματος", "τεμ", 1), ("2", "Φωτιστικά ράγας: εγκατάσταση", "τεμ", 140),
            ("3", "Καλωδιώσεις NYM 3x2,5", "m", 2200)],
            description="Ηλεκτρολογική εγκατάσταση νέου καταστήματος λιανικής.", category="commercial",
            location="Γλυφάδα", trades=["power", "lighting"], deadline=now + timedelta(days=1),
            start=now.date() - timedelta(days=20), duration="6 εβδομάδες")
        won = self.bid(shop, subs["sub2"], [6200, 24, "1.35"], duration_days=40, payment_terms="Μηνιαίοι λογαριασμοί")
        self.bid(shop, subs["sub1"], [6900, 27, "1.40"], duration_days=35)
        Job.objects.filter(id=shop.id).update(bid_deadline=now - timedelta(days=25), status=Job.Status.AWARDED,
                                              awarded_bid=won, opened_notified=True, reminder_sent=True)
        Award.objects.create(job=shop, bid=won, amount=won.total())
        for sender, text in [(gc, "Καλημέρα, το εργοτάξιο είναι διαθέσιμο από Δευτέρα. Θα σας στείλουμε τα αναθεωρημένα σχέδια φωτισμού."),
                             (subs["sub2"], "Τέλεια, ξεκινάμε Δευτέρα 8:00 με συνεργείο 4 ατόμων.")]:
            Message.objects.create(job=shop, subcontractor=subs["sub2"], sender=sender, text=text, read_at=now)
        Review.objects.create(job=shop, author=gc, target=subs["sub2"].company, rating=5,
                              criteria={"quality": 5, "timeliness": 5, "cooperation": 4},
                              comment="Πολύ καθαρή δουλειά, παράδοση μία εβδομάδα νωρίτερα.")
        Review.objects.create(job=shop, author=subs["sub2"], target=gc.company, rating=4,
                              criteria={"payments": 4, "organization": 4, "communication": 5},
                              comment="Οργανωμένο εργοτάξιο και άμεση επικοινωνία.")

        # 7) Ιστορικό: κλειστές εργασίες με τιμές από πολλές εταιρείες (για δείκτες τιμών και τιμοκατάλογο)
        history = [
            ("Ηλεκτρολογικά γραφείων Χαλανδρίου", OFFICE_BOQ, ["power", "low_voltage", "fire"],
             [("sub1", 1.04), ("sub2", 0.97), ("sub3", 1.10), ("sub4", 1.00)], OFFICE_PRICES["sub1"], 160),
            ("Γυψοσανίδες ξενοδοχείου Βουλιαγμένης", DRYWALL_BOQ, ["drywall"],
             [("dry", 1.0), ("sub3", 1.12), ("sub5", 0.95), ("plumb", 1.20)], [32, 26, 21, 34, 38], 90),
        ]
        for title, boq, trades, bidders, base, days_ago in history:
            old = self.job(gc, title, boq, description="Ολοκληρωμένη εργασία (ιστορικό).", category="commercial",
                           location="Αττική", trades=trades, deadline=now + timedelta(days=1),
                           start=now.date() - timedelta(days=days_ago - 10), duration="")
            bids = []
            for key, factor in bidders:
                prices = [None if p is None else round(float(p) * factor, 2) for p in base]
                bids.append(self.bid(old, subs[key], prices, duration_days=60))
            Job.objects.filter(id=old.id).update(bid_deadline=now - timedelta(days=days_ago), status=Job.Status.AWARDED,
                                                 awarded_bid=bids[0], opened_notified=True, reminder_sent=True)
            Award.objects.create(job=old, bid=bids[0], amount=bids[0].total())

        # 8) Πρόχειρο
        Job.objects.create(contractor=gc, title="Σταθμοί φόρτισης ΗΟ σε υπόγειο πάρκινγκ",
                           region="attiki", location="Γλυφάδα", category="commercial", trades=["ev", "power"])

        self.stdout.write(self.style.SUCCESS(
            "Έτοιμο. Εργολάβοι: ergolavos@demo.gr, kritikataskeves@demo.gr. Υπεργολάβοι: "
            "hlektrotexniki@demo.gr, volt@demo.gr, ydrothermiki@demo.gr, gypsotechniki@demo.gr, aluminia@demo.gr κ.ά. "
            f"Κωδικός: {PASSWORD}"))

    def user(self, email, role, first, last, verified=False, **company):
        u = User.objects.create_user(email=email, password=PASSWORD, role=role, first_name=first, last_name=last,
                                     email_verified=True, terms_accepted_at=timezone.now())
        Company.objects.create(user=u, verified=verified, **company)
        return u

    def job(self, gc, title, boq, region="attiki", deadline=None, start=None, duration="", docs=(), **kw):
        job = Job.objects.create(contractor=gc, title=title, region=region, bid_deadline=deadline,
                                 start_date=start, duration_text=duration, status=Job.Status.OPEN,
                                 published_at=timezone.now(), **kw)
        BOQItem.objects.bulk_create([
            BOQItem(job=job, position=i, code=c, description=d, unit=u or "",
                    quantity=Decimal(str(q)) if q is not None else None)
            for i, (c, d, u, q) in enumerate(boq, start=1)
        ])
        for name in docs:
            slug = "".join(ch if ch.isalnum() else "-" for ch in name.lower())
            JobDocument.objects.create(job=job, title=name, kind=JobDocument.Kind.DRAWING,
                                       file=ContentFile(tiny_pdf(f"DEMO DRAWING #{job.id}"), name=f"{slug}.pdf"),
                                       size=900)
        return job

    def projects(self, company, rows):
        for i, (title, client, loc, region, year, cat, value, specs, desc, photo) in enumerate(rows):
            p = ProjectReference.objects.create(
                company=company, title=title, client=client, location=loc, region=region, year=year,
                category=cat, value_range=value, specialties=specs, description=desc)
            if photo:
                p.photo.save(f"demo-{company.id}-{i}.png", ContentFile(demo_png(company.id * 7 + i)), save=True)

    def bid(self, job, sub, prices, **kw):
        bid = Bid.objects.create(job=job, subcontractor=sub, status=Bid.Status.SUBMITTED,
                                 submitted_at=timezone.now(), job_revision=job.revision, **kw)
        items = list(job.boq_items.exclude(quantity=None))
        BidLine.objects.bulk_create([
            BidLine(bid=bid, item=it, unit_price=Decimal(str(p)) if p is not None else None,
                    note="Εκτός αντικειμένου· προτείνουμε συνεργάτη" if p is None else "")
            for it, p in zip(items, prices)
        ])
        return bid
