import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

# uvicorn's logger is the one Render shows at INFO, so sends are visible too.
log = logging.getLogger("uvicorn.error")

TIMEOUT_SECONDS = 20


def configured():
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


# Never raises: a mail outage shouldn't fail a posting or an ingest run.
def send(to, subject, body):
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

    try:
        with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.zoho.com"), 465, timeout=TIMEOUT_SECONDS) as smtp:
            smtp.login(sender, os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
        log.info("mail sent to %s: %s", to, subject)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        log.error("mail to %s failed: %s", to, exc)
        return False


def notify_owner(subject, body):
    return send(os.environ.get("ALERT_EMAIL") or os.environ.get("SMTP_USER", ""), subject, body)


def posting_received(to, title, employer, manage_url, placed):
    where = (
        "We found the address and it'll go on the map once it's reviewed."
        if placed else
        "We couldn't match the address automatically, so we'll place it by hand during review."
    )
    send(
        to,
        f"Your Cupholder posting: {title}",
        f"""Thanks for posting {title} at {employer}.

{where}

This link lets you renew the posting or take it down once the job's filled. It's the only key to your posting, so keep it:

{manage_url}

Postings stay up 30 days after they go live. Questions, just reply to this email.

Tristen
Cupholder
""",
    )


def new_submission(site, title, employer, placed):
    notify_owner(
        f"New post to review: {title}",
        f"""{employer} posted {title}.{'' if placed else ' The address needs placing by hand.'}

{site}/admin.html
""",
    )
