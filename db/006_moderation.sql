-- 'removed' is a takedown: an admin pulled it, the employer closed it, or the
-- employer opted out. Ingest upserts never touch status, so it sticks.
alter table jobs drop constraint if exists jobs_status_check;
alter table jobs add constraint jobs_status_check
    check (status in ('live', 'pending', 'rejected', 'removed'));

-- Only the hash is stored; the link with the token goes to the employer once.
alter table jobs add column if not exists manage_token_hash text;
create unique index if not exists jobs_manage_token_idx on jobs (manage_token_hash)
    where manage_token_hash is not null;

create table if not exists job_reports (
    id bigserial primary key,
    job_id bigint not null references jobs (id) on delete cascade,
    reason text not null check (reason in ('scam', 'filled', 'wrong_location', 'other')),
    details text,
    created_at timestamptz not null default now(),
    resolved_at timestamptz
);
create index if not exists job_reports_open_idx on job_reports (created_at desc) where resolved_at is null;

-- Rate limiting for public forms. The address is a salted hash, never stored raw.
create table if not exists form_hits (
    id bigserial primary key,
    form text not null,
    client_hash text not null,
    created_at timestamptz not null default now()
);
create index if not exists form_hits_lookup_idx on form_hits (form, client_hash, created_at desc);
