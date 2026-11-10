"""
Κατάλογος εταιρειών και δημόσια προφίλ.

Ο εργολάβος ψάχνει υπεργολάβους και ο υπεργολάβος εργολάβους (προεπιλογή: η «άλλη» πλευρά).
Κάθε εταιρεία διαχειρίζεται τα έργα της (εμπειρία) μέσω /api/me/projects.
"""
import os

from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .api import REGION_KEYS, SPECIALTY_KEYS
from .models import Company, ProjectReference, User
from .textsearch import matches

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PHOTO_SIZE = 8 * 1024 * 1024
MAX_PROJECTS = 100


class ProjectSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    region_display = serializers.CharField(source="get_region_display", read_only=True)
    value_display = serializers.CharField(source="get_value_range_display", read_only=True)
    has_photo = serializers.SerializerMethodField()

    class Meta:
        model = ProjectReference
        fields = [
            "id", "title", "client", "location", "region", "region_display", "year",
            "category", "category_display", "value_range", "value_display",
            "specialties", "description", "has_photo",
        ]

    def get_has_photo(self, obj):
        return bool(obj.photo)

    def validate_year(self, value):
        if value is not None and not 1950 <= value <= timezone.now().year + 1:
            raise serializers.ValidationError("Μη έγκυρο έτος.")
        return value

    def validate_specialties(self, value):
        if isinstance(value, str):  # από multipart: «power,pv»
            value = [v for v in value.split(",") if v]
        bad = [v for v in value if v not in SPECIALTY_KEYS]
        if bad:
            raise serializers.ValidationError(f"Άγνωστες ειδικότητες: {', '.join(bad)}")
        return value


def _stats(company):
    user = company.user
    if user.role == User.Role.CONTRACTOR:
        jobs = user.jobs.exclude(status="draft")
        return {
            "jobs_published": jobs.count(),
            "jobs_awarded": jobs.filter(status="awarded").count(),
            "jobs_open": jobs.filter(status="open", bid_deadline__gt=timezone.now()).count(),
        }
    bids = user.bids.filter(status="submitted")
    return {
        "bids_submitted": bids.count(),
        "jobs_won": sum(1 for b in bids.select_related("job") if b.job.awarded_bid_id == b.id),
    }


class CompanyCardSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="user.role", read_only=True)
    region_display = serializers.CharField(source="get_region_display", read_only=True)
    license_display = serializers.CharField(source="get_license_category_display", read_only=True)
    projects_count = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            "id", "name", "role", "city", "region", "region_display", "service_regions",
            "license_category", "license_display", "specialties", "employees",
            "founded_year", "description", "verified", "projects_count",
        ]

    def get_projects_count(self, obj):
        if hasattr(obj, "projects_count"):
            return obj.projects_count
        return obj.projects.count()


class CompanyProfileSerializer(CompanyCardSerializer):
    projects = ProjectSerializer(many=True, read_only=True)
    stats = serializers.SerializerMethodField()
    open_jobs = serializers.SerializerMethodField()
    is_me = serializers.SerializerMethodField()
    member_since = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta(CompanyCardSerializer.Meta):
        fields = CompanyCardSerializer.Meta.fields + [
            "phone", "website", "vat_number", "projects", "stats", "open_jobs", "is_me", "member_since",
        ]

    def get_stats(self, obj):
        return _stats(obj)

    def get_is_me(self, obj):
        return obj.user_id == self.context["request"].user.id

    def get_open_jobs(self, obj):
        if obj.user.role != User.Role.CONTRACTOR:
            return []
        jobs = obj.user.jobs.filter(status="open", visibility="public",
                                    bid_deadline__gt=timezone.now()).order_by("bid_deadline")
        return [{"id": j.id, "title": j.title, "location": j.location or j.get_region_display(),
                 "bid_deadline": j.bid_deadline} for j in jobs[:20]]


@api_view(["GET"])
def company_list(request):
    """
    ?role=subcontractor|contractor (προεπιλογή: ο αντίθετος ρόλος από τον χρήστη)
    &region=  (έδρα ή περιοχή δραστηριότητας) &specialty= &license= (ελάχιστη) &verified=1 &q=
    """
    p = request.query_params
    me = request.user
    role = p.get("role") or (User.Role.SUBCONTRACTOR if me.is_contractor else User.Role.CONTRACTOR)
    if role not in User.Role.values:
        raise ValidationError("Άγνωστος ρόλος.")
    qs = (Company.objects.filter(user__role=role, user__is_active=True)
          .exclude(user=me).select_related("user")
          .annotate(projects_count=Count("projects")))
    if p.get("verified") in ("1", "true"):
        qs = qs.filter(verified=True)
    if p.get("license"):
        order = ["A", "B", "C", "D"]
        if p["license"] in order:
            qs = qs.filter(license_category__in=order[order.index(p["license"]):])
    companies = list(qs.order_by("-verified", "-projects_count", "name"))
    if p.get("q"):
        titles = {}
        for cid, title, client in ProjectReference.objects.filter(
                company__in=[c.id for c in companies]).values_list("company_id", "title", "client"):
            titles.setdefault(cid, []).extend([title, client])
        companies = [c for c in companies
                     if matches(p["q"], c.name, c.description, c.city, *titles.get(c.id, []))]
    # Φίλτρα σε JSON πεδία στην Python (η SQLite δεν υποστηρίζει __contains σε JSONField)
    region, specialty = p.get("region"), p.get("specialty")
    if region in REGION_KEYS:
        companies = [c for c in companies if c.region == region or region in (c.service_regions or [])]
    if specialty in SPECIALTY_KEYS:
        companies = [c for c in companies if specialty in (c.specialties or [])]
    return Response(CompanyCardSerializer(companies[:200], many=True).data)


@api_view(["GET"])
def company_detail(request, pk):
    company = get_object_or_404(Company.objects.select_related("user"), pk=pk, user__is_active=True)
    return Response(CompanyProfileSerializer(company, context={"request": request}).data)


def _save_photo(project, request):
    photo = request.FILES.get("photo")
    if photo:
        ext = os.path.splitext(photo.name)[1].lower()
        if ext not in PHOTO_EXTENSIONS:
            raise ValidationError("Η φωτογραφία πρέπει να είναι JPG, PNG ή WEBP.")
        if photo.size > MAX_PHOTO_SIZE:
            raise ValidationError("Η φωτογραφία ξεπερνά τα 8 MB.")
        if project.photo:
            project.photo.delete(save=False)
        project.photo = photo
        project.save()
    elif request.data.get("remove_photo") in ("1", "true") and project.photo:
        project.photo.delete(save=False)
        project.photo = ""
        project.save()


def _project_data(request):
    """Δέχεται JSON ή multipart (όπου οι λίστες έρχονται ως «a,b»)."""
    data = {k: v for k, v in request.data.items() if k not in ("photo", "remove_photo")}
    for k in ("year",):
        if data.get(k) == "":
            data[k] = None
    return data


@api_view(["GET", "POST"])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def my_projects(request):
    company = request.user.company
    if request.method == "GET":
        return Response(ProjectSerializer(company.projects.all(), many=True).data)
    if company.projects.count() >= MAX_PROJECTS:
        raise ValidationError(f"Έως {MAX_PROJECTS} έργα ανά εταιρεία.")
    s = ProjectSerializer(data=_project_data(request))
    s.is_valid(raise_exception=True)
    project = s.save(company=company)
    _save_photo(project, request)
    return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def my_project_detail(request, pk):
    project = get_object_or_404(ProjectReference, pk=pk, company__user=request.user)
    if request.method == "DELETE":
        if project.photo:
            project.photo.delete(save=False)
        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    s = ProjectSerializer(project, data=_project_data(request), partial=True)
    s.is_valid(raise_exception=True)
    s.save()
    _save_photo(project, request)
    return Response(ProjectSerializer(project).data)


@api_view(["GET"])
def project_photo(request, pk):
    project = get_object_or_404(ProjectReference, pk=pk)
    if not project.photo:
        return Response(status=status.HTTP_404_NOT_FOUND)
    try:
        resp = FileResponse(project.photo.open("rb"))
    except FileNotFoundError:
        return Response(status=status.HTTP_404_NOT_FOUND)
    resp["Cache-Control"] = "private, max-age=3600"
    return resp
