import requests

from app.ats import USER_AGENT

API_URL = "https://api.ashbyhq.com/posting-api/job-board/{token}"
TIMEOUT_SECONDS = 30


def fetch(token):
    response = requests.get(
        API_URL.format(token=token),
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return [normalize(job, token) for job in response.json().get("jobs", []) if job.get("isListed", True)]


def place(entry):
    postal = (entry.get("address") or {}).get("postalAddress") or {}
    town, region = postal.get("addressLocality"), postal.get("addressRegion")
    return {
        "text": f"{town}, {region}" if town and region else entry.get("location"),
        "street_address": postal.get("streetAddress"),
    }


def normalize(job, token):
    return {
        "source_id": f"{token}:{job['id']}",
        "title": job.get("title"),
        "description": job.get("descriptionPlain") or "",
        "url": job.get("jobUrl"),
        "date_posted": job.get("publishedAt"),
        "date_closes": None,
        "employment_type": [job["employmentType"]] if job.get("employmentType") else [],
        "is_remote": job.get("workplaceType") == "Remote",
        "places": [place(job)] + [place(entry) for entry in job.get("secondaryLocations") or []],
        "raw": job,
    }
