### FastAPI entrypoint ###

import os
import re
import secrets
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db, moderation, pages, submissions
from app.models import (
    Job, JobLocation, JobSubmission, OptOutRequest, PlaceRequest, RemoveRequest, ReviewRequest, SearchRequest,
    is_safe_link,
)

# Link-preview fetchers and crawlers that ignore robots.txt would otherwise
# inflate the one number shown to employers.
NON_HUMAN_AGENTS = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|embedly|curl|wget|python-requests|httpx|headless",
    re.IGNORECASE,
)

templates = Jinja2Templates(directory="templates")

app = FastAPI()


# The onrender.com hostname keeps serving the site after the custom domain is
# live, and Google will index both copies unless one redirects. Three guards:
# it does nothing until SITE_BASE_URL is set, so it can't send traffic to a
# domain that doesn't resolve yet; it skips /api/ so Render's health check never
# sees a 301; and it compares hosts so a misconfigured base can't loop.
@app.middleware("http")
async def canonical_host(request: Request, call_next):
    base = os.environ.get("SITE_BASE_URL", "").rstrip("/")
    host = request.headers.get("host", "").split(":")[0]
    if (
        base
        and host.endswith(".onrender.com")
        and host != urlsplit(base).hostname
        and not request.url.path.startswith("/api/")
    ):
        target = base + request.url.path
        if request.url.query:
            target += "?" + request.url.query
        return RedirectResponse(target, status_code=301)
    return await call_next(request)


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


SUBMISSIONS_PER_HOUR = 5
REPORTS_PER_HOUR = 10
REPORT_REASONS = ("scam", "filled", "wrong_location", "other")


@app.post("/api/jobs/submit")
def submit_job(request: Request, payload: JobSubmission):
    # A filled honeypot gets the same answer a person would, so the bot
    # has nothing to learn from.
    if payload.website:
        return {"status": "pending review", "placed": False, "location": payload.street_address}

    with db.connect() as conn, conn.cursor() as cur:
        if not moderation.allow(cur, "submit", request, SUBMISSIONS_PER_HOUR):
            conn.commit()
            raise HTTPException(429, "That's a lot of posts in an hour. Try again later, or email tristen@cupholder.work.")
        conn.commit()
        result, error = submissions.submit(cur, payload)
        if result is None:
            raise HTTPException(422, error or "Could not accept that submission.")
        conn.commit()

    location = result["location"]
    return {
        "status": "pending review",
        "placed": location is not None,
        "location": location["raw"] if location else payload.street_address,
        "manage_url": f"{site_base(request)}/manage/{result['manage_token']}",
    }


@app.get("/manage/{token}", response_class=HTMLResponse)
def manage_page(request: Request, token: str, done: str | None = None):
    with db.connect() as conn, conn.cursor() as cur:
        job = moderation.find_by_token(cur, token)
    if job is None:
        raise HTTPException(404, "That link doesn't match a posting.")
    return templates.TemplateResponse(request, "manage.html", {"job": job, "token": token, "done": done})


@app.post("/manage/{token}/{action}")
def manage_action(token: str, action: str):
    if action not in ("close", "renew"):
        raise HTTPException(404)
    with db.connect() as conn, conn.cursor() as cur:
        job = moderation.find_by_token(cur, token)
        if job is None:
            raise HTTPException(404, "That link doesn't match a posting.")
        if action == "close":
            moderation.close(cur, job["id"], "closed by employer")
        else:
            moderation.renew(cur, job["id"])
        conn.commit()
    return RedirectResponse(f"/manage/{token}?done={action}", status_code=303)


@app.post("/jobs/{job_id}/report")
def report_job(
    request: Request,
    job_id: int,
    reason: str = Form(...),
    details: str = Form(default="", max_length=1000),
    website: str = Form(default=""),
):
    if reason not in REPORT_REASONS:
        raise HTTPException(422, "Pick a reason.")
    if not website:
        with db.connect() as conn, conn.cursor() as cur:
            if moderation.allow(cur, "report", request, REPORTS_PER_HOUR):
                moderation.report(cur, job_id, reason, details.strip())
            conn.commit()
    return RedirectResponse(f"/jobs/{job_id}?reported=1", status_code=303)


@app.get("/api/admin/pending", dependencies=[Depends(require_admin)])
def pending_jobs():
    with db.connect() as conn, conn.cursor() as cur:
        return submissions.list_pending(cur)


@app.post("/api/admin/review/{job_id}", dependencies=[Depends(require_admin)])
def review_job(job_id: int, request: ReviewRequest):
    with db.connect() as conn, conn.cursor() as cur:
        row = submissions.review(cur, job_id, request.approve, request.note)
        if row == "unplaced":
            raise HTTPException(409, "Place it on the map before approving.")
        if row is None:
            raise HTTPException(404, "No pending job with that id.")
        conn.commit()
    return {"job_id": row[0], "status": row[1]}


@app.post("/api/admin/place/{job_id}", dependencies=[Depends(require_admin)])
def place_job(job_id: int, request: PlaceRequest):
    with db.connect() as conn, conn.cursor() as cur:
        location, error = submissions.place(cur, job_id, request.address, request.latitude, request.longitude)
        if location is None:
            raise HTTPException(422, error)
        conn.commit()
    return {"job_id": job_id, "location": location["raw"], "precision": location["precision"]}


@app.get("/api/admin/reports", dependencies=[Depends(require_admin)])
def reports():
    with db.connect() as conn, conn.cursor() as cur:
        return moderation.open_reports(cur)


@app.post("/api/admin/reports/{job_id}/dismiss", dependencies=[Depends(require_admin)])
def dismiss_reports(job_id: int):
    with db.connect() as conn, conn.cursor() as cur:
        moderation.resolve_reports(cur, job_id)
        conn.commit()
    return {"job_id": job_id, "dismissed": True}


@app.post("/api/admin/jobs/{job_id}/remove", dependencies=[Depends(require_admin)])
def remove_job(job_id: int, request: RemoveRequest):
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("select title, employer_name_raw from jobs where id = %s", (job_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(404, "No job with that id.")
        removed = moderation.remove_job(cur, job_id, request.note)
        conn.commit()
    return {"job_id": job_id, "title": row[0], "employer": row[1], "removed": removed}


@app.post("/api/admin/employers/opt-out", dependencies=[Depends(require_admin)])
def opt_out(request: OptOutRequest):
    with db.connect() as conn, conn.cursor() as cur:
        removed = moderation.opt_out(cur, request.name.strip())
        conn.commit()
    return {"employer": request.name.strip(), "jobs_removed": removed}


@app.get("/api/admin/clicks", dependencies=[Depends(require_admin)])
def click_stats(days: int = 30):
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select coalesce(e.name, j.employer_name_raw, 'Unknown') as employer,
                   j.source,
                   count(distinct j.id) as jobs_clicked,
                   count(c.id) as clicks,
                   max(c.clicked_at) as last_click
            from job_clicks c
            join jobs j on j.id = c.job_id
            left join employers e on e.id = j.employer_id
            where c.clicked_at > now() - make_interval(days => %s)
            group by 1, 2
            order by clicks desc
            """,
            (days,),
        )
        rows = cur.fetchall()

    return {
        "days": days,
        "employers": [
            {
                "employer": employer,
                "source": source,
                "jobs_clicked": jobs_clicked,
                "clicks": clicks,
                "last_click": last_click.isoformat() if last_click else None,
            }
            for employer, source, jobs_clicked, clicks, last_click in rows
        ],
    }


@app.get("/api/config")
def client_config():
    # Null until the basemap is hosted; the map falls back to OSM raster tiles.
    return {"tiles_url": os.environ.get("PMTILES_URL") or None}


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
def job_page(request: Request, job_id: int, slug: str | None = None, reported: str | None = None):
    with db.connect() as conn, conn.cursor() as cur:
        job = pages.load(cur, job_id)

    if job is None:
        raise HTTPException(404, "That job is no longer listed.")

    canonical = f"{site_base(request)}/jobs/{job['id']}/{job['slug']}"
    if slug != job["slug"]:
        return RedirectResponse(canonical + ("?reported=1" if reported else ""), status_code=301)

    return templates.TemplateResponse(
        request,
        "job.html",
        {
            "job": job,
            "canonical": canonical,
            "reported": bool(reported),
            # Standing registers are not vacancies at a place; marking them up as
            # JobPosting would put low-quality listings in Google's index.
            "noindex": job["is_blanket"],
            "structured_data": None if job["is_blanket"] else pages.structured_data(job, canonical),
        },
    )


@app.get("/go/{job_id}")
def apply_redirect(request: Request, job_id: int):
    # Redirect only to the URL stored on the job, never one taken from the
    # request, so this cannot be used as an open redirect. The scheme is
    # rechecked because rows submitted before validation existed may predate it.
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("select url from jobs where id = %s and status = 'live'", (job_id,))
        row = cur.fetchone()
        if row is None or not is_safe_link(row[0]):
            raise HTTPException(404, "That job is no longer listed.")

        if not NON_HUMAN_AGENTS.search(request.headers.get("user-agent", "")):
            cur.execute("insert into job_clicks (job_id) values (%s)", (job_id,))
            conn.commit()

    return RedirectResponse(row[0].strip(), status_code=302)


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
    body = (
        "User-agent: *\nAllow: /\nDisallow: /admin.html\nDisallow: /api/\nDisallow: /go/\n\n"
        f"Sitemap: {site_base(request)}/sitemap.xml\n"
    )
    return Response(body, media_type="text/plain")


# Without this, an unmatched /api path falls through to the static mount below,
# which answers any non-GET with a 405 that looks like a method bug.
@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def unknown_api_route(rest: str):
    raise HTTPException(404, f"No API route at /api/{rest}")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
