import re

from app import ashby, geocode, greenhouse, lever, markup, places
from app.ats import detect

REGION = ("OR", "WA")

# Platforms whose feed is keyed by a board token parsed out of the careers URL.
# "markup" reads schema.org JobPosting off the careers page itself.
ADAPTERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "markup": markup.fetch,
}

EMPLOYERS_SQL = """
select id, name, careers_url, town, state_code, street_address, ST_Y(geom), ST_X(geom)
from employers
where platform = %s and not opted_out and careers_url is not null
order by id
"""

HAS_STREET_NUMBER = re.compile(r"^\s*\d+[A-Za-z]?\s+\S")


def load(cur, platform):
    cur.execute(EMPLOYERS_SQL, (platform,))
    return [
        {
            "id": row[0], "name": row[1], "careers_url": row[2], "town": row[3], "state": row[4],
            "street_address": row[5], "latitude": row[6], "longitude": row[7],
        }
        for row in cur.fetchall()
    ]


def board_token(employer, platform):
    if platform == "markup":
        return employer["careers_url"]
    found = detect(employer["careers_url"])
    if not found or found["platform"] != platform:
        raise ValueError(f"{employer['careers_url']} doesn't look like a {platform} board")
    return found["token"]


class Locator:
    def __init__(self, cur):
        self.cur = cur
        self.towns = {}
        self.addresses = {}

    def street(self, street_address, town, state):
        key = f"{street_address}, {town}, {state}"
        if key not in self.addresses:
            try:
                self.addresses[key] = geocode.geocode_address(key)
            except Exception:
                self.addresses[key] = None
        return self.addresses[key]

    def locate(self, place, employer):
        parsed = places.parse_location(place.get("text"))
        if not parsed or parsed[1] not in REGION:
            return None
        town, state = parsed

        # A single-site employer we've placed by hand: their jobs in that town
        # are at that address, not floating over the town.
        if (employer["latitude"] is not None and employer["town"]
                and employer["town"].lower() == town.lower() and employer["state"] == state):
            return {
                "raw": f"{employer['street_address']}, {town}, {state}" if employer["street_address"] else f"{town}, {state}",
                "precision": "exact",
                "latitude": employer["latitude"],
                "longitude": employer["longitude"],
            }

        street = place.get("street_address")
        if street and HAS_STREET_NUMBER.match(street):
            match = self.street(street, town, state)
            if match:
                return {"raw": match["matched_address"], "precision": "exact",
                        "latitude": match["latitude"], "longitude": match["longitude"]}

        resolved = places.resolve(self.cur, f"{town}, {state}", self.towns)
        if resolved:
            return {"raw": f"{town}, {state}", "precision": "town",
                    "latitude": resolved["latitude"], "longitude": resolved["longitude"]}
        return None


def collect(cur, platform):
    locator = Locator(cur)
    jobs, failed = [], []
    roster = load(cur, platform)

    for employer in roster:
        try:
            token = board_token(employer, platform)
            postings = ADAPTERS[platform](token)
        except Exception as exc:
            failed.append({"employer_id": employer["id"], "name": employer["name"],
                           "error": f"{type(exc).__name__}: {exc}"[:300]})
            continue

        for posting in postings:
            if posting.get("is_remote") or not posting.get("title"):
                continue
            located = [locator.locate(place, employer) for place in posting["places"]]
            located = list({(l["latitude"], l["longitude"]): l for l in located if l}.values())
            if not located:
                continue
            jobs.append({
                **posting,
                "source": platform,
                "employer_id": employer["id"],
                "employer_name": employer["name"],
                "locations": located,
                "total_locations": len(located),
            })

    return {"jobs": jobs, "failed": failed, "employers": len(roster)}
