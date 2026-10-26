import re
import time
from datetime import datetime

import requests

from app.ats import USER_AGENT
from app.text import html_to_text

SITE_URL = "https://{token}.applicantpro.com"
TIMEOUT_SECONDS = 30
DELAY_SECONDS = 1
DOMAIN_ID = re.compile(r"domain_id\s*=\s*'(\d+)'")


def get(session, url, **params):
    response = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    time.sleep(DELAY_SECONDS)
    return response


# The listings endpoint is keyed by a numeric site id that only appears in
# the public jobs page, so that page is read first.
def fetch(token):
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    base = SITE_URL.format(token=token)

    match = DOMAIN_ID.search(get(session, f"{base}/jobs/").text)
    if not match:
        raise ValueError(f"no site id on {base}/jobs/")
    domain_id = match.group(1)

    listing = get(session, f"{base}/core/jobs/{domain_id}", getParams='{"isInternal":0}').json()
    if not listing.get("success"):
        raise ValueError(f"listing request for {token} was refused")

    jobs = []
    for job in listing["data"]["jobs"] or []:
        detail = get(session, f"{base}/core/jobs/{domain_id}/{job['id']}/job-details").json().get("data") or {}
        # Employers can keep a posting off outside job boards; we count as one.
        if detail.get("hideFromIndeed"):
            continue
        jobs.append(normalize(job, detail, token))
    return jobs


def parse_date(value):
    for pattern in ("%B %d, %Y", "%b %d, %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date().isoformat()
        except (AttributeError, ValueError):
            continue
    return None


def normalize(job, detail, token):
    town, state = job.get("city"), job.get("abbreviation")
    return {
        "source_id": f"{token}:{job['id']}",
        "title": (job.get("title") or "").strip(),
        "description": html_to_text(detail.get("description") or detail.get("advertisingDescriptionHtml")),
        "url": job.get("jobUrl"),
        "date_posted": parse_date(job.get("startDateRef")),
        "date_closes": None if job.get("untilFilled") else parse_date(job.get("endDateRef")),
        "employment_type": [job["employmentType"]] if job.get("employmentType") else [],
        "is_remote": job.get("workplaceType") == "Remote",
        "places": [{
            "text": f"{town}, {state}" if town and state else job.get("jobLocation"),
            "street_address": job.get("streetAddress") or None,
        }],
        "raw": {"listing": job, "detail": detail},
    }
