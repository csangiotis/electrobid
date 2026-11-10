from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from accounts import api as accounts_api
from accounts import directory

api_patterns = [
    path("auth/register", accounts_api.register),
    path("auth/login", accounts_api.login),
    path("auth/logout", accounts_api.logout),
    path("me", accounts_api.me),
    path("choices", accounts_api.choices),
    path("me/projects", directory.my_projects),
    path("me/projects/<int:pk>", directory.my_project_detail),
    path("companies", directory.company_list),
    path("companies/<int:pk>", directory.company_detail),
    path("projects/<int:pk>/photo", directory.project_photo),
    path("", include("tenders.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(api_patterns)),
    # Το frontend είναι single-page app· όλα τα υπόλοιπα URL σερβίρουν το index.html
    path("", TemplateView.as_view(template_name="index.html"), name="app"),
]

# Τα ανεβασμένα αρχεία ΔΕΝ σερβίρονται δημόσια· η λήψη γίνεται μέσω
# /api/documents/<id>/download με έλεγχο δικαιωμάτων.
