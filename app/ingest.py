import json

from psycopg.types.json import Jsonb

from app import db, usajobs

# A posting listing this many duty stations is a standing register, not a vacancy
# at any one of them.
BLANKET_LOCATION_THRESHOLD = 20

# Refuse to expire anything if a run returns less than this share of what the
# previous successful run saw. Catches a source breaking rather than emptying.
SUSPICIOUS_DROP_RATIO = 0.5

UPSERT_JOB = """
insert into jobs (
    source, source_id, employer_name_raw, title, description, url,
    date_posted, date_closes, employment_type,
    salary_min, salary_max, salary_interval, is_blanket, is_remote, raw,
    last_seen_at, updated_at, expired_at
)
values (
    %(source)s, %(source_id)s, %(employer_name)s, %(title)s, %(description)s, %(url)s,
    %(date_posted)s, %(date_closes)s, %(employment_type)s,
    %(salary_min)s, %(salary_max)s, %(salary_interval)s, %(is_blanket)s, %(is_remote)s, %(raw)s,
    now(), now(), null
)
on conflict (source, source_id) do update set
    employer_name_raw = excluded.employer_name_raw,
    title = excluded.title,
    description = excluded.description,
    url = excluded.url,
    date_posted = excluded.date_posted,
    date_closes = excluded.date_closes,
    employment_type = excluded.employment_type,
    salary_min = excluded.salary_min,
    salary_max = excluded.salary_max,
    salary_interval = excluded.salary_interval,
    is_blanket = excluded.is_blanket,
    is_remote = excluded.is_remote,
    raw = excluded.raw,
    last_seen_at = now(),
    updated_at = now(),
    expired_at = null
returning id, (xmax = 0) as inserted
"""

INSERT_LOCATION = """
insert into job_locations (job_id, raw_location, precision, geom)
values (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
"""


def blank_to_none(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def upsert_job(cur, job):
    cur.execute(
        UPSERT_JOB,
        {
            "source": job["source"],
            "source_id": job["source_id"],
            "employer_name": job.get("employer_name"),
            "title": job["title"],
            "description": job.get("description"),
            "url": job.get("url"),
            "date_posted": blank_to_none(job.get("date_posted")),
            "date_closes": blank_to_none(job.get("date_closes")),
            "employment_type": job.get("employment_type") or None,
            "salary_min": blank_to_none(job.get("salary_min")),
            "salary_max": blank_to_none(job.get("salary_max")),
            "salary_interval": job.get("salary_interval"),
            "is_blanket": job.get("total_locations", 0) >= BLANKET_LOCATION_THRESHOLD,
            "is_remote": bool(job.get("is_remote")),
            "raw": Jsonb(job.get("raw")),
        },
    )
    job_id, inserted = cur.fetchone()

    cur.execute("delete from job_locations where job_id = %s", (job_id,))
    for location in job["locations"]:
        cur.execute(
            INSERT_LOCATION,
            (job_id, location["raw"], location["precision"], location["longitude"], location["latitude"]),
        )

    return inserted


def previous_success_count(cur, source):
    cur.execute(
        """
        select jobs_found from ingest_runs
        where source = %s and status = 'success'
        order by started_at desc limit 1
        """,
        (source,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def expire_missing(cur, source, run_started_at):
    cur.execute(
        """
        update jobs set expired_at = now(), updated_at = now()
        where source = %s and expired_at is null and last_seen_at < %s
        """,
        (source, run_started_at),
    )
    return cur.rowcount


def run(source, fetch):
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into ingest_runs (source, status) values (%s, 'running') returning id, started_at",
                (source,),
            )
            run_id, started_at = cur.fetchone()
        conn.commit()

        try:
            jobs = fetch()
        except Exception as exc:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update ingest_runs set status = 'failed', finished_at = now(), error_message = %s
                    where id = %s
                    """,
                    (f"{type(exc).__name__}: {exc}"[:2000], run_id),
                )
            conn.commit()
            raise

        added = updated = 0
        with conn.cursor() as cur:
            for job in jobs:
                if upsert_job(cur, job):
                    added += 1
                else:
                    updated += 1

            previous = previous_success_count(cur, source)
            collapsed = (
                previous is not None
                and previous > 0
                and len(jobs) < previous * SUSPICIOUS_DROP_RATIO
            )

            if not jobs or collapsed:
                expired = 0
                note = (
                    f"expiry skipped: {len(jobs)} found vs {previous} last run"
                    if collapsed
                    else "expiry skipped: run returned no jobs"
                )
            else:
                expired = expire_missing(cur, source, started_at)
                note = None

            cur.execute(
                """
                update ingest_runs set
                    status = 'success', finished_at = now(),
                    jobs_found = %s, jobs_added = %s, jobs_updated = %s, jobs_expired = %s,
                    error_message = %s
                where id = %s
                """,
                (len(jobs), added, updated, expired, note, run_id),
            )
        conn.commit()

    return {
        "run_id": run_id,
        "found": len(jobs),
        "added": added,
        "updated": updated,
        "expired": expired,
        "note": note,
    }


def run_usajobs():
    return run("usajobs", usajobs.fetch_corridor_jobs)


if __name__ == "__main__":
    print(json.dumps(run_usajobs(), indent=2))
