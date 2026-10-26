import json
import sys

from psycopg.types.json import Jsonb

from app import db, employers, mailer, moderation, places, usajobs

# A posting listing this many duty stations is a standing register, not a vacancy
# at any one of them.
BLANKET_LOCATION_THRESHOLD = 20

# Refuse to expire anything if a run returns less than this share of what the
# previous successful run saw. Catches a source breaking rather than emptying.
SUSPICIOUS_DROP_RATIO = 0.5
# Below this, a source going from 2 jobs to 0 is a filled position, not an
# outage, so the drop check doesn't apply.
SMALL_SOURCE_JOBS = 10

UPSERT_JOB = """
insert into jobs (
    source, source_id, employer_id, employer_name_raw, title, description, url,
    date_posted, date_closes, employment_type,
    salary_min, salary_max, salary_interval, is_blanket, is_remote, raw,
    last_seen_at, updated_at, expired_at
)
values (
    %(source)s, %(source_id)s, %(employer_id)s, %(employer_name)s, %(title)s, %(description)s, %(url)s,
    %(date_posted)s, %(date_closes)s, %(employment_type)s,
    %(salary_min)s, %(salary_max)s, %(salary_interval)s, %(is_blanket)s, %(is_remote)s, %(raw)s,
    now(), now(), null
)
on conflict (source, source_id) do update set
    employer_id = excluded.employer_id,
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
            "employer_id": job.get("employer_id"),
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


# Jobs from an employer whose feed errored this run are left alone: not
# seeing them says nothing about whether they're still open.
def expire_missing(cur, source, run_started_at, skip_employer_ids=()):
    cur.execute(
        """
        update jobs set expired_at = now(), updated_at = now()
        where source = %s and expired_at is null and last_seen_at < %s
          and (employer_id is null or employer_id <> all(%s))
        """,
        (source, run_started_at, list(skip_employer_ids)),
    )
    return cur.rowcount


def mark_failed(run_id, exc):
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "update ingest_runs set status = 'failed', finished_at = now(), error_message = %s where id = %s",
            (f"{type(exc).__name__}: {exc}"[:2000], run_id),
        )
        conn.commit()


# A fetch can run for minutes, and the Supabase pooler drops a connection
# left idle that long. So no connection is held open across it: one to log
# the start, a fresh one to write the results.
def run(source, fetch):
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into ingest_runs (source, status) values (%s, 'running') returning id, started_at",
            (source,),
        )
        run_id, started_at = cur.fetchone()
        conn.commit()

    try:
        result = fetch()
        jobs = result["jobs"] if isinstance(result, dict) else result
        failed = result.get("failed", []) if isinstance(result, dict) else []
        if failed and not jobs and len(failed) == result.get("employers", len(failed)):
            raise RuntimeError("every employer failed: " + "; ".join(f["error"] for f in failed[:5]))

        added = updated = 0
        with db.connect() as conn, conn.cursor() as cur:
            for job in jobs:
                if upsert_job(cur, job):
                    added += 1
                else:
                    updated += 1

            previous = previous_success_count(cur, source)
            collapsed = (
                previous is not None
                and previous >= SMALL_SOURCE_JOBS
                and len(jobs) < previous * SUSPICIOUS_DROP_RATIO
            )

            if collapsed or (not jobs and previous is None):
                expired = 0
                note = (
                    f"expiry skipped: {len(jobs)} found vs {previous} last run"
                    if collapsed
                    else "expiry skipped: run returned no jobs"
                )
            else:
                expired = expire_missing(cur, source, started_at, [f["employer_id"] for f in failed])
                note = None

            if failed:
                failures = "; ".join(f"{f['name']}: {f['error']}" for f in failed)
                note = f"{note + ' | ' if note else ''}{len(failed)} employer(s) failed: {failures}"[:2000]

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
    except Exception as exc:
        mark_failed(run_id, exc)
        raise

    return {
        "run_id": run_id,
        "found": len(jobs),
        "added": added,
        "updated": updated,
        "expired": expired,
        "previous": previous,
        "note": note,
    }


# USAJobs sends its own point per duty station, and it varies between postings
# in the same town. Snapping to our places table keeps one town to one marker.
def snap_to_places(jobs):
    cache = {}
    with db.connect() as conn, conn.cursor() as cur:
        for job in jobs:
            for location in job["locations"]:
                place = places.resolve(cur, location["raw"], cache)
                if place and location["precision"] == "town":
                    location["latitude"], location["longitude"] = place["latitude"], place["longitude"]
    return jobs


def run_usajobs():
    return run("usajobs", lambda: snap_to_places(usajobs.fetch_region_jobs()))


def run_platform(platform):
    def fetch():
        with db.connect() as conn, conn.cursor() as cur:
            return employers.collect(cur, platform)
    return run(platform, fetch)


# Direct posts run 30 days unless the employer renews from their manage link.
def run_sweep():
    with db.connect() as conn, conn.cursor() as cur:
        expired = moderation.sweep(cur)
        conn.commit()
    return {"direct_posts_expired": expired}


# Failed runs, collapsed counts and broken employer feeds all mail the owner.
def alert(source, result=None, error=None):
    if error:
        mailer.notify_owner(f"Ingest failed: {source}", f"{source} failed and nothing was expired.\n\n{error}")
    elif (result and (result.get("previous") or 0) >= SMALL_SOURCE_JOBS
          and result["found"] < result["previous"] * SUSPICIOUS_DROP_RATIO):
        mailer.notify_owner(
            f"Suspicious drop: {source}",
            f"{source} found {result['found']} jobs, down from {result['previous']}. Nothing was expired.",
        )
    elif result and result.get("note") and "failed:" in result["note"]:
        mailer.notify_owner(f"Some {source} employers failed", result["note"])


# Each source runs on its own; one failing never stops the rest.
def main(sources):
    failures = 0
    for source in sources:
        try:
            if source == "sweep":
                result = run_sweep()
            elif source == "usajobs":
                result = run_usajobs()
            else:
                result = run_platform(source)
            print(source, json.dumps(result, default=str))
            alert(source, result=result)
        except Exception as exc:
            failures += 1
            print(source, "FAILED", f"{type(exc).__name__}: {exc}")
            alert(source, error=f"{type(exc).__name__}: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["usajobs"]))
