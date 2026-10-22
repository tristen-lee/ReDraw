import uuid

from app import geocode, places

INSERT_JOB = """
insert into jobs (
    source, source_id, employer_name_raw, title, description, url,
    contact_email, submitted_by, status, employment_type
)
values (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
returning id
"""

INSERT_LOCATION = """
insert into job_locations (job_id, raw_location, precision, geom)
values (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
"""


def locate(cur, street_address, town_line):
    if street_address:
        match = geocode.geocode_address(f"{street_address}, {town_line}" if town_line else street_address)
        if match:
            return {
                "raw": match["matched_address"],
                "precision": "exact",
                "latitude": match["latitude"],
                "longitude": match["longitude"],
            }

    resolved = places.resolve(cur, town_line)
    if resolved:
        return {
            "raw": town_line,
            "precision": "town",
            "latitude": resolved["latitude"],
            "longitude": resolved["longitude"],
        }
    return None


def submit(cur, payload):
    location = locate(cur, payload.street_address, payload.town)
    if location is None:
        return None, "Could not place that address. Check the street and town."

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
        ),
    )
    job_id = cur.fetchone()[0]

    cur.execute(
        INSERT_LOCATION,
        (job_id, location["raw"], location["precision"], location["longitude"], location["latitude"]),
    )

    return {"job_id": job_id, "location": location}, None


def list_pending(cur, limit=100):
    cur.execute(
        """
        select j.id, j.employer_name_raw, j.title, j.contact_email, j.first_seen_at,
               l.raw_location, l.precision, j.url
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
        }
        for row in cur.fetchall()
    ]


def review(cur, job_id, approve, note=None):
    cur.execute(
        """
        update jobs
        set status = %s, reviewed_at = now(), review_note = %s, updated_at = now()
        where id = %s and status = 'pending'
        returning id, status
        """,
        ("live" if approve else "rejected", note, job_id),
    )
    return cur.fetchone()
