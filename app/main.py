### FastAPI entrypoint ###

from fastapi import FastAPI
from app.adzuna import get_job
from app.models import SearchRequest
from app.geo import filter_by_polygon

app = FastAPI()

@app.post("/search")

def search(request: SearchRequest):
    jobs = get_job(request.what, request.where)
    filtered_jobs = filter_by_polygon(jobs, request.polygon)
    return filtered_jobs