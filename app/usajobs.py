import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://data.usajobs.gov/api/Search"
RESULTS_PER_PAGE = 500
TIMEOUT_SECONDS = 30

CORRIDOR_TOWNS = [
    "Clatskanie, Oregon",
    "Rainier, Oregon",
    "Saint Helens, Oregon",
    "Scappoose, Oregon",
    "Vernonia, Oregon",
]

# Oregon + SW Washington, drawn generously; exact shape filtering happens in PostGIS.
REGION_BOUNDS = {"min_lat": 41.9, "max_lat": 47.5, "min_lon": -124.8, "max_lon": -116.4}


def headers():
    api_key = os.environ.get("USA_JOBS_API_KEY")
    user_agent = os.environ.get("USER_AGENT")
    if not api_key or not user_agent:
        raise RuntimeError("USA_JOBS_API_KEY and USER_AGENT must be set in .env")
    return {
        "Host": "data.usajobs.gov",
        "User-Agent": user_agent,
        "Authorization-Key": api_key,
    }


def search_location(location_name, keyword=None):
    items = []
    page = 1

    while True:
        params = {
            "LocationName": location_name,
            "ResultsPerPage": RESULTS_PER_PAGE,
            "Page": page,
        }
        if keyword:
            params["Keyword"] = keyword

        response = requests.get(API_URL, headers=headers(), params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        result = response.json()["SearchResult"]

        batch = result.get("SearchResultItems") or []
        items.extend(batch)

        total = int(result.get("SearchResultCountAll") or 0)
        if not batch or len(items) >= total:
            return items
        page += 1


def search(location_names=None, keyword=None):
    locations = location_names or CORRIDOR_TOWNS
    by_id = {}
    for location_name in locations:
        for item in search_location(location_name, keyword=keyword):
            by_id[item.get("MatchedObjectId")] = item
    return list(by_id.values())


def has_coordinates(location):
    latitude = location.get("Latitude")
    longitude = location.get("Longitude")
    if latitude is None or longitude is None:
        return False
    return not (latitude == 0 and longitude == 0)


def in_region(location):
    latitude = location.get("Latitude")
    longitude = location.get("Longitude")
    return (
        REGION_BOUNDS["min_lat"] <= latitude <= REGION_BOUNDS["max_lat"]
        and REGION_BOUNDS["min_lon"] <= longitude <= REGION_BOUNDS["max_lon"]
    )


def normalize(item):
    descriptor = item.get("MatchedObjectDescriptor") or {}
    pay = (descriptor.get("PositionRemuneration") or [{}])[0]
    details = (descriptor.get("UserArea") or {}).get("Details") or {}
    raw_locations = descriptor.get("PositionLocation") or []

    locations = [
        {
            "raw": location.get("LocationName"),
            "latitude": location.get("Latitude"),
            "longitude": location.get("Longitude"),
            "precision": "town",
        }
        for location in raw_locations
        if has_coordinates(location) and in_region(location)
    ]

    return {
        "source": "usajobs",
        "source_id": item.get("MatchedObjectId"),
        "title": descriptor.get("PositionTitle"),
        "employer_name": descriptor.get("OrganizationName"),
        "department": descriptor.get("DepartmentName"),
        "url": (descriptor.get("PositionURI") or "").replace(":443", ""),
        "date_posted": descriptor.get("PublicationStartDate"),
        "date_closes": descriptor.get("ApplicationCloseDate"),
        "employment_type": [
            name for s in descriptor.get("PositionSchedule") or [] if (name := (s.get("Name") or "").strip())
        ] or None,
        "salary_min": pay.get("MinimumRange"),
        "salary_max": pay.get("MaximumRange"),
        "salary_interval": pay.get("RateIntervalCode"),
        "description": details.get("JobSummary"),
        "locations": locations,
        "unplaced_locations": [
            location.get("LocationName") for location in raw_locations if not has_coordinates(location)
        ],
        "total_locations": len(raw_locations),
        "raw": item,
    }


def fetch_corridor_jobs():
    return [normalize(item) for item in search()]


if __name__ == "__main__":
    jobs = fetch_corridor_jobs()
    placed = [job for job in jobs if job["locations"]]
    location_count = sum(len(job["locations"]) for job in placed)

    print(f"{len(jobs)} unique jobs, {len(placed)} in region, {location_count} location rows")
    for job in placed[:10]:
        print(f"\n{job['title']} | {job['employer_name']}")
        print(f"  {len(job['locations'])} location(s): {[l['raw'] for l in job['locations']][:4]}")
        print(f"  {job['url']}")
