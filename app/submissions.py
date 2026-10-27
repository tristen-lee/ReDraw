import uuid

import requests

from app import geocode, moderation

INSERT_JOB = """
insert into jobs (
    source, source_id, employer_name_raw, title, description, url,
    contact_email, submitted_by, status, employment_type, submitted_address, manage_token_hash
)
values (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s)
returning id
"""

INSERT_LOCATION = """
insert into job_locations (job_id, raw_location, precision, geom)
values (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
"""


# Direct posts are exact or they don't go live. An address the geocoder misses
# still gets submitted, and waits in the review queue for a hand placement.
# Kept short: a slow lookup holds a server worker, and the form is public.
SUBMIT_GEOCODE_TIMEOUT = 10
MAX_PENDING = 200


def locate(address, timeout=geocode.TIMEOUT_SECONDS):
    try:
        match = geocode.geocode_address(address, timeout)
    except requests.RequestException:
        return None
    if match is None:
        return None
    return {
        # What the employer typed reads better than the geocoder's all-caps match.
        "raw": address,
        "precision": "exact",
        "latitude": match["latitude"],
        "longitude": match["longitude"],
    }


def save_location(cur, job_id, location):
    cur.execute("delete from job_locations where job_id = %s", (job_id,))
    cur.execute(
        INSERT_LOCATION,
        (job_id, location["raw"], location["precision"], location["longitude"], location["latitude"]),
    )


def submit(cur, payload):
    cur.execute("select count(*) from jobs where status = 'pending'")
    if cur.fetchone()[0] >= MAX_PENDING:
        return None, "We're behind on reviewing posts. Try again tomorrow, or email tristen@cupholder.work."

    address = f"{payload.street_address.strip()}, {payload.town.strip()}"
    location = locate(address, SUBMIT_GEOCODE_TIMEOUT)
    token, token_hash = moderation.new_manage_token()

    cur.execute(
        INSERT_JOB,
        (
            "direct",
            f"direct:{uuid.uuid4()}",
            payload.employer,
            payload.title,
            payload.description,
            payload.apply_url,
            payload.contact_email,
            payload.contact_email,
            payload.employment_type or None,
            address,
            token_hash,
        ),
    )
    job_id = cur.fetchone()[0]

    if location:
        save_location(cur, job_id, location)

    return {"job_id": job_id, "location": location, "manage_token": token}, None


def place(cur, job_id, address=None, latitude=None, longitude=None):
    cur.execute("select submitted_address from jobs where id = %s and status = 'pending'", (job_id,))
    row = cur.fetchone()
    if row is None:
        return None, "No pending job with that id."

    if address:
        location = locate(address)
        if location is None:
            return None, "The geocoder couldn't find that one either. Paste coordinates instead."
    else:
        location = {
            "raw": row[0] or "Placed by hand",
            "precision": "exact",
            "latitude": latitude,
            "longitude": longitude,
        }

    save_location(cur, job_id, location)
    return location, None


def list_pending(cur, limit=100):
    cur.execute(
        """
        select j.id, j.employer_name_raw, j.title, j.contact_email, j.first_seen_at,
               l.raw_location, l.precision, j.url, j.submitted_address
        from jobs j
        left join job_locations l on l.job_id = j.id
        where j.status = 'pending'
        order by j.first_seen_at desc
        limit %s
        """,
        (limit,),
    )
    return [
        {
            "id": row[0],
            "employer": row[1],
            "title": row[2],
            "contact_email": row[3],
            "submitted_at": row[4].isoformat() if row[4] else None,
            "location": row[5],
            "precision": row[6],
            "apply_url": row[7],
            "submitted_address": row[8],
        }
        for row in cur.fetchall()
    ]


def review(cur, job_id, approve, note=None):
    if approve:
        cur.execute(
            """
            select 1 from jobs j
            where j.id = %s and j.status = 'pending'
              and not exists (select 1 from job_locations l where l.job_id = j.id)
            """,
            (job_id,),
        )
        if cur.fetchone():
            return "unplaced"
    cur.execute(
        """
        update jobs
        set status = %s, reviewed_at = now(), review_note = %s, updated_at = now(),
            date_closes = case when %s then coalesce(date_closes, now() + %s * interval '1 day') else date_closes end
        where id = %s and status = 'pending'
        returning id, status
        """,
        ("live" if approve else "rejected", note, approve, moderation.LISTING_DAYS, job_id),
    )
    return cur.fetchone()
