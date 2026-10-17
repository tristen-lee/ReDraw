import re

STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "puerto rico": "PR",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

COUNTRY_NOISE = {"united states", "united states of america", "usa", "us", "u.s.", "u.s.a."}
REMOTE_MARKERS = ("remote", "anywhere", "work from home", "distributed", "virtual")

LOOKUP_SQL = """
select id, ST_X(geom), ST_Y(geom)
from places
where lower(name) = lower(%s) and state_code = %s
limit 1
"""


def is_remote(text):
    return bool(text) and any(marker in text.lower() for marker in REMOTE_MARKERS)


def parse_location(text):
    if not text:
        return None

    # A named town wins over a remote marker: "Portland, OR (Remote)" is a
    # Portland job as far as the employer is concerned. Bare "Remote" isn't.
    cleaned = re.sub(r"\([^)]*\)", " ", text)

    # "Portland, OR / Hillsboro, OR" and "Portland, OR; Seattle, WA" -> first only.
    head = re.split(r"\s*[/;|]\s*", cleaned.strip())[0]
    parts = [p.strip(" -–—\t") for p in head.split(",")]
    parts = [p for p in parts if p and p.lower() not in COUNTRY_NOISE]

    if len(parts) < 2:
        return None

    town, state_raw = parts[0], parts[1]
    state_raw = re.split(r"\s+[-–—]\s+", state_raw)[0]
    state_raw = re.sub(r"\s+\d{5}(-\d{4})?$", "", state_raw).strip()

    if len(state_raw) == 2 and state_raw.isalpha():
        state_code = state_raw.upper()
    else:
        state_code = STATE_CODES.get(state_raw.lower())

    if not state_code or not town:
        return None
    return town, state_code


def resolve(cur, text, cache=None):
    parsed = parse_location(text)
    if not parsed:
        return None

    if cache is not None and parsed in cache:
        return cache[parsed]

    cur.execute(LOOKUP_SQL, parsed)
    row = cur.fetchone()
    result = (
        {"place_id": row[0], "longitude": row[1], "latitude": row[2], "precision": "town"}
        if row
        else None
    )

    if cache is not None:
        cache[parsed] = result
    return result
