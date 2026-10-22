import requests

from app.ats import USER_AGENT
from app.text import html_to_text

API_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
TIMEOUT_SECONDS = 30


def fetch(token):
    response = requests.get(
        API_URL.format(token=token),
        params={"content": "true"},
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return [normalize(job, token) for job in response.json().get("jobs", [])]


def normalize(job, token):
    places = [(job.get("location") or {}).get("name")]
    places += [office.get("location") or office.get("name") for office in job.get("offices") or []]

    return {
        "source_id": f"{token}:{job['id']}",
        "title": job.get("title"),
        "description": html_to_text(job.get("content"), escaped=True),
        "url": job.get("absolute_url"),
        "date_posted": job.get("first_published") or job.get("updated_at"),
        "date_closes": job.get("application_deadline"),
        "employment_type": [],
        "places": [{"text": text} for text in dict.fromkeys(p for p in places if p)],
        "raw": job,
    }
