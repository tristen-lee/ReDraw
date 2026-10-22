import hashlib
import json
import time
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.ats import USER_AGENT
from app.text import html_to_text

ROBOTS_AGENT = "Cupholder"
DELAY_SECONDS = 2
TIMEOUT_SECONDS = 15
MAX_JOB_PAGES = 60
JOB_LINK_HINTS = ("job", "career", "employment", "position", "opening", "vacancy", "recruit")


class Blocked(Exception):
    pass


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def load_robots(http, root):
    parser = urllib.robotparser.RobotFileParser()
    response = http.get(f"{root}/robots.txt", timeout=TIMEOUT_SECONDS)
    if response.status_code in (401, 403):
        parser.disallow_all = True
    elif response.status_code >= 400:
        parser.allow_all = True
    else:
        parser.parse(response.text.splitlines())
    return parser


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def is_job_posting(node):
    kind = node.get("@type")
    return "JobPosting" in kind if isinstance(kind, list) else kind == "JobPosting"


def job_postings(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    found = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            document = json.loads(script.get_text(strip=True) or "null")
        except ValueError:
            continue
        found.extend(node for node in walk(document) if is_job_posting(node))
    return found


def job_links(page_html, base_url):
    soup = BeautifulSoup(page_html, "html.parser")
    host = urlparse(base_url).netloc
    links = []
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, anchor["href"]).split("#")[0]
        if urlparse(url).netloc != host or url.rstrip("/") == base_url.rstrip("/") or url in links:
            continue
        if any(hint in f"{url} {anchor.get_text(' ', strip=True)}".lower() for hint in JOB_LINK_HINTS):
            links.append(url)
    return links[:MAX_JOB_PAGES]


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def place(location):
    address = location.get("address") if isinstance(location, dict) else None
    if isinstance(address, str):
        return {"text": address}
    address = address or {}
    town, region = address.get("addressLocality"), address.get("addressRegion")
    return {
        "text": f"{town}, {region}" if town and region else None,
        "street_address": address.get("streetAddress"),
    }


def salary(posting):
    value = (posting.get("baseSalary") or {}).get("value") if isinstance(posting.get("baseSalary"), dict) else None
    if not isinstance(value, dict):
        return None, None, None
    unit = {"HOUR": "PH", "DAY": "PD", "WEEK": "PW", "MONTH": "PM", "YEAR": "PA"}.get(str(value.get("unitText", "")).upper())
    low = value.get("minValue", value.get("value"))
    return low, value.get("maxValue"), unit


def normalize(posting, page_url):
    url = posting.get("url") or page_url
    low, high, unit = salary(posting)
    return {
        # One listing page can carry several postings with no url of their own.
        "source_id": hashlib.sha1(f"{url}|{posting.get('title')}".encode()).hexdigest()[:20],
        "title": posting.get("title"),
        "description": html_to_text(posting.get("description")),
        "url": url,
        "date_posted": posting.get("datePosted"),
        "date_closes": posting.get("validThrough"),
        "employment_type": [str(t) for t in as_list(posting.get("employmentType"))],
        "salary_min": low,
        "salary_max": high,
        "salary_interval": unit,
        "is_remote": posting.get("jobLocationType") == "TELECOMMUTE",
        "places": [place(location) for location in as_list(posting.get("jobLocation"))],
        "raw": posting,
    }


# Only the employer's own site, only what robots.txt allows. A site that
# blocks us raises Blocked, and that employer comes off the list.
def fetch(careers_url):
    http = session()
    parsed = urlparse(careers_url)
    robots = load_robots(http, f"{parsed.scheme}://{parsed.netloc}")
    if not robots.can_fetch(ROBOTS_AGENT, careers_url):
        raise Blocked(f"robots.txt disallows {careers_url}")

    listing = http.get(careers_url, timeout=TIMEOUT_SECONDS)
    if listing.status_code in (401, 403, 429):
        raise Blocked(f"{listing.status_code} from {careers_url}")
    listing.raise_for_status()

    jobs = {}
    for posting in job_postings(listing.text):
        job = normalize(posting, listing.url)
        jobs[job["source_id"]] = job

    for url in job_links(listing.text, listing.url):
        if not robots.can_fetch(ROBOTS_AGENT, url):
            continue
        time.sleep(DELAY_SECONDS)
        try:
            page = http.get(url, timeout=TIMEOUT_SECONDS)
        except requests.RequestException:
            continue
        if page.status_code in (401, 403, 429):
            raise Blocked(f"{page.status_code} from {url}")
        if page.ok:
            for posting in job_postings(page.text):
                job = normalize(posting, page.url)
                jobs[job["source_id"]] = job

    return list(jobs.values())
