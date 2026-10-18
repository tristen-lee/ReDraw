### FastAPI entrypoint ###

import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from app import db, submissions
from app.models import Job, JobLocation, JobSubmission, ReviewRequest, SearchRequest

app = FastAPI()


def require_admin(x_admin_token: str = Header(default="")):
    expected = os.environ.get("ADMIN_TOKEN")
    if not expected:
        raise HTTPException(503, "Admin access is not configured.")
    if not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "Bad admin token.")

SEARCH_SQL = """
with shape as (
    select ST_MakeValid(ST_GeomFromText(%(wkt)s, 4326)) as geom
)
select
    j.id, j.source, j.title, j.employer_name_raw, j.url,
    j.date_posted, j.salary_min, j.salary_max, j.salary_interval, j.is_blanket,
    l.raw_location, l.precision, ST_Y(l.geom), ST_X(l.geom)
from job_locations l
join jobs j on j.id = l.job_id
cross join shape s
where j.expired_at is null
  and j.status = 'live'
  and ST_Contains(s.geom, l.geom)
  and (%(include_blanket)s::boolean or not j.is_blanket)
  and (
      %(what)s::text is null
      or j.title ilike %(pattern)s::text
      or j.description ilike %(pattern)s::text
  )
order by j.date_posted desc nulls last, j.id
limit %(limit)s
"""


def polygon_wkt(points):
    ring = list(points)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    coords = ", ".join(f"{lon} {lat}" for lon, lat in ring)
    return f"POLYGON(({coords}))"


@app.post("/search")
def search(request: SearchRequest) -> list[Job]:
    what = (request.what or "").strip() or None
    params = {
        "wkt": polygon_wkt(request.polygon),
        "include_blanket": request.include_blanket,
        "what": what,
        "pattern": f"%{what}%" if what else None,
        "limit": request.limit,
    }

    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(SEARCH_SQL, params)
        rows = cur.fetchall()

    jobs: dict[int, Job] = {}
    for (
        job_id, source, title, employer, url,
        date_posted, salary_min, salary_max, salary_interval, is_blanket,
        raw_location, precision, latitude, longitude,
    ) in rows:
        job = jobs.get(job_id)
        if job is None:
            job = Job(
                id=job_id,
                source=source,
                title=title,
                employer=employer,
                url=url,
                date_posted=date_posted.isoformat() if date_posted else None,
                salary_min=salary_min,
                salary_max=salary_max,
                salary_interval=salary_interval,
                is_blanket=is_blanket,
                locations=[],
            )
            jobs[job_id] = job
        job.locations.append(
            JobLocation(
                raw_location=raw_location,
                precision=precision,
                latitude=latitude,
                longitude=longitude,
            )
        )

    return list(jobs.values())


@app.post("/jobs/submit")
def submit_job(payload: JobSubmission):
    with db.connect() as conn, conn.cursor() as cur:
        result, error = submissions.submit(cur, payload)
        if result is None:
            raise HTTPException(422, error or "Could not accept that submission.")
        conn.commit()

    return {
        "status": "pending review",
        "job_id": result["job_id"],
        "placed_as": result["location"]["precision"],
        "location": result["location"]["raw"],
    }


@app.get("/admin/pending", dependencies=[Depends(require_admin)])
def pending_jobs():
    with db.connect() as conn, conn.cursor() as cur:
        return submissions.list_pending(cur)


@app.post("/admin/review/{job_id}", dependencies=[Depends(require_admin)])
def review_job(job_id: int, request: ReviewRequest):
    with db.connect() as conn, conn.cursor() as cur:
        row = submissions.review(cur, job_id, request.approve, request.note)
        if row is None:
            raise HTTPException(404, "No pending job with that id.")
        conn.commit()
    return {"job_id": row[0], "status": row[1]}


@app.get("/health")
def health():
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("select count(*) from jobs where expired_at is null")
        live_jobs = cur.fetchone()[0]
        cur.execute(
            """
            select source, finished_at, jobs_found
            from ingest_runs where status = 'success'
            order by finished_at desc limit 1
            """
        )
        row = cur.fetchone()

    return {
        "live_jobs": live_jobs,
        "last_successful_run": {
            "source": row[0],
            "finished_at": row[1].isoformat() if row[1] else None,
            "jobs_found": row[2],
        }
        if row
        else None,
    }


app.mount("/", StaticFiles(directory="static", html=True), name="static")
