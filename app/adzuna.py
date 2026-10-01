### Adzuna API call -- COMPLETED ###
import os

import requests
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.environ["ADZUNA_APP_ID"]
APP_KEY = os.environ["ADZUNA_APP_KEY"]

url = "https://api.adzuna.com/v1/api/jobs/us/search/1"

### Searches for the jobs ###

def search_job(job):
    return {
        "id": job["id"],
        "title": job["title"],
        "company": job["company"]["display_name"],
        "location": job["location"]["display_name"],
        "latitude": job.get("latitude"),
        "longitude": job.get("longitude"),
        "salary_min": job.get("salary_min"),
        "salary_max": job.get("salary_max"),
        "url": job["redirect_url"],
    }

### Calls Adzuna, then takes the JSON, puts it in a dict, loops through it, trims it, then returns  the new list. ###

def get_job(what, where=None):
    params = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "results_per_page": 50,
        "what": what,
    }
    if where:
        params["where"] = where

    response = requests.get(url, params=params)
    jobs = [search_job(job) for job in response.json()["results"]]
    return jobs





### Testable Code for later ###
if __name__ == "__main__":
    params = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "results_per_page": 50,
        "what": "software developer",
    }

    response = requests.get(url, params=params)
    print(response.status_code)
    print(response.json())

    jobs = [search_job(job) for job in response.json()["results"]]
