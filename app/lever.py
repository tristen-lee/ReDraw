import re
import time
from datetime import datetime, timezone

import requests

from app.ats import USER_AGENT
from app.text import html_to_text

API_URL = "https://api.lever.co/v0/postings/{token}"
PAGE_SIZE = 100
TIMEOUT_SECONDS = 30
DELAY_SECONDS = 1


def fetch(token):
    postings, skip = [], 0
    while True:
        response = requests.get(
            API_URL.format(token=token),
            params={"mode": "json", "skip": skip, "limit": PAGE_SIZE},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list) or not batch:
            break
        postings.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
        time.sleep(DELAY_SECONDS)
    return [normalize(posting, token) for posting in postings]


def epoch_ms_to_iso(value):
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat() if value else None


def description(posting):
    parts = [posting.get("descriptionPlain") or ""]
    for section in posting.get("lists") or []:
        parts.append(f"{section.get('text', '')}\n{html_to_text(section.get('content'))}")
    parts.append(posting.get("additionalPlain") or "")
    text = "\n\n".join(part.strip() for part in parts if part and part.strip())
    return re.sub(r"\n\s*\n\s*", "\n\n", text)


def normalize(posting, token):
    categories = posting.get("categories") or {}
    places = [categories.get("location")] + list(categories.get("allLocations") or [])
    return {
        "source_id": f"{token}:{posting.get('id')}",
        "title": posting.get("text"),
        "description": description(posting),
        "url": posting.get("hostedUrl") or posting.get("applyUrl"),
        "date_posted": epoch_ms_to_iso(posting.get("createdAt")),
        "date_closes": None,
        "employment_type": [categories["commitment"]] if categories.get("commitment") else [],
        "is_remote": posting.get("workplaceType") == "remote",
        "places": [{"text": text} for text in dict.fromkeys(p for p in places if p)],
        "raw": posting,
    }
