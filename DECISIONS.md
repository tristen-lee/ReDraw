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
