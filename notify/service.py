"""Αποστολή ειδοποιήσεων: in-app (πάντα) και email (αν το επιτρέπουν οι προτιμήσεις)."""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.html import escape

from .models import Notification

log = logging.getLogger(__name__)


def absolute(url):
    return f"{settings.SITE_URL.rstrip('/')}/{url.lstrip('/')}" if url else settings.SITE_URL


def build_email(to, subject, body, url="", cta="Άνοιγμα"):
    link = absolute(url)
    text = f"{body}\n\n{cta}: {link}\n\n— {settings.SITE_NAME}"
    paragraphs = "".join(f"<p style='margin:0 0 12px'>{escape(p)}</p>" for p in body.split("\n\n") if p.strip())
    html = f"""<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;color:#1b2333">
  <div style="background:#14213d;color:#fff;padding:14px 20px;border-radius:8px 8px 0 0;font-weight:700">
    subcontractor<span style="color:#f2a900">.gr</span></div>
  <div style="border:1px solid #e2e5ec;border-top:0;padding:20px;border-radius:0 0 8px 8px">
    <h2 style="margin:0 0 14px;font-size:18px;color:#14213d">{escape(subject)}</h2>
    {paragraphs}
    <p style="margin:18px 0 6px"><a href="{escape(link)}" style="background:#f2a900;color:#14213d;
      padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:700">{escape(cta)}</a></p>
    <p style="color:#667085;font-size:12px;margin-top:22px">Μπορείτε να αλλάξετε ποια email λαμβάνετε
      από το προφίλ σας.</p>
  </div></div>"""
    msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to])
    msg.attach_alternative(html, "text/html")
    return msg


def send_account_email(user, subject, body, url, cta):
    """Email λογαριασμού (επιβεβαίωση, κωδικός): στέλνεται πάντα."""
    try:
        build_email(user.email, subject, body, url, cta).send()
    except Exception:  # δεν σταματάμε τη ροή αν πέσει ο SMTP
        log.exception("Αποτυχία αποστολής email σε %s", user.email)


def notify(users, kind, title, body="", url="", cta="Άνοιγμα"):
    """Δημιουργεί ειδοποίηση για κάθε χρήστη και στέλνει email όπου επιτρέπεται."""
    users = [u for u in dict.fromkeys(users) if u is not None and u.is_active]
    if not users:
        return []
    created = Notification.objects.bulk_create(
        [Notification(user=u, kind=kind, title=title[:200], body=body, url=url) for u in users])
    to_email = [n for n, u in zip(created, users) if u.email_prefs.get(kind, True)]
    if to_email:
        try:
            with get_connection() as conn:
                for n in to_email:
                    msg = build_email(n.user.email, title, body, url, cta)
                    msg.connection = conn
                    msg.send()
            Notification.objects.filter(id__in=[n.id for n in to_email]).update(emailed=True)
        except Exception:
            log.exception("Αποτυχία αποστολής ειδοποιήσεων (%s)", kind)
    return created
