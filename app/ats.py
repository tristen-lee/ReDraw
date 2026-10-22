import re

import requests

TIMEOUT_SECONDS = 15
USER_AGENT = "ReDraw/0.1 (tristen.lee1221@gmail.com)"

CAREERS_PATHS = ("/careers", "/jobs", "/careers/", "/jobs/", "/about/careers", "/company/careers", "/join-us")

# Ordered: the first pattern that matches wins, so put the more specific
# host forms ahead of the generic ones.
PATTERNS = [
    ("lever", r"(?:jobs|api)\.lever\.co/(?:v0/postings/)?([A-Za-z0-9_-]+)"),
    ("greenhouse", r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)"),
    ("greenhouse", r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)"),
    ("greenhouse", r"greenhouse\.io/embed/job_board\?for=([A-Za-z0-9_-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9_-]+)"),
    ("smartrecruiters", r"(?:careers|api)\.smartrecruiters\.com/(?:v1/companies/)?([A-Za-z0-9_-]+)"),
    ("workable", r"apply\.workable\.com/([A-Za-z0-9_-]+)"),
    ("recruitee", r"([A-Za-z0-9_-]+)\.recruitee\.com"),
    ("bamboohr", r"([A-Za-z0-9_-]+)\.bamboohr\.com/(?:careers|jobs)"),
    ("workday", r"([A-Za-z0-9_-]+)\.wd\d+\.myworkdayjobs\.com/(?:wday/cxs/[^/]+/)?([A-Za-z0-9_-]+)"),
    ("icims", r"([A-Za-z0-9_-]+)\.icims\.com"),
    ("successfactors", r"career\d*\.successfactors\.com/career\?company=([A-Za-z0-9_-]+)"),
    # Taleo ships as two products. Business Edition puts every customer on a
    # shared *.tbe.taleo.net host, so the tenant is the path segment, not the
    # subdomain. Enterprise gives each customer a subdomain plus a section.
    ("taleo_business", r"([A-Za-z0-9-]+\.tbe\.taleo\.net/[A-Za-z0-9]+)/ats/careers"),
    ("taleo", r"([A-Za-z0-9-]+)\.taleo\.net/careersection/([A-Za-z0-9_-]+)"),
]

IGNORED_TOKENS = {"www", "jobs", "careers", "api", "embed", "job_board", "boards"}


def detect(text):
    for platform, pattern in PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        token = match.group(1)
        if token.lower() in IGNORED_TOKENS:
            continue
        extra = match.group(2) if match.lastindex and match.lastindex > 1 else None
        return {"platform": platform, "token": token, "site": extra}
    return None


def inspect(url, session=None):
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", USER_AGENT)

    try:
        response = session.get(url, timeout=TIMEOUT_SECONDS, allow_redirects=True)
    except requests.RequestException as exc:
        return {"url": url, "error": f"{type(exc).__name__}"}

    result = {"url": url, "final_url": response.url, "status": response.status_code}
    if response.status_code != 200:
        return result

    found = detect(response.url) or detect(response.text)
    if found:
        result.update(found)
    return result


def find_careers_page(domain, session=None):
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", USER_AGENT)
    base = domain if domain.startswith("http") else f"https://{domain}"

    for path in CAREERS_PATHS:
        candidate = base.rstrip("/") + path
        try:
            response = session.get(candidate, timeout=TIMEOUT_SECONDS, allow_redirects=True)
        except requests.RequestException:
            continue
        if response.status_code == 200:
            return candidate
    return None
