import requests

ONELINE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
BENCHMARK = "Public_AR_Current"
TIMEOUT_SECONDS = 30


def geocode_address(address):
    if not address or not address.strip():
        return None

    response = requests.get(
        ONELINE_URL,
        params={"address": address, "benchmark": BENCHMARK, "format": "json"},
        headers={"User-Agent": "Cupholder/0.1 (+https://cupholder.work)"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    matches = (response.json().get("result") or {}).get("addressMatches") or []
    if not matches:
        return None

    match = matches[0]
    coordinates = match.get("coordinates") or {}
    if coordinates.get("x") is None or coordinates.get("y") is None:
        return None

    return {
        "latitude": coordinates["y"],
        "longitude": coordinates["x"],
        "matched_address": match.get("matchedAddress"),
        "precision": "exact",
    }
