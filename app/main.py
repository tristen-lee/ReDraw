# FastAPI entrypoint — build order step 2

from fastapi import FastAPI
from app.adzuna import get_job

app = FastAPI()

@app.get("/search")

def search_job(what: str, where: str):
    return get_job(what, where)