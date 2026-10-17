import time
from datetime import datetime, timezone

import requests

API_URL = "https://api.lever.co/v0/postings/{site}"
PAGE_SIZE = 100
TIMEOUT_SECONDS = 30
DELAY_SECONDS = 1


def headers():
    return {"User-Agent": "ReDraw/0.1 (tristen.lee1221@gmail.com)"}


def site_exists(site):
    response = requests.get(
        API_URL.format(site=site),
        params={"mode": "json", "limit": 1},
        headers=headers(),
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code == 200:
        return isinstance(response.json(), list)
    return False


def fetch_site(site):
    postings = []
    skip = 0

    while True:
        response = requests.get(
            API_URL.format(site=site),
            params={"mode": "json", "skip": skip, "limit": PAGE_SIZE},
            headers=headers(),
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list) or not batch:
            return postings

        postings.extend(batch)
        if len(batch) < PAGE_SIZE:
            return postings

        skip += PAGE_SIZE
        time.sleep(DELAY_SECONDS)


def epoch_ms_to_iso(value):
    if not value:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def normalize(posting, site, employer_name=None):
    categories = posting.get("categories") or {}
    location = categories.get("location")

    return {
        "source": "lever",
        "source_id": f"{site}:{posting.get('id')}",
        "employer_name": employer_name or site,
        "title": posting.get("text"),
        "description": posting.get("descriptionPlain") or posting.get("description"),
        "url": posting.get("hostedUrl") or posting.get("applyUrl"),
        "date_posted": epoch_ms_to_iso(posting.get("createdAt")),
        "date_closes": None,
        "employment_type": [c for c in [categories.get("commitment")] if c],
        "salary_min": None,
        "salary_max": None,
        "salary_interval": None,
        "workplace_type": posting.get("workplaceType"),
        "location_text": location,
        "total_locations": 1 if location else 0,
        "raw": posting,
    }


def fetch_jobs(sites):
    jobs = []
    for entry in sites:
        site, employer_name = entry if isinstance(entry, tuple) else (entry, None)
        for posting in fetch_site(site):
            jobs.append(normalize(posting, site, employer_name))
        time.sleep(DELAY_SECONDS)
    return jobs
