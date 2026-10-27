import requests

from app.ats import USER_AGENT
from app.text import html_to_text

API_URL = "https://{token}.recruitee.com/api/offers/"
TIMEOUT_SECONDS = 30

# Recruitee starts requiring a per-company token on this endpoint on
# 2027-02-10. Past that date each employer has to issue us one.
SALARY_UNITS = {"hour": "PH", "day": "PD", "week": "PW", "month": "PM", "year": "PA"}


def fetch(token):
    response = requests.get(API_URL.format(token=token), headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return [normalize(offer, token) for offer in response.json().get("offers", [])]


def place(location, offer):
    english = (location.get("translations") or {}).get("en") or {}
    town = (english.get("city") or location.get("city") or offer.get("city") or "").strip()
    state = location.get("state_code") or offer.get("state_code") or location.get("state")
    return {
        "text": f"{town}, {state}" if town and state else None,
        "street_address": (english.get("street") or "").strip() or None,
    }


def money(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def normalize(offer, token):
    salary = offer.get("salary") or {}
    locations = offer.get("locations") or [{}]
    description = "\n\n".join(
        text for text in (html_to_text(offer.get("description")), html_to_text(offer.get("requirements"))) if text
    )
    return {
        "source_id": f"{token}:{offer['id']}",
        "title": (offer.get("title") or "").strip(),
        "description": description,
        "url": offer.get("careers_url"),
        "date_posted": (offer.get("published_at") or "").replace(" UTC", "+00:00") or None,
        "date_closes": offer.get("close_at"),
        "employment_type": [offer["employment_type_code"]] if offer.get("employment_type_code") else [],
        "salary_min": money(salary.get("min")),
        "salary_max": money(salary.get("max")),
        "salary_interval": SALARY_UNITS.get(salary.get("period")),
        "is_remote": bool(offer.get("remote")) and not offer.get("on_site"),
        "places": [place(location, offer) for location in locations],
        "raw": offer,
    }
