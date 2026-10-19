### FastAPI entrypoint ###

import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db, pages, submissions
from app.models import Job, JobLocation, JobSubmission, ReviewRequest, SearchRequest

templates = Jinja2Templates(directory="templates")

app = FastAPI()


# Browsers happily serve a stale map.js for hours, which shows up as a 405
# when the cached copy calls a route that has since moved. "no-cache" still
# caches, it just forces a revalidation, so an unchanged file costs a 304.
@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.endswith((".js", ".css", ".html")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


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


@app.post("/api/search")
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
                path=f"/jobs/{job_id}/{pages.slugify(f'{title} {raw_location}')}",
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


@app.post("/api/jobs/submit")
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


@app.get("/api/admin/pending", dependencies=[Depends(require_admin)])
def pending_jobs():
    with db.connect() as conn, conn.cursor() as cur:
        return submissions.list_pending(cur)


@app.post("/api/admin/review/{job_id}", dependencies=[Depends(require_admin)])
def review_job(job_id: int, request: ReviewRequest):
    with db.connect() as conn, conn.cursor() as cur:
        row = submissions.review(cur, job_id, request.approve, request.note)
        if row is None:
            raise HTTPException(404, "No pending job with that id.")
        conn.commit()
    return {"job_id": row[0], "status": row[1]}


@app.get("/api/health")
def health():
    with db.connect() as conn, conn.cursor() as cur:
        # "stored" counts everything held; "mappable" is what a drawn shape can
        # actually return, which is the only number worth showing a visitor.
        cur.execute(
            """
            select
                count(*) filter (where expired_at is null and status = 'live'),
                count(*) filter (where expired_at is null and status = 'live' and is_blanket)
            from jobs
            """
        )
        stored, blanket = cur.fetchone()

        cur.execute(
            """
            select count(distinct j.id)
            from jobs j join job_locations l on l.job_id = j.id
            where j.expired_at is null and j.status = 'live' and not j.is_blanket
            """
        )
        mappable = cur.fetchone()[0]
        cur.execute(
            """
            select source, finished_at, jobs_found
            from ingest_runs where status = 'success'
            order by finished_at desc limit 1
            """
        )
        row = cur.fetchone()

    return {
        "mappable_jobs": mappable,
        "stored_jobs": stored,
        "standing_registers": blanket,
        "unmappable_jobs": stored - blanket - mappable,
        "last_successful_run": {
            "source": row[0],
            "finished_at": row[1].isoformat() if row[1] else None,
            "jobs_found": row[2],
        }
        if row
        else None,
    }


def site_base(request: Request):
    configured = os.environ.get("SITE_BASE_URL")
    return (configured or str(request.base_url)).rstrip("/")


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
@app.get("/jobs/{job_id}/{slug}", response_class=HTMLResponse)
def job_page(request: Request, job_id: int, slug: str | None = None):
    with db.connect() as conn, conn.cursor() as cur:
        job = pages.load(cur, job_id)

    if job is None:
        raise HTTPException(404, "That job is no longer listed.")

    canonical = f"{site_base(request)}/jobs/{job['id']}/{job['slug']}"
    if slug != job["slug"]:
        return RedirectResponse(canonical, status_code=301)

    return templates.TemplateResponse(
        request,
        "job.html",
        {
            "job": job,
            "canonical": canonical,
            # Standing registers are not vacancies at a place; marking them up as
            # JobPosting would put low-quality listings in Google's index.
            "noindex": job["is_blanket"],
            "structured_data": None if job["is_blanket"] else pages.structured_data(job, canonical),
        },
    )


@app.get("/sitemap.xml")
def sitemap(request: Request):
    base = site_base(request)
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select j.id, j.title, min(l.raw_location), max(j.updated_at)
            from jobs j join job_locations l on l.job_id = j.id
            where j.status = 'live' and j.expired_at is null and not j.is_blanket
            group by j.id, j.title
            order by j.id
            limit 50000
            """
        )
        rows = cur.fetchall()

    urls = "".join(
        f"<url><loc>{base}/jobs/{job_id}/{pages.slugify(f'{title} {place}')}</loc>"
        f"<lastmod>{updated.date().isoformat()}</lastmod></url>"
        for job_id, title, place, updated in rows
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{base}/</loc></url>{urls}</urlset>"
    )
    return Response(xml, media_type="application/xml")


@app.get("/robots.txt")
def robots(request: Request):
    body = f"User-agent: *\nAllow: /\nDisallow: /admin.html\nDisallow: /api/\n\nSitemap: {site_base(request)}/sitemap.xml\n"
    return Response(body, media_type="text/plain")


# Without this, an unmatched /api path falls through to the static mount below,
# which answers any non-GET with a 405 that looks like a method bug.
@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def unknown_api_route(rest: str):
    raise HTTPException(404, f"No API route at /api/{rest}")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
