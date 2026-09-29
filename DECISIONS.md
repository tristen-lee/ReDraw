# Decisions log

## 2026-09-23 — Adzuna over scraping
Decided: use Adzuna's licensed API instead of scraping Indeed/LinkedIn.
Why: scraping the big boards directly violates their ToS — real legal/blocking
risk for zero benefit. Adzuna is a legitimate licensed data source, so the
corridor-search feature is built on solid legal ground instead of something
that gets shut down the moment it gets attention.

## 2026-09-23 — SQLite now, Postgres later
Decided: start on SQLite, not Postgres.
Why: no concurrent multi-user writes to worry about yet, and SQLite has
zero setup friction while the actual unproven part of this project — does
the geospatial filtering work and is it useful — gets validated. Migration
to Postgres is a well-understood path if/when real usage demands it. Not
worth the setup cost before there's a reason.

## 2026-09-23 — point-in-polygon filtering in app code (Shapely), not the DB
Decided: filter job coordinates against the drawn shape in Python with
Shapely, not as a spatial DB query (e.g. PostGIS).
Why: Adzuna returns small result sets per query (dozens to low hundreds).
In-memory filtering is simpler, fast enough, and doesn't require standing
up PostGIS to solve a scale problem that doesn't exist yet.

## 2026-09-23 — live Adzuna proxy vs. caching/own listings store
Decided: MVP calls Adzuna live per search. Before any public launch, add a
short-TTL cache (~15-60 min) keyed on the query, to avoid paying for
duplicate/near-duplicate searches.
Why: live-per-search is the simplest version to prove the concept works at
all. Known limitation: Adzuna's free tier is 250 calls/day, 1000/week,
2500/month — that ceiling is easy to hit with real traffic, especially a
traffic spike from one social post. A short cache stretches the budget
cheaply. Explicitly decided AGAINST building a permanent local copy of
Adzuna's data for now — their ToS prohibits "aggregation... to deliver any
ongoing work," and a persistent warehouse of their data is a lot closer to
that violation than a short-lived cache is. Revisit only if this becomes a
real product with its own licensing conversation.

## 2026-09-23 — Adzuna commercial/freemium use needs a separate license
Decided: treat "turn this into a real, many-user product" as a
business-development problem, not a scaling problem.
Why: Adzuna's ToS caps commercial use at a 14-day trial; anything beyond
that (which freemium would be) needs a negotiated license agreement
directly with them. Scaling the code doesn't get around this — it's a
conversation to have with Adzuna, separately from anything built here.

## 2026-09-23 — rate limits vs. Facebook launch
Decided: before posting publicly, (1) add the short-TTL query cache above,
(2) optionally pull in a supplementary free source with no shared quota —
Greenhouse/Lever public board endpoints are per-company, not rate-limited
against Adzuna's budget, (3) email Adzuna ahead of time asking for a
temporary limit bump for a testing/demo launch.
Why: a single Facebook post can spike traffic fast enough to burn the
daily (250) or weekly (1000) cap in hours, locking the demo out mid-launch.
These three mitigations cost little and avoid that failure mode without
committing to the bigger own-database rebuild.

## 2026-09-23 — Adzuna is a prototyping data source, not the final one
Decided: keep using Adzuna to build and prove the corridor-search mechanics
(API call, Shapely point-in-polygon filtering, the full pipeline end to
end), but don't treat it as the permanent backend. Real v2 data comes from
company ATS boards (Greenhouse, Lever, etc.) and/or schema.org JobPosting
data pulled from career pages, geocoded properly (e.g. Census Bureau
Geocoder for US addresses), with data precision labeled in the UI so a
verified-address pin and an approximate-area pin don't look the same.
Why: pulled a real Adzuna response and checked it — three different
companies (Autodesk, Amazon, Curtiss-Wright), all tagged "Portland,
Multnomah County," came back with the exact same lat/long to 6 decimal
places. A fourth Portland-tagged listing had a different point entirely.
That means Adzuna's coordinates are pinned to a named-area reference point,
not the actual job location — the point-in-polygon math is exact, but the
input data isn't. Since ReDraw's whole pitch is being more precise than a
city+radius search, shipping on Adzuna's geocoding long-term would quietly
undermine the one thing this product is supposed to do better than
everyone else. Adzuna's still fine, and still legally clean, for proving
the mechanics work — it's just not where this ends up.