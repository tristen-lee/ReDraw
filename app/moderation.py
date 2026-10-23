import hashlib
import os
import secrets

from app.pages import slugify

LISTING_DAYS = 30


def client_hash(request):
    # Render sits behind Cloudflare, which puts the real client address here.
    address = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        or (request.client.host if request.client else "unknown")
    )
    salt = os.environ.get("ADMIN_TOKEN", "")
    return hashlib.sha256(f"{salt}:{address}".encode()).hexdigest()[:32]


def allow(cur, form, request, limit, window="1 hour"):
    who = client_hash(request)
    cur.execute(
        "select count(*) from form_hits where form = %s and client_hash = %s and created_at > now() - %s::interval",
        (form, who, window),
    )
    if cur.fetchone()[0] >= limit:
        return False
    cur.execute("insert into form_hits (form, client_hash) values (%s, %s)", (form, who))
    return True


def new_manage_token():
    token = secrets.token_urlsafe(24)
    return token, hash_token(token)


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def find_by_token(cur, token):
    cur.execute(
        """
        select j.id, j.title, j.employer_name_raw, j.status, j.expired_at, j.date_closes,
               (select raw_location from job_locations l where l.job_id = j.id order by l.id limit 1)
        from jobs j where j.manage_token_hash = %s and j.source = 'direct'
        """,
        (hash_token(token),),
    )
    row = cur.fetchone()
    if row is None:
        return None
    id_, title, employer, status, expired_at, date_closes, place = row
    return {
        "id": id_, "title": title, "employer": employer, "place": place,
        "status": "expired" if status == "live" and expired_at else status,
        "date_closes": date_closes,
    }


def close(cur, job_id, note):
    cur.execute(
        """
        update jobs set status = 'removed', expired_at = coalesce(expired_at, now()),
               review_note = %s, updated_at = now()
        where id = %s and status in ('live', 'pending')
        returning id
        """,
        (note, job_id),
    )
    return cur.fetchone() is not None


def renew(cur, job_id):
    cur.execute(
        """
        update jobs set expired_at = null, date_closes = now() + %s * interval '1 day', updated_at = now()
        where id = %s and status = 'live'
        returning date_closes
        """,
        (LISTING_DAYS, job_id),
    )
    row = cur.fetchone()
    return row[0] if row else None


def report(cur, job_id, reason, details):
    cur.execute("select 1 from jobs where id = %s and status = 'live'", (job_id,))
    if cur.fetchone() is None:
        return False
    cur.execute(
        "insert into job_reports (job_id, reason, details) values (%s, %s, %s)",
        (job_id, reason, details or None),
    )
    return True


def open_reports(cur):
    cur.execute(
        """
        select r.id, r.job_id, r.reason, r.details, r.created_at, j.title, j.employer_name_raw, j.source,
               count(*) over (partition by r.job_id)
        from job_reports r join jobs j on j.id = r.job_id
        where r.resolved_at is null
        order by r.created_at desc
        limit 200
        """
    )
    return [
        {
            "id": row[0], "job_id": row[1], "reason": row[2], "details": row[3],
            "reported_at": row[4].isoformat(), "title": row[5], "employer": row[6],
            "source": row[7], "reports_on_job": row[8],
        }
        for row in cur.fetchall()
    ]


def resolve_reports(cur, job_id):
    cur.execute("update job_reports set resolved_at = now() where job_id = %s and resolved_at is null", (job_id,))


def remove_job(cur, job_id, note):
    removed = close(cur, job_id, note or "removed by admin")
    resolve_reports(cur, job_id)
    return removed


# Honors an employer's request to be left out: future crawls skip them and
# everything already listed comes down. Federal listings have no employer row,
# so the raw name is matched too.
def opt_out(cur, name):
    cur.execute(
        "update employers set opted_out = true, updated_at = now() where lower(name) = lower(%s) returning id",
        (name,),
    )
    if cur.fetchone() is None:
        cur.execute(
            """
            insert into employers (name, slug, opted_out, notes) values (%s, %s, true, 'opted out')
            on conflict (slug) do update set opted_out = true, updated_at = now()
            """,
            (name, slugify(name)),
        )
    cur.execute(
        """
        update jobs set status = 'removed', expired_at = coalesce(expired_at, now()),
               review_note = 'employer opted out', updated_at = now()
        where status in ('live', 'pending')
          and (lower(employer_name_raw) = lower(%s)
               or employer_id in (select id from employers where lower(name) = lower(%s)))
        """,
        (name, name),
    )
    return cur.rowcount


def sweep(cur):
    cur.execute(
        """
        update jobs set expired_at = now(), updated_at = now()
        where source = 'direct' and status = 'live' and expired_at is null and date_closes < now()
        """
    )
    expired = cur.rowcount
    cur.execute("delete from form_hits where created_at < now() - interval '2 days'")
    return expired
