-- First-party analytics. Visitors are a random id the browser makes up and
-- keeps in localStorage; sessions are another one that lapses after 30 idle
-- minutes. No IP address, user agent string, or anything tied to a person.
create table if not exists events (
    id bigserial primary key,
    occurred_at timestamptz not null default now(),
    visitor_id uuid,
    session_id uuid,
    name text not null,
    path text,
    referrer_host text,
    utm_source text,
    utm_medium text,
    utm_campaign text,
    device text,
    props jsonb not null default '{}'
);

create index if not exists events_time_idx on events (occurred_at desc);
create index if not exists events_name_time_idx on events (name, occurred_at desc);
create index if not exists events_session_idx on events (session_id, occurred_at);

-- Every drawn search, shape included: where people are willing to work is the
-- thing to show employers and the map of where to look for supply next.
create table if not exists searches (
    id bigserial primary key,
    occurred_at timestamptz not null default now(),
    visitor_id uuid,
    session_id uuid,
    shape geometry(Polygon, 4326) not null,
    area_sq_mi double precision,
    vertex_count int,
    keyword text,
    trigger text,
    result_count int not null,
    exact_count int not null,
    town_count int not null,
    took_ms int
);

create index if not exists searches_time_idx on searches (occurred_at desc);
create index if not exists searches_shape_idx on searches using gist (shape);
