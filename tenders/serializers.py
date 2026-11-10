from decimal import Decimal

from rest_framework import serializers

from .models import Bid, BidLine, BOQItem, Job, JobDocument, JobQuestion

LICENSE_ORDER = {"A": 1, "B": 2, "C": 3, "D": 4}


def company_brief(user):
    c = getattr(user, "company", None)
    if not c:
        return {"name": user.email, "verified": False}
    return {
        "id": c.id,
        "name": c.name,
        "region": c.region,
        "region_display": c.get_region_display(),
        "license_category": c.license_category,
        "license_display": c.get_license_category_display(),
        "verified": c.verified,
    }


class BOQItemSerializer(serializers.ModelSerializer):
    is_section = serializers.BooleanField(read_only=True)

    class Meta:
        model = BOQItem
        fields = ["id", "position", "code", "description", "unit", "quantity", "is_section"]
        read_only_fields = ["id", "position"]


class BOQWriteItemSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50, allow_blank=True, required=False, default="")
    description = serializers.CharField()
    unit = serializers.CharField(max_length=20, allow_blank=True, required=False, default="")
    quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, allow_null=True, required=False, default=None,
        min_value=Decimal("0"),
    )


class JobDocumentSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    filename = serializers.CharField(read_only=True)

    class Meta:
        model = JobDocument
        fields = [
            "id", "title", "kind", "kind_display", "version", "is_addendum",
            "job_revision", "size", "filename", "uploaded_at",
        ]


class JobListSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    region_display = serializers.CharField(source="get_region_display", read_only=True)
    license_display = serializers.CharField(source="get_required_license_display", read_only=True)
    phase = serializers.CharField(read_only=True)
    contractor = serializers.SerializerMethodField()
    boq_count = serializers.SerializerMethodField()
    documents_count = serializers.SerializerMethodField()
    bids_count = serializers.SerializerMethodField()
    my_bid_status = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "title", "category", "category_display", "region", "region_display",
            "location", "required_license", "license_display", "bid_deadline",
            "start_date", "duration_text", "status", "phase", "revision", "published_at",
            "contractor", "boq_count", "documents_count", "bids_count",
            "my_bid_status", "is_owner", "created_at",
        ]

    def get_contractor(self, obj):
        return company_brief(obj.contractor)

    def get_is_owner(self, obj):
        return obj.contractor_id == self.context["request"].user.id

    def get_my_bid_status(self, obj):
        if hasattr(obj, "my_bid_status"):
            return obj.my_bid_status
        user = self.context["request"].user
        return obj.bids.filter(subcontractor=user).values_list("status", flat=True).first()

    def get_boq_count(self, obj):
        if hasattr(obj, "boq_count"):
            return obj.boq_count
        return obj.boq_items.exclude(quantity=None).count()

    def get_documents_count(self, obj):
        if hasattr(obj, "documents_count"):
            return obj.documents_count
        return obj.documents.count()

    def get_bids_count(self, obj):
        if hasattr(obj, "bids_count"):
            return obj.bids_count
        return obj.bids.filter(status=Bid.Status.SUBMITTED).count()


class JobDetailSerializer(JobListSerializer):
    documents = JobDocumentSerializer(many=True, read_only=True)
    awarded = serializers.SerializerMethodField()

    class Meta(JobListSerializer.Meta):
        fields = JobListSerializer.Meta.fields + ["description", "documents", "awarded"]

    def get_awarded(self, obj):
        bid = obj.awarded_bid
        if not bid:
            return None
        user = self.context["request"].user
        if user.id in (obj.contractor_id, bid.subcontractor_id):
            return {"bid_id": bid.id, "company": company_brief(bid.subcontractor),
                    "total": bid.total(), "is_me": user.id == bid.subcontractor_id}
        return {"bid_id": None, "is_me": False}


class JobWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            "id", "title", "description", "category", "region", "location",
            "required_license", "bid_deadline", "start_date", "duration_text",
        ]


class QuestionSerializer(serializers.ModelSerializer):
    asked_by = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = JobQuestion
        fields = ["id", "text", "answer", "created_at", "answered_at", "asked_by", "is_mine"]
        read_only_fields = ["answer", "created_at", "answered_at"]

    def get_is_mine(self, obj):
        return obj.author_id == self.context["request"].user.id

    def get_asked_by(self, obj):
        # Μόνο ο εργολάβος βλέπει ποιος ρώτησε· για τους υπόλοιπους είναι ανώνυμο.
        if obj.job.contractor_id == self.context["request"].user.id:
            return company_brief(obj.author)["name"]
        return None


class BidLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = BidLine
        fields = ["item", "unit_price", "note"]


class BidLineWriteSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    unit_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, allow_null=True, required=False,
        min_value=Decimal("0"),
    )
    note = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")


class BidSerializer(serializers.ModelSerializer):
    lines = BidLineSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    outdated = serializers.SerializerMethodField()

    class Meta:
        model = Bid
        fields = [
            "id", "job", "status", "notes", "exclusions", "payment_terms",
            "duration_days", "validity_days", "job_revision", "submitted_at",
            "updated_at", "lines", "total", "outdated",
        ]
        read_only_fields = ["job", "status", "job_revision", "submitted_at", "updated_at"]

    def get_total(self, obj):
        return obj.total()

    def get_outdated(self, obj):
        return obj.status == Bid.Status.SUBMITTED and obj.job_revision < obj.job.revision


class BidWriteSerializer(serializers.Serializer):
    notes = serializers.CharField(allow_blank=True, required=False)
    exclusions = serializers.CharField(allow_blank=True, required=False)
    payment_terms = serializers.CharField(max_length=300, allow_blank=True, required=False)
    duration_days = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    validity_days = serializers.IntegerField(min_value=1, required=False)
    lines = BidLineWriteSerializer(many=True, required=False)


class MyBidListSerializer(serializers.ModelSerializer):
    job = JobListSerializer(read_only=True)
    total = serializers.SerializerMethodField()
    won = serializers.SerializerMethodField()

    class Meta:
        model = Bid
        fields = ["id", "status", "submitted_at", "updated_at", "total", "job", "won"]

    def get_total(self, obj):
        return obj.total()

    def get_won(self, obj):
        if obj.job.status != Job.Status.AWARDED:
            return None
        return obj.job.awarded_bid_id == obj.id
