import csv
import io
import sys
import zipfile

import requests

from app import db

YEAR = 2026
URL = f"https://www2.census.gov/geo/docs/maps-data/data/gazetteer/{YEAR}_Gazetteer/{YEAR}_Gaz_place_national.zip"

# Gazetteer NAME carries the legal type ("Portland city"). Sources give us bare
# town names, so one trailing type word gets stripped for matching.
TYPE_SUFFIXES = (
    "city",
    "town",
    "village",
    "borough",
    "municipality",
    "township",
    "CDP",
    "comunidad",
    "zona urbana",
    "plantation",
    "reservation",
    "government",
    "county",
)


def strip_type_suffix(name):
    lowered = name.lower()
    for suffix in TYPE_SUFFIXES:
        if lowered.endswith(" " + suffix.lower()):
            return name[: -(len(suffix) + 1)].strip()
    return name


def fetch_rows():
    response = requests.get(URL, timeout=180)
    response.raise_for_status()

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    name = archive.namelist()[0]
    text = archive.read(name).decode("latin-1")

    for row in csv.DictReader(io.StringIO(text), delimiter="|"):
        clean = {key.strip(): (value.strip() if value else value) for key, value in row.items()}
        lat, lon = clean.get("INTPTLAT"), clean.get("INTPTLONG")
        if not lat or not lon:
            continue
        yield (
            clean["GEOID"],
            strip_type_suffix(clean["NAME"]),
            clean["USPS"],
            float(lon),
            float(lat),
        )


def main():
    states = {s.upper() for s in sys.argv[1:]}
    rows = [r for r in fetch_rows() if not states or r[2] in states]
    if not rows:
        sys.exit("no rows matched")

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create temp table places_staging (
                    geoid text, name text, state_code char(2), lon double precision, lat double precision
                ) on commit drop
                """
            )
            with cur.copy("copy places_staging (geoid, name, state_code, lon, lat) from stdin") as copy:
                for row in rows:
                    copy.write_row(row)

            cur.execute(
                """
                insert into places (geoid, name, state_code, geom)
                select geoid, name, state_code, ST_SetSRID(ST_MakePoint(lon, lat), 4326)
                from places_staging
                on conflict (geoid) do update set
                    name = excluded.name,
                    state_code = excluded.state_code,
                    geom = excluded.geom
                """
            )
            loaded = cur.rowcount
        conn.commit()

    print(f"loaded {loaded} places from {YEAR} gazetteer" + (f" ({', '.join(sorted(states))})" if states else ""))


if __name__ == "__main__":
    main()
