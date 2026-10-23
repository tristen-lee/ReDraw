import csv
import pathlib
import sys

from app import db, geocode
from app.ats import detect, inspect
from app.employers import ADAPTERS
from app.pages import slugify

SEED_FILE = pathlib.Path(__file__).parent.parent / "data" / "employers.csv"

UPSERT = """
insert into employers (name, slug, careers_url, platform, town, state_code, street_address, geom, notes)
values (%(name)s, %(slug)s, %(careers_url)s, %(platform)s, %(town)s, %(state)s, %(street_address)s,
        case when %(longitude)s::float is null then null
             else ST_SetSRID(ST_MakePoint(%(longitude)s::float, %(latitude)s::float), 4326) end,
        %(notes)s)
on conflict (slug) do update set
    name = excluded.name,
    careers_url = excluded.careers_url,
    platform = excluded.platform,
    town = excluded.town,
    state_code = excluded.state_code,
    street_address = excluded.street_address,
    geom = coalesce(excluded.geom, employers.geom),
    notes = excluded.notes,
    updated_at = now()
"""


BOARD_URLS = {
    "greenhouse": "https://boards.greenhouse.io/{}",
    "lever": "https://jobs.lever.co/{}",
    "ashby": "https://jobs.ashbyhq.com/{}",
    "smartrecruiters": "https://careers.smartrecruiters.com/{}",
}


# Takes whatever careers URL is in the sheet. If it isn't a board URL itself,
# the page is opened to find a board embedded or linked from it. A platform
# with no adapter yet (Workday, iCIMS...) is still recorded for later.
def platform_for(url):
    found = detect(url) or inspect(url)
    if found.get("platform"):
        board = BOARD_URLS.get(found["platform"])
        return found["platform"], board.format(found["token"]) if board else url, None
    if found.get("status") != 200:
        return "markup", url, f"site answered {found.get('status') or found.get('error')}; paste the job board link instead"
    return "markup", url, None


def main(path=SEED_FILE):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    with db.connect() as conn, conn.cursor() as cur:
        for row in rows:
            row = {k: (v or "").strip() or None for k, v in row.items()}
            point = None
            if row.get("street_address") and row.get("town"):
                point = geocode.geocode_address(f"{row['street_address']}, {row['town']}, {row['state']}")
            platform, careers_url, problem = platform_for(row["careers_url"])
            cur.execute(UPSERT, {
                **row,
                "careers_url": careers_url,
                "slug": slugify(row["name"]),
                "platform": platform,
                "latitude": point and point["latitude"],
                "longitude": point and point["longitude"],
            })
            flag = "" if platform in ADAPTERS else "  (no adapter yet)"
            missed = "  (address not found)" if row.get("street_address") and not point else ""
            print(f"{platform:16} {row['name']}{flag}{missed}{f'  ({problem})' if problem else ''}")
        conn.commit()
    print(f"seeded {len(rows)} employer(s)")


if __name__ == "__main__":
    main(*sys.argv[1:])
