alter table jobs add column if not exists is_remote boolean not null default false;

create index if not exists jobs_remote_idx on jobs (is_remote) where is_remote;
