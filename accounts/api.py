"""API λογαριασμών: εγγραφή, σύνδεση, προφίλ, επιλογές."""
import re

from django.contrib.auth import authenticate, password_validation
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import (
    LICENSE_CATEGORIES, PROJECT_CATEGORIES, REGIONS, SPECIALTIES, SPECIALTY_GROUP, VALUE_RANGES, Company, User,
)

REGION_KEYS = {k for k, _ in REGIONS}
SPECIALTY_KEYS = {k for k, _ in SPECIALTIES}


class CompanySerializer(serializers.ModelSerializer):
    region_display = serializers.CharField(source="get_region_display", read_only=True)
    license_display = serializers.CharField(source="get_license_category_display", read_only=True)

    class Meta:
        model = Company
        fields = [
            "name", "vat_number", "phone", "city", "region", "region_display",
            "service_regions", "license_category", "license_display",
            "specialties", "employees", "founded_year", "website", "description", "verified",
        ]
        read_only_fields = ["verified"]

    def validate_vat_number(self, value):
        value = value.strip()
        if not re.fullmatch(r"\d{9}", value):
            raise serializers.ValidationError("Ο ΑΦΜ πρέπει να έχει 9 ψηφία.")
        return value

    def validate_founded_year(self, value):
        if value is not None and not 1900 <= value <= 2100:
            raise serializers.ValidationError("Μη έγκυρο έτος.")
        return value

    def validate_service_regions(self, value):
        bad = [v for v in value if v not in REGION_KEYS]
        if bad:
            raise serializers.ValidationError(f"Άγνωστες περιφέρειες: {', '.join(bad)}")
        return value

    def validate_specialties(self, value):
        bad = [v for v in value if v not in SPECIALTY_KEYS]
        if bad:
            raise serializers.ValidationError(f"Άγνωστες ειδικότητες: {', '.join(bad)}")
        return value


class MeSerializer(serializers.ModelSerializer):
    company = CompanySerializer()
    company_id = serializers.IntegerField(source="company.id", read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "company", "company_id"]
        read_only_fields = ["id", "email", "role"]

    def update(self, instance, validated_data):
        company_data = validated_data.pop("company", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if company_data:
            for k, v in company_data.items():
                setattr(instance.company, k, v)
            instance.company.save()
        return instance


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=User.Role.choices)
    company = CompanySerializer()

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Υπάρχει ήδη λογαριασμός με αυτό το email.")
        return value

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    @transaction.atomic
    def create(self, data):
        company = data.pop("company")
        user = User.objects.create_user(**data)
        Company.objects.create(user=user, **company)
        return user


def _auth_payload(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {"token": token.key, "user": MeSerializer(user).data}


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    s = RegisterSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    user = s.save()
    return Response(_auth_payload(user), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    email = (request.data.get("email") or "").lower().strip()
    password = request.data.get("password") or ""
    user = authenticate(request, email=email, password=password)
    if not user:
        return Response({"detail": "Λάθος email ή κωδικός."}, status=status.HTTP_400_BAD_REQUEST)
    return Response(_auth_payload(user))


@api_view(["POST"])
def logout(request):
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET", "PATCH"])
def me(request):
    if request.method == "PATCH":
        s = MeSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)
    return Response(MeSerializer(request.user).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def choices(request):
    """Λίστες επιλογών για τις φόρμες του frontend."""
    from tenders.models import Job, JobDocument

    def pairs(items):
        return [{"value": k, "label": v} for k, v in items]

    return Response({
        "regions": pairs(REGIONS),
        "licenses": pairs(LICENSE_CATEGORIES),
        "specialties": [{"value": k, "label": v, "group": SPECIALTY_GROUP[k]} for k, v in SPECIALTIES],
        "roles": pairs(User.Role.choices),
        "job_categories": pairs(Job.Category.choices),
        "document_kinds": pairs(JobDocument.Kind.choices),
        "project_categories": pairs(PROJECT_CATEGORIES),
        "value_ranges": pairs(VALUE_RANGES),
    })
