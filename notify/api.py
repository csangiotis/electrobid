from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Kind, Notification


def _row(n):
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "url": n.url,
            "read": n.read_at is not None, "created_at": n.created_at}


@api_view(["GET"])
def notifications(request):
    qs = Notification.objects.filter(user=request.user)
    return Response({"unread": qs.filter(read_at=None).count(), "items": [_row(n) for n in qs[:50]]})


@api_view(["POST"])
def mark_read(request):
    qs = Notification.objects.filter(user=request.user, read_at=None)
    ids = request.data.get("ids")
    if ids:
        qs = qs.filter(id__in=[int(i) for i in ids])
    qs.update(read_at=timezone.now())
    return Response({"ok": True})


@api_view(["GET", "PUT"])
def email_prefs(request):
    user = request.user
    if request.method == "PUT":
        prefs = {k: bool(v) for k, v in (request.data or {}).items() if k in Kind.values}
        user.email_prefs = {**user.email_prefs, **prefs}
        user.save(update_fields=["email_prefs"])
    return Response([{"kind": k, "label": label, "enabled": user.email_prefs.get(k, True)}
                     for k, label in Kind.choices])
