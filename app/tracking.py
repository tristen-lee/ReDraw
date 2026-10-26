import json
import uuid
from urllib.parse import urlsplit

from psycopg.types.json import Jsonb

# Anything not on this list is dropped, so a typo in the frontend shows up as
# a missing number instead of a new event nobody knows to query.
EVENT_NAMES = {
    "page_view", "page_leave", "js_error",
    "draw_start", "draw_cancel", "draw_too_short", "shape_cleared", "keyword_cleared",
    "marker_click", "card_click", "job_open", "show_more",
    "job_view", "apply_click", "report_open",
    "post_start", "post_submitted", "post_failed",
    "cta_click", "outbound_click",
}
DEVICES = {"phone", "tablet", "desktop"}
MAX_PROPS_BYTES = 2000

INSERT_EVENT = """
insert into events (visitor_id, session_id, name, path, referrer_host,
                    utm_source, utm_medium, utm_campaign, device, props)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

INSERT_SEARCH = """
insert into searches (visitor_id, session_id, shape, area_sq_mi, vertex_count, keyword, trigger,
                      result_count, exact_count, town_count, took_ms)
select %(visitor)s, %(session)s, g, ST_Area(g::geography) / 2589988.11, %(vertices)s, %(keyword)s, %(trigger)s,
       %(results)s, %(exact)s, %(town)s, %(took)s
from (select ST_MakeValid(ST_GeomFromText(%(wkt)s, 4326)) as g) s
where GeometryType(g) = 'POLYGON'
"""


def as_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return None


def clip(value, length):
    return str(value)[:length] if value else None


def referrer_host(referrer, own_host):
    host = urlsplit(referrer or "").hostname
    if not host or host == own_host:
        return None
    return host.removeprefix("www.")[:120]


def record_event(cur, payload, own_host):
    name = payload.get("name")
    if name not in EVENT_NAMES:
        return False
    props = payload.get("props") if isinstance(payload.get("props"), dict) else {}
    if len(json.dumps(props)) > MAX_PROPS_BYTES:
        props = {"truncated": True}
    device = payload.get("device") if payload.get("device") in DEVICES else None
    cur.execute(INSERT_EVENT, (
        as_uuid(payload.get("visitor")),
        as_uuid(payload.get("session")),
        name,
        clip(payload.get("path"), 300),
        referrer_host(payload.get("referrer"), own_host),
        clip(payload.get("utm_source"), 100),
        clip(payload.get("utm_medium"), 100),
        clip(payload.get("utm_campaign"), 100),
        device,
        Jsonb(props),
    ))
    return True


TRIGGERS = {"draw", "keyword"}


def record_search(cur, *, visitor, session, wkt, vertices, keyword, trigger, jobs, took_ms):
    precisions = [location.precision for job in jobs for location in job.locations]
    cur.execute(INSERT_SEARCH, {
        "visitor": as_uuid(visitor),
        "session": as_uuid(session),
        "wkt": wkt,
        "vertices": vertices,
        "keyword": clip(keyword, 200),
        "trigger": trigger if trigger in TRIGGERS else None,
        "results": len(jobs),
        "exact": precisions.count("exact"),
        "town": precisions.count("town"),
        "took": took_ms,
    })


# ---------------------------------------------------------------------------
# Dashboard

def rows(cur, sql, params):
    cur.execute(sql, params)
    names = [column.name for column in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def one(cur, sql, params):
    return rows(cur, sql, params)[0]


WINDOW = "occurred_at > now() - make_interval(days => %(days)s)"


def stats(cur, days):
    p = {"days": days}

    overview = one(cur, f"""
        select
            (select count(distinct visitor_id) from events where name = 'page_view' and {WINDOW}) as visitors,
            (select count(distinct session_id) from events where name = 'page_view' and {WINDOW}) as sessions,
            (select count(*) from events where name = 'page_view' and {WINDOW}) as page_views,
            (select count(*) from searches where {WINDOW}) as searches,
            (select count(distinct visitor_id) from searches where {WINDOW}) as searchers,
            (select count(*) from events where name = 'job_view' and {WINDOW}) as job_views,
            (select count(*) from job_clicks where clicked_at > now() - make_interval(days => %(days)s)) as apply_clicks,
            (select count(*) from (
                select visitor_id from events
                where name = 'page_view' and {WINDOW}
                group by visitor_id having count(distinct occurred_at::date) > 1
            ) r) as returning_visitors
    """, p)

    # Per session, did it reach each step. Sessions are the unit because one
    # visitor coming back three times is three chances to convert.
    funnel = one(cur, f"""
        with s as (
            select session_id,
                   bool_or(name = 'draw_start') as drew,
                   bool_or(name in ('job_open', 'job_view')) as opened,
                   bool_or(name = 'apply_click') as applied
            from events where {WINDOW} and session_id is not null
            group by session_id
        ), q as (
            select session_id, max(result_count) as best from searches where {WINDOW} group by session_id
        )
        select count(*) as sessions,
               count(*) filter (where drew) as drew,
               count(*) filter (where q.session_id is not null) as searched,
               count(*) filter (where q.best > 0) as got_results,
               count(*) filter (where opened) as opened_job,
               count(*) filter (where applied) as clicked_apply
        from s left join q using (session_id)
    """, p)

    daily = rows(cur, """
        with d as (
            select generate_series((now() - make_interval(days => %(days)s - 1))::date, now()::date, '1 day')::date as day
        )
        select d.day,
               (select count(distinct visitor_id) from events e
                 where e.name = 'page_view' and e.occurred_at::date = d.day) as visitors,
               (select count(*) from searches s where s.occurred_at::date = d.day) as searches,
               (select count(*) from job_clicks c where c.clicked_at::date = d.day) as apply_clicks
        from d order by d.day
    """, p)

    # Attribution is whatever brought the session in: its first event.
    sources = rows(cur, f"""
        with first as (
            select distinct on (session_id) session_id,
                   coalesce(utm_source, referrer_host, 'direct') as source,
                   utm_campaign as campaign
            from events where {WINDOW} and session_id is not null
            order by session_id, occurred_at
        )
        select f.source, f.campaign,
               count(*) as sessions,
               count(*) filter (where exists (select 1 from searches s where s.session_id = f.session_id)) as searched,
               count(*) filter (where exists (select 1 from events e where e.session_id = f.session_id
                                              and e.name = 'apply_click')) as applied
        from first f group by 1, 2 order by sessions desc limit 25
    """, p)

    devices = rows(cur, f"""
        select coalesce(device, 'unknown') as device, count(distinct session_id) as sessions
        from events where name = 'page_view' and {WINDOW} group by 1 order by 2 desc
    """, p)

    pages = rows(cur, f"""
        select v.path, v.views, round(l.median_seconds) as median_seconds
        from (select path, count(*) as views from events
              where name = 'page_view' and {WINDOW} group by path) v
        left join (select path, percentile_cont(0.5) within group (order by (props->>'seconds')::numeric) as median_seconds
                   from events where name = 'page_leave' and {WINDOW} group by path) l using (path)
        order by v.views desc limit 20
    """, p)

    searching = one(cur, f"""
        select count(*) as searches,
               count(*) filter (where trigger = 'draw') as shapes_drawn,
               count(distinct session_id) as searching_sessions,
               round(percentile_cont(0.5) within group (order by area_sq_mi)::numeric, 1) as median_area_sq_mi,
               round(percentile_cont(0.5) within group (order by result_count)::numeric) as median_results,
               count(*) filter (where result_count = 0) as zero_results,
               count(*) filter (where keyword is not null) as with_keyword,
               round(avg(took_ms)) as avg_ms
        from searches where {WINDOW}
    """, p)

    keywords = rows(cur, f"""
        select lower(keyword) as keyword, count(*) as searches,
               round(avg(result_count)) as avg_results,
               count(*) filter (where result_count = 0) as zero_results
        from searches where keyword is not null and {WINDOW}
        group by 1 order by searches desc limit 25
    """, p)

    jobs = rows(cur, f"""
        select j.id, j.title, coalesce(j.employer_name_raw, '') as employer, j.source,
               count(*) filter (where e.name = 'job_view') as views,
               count(*) filter (where e.name = 'apply_click') as applies
        from events e join jobs j on j.id = (e.props->>'job_id')::bigint
        where e.name in ('job_view', 'apply_click') and e.occurred_at > now() - make_interval(days => %(days)s)
        group by j.id order by views desc, applies desc limit 25
    """, p)

    errors = rows(cur, f"""
        select occurred_at, path, props->>'message' as message, props->>'source' as source
        from events where name = 'js_error' and {WINDOW}
        order by occurred_at desc limit 20
    """, p)

    shapes = rows(cur, f"""
        select ST_AsGeoJSON(shape, 5)::json as geometry, result_count, keyword, occurred_at
        from searches where {WINDOW}
        order by occurred_at desc limit 500
    """, p)

    return {
        "days": days,
        "overview": overview,
        "funnel": funnel,
        "daily": daily,
        "sources": sources,
        "devices": devices,
        "pages": pages,
        "searching": searching,
        "keywords": keywords,
        "jobs": jobs,
        "errors": errors,
        "shapes": shapes,
    }
