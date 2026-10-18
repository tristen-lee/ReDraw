-- Ingested jobs are live on arrival; anything an employer submits waits for review.
alter table jobs add column if not exists status text not null default 'live'
    check (status in ('live', 'pending', 'rejected'));

alter table jobs add column if not exists contact_email text;
alter table jobs add column if not exists submitted_by text;
alter table jobs add column if not exists reviewed_at timestamptz;
alter table jobs add column if not exists review_note text;

create index if not exists jobs_pending_idx on jobs (status, first_seen_at desc)
    where status = 'pending';

alter table employers add column if not exists contact_email text;
