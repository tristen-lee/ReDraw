# Decisions log

## 2026-09-23 — Adzuna over scraping the big boards
Scraping Indeed/LinkedIn violates their ToS. Adzuna is licensed and legally clean.

## 2026-09-23 — SQLite now, Postgres later
No concurrent writes yet, zero setup friction, and the unproven part is the geospatial filtering, not the database.

## 2026-09-23 — point-in-polygon in Python (Shapely), not the DB
Adzuna returns dozens to low hundreds of results per query. In-memory filtering is fast enough and doesn't need PostGIS.

## 2026-09-23 — live Adzuna proxy, with a short cache before launch
Simplest version that proves the concept. Their free tier is 250/day and a single Facebook post could burn it in hours.

## 2026-09-23 — commercial Adzuna use is a business problem, not a scaling one
Their ToS caps commercial use at a 14-day trial. More code doesn't fix that; a negotiated license does.

## 2026-09-24 — Adzuna is a prototyping source, not the final one
Three different Portland employers came back with identical lat/long to six decimals. Their coordinates are named-area reference points, not job locations — which undermines the one thing this product is supposed to do better.

## 2026-09-30 — FastAPI serves the static frontend directly
Single origin, no CORS, one deployment. Splitting to a CDN later is a known migration, not a rewrite.

## 2026-09-30 — drop the location text box, derive it from the drawn shape
If the typed location and the drawn shape disagreed, results silently came back empty. Sampling points from the polygon is deterministic instead of a guess, and it handles a long bent corridor that a single centroid gets wrong.

## 2026-09-30 — Nominatim's free public API for reverse geocoding
Their policy explicitly permits end-user-triggered lookups at moderate volume, but the 1 req/sec limit is global across all traffic, not per user.

## 2026-10-01 — ingest-and-store replaces live-proxy; Postgres + PostGIS replaces SQLite
Nominatim's rate limit can't be coordinated across users at request time, and geocoding only needs to happen once per job, not once per search. Search becomes a single spatial query against data we own.

## 2026-10-01 — every source is its own adapter module
Any one of them can be dropped or swapped without touching ingestion or search. Written specifically because borrowed sources get revoked.

## 2026-10-02 — CareerOneStop dropped
Their terms require their logo on every page and no-login access to any feature using their data, which rules out ever putting accounts in front of it.

## 2026-10-02 — USAJobs cleared as the first real source
Read their actual terms: storing and normalizing is explicitly permitted, with attribution and apply links pointing back to USAJOBS.

## 2026-10-02 — Workday blocked, and with it four of the biggest employers audited
Their platform terms ban data mining and building applications against their sites without written consent. A permissive robots.txt doesn't override that — Workday treats robots.txt as a floor, not a grant.

## 2026-10-17 — Albertsons/Safeway blocked, iCIMS gated
Albertsons' own terms ban scrapers across all their banners. iCIMS has no public jobs API and gates access behind a partner program.

## 2026-10-17 — the enterprise ATS tier gates aggregation on purpose
Four platforms, same answer. Job distribution is what they sell their customers, so a free aggregator is a competitor by definition. This is structural, not bad luck.

## 2026-10-17 — aggregator first, marketplace second
Nobody cold-started a two-sided marketplace. Indeed aggregated, LinkedIn built a network, Monster already had newspaper inventory. Aggregated listings are also what makes employer outreach warm instead of cold.

## 2026-10-17 — supply from Portland metro, distribution from Columbia County
Aggregating a public job board needs no relationships, which solves having no network in Portland. Columbia County is where I'm local, and it's where direct postings come from later.

## 2026-10-17 — Lever cleared, Greenhouse parked
Lever's docs say the API is "designed to help you create a job site" and that postings may be scraped by third parties. Greenhouse's job board API is public but their user agreement separately bans automated access, which is too close to the Workday shape to build on.

## 2026-10-17 — board tokens can't be guessed, so detect them from careers pages
Probing ten plausible company names against Lever found only Lever's own demo site.

## 2026-10-17 — direct employer posting is the actual business
It's the only data nobody can revoke, the only source that gives street addresses, and the only thing there's any money in.

## 2026-10-17 — moderation instead of employer accounts
Under twenty employers, all known personally. Review is cheaper than building auth and doubles as the spam defense.

## 2026-10-17 — geometry lives on job_locations, not jobs
One federal requisition listed 1,176 duty stations. A single coordinate column on a job was never going to work.

## 2026-10-17 — standing registers flagged, not dropped
Federal "Public Notice" postings list dozens of towns and aren't a vacancy at any of them. Excluded from search and noindexed, but kept, because that's a display decision I might reverse.

## 2026-10-17 — expiry only runs after a successful ingest
And it refuses to expire anything if a run returns nothing or less than half the previous count, so a broken source can't empty the site.

## 2026-10-18 — publish our own JobPosting markup and per-job pages
A map of markers is invisible to search engines. SEO is the only free traffic channel available.

## 2026-10-18 — renamed to Cupholder
Car, commute, the corridor you actually drive. cupholder.work.

## 2026-10-19 — freehand drawing instead of clicking vertices
Leaflet.draw hasn't shipped since 2017 and its polygon tool means eight taps along Highway 30. One drag is the real gesture, and on a phone it's a single touch.

## 2026-10-19 — drawing over route corridors, even though routing fits the pitch
A route buffer assumes jobs cluster along the road. In Columbia County they don't, and willingness to drive isn't symmetric — people will go 40 minutes one way and refuse 15 the other.
