import csv
import pathlib
import sys

from app import db, geocode
from app.ats import detect
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


# A careers URL on a platform we have no adapter for (Workday, iCIMS...) is
# still recorded, so the row is there when an adapter or permission comes.
def platform_for(url):
    found = detect(url)
    if found:
        return found["platform"]
    return "markup"


def main(path=SEED_FILE):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    with db.connect() as conn, conn.cursor() as cur:
        for row in rows:
            row = {k: (v or "").strip() or None for k, v in row.items()}
            point = None
            if row.get("street_address") and row.get("town"):
                point = geocode.geocode_address(f"{row['street_address']}, {row['town']}, {row['state']}")
            platform = platform_for(row["careers_url"])
            cur.execute(UPSERT, {
                **row,
                "slug": slugify(row["name"]),
                "platform": platform,
                "latitude": point and point["latitude"],
                "longitude": point and point["longitude"],
            })
            flag = "" if platform in ADAPTERS else "  (no adapter yet)"
            missed = "  (address not found)" if row.get("street_address") and not point else ""
            print(f"{platform:16} {row['name']}{flag}{missed}")
        conn.commit()
    print(f"seeded {len(rows)} employer(s)")


if __name__ == "__main__":
    main(*sys.argv[1:])
