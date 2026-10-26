import csv
import json
import pathlib
import sys

from app import db

ROOT = pathlib.Path(__file__).parent.parent
SOURCE = ROOT / "data" / "town_labels.csv"
OUTPUT = ROOT / "static" / "towns.geojson"


# The basemap only names small towns once you're zoomed well in, which hides
# exactly the places this site is for. The map draws these itself instead.
# Rank 1 shows at every zoom; rank 2 once the region fills the screen. "until"
# is the zoom where the basemap starts naming the town itself, so the label
# steps aside there instead of printing twice. "side" puts the name left or
# right of the dot, for the few that land on a basemap label. Retune both when
# the basemap changes.
def main():
    rows = list(csv.DictReader(open(SOURCE, encoding="utf-8")))
    features, missing = [], []
    with db.connect() as conn, conn.cursor() as cur:
        for row in rows:
            cur.execute(
                "select ST_X(geom), ST_Y(geom) from places where lower(name) = lower(%s) and state_code = %s limit 1",
                (row["name"], row["state"]),
            )
            found = cur.fetchone()
            if not found:
                missing.append(f"{row['name']}, {row['state']}")
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(found[0], 5), round(found[1], 5)]},
                "properties": {"name": row["name"], "rank": int(row["rank"]), "until": float(row["until"]), "side": row["side"]},
            })

    OUTPUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    print(f"wrote {len(features)} towns to {OUTPUT.name}")
    if missing:
        sys.exit("not in the places table: " + "; ".join(missing))


if __name__ == "__main__":
    main()
