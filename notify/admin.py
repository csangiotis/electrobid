from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["user", "kind", "title", "emailed", "read_at", "created_at"]
    list_filter = ["kind", "emailed"]
    search_fields = ["user__email", "title"]
