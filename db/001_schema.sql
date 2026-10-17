create extension if not exists postgis;

-- Census Gazetteer places. Reference data: loaded once, read-only to ingestion.
-- Lets a source that only gives "Rainier, OR" resolve to a point with no API call.
create table if not exists places (
    id bigserial primary key,
    geoid text unique,
    name text not null,
    state_code char(2) not null,
    geom geometry(Point, 4326) not null
);

create index if not exists places_name_state_idx on places (lower(name), state_code);
create index if not exists places_geom_idx on places using gist (geom);

create table if not exists employers (
    id bigserial primary key,
    name text not null,
    slug text unique,
    careers_url text,
    platform text,
    town text,
    state_code char(2),
    street_address text,
    -- Set for single-site employers, so their jobs get exact precision with no geocoding.
    geom geometry(Point, 4326),
    crawl_allowed boolean,
    robots_checked_at timestamptz,
    terms_checked_at timestamptz,
    -- Non-negotiable: an employer asking to be removed is honored here.
    opted_out boolean not null default false,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists employers_platform_idx on employers (platform);

create table if not exists jobs (
    id bigserial primary key,
    source text not null,
    source_id text not null,
    employer_id bigint references employers (id) on delete set null,
    employer_name_raw text,
    title text not null,
    description text,
    url text,
    date_posted timestamptz,
    date_closes timestamptz,
    employment_type text[],
    salary_min numeric,
    salary_max numeric,
    salary_interval text,
    -- Blanket postings (e.g. federal "Public Notice" registers) list dozens of
    -- towns and aren't a vacancy at any one of them. Flagged, not dropped.
    is_blanket boolean not null default false,
    -- License terms for borrowed sources require the unmodified record be kept
    -- separate from our normalized columns.
    raw jsonb,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    expired_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source, source_id)
);

create index if not exists jobs_employer_idx on jobs (employer_id);
create index if not exists jobs_live_idx on jobs (source, expired_at) where expired_at is null;

-- One row per place a posting can be worked. A single federal requisition can
-- list 50+ duty stations, so geometry lives here and not on jobs.
create table if not exists job_locations (
    id bigserial primary key,
    job_id bigint not null references jobs (id) on delete cascade,
    place_id bigint references places (id) on delete set null,
    raw_location text,
    precision text not null check (precision in ('exact', 'town', 'county', 'unknown')),
    geom geometry(Point, 4326) not null,
    created_at timestamptz not null default now()
);

create index if not exists job_locations_geom_idx on job_locations using gist (geom);
create index if not exists job_locations_job_idx on job_locations (job_id);

create table if not exists ingest_runs (
    id bigserial primary key,
    source text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    status text not null check (status in ('running', 'success', 'failed')),
    jobs_found integer not null default 0,
    jobs_added integer not null default 0,
    jobs_updated integer not null default 0,
    jobs_expired integer not null default 0,
    error_message text
);

create index if not exists ingest_runs_source_idx on ingest_runs (source, started_at desc);
