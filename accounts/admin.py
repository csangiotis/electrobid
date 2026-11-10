from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Company, ProjectReference, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "role", "is_active", "date_joined"]
    list_filter = ["role", "is_active"]
    search_fields = ["email"]
    fieldsets = (
        (None, {"fields": ("email", "password", "role")}),
        ("Στοιχεία", {"fields": ("first_name", "last_name")}),
        ("Δικαιώματα", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "role", "password1", "password2")}),)


class ProjectInline(admin.StackedInline):
    model = ProjectReference
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    inlines = [ProjectInline]
    list_display = ["name", "vat_number", "region", "license_category", "verified"]
    list_filter = ["verified", "region", "license_category"]
    list_editable = ["verified"]
    search_fields = ["name", "vat_number"]
