-- One row per apply click that reached an employer. No IP, no user agent, no
-- identifier: the only question this answers is how many people a posting sent.
create table if not exists job_clicks (
    id bigserial primary key,
    job_id bigint not null references jobs (id) on delete cascade,
    clicked_at timestamptz not null default now()
);

create index if not exists job_clicks_job_idx on job_clicks (job_id, clicked_at desc);
