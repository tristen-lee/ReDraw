import json
import time

import requests

from app import ats

DELAY_SECONDS = 1.5
PATHS = ("/careers", "/jobs")

EMPLOYERS = [
    ("Nike", "nike.com"),
    ("Intel", "intel.com"),
    ("Columbia Sportswear", "columbia.com"),
    ("Adidas America", "adidas-group.com"),
    ("Daimler Truck North America", "daimlertruck.com"),
    ("Providence Health", "providence.org"),
    ("OHSU", "ohsu.edu"),
    ("Legacy Health", "legacyhealth.org"),
    ("Kaiser Permanente NW", "kaiserpermanente.org"),
    ("Cambia Health Solutions", "cambiahealth.com"),
    ("Moda Health", "modahealth.com"),
    ("Vacasa", "vacasa.com"),
    ("Jama Software", "jamasoftware.com"),
    ("Puppet", "puppet.com"),
    ("New Relic", "newrelic.com"),
    ("Smarsh", "smarsh.com"),
    ("Act-On Software", "act-on.com"),
    ("Lytics", "lytics.com"),
    ("Opal", "workwithopal.com"),
    ("Thesis", "thesisagency.com"),
    ("CLEAResult", "clearesult.com"),
    ("Expensify", "expensify.com"),
    ("Trimble Viewpoint", "viewpoint.com"),
    ("Umpqua Bank", "umpquabank.com"),
    ("Radius Recycling", "radiusrecycling.com"),
    ("Precision Castparts", "precast.com"),
    ("Leatherman", "leatherman.com"),
    ("Powell's Books", "powells.com"),
    ("Port of Portland", "portofportland.com"),
    ("TriMet", "trimet.org"),
    ("City of Portland", "portland.gov"),
    ("Multnomah County", "multco.us"),
    ("Portland State University", "pdx.edu"),
    ("Dutch Bros", "dutchbros.com"),
    ("Tillamook", "tillamook.com"),
    ("Bonneville Power Administration", "bpa.gov"),
    ("Zoomcare", "zoomcare.com"),
    ("Ruby Receptionists", "ruby.com"),
]


def probe(session, name, domain):
    base = f"https://{domain}"
    for path in PATHS:
        url = base + path
        result = ats.inspect(url, session=session)
        time.sleep(DELAY_SECONDS)
        if result.get("platform"):
            return {"employer": name, "domain": domain, **result}
        if result.get("status") == 200:
            last = result
    return {"employer": name, "domain": domain, "platform": None}


def main():
    session = requests.Session()
    session.headers["User-Agent"] = ats.USER_AGENT

    results = []
    for name, domain in EMPLOYERS:
        row = probe(session, name, domain)
        results.append(row)
        platform = row.get("platform") or "-"
        token = row.get("token") or ""
        print(f"{name:32} {platform:16} {token}")

    print()
    by_platform = {}
    for row in results:
        by_platform.setdefault(row.get("platform") or "none", []).append(row["employer"])
    for platform, names in sorted(by_platform.items(), key=lambda kv: -len(kv[1])):
        print(f"{platform:16} {len(names):3}  {', '.join(names[:6])}")

    with open("ats_discovery.json", "w") as handle:
        json.dump(results, handle, indent=2)


if __name__ == "__main__":
    main()
