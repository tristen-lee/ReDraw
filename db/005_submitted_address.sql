-- What the employer typed, kept so an address the geocoder missed can be placed
-- by hand. A pending job with no job_locations row is one still waiting on that.
alter table jobs add column if not exists submitted_address text;
