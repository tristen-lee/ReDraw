import json
import re

from app import places

SOURCE_LABELS = {"usajobs": "USAJOBS", "lever": "the employer's site", "direct": "the employer"}

# USAJobs rate interval codes. "WC" is without compensation, so it gets no salary.
SALARY_UNITS = {"PH": "HOUR", "PD": "DAY", "PW": "WEEK", "BW": "WEEK", "PM": "MONTH", "PA": "YEAR"}
SALARY_WORDS = {"HOUR": "an hour", "DAY": "a day", "WEEK": "a week", "MONTH": "a month", "YEAR": "a year"}

JOB_SQL = """
select j.id, j.source, j.source_id, j.title, j.description, j.url,
       j.employer_name_raw, j.date_posted, j.date_closes,
       j.salary_min, j.salary_max, j.salary_interval, j.is_blanket, j.status, j.expired_at
from jobs j
where j.id = %s
"""

LOCATIONS_SQL = """
select raw_location, precision, ST_Y(geom), ST_X(geom)
from job_locations where job_id = %s order by id
"""


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:80] or "job"


def money(value):
    return f"${value:,.0f}"


def display_date(value):
    # "%-d" is not portable to Windows, so the day is trimmed by hand.
    return f"{value.strftime('%b')} {value.day}, {value.year}" if value else None


def salary_text(minimum, maximum, interval):
    unit = SALARY_UNITS.get(interval)
    if not unit or minimum is None:
        return None
    per = SALARY_WORDS[unit]
    if maximum and maximum != minimum:
        return f"{money(minimum)} – {money(maximum)} {per}"
    return f"{money(minimum)} {per}"


def load(cur, job_id):
    cur.execute(JOB_SQL, (job_id,))
    row = cur.fetchone()
    if row is None:
        return None

    (
        id_, source, source_id, title, description, url,
        employer, date_posted, date_closes,
        salary_min, salary_max, salary_interval, is_blanket, status, expired_at,
    ) = row

    if status != "live" or expired_at is not None:
        return None

    cur.execute(LOCATIONS_SQL, (id_,))
    locations = cur.fetchall()
    if not locations:
        return None

    primary = locations[0]
    others = [l[0] for l in locations[1:4]]

    return {
        "id": id_,
        "source": source,
        "source_label": SOURCE_LABELS.get(source, source),
        "source_id": source_id,
        "title": title,
        "description": description or "",
        "meta_description": (description or title)[:155].replace("\n", " "),
        "url": url,
        "employer": employer or "Employer not listed",
        "date_posted": date_posted,
        "date_closes": date_closes,
        "date_posted_display": display_date(date_posted),
        "date_closes_display": display_date(date_closes),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_unit": SALARY_UNITS.get(salary_interval),
        "salary_text": salary_text(salary_min, salary_max, salary_interval),
        "is_blanket": is_blanket,
        "place": primary[0],
        "precision": primary[1],
        "latitude": primary[2],
        "longitude": primary[3],
        "locations": locations,
        "location_count": len(locations),
        "other_locations": others,
        "more_locations": max(0, len(locations) - 1 - len(others)) or None,
        "slug": slugify(f"{title} {primary[0]}"),
    }


def job_location_markup(raw_location, latitude, longitude):
    parsed = places.parse_location(raw_location)
    address = {"@type": "PostalAddress", "addressCountry": "US"}
    if parsed:
        address["addressLocality"], address["addressRegion"] = parsed
    else:
        address["addressLocality"] = raw_location

    return {
        "@type": "Place",
        "address": address,
        "geo": {"@type": "GeoCoordinates", "latitude": latitude, "longitude": longitude},
    }


def structured_data(job, canonical):
    # employmentType is deliberately omitted: the source field is free text, not
    # the enum schema.org expects, so emitting it would be invalid markup.
    data = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": job["title"],
        "description": job["description"],
        "identifier": {
            "@type": "PropertyValue",
            "name": job["employer"],
            "value": job["source_id"],
        },
        "hiringOrganization": {"@type": "Organization", "name": job["employer"]},
        "jobLocation": [
            job_location_markup(raw, lat, lon) for raw, _precision, lat, lon in job["locations"][:20]
        ],
        "directApply": False,
        "url": canonical,
    }

    if job["date_posted"]:
        data["datePosted"] = job["date_posted"].date().isoformat()
    if job["date_closes"]:
        data["validThrough"] = job["date_closes"].date().isoformat()
    if job["salary_unit"] and job["salary_min"] is not None:
        value = {"@type": "QuantitativeValue", "unitText": job["salary_unit"]}
        if job["salary_max"] and job["salary_max"] != job["salary_min"]:
            value["minValue"] = float(job["salary_min"])
            value["maxValue"] = float(job["salary_max"])
        else:
            value["value"] = float(job["salary_min"])
        data["baseSalary"] = {"@type": "MonetaryAmount", "currency": "USD", "value": value}

    return json.dumps(data, ensure_ascii=False)
