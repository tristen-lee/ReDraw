import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20

# The site's palette. Mail clients ignore stylesheets, so it all goes inline.
BG = "#171513"
TEXT = "#F0EBE0"
MUTED = "#9C9389"
BRAND = "#E09B3D"
FONT = "'Public Sans', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


def configured():
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def layout(paragraphs, button=None, footnote=None):
    body = "".join(
        f'<p style="margin:0 0 16px;font-size:16px;line-height:1.5;color:{TEXT};">{p}</p>' for p in paragraphs
    )
    if button:
        label, url = button
        body += (
            f'<p style="margin:24px 0;"><a href="{escape(url)}" style="display:inline-block;padding:12px 20px;'
            f'background:{BRAND};color:{BG};font-weight:700;text-decoration:none;border-radius:6px;">{escape(label)}</a></p>'
            f'<p style="margin:0 0 16px;font-size:13px;line-height:1.5;color:{MUTED};word-break:break-all;">{escape(url)}</p>'
        )
    if footnote:
        body += f'<p style="margin:24px 0 0;font-size:14px;line-height:1.5;color:{MUTED};">{footnote}</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="color-scheme" content="dark">
<meta name="supported-color-schemes" content="dark">
</head>
<body style="margin:0;padding:0;background:{BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;font-family:{FONT};">
<tr><td style="padding-bottom:24px;font-size:22px;letter-spacing:-0.3px;color:{TEXT};">Cup<span style="color:{BRAND};">H</span>older</td></tr>
<tr><td>{body}</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


# Never raises: a mail outage shouldn't fail a posting or an ingest run.
def send(to, subject, body, html=None):
    if not configured():
        log.warning("SMTP not configured; skipped mail to %s: %s", to, subject)
        return False

    sender = os.environ["SMTP_USER"]
    message = EmailMessage()
    message["From"] = formataddr(("Cupholder", sender))
    message["To"] = to
    message["Reply-To"] = sender
    message["Subject"] = subject
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.zoho.com"), 465, timeout=TIMEOUT_SECONDS) as smtp:
            smtp.login(sender, os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        log.error("mail to %s failed: %s", to, exc)
        return False


def notify_owner(subject, body, html=None):
    return send(os.environ.get("ALERT_EMAIL") or os.environ.get("SMTP_USER", ""), subject, body, html)


def posting_received(to, title, employer, manage_url, placed):
    where = (
        "We found the address and it'll go on the map once it's reviewed."
        if placed else
        "We couldn't match the address automatically, so we'll place it by hand during review."
    )
    keep = "This link lets you renew the posting or take it down once the job's filled. It's the only key to your posting, so keep it."
    send(
        to,
        f"Your Cupholder posting: {title}",
        f"""Thanks for posting {title} at {employer}.

{where}

{keep}

{manage_url}

Postings stay up 30 days after they go live. Questions, just reply to this email.

Tristen
Cupholder
""",
        layout(
            [f"Thanks for posting <strong>{escape(title)}</strong> at {escape(employer)}.", where, keep],
            button=("Manage your posting", manage_url),
            footnote="Postings stay up 30 days after they go live. Questions, just reply to this email.<br><br>Tristen<br>Cupholder",
        ),
    )


def new_submission(site, title, employer, placed):
    needs = "" if placed else " The address needs placing by hand."
    notify_owner(
        f"New post to review: {title}",
        f"{employer} posted {title}.{needs}\n\n{site}/admin.html\n",
        layout(
            [f"{escape(employer)} posted <strong>{escape(title)}</strong>.{needs}"],
            button=("Open the review queue", f"{site}/admin.html"),
        ),
    )
