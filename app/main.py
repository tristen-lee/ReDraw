### FastAPI entrypoint ###

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.adzuna import get_job
from app.models import SearchRequest
from app.geo import filter_by_polygon
from app.geocode import get_locations

app = FastAPI()

@app.post("/search")

def search(request: SearchRequest):
    locations = get_locations(request.polygon)

    if locations:
        all_jobs = []
        for place in locations:
            all_jobs.extend(get_job(request.what, where=place))
    else:
        all_jobs = get_job(request.what)

    unique_jobs = list({job["id"]: job for job in all_jobs}.values())
    filtered_jobs = filter_by_polygon(unique_jobs, request.polygon)
    return filtered_jobs

app.mount("/", StaticFiles(directory="static", html=True), name="static")