from django.contrib import admin

from .models import Bid, BidLine, BOQItem, Job, JobDocument, JobQuestion


class BOQInline(admin.TabularInline):
    model = BOQItem
    extra = 0


class DocInline(admin.TabularInline):
    model = JobDocument
    extra = 0


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["title", "contractor", "region", "status", "bid_deadline"]
    list_filter = ["status", "region", "category"]
    search_fields = ["title"]
    inlines = [DocInline, BOQInline]


class BidLineInline(admin.TabularInline):
    model = BidLine
    extra = 0


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ["job", "subcontractor", "status", "submitted_at"]
    list_filter = ["status"]
    inlines = [BidLineInline]


admin.site.register(JobQuestion)
