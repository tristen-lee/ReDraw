import json
import time
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.ats import USER_AGENT
ROBOTS_AGENT = "Cupholder"
DELAY_SECONDS = 2
TIMEOUT_SECONDS = 10
MAX_JOB_PAGES = 8

JOB_LINK_HINTS = ("job", "career", "employment", "position", "opening", "vacancy", "recruit")

EMPLOYERS = [
    ("Columbia County (government)", "https://www.columbiacountyor.gov/jobs"),
    ("City of Rainier", "https://cityofrainier.com/city-news/jobs/"),
    ("City of Vernonia", "https://www.vernonia-or.gov/employment/"),
    ("Clatskanie People's Utility District", "https://www.clatskaniepud.com/about-us/careers/"),
    ("Columbia 9-1-1 Communications District", "https://www.columbia911.com/jobs"),
    ("Community Action Team", "https://cat-team.org/jobs"),
    ("Columbia River Fire & Rescue", "https://www.crfr.com/join-us"),
    ("Global Partners (Clatskanie terminal)", "https://careers.globalp.com/"),
]


def load_robots(session, host_root):
    parser = urllib.robotparser.RobotFileParser()
    try:
        response = session.get(f"{host_root}/robots.txt", timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        parser.allow_all = True
        return parser, f"unreachable ({exc.__class__.__name__})"

    if response.status_code in (401, 403):
        parser.disallow_all = True
        return parser, f"denied ({response.status_code})"
    if 400 <= response.status_code < 500:
        parser.allow_all = True
        return parser, f"absent ({response.status_code})"

    parser.parse(response.text.splitlines())
    return parser, "ok"


def fetch(session, url):
    time.sleep(DELAY_SECONDS)
    try:
        response = session.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        return None, f"{exc.__class__.__name__}: {exc}"
    return response, None


def is_job_posting(item):
    if not isinstance(item, dict):
        return False
    item_type = item.get("@type")
    if isinstance(item_type, list):
        return "JobPosting" in item_type
    return item_type == "JobPosting"


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def find_job_postings(html):
    soup = BeautifulSoup(html, "html.parser")
    postings = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.get_text(strip=True)
        if not raw:
            continue
        try:
            document = json.loads(raw)
        except ValueError:
            continue
        postings.extend(node for node in walk(document) if is_job_posting(node))
    return postings


def find_job_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc
    links = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        absolute = urljoin(base_url, anchor["href"]).split("#")[0]
        if absolute in seen or absolute.rstrip("/") == base_url.rstrip("/"):
            continue
        if urlparse(absolute).netloc != base_host:
            continue
        haystack = f"{absolute} {anchor.get_text(' ', strip=True)}".lower()
        if any(hint in haystack for hint in JOB_LINK_HINTS):
            seen.add(absolute)
            links.append(absolute)
    return links[:MAX_JOB_PAGES]


def check_employer(session, name, listing_url):
    result = {
        "employer": name,
        "listing_url": listing_url,
        "final_url": None,
        "robots": None,
        "listing_markup": 0,
        "job_pages_checked": 0,
        "job_page_markup": 0,
        "sample_titles": [],
        "error": None,
    }

    parsed = urlparse(listing_url)
    robots, robots_status = load_robots(session, f"{parsed.scheme}://{parsed.netloc}")
    result["robots"] = robots_status

    if not robots.can_fetch(ROBOTS_AGENT, listing_url):
        result["error"] = "disallowed by robots.txt"
        return result

    listing, error = fetch(session, listing_url)
    if error:
        result["error"] = error
        return result

    result["final_url"] = listing.url

    listing_postings = find_job_postings(listing.text)
    result["listing_markup"] = len(listing_postings)
    titles = [p.get("title") for p in listing_postings if p.get("title")]

    for job_url in find_job_links(listing.text, listing.url):
        if not robots.can_fetch(ROBOTS_AGENT, job_url):
            continue
        result["job_pages_checked"] += 1
        page, page_error = fetch(session, job_url)
        if page_error:
            continue
        postings = find_job_postings(page.text)
        result["job_page_markup"] += len(postings)
        titles.extend(p.get("title") for p in postings if p.get("title"))

    result["sample_titles"] = titles[:5]
    return result


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    for name, url in EMPLOYERS:
        print(json.dumps(check_employer(session, name, url), indent=2))


if __name__ == "__main__":
    main()
