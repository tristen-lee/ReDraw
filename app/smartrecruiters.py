import time

import requests

from app.ats import USER_AGENT
from app.text import html_to_text

API_URL = "https://api.smartrecruiters.com/v1/companies/{token}/postings"
PAGE_SIZE = 100
TIMEOUT_SECONDS = 30
DELAY_SECONDS = 0.5
SECTIONS = ("jobDescription", "qualifications", "additionalInformation")


def get(url, **params):
    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


# The listing has locations but no description, so detail pages are only
# fetched for postings that land in the region.
def fetch(token, wanted=None):
    postings, offset = [], 0
    while True:
        page = get(API_URL.format(token=token), country="us", limit=PAGE_SIZE, offset=offset)
        postings.extend(page.get("content", []))
        offset += PAGE_SIZE
        if offset >= page.get("totalFound", 0):
            break
        time.sleep(DELAY_SECONDS)

    jobs = []
    for posting in postings:
        job = normalize(posting, token)
        if wanted and not wanted(job):
            continue
        time.sleep(DELAY_SECONDS)
        detail = get(posting["ref"])
        sections = (detail.get("jobAd") or {}).get("sections") or {}
        job["description"] = "\n\n".join(
            f"{sections[key].get('title') or ''}\n{html_to_text(sections[key].get('text'))}".strip()
            for key in SECTIONS if sections.get(key, {}).get("text")
        )
        job["url"] = detail.get("postingUrl") or job["url"]
        job["raw"] = detail
        jobs.append(job)
    return jobs


def normalize(posting, token):
    location = posting.get("location") or {}
    city, region = location.get("city"), location.get("region")
    employment = (posting.get("typeOfEmployment") or {}).get("label")
    return {
        "source_id": f"{token}:{posting['id']}",
        "title": posting.get("name"),
        "description": "",
        "url": f"https://jobs.smartrecruiters.com/{token}/{posting['id']}",
        "date_posted": posting.get("releasedDate"),
        "date_closes": None,
        "employment_type": [employment] if employment else [],
        "is_remote": bool(location.get("remote")),
        # Their latitude/longitude is left alone: we don't know its license,
        # so the street address goes through our own geocoder instead.
        "places": [{"text": f"{city}, {region}" if city and region else None,
                    "street_address": location.get("address")}],
        "raw": posting,
    }
