"""Private admin-only membership analytics backed by persistent SQLite.

"Online" means authenticated client accounts with a request or heartbeat in
the last 5 minutes, NOT anonymous visitors or live browser connections.
Historical daily activity starts at adoption of this feature.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import access, purchase_requests, referral_wallet

EAT = timezone(timedelta(hours=3))
RETENTION_DAYS = 90


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def snapshot(now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = now.astimezone(EAT).date()
    midnight = datetime(today.year, today.month, today.day, tzinfo=EAT)
    month_start = datetime(today.year, today.month, 1, tzinfo=EAT)

    # Initialize incremental schemas before querying optional billing tables.
    pc = purchase_requests.connect()
    pc.close()
    con = referral_wallet.connect()
    try:
        basic = con.execute("""
            SELECT
                COUNT(*) AS signups_total,
                COALESCE(SUM(CASE WHEN created_at>=? THEN 1 ELSE 0 END),0) AS signups_today,
                COALESCE(SUM(CASE WHEN created_at>=? THEN 1 ELSE 0 END),0) AS signups_7d,
                COALESCE(SUM(CASE WHEN created_at>=? THEN 1 ELSE 0 END),0) AS signups_month,
                COALESCE(SUM(CASE WHEN status='active' AND EXISTS(
                    SELECT 1 FROM subscriptions sub WHERE sub.account_id=accounts.id
                        AND sub.status='active'
                        AND (sub.expires_at>? OR
                            (sub.plan_code='lifetime' AND sub.expires_at IS NULL))
                ) THEN 1 ELSE 0 END),0) AS active_vip,
                COALESCE(SUM(CASE WHEN status='active' AND NOT EXISTS(
                    SELECT 1 FROM subscriptions sub WHERE sub.account_id=accounts.id
                        AND sub.status='active'
                        AND (sub.expires_at>? OR
                            (sub.plan_code='lifetime' AND sub.expires_at IS NULL))
                ) THEN 1 ELSE 0 END),0) AS free_members
            FROM accounts WHERE role='client'
        """,(_utc(midnight),_utc(now-timedelta(days=7)),_utc(month_start),
             _utc(now),_utc(now))).fetchone()

        activity=con.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN last_seen>=? THEN 1 ELSE 0 END),0) AS online_now,
                COALESCE(SUM(CASE WHEN last_seen>=? THEN 1 ELSE 0 END),0) AS active_24h,
                COALESCE(SUM(CASE WHEN last_seen>=? THEN 1 ELSE 0 END),0) AS active_7d
            FROM member_activity ma JOIN accounts a ON a.id=ma.account_id
            WHERE a.role='client' AND a.status='active'
        """,(_utc(now-timedelta(minutes=5)),_utc(now-timedelta(hours=24)),
             _utc(now-timedelta(days=7)))).fetchone()

        external=con.execute("""
            SELECT COUNT(*) AS verified_external_purchases,
                   COALESCE(SUM(expected_ugx),0) AS gross_external_paid_ugx
            FROM purchase_requests
            WHERE status='approved' AND expected_ugx>0
        """).fetchone()
        wallet=con.execute("""
            SELECT COUNT(*) AS wallet_vip_purchases,
                   COALESCE(SUM(amount_ugx),0) AS wallet_vip_spent_ugx
            FROM referral_wallet_spends
        """).fetchone()
        referrals=con.execute("""
            SELECT COALESCE(SUM(CASE WHEN referred_by IS NOT NULL THEN 1 ELSE 0 END),0) AS referred_signups,
                   COALESCE(SUM(CASE WHEN referred_by IS NOT NULL AND vip_converted_at IS NOT NULL THEN 1 ELSE 0 END),0) AS referral_vip_conversions,
                   COALESCE(SUM(visits),0) AS referral_link_visits
            FROM referral_profiles
        """).fetchone()

        beginning=today-timedelta(days=13)
        signup_rows=con.execute("""
            SELECT DATE(datetime(created_at,'+3 hours')) AS day,COUNT(*) AS n
            FROM accounts
            WHERE role='client' AND created_at>=?
            GROUP BY day
        """,(_utc(datetime(beginning.year,beginning.month,beginning.day,tzinfo=EAT)),)).fetchall()
        active_rows=con.execute("""
            SELECT activity_day AS day,COUNT(*) AS n FROM member_daily_activity
            WHERE activity_day>=? GROUP BY activity_day
        """,(beginning.isoformat(),)).fetchall()
        signups={row["day"]:int(row["n"]) for row in signup_rows}
        active={row["day"]:int(row["n"]) for row in active_rows}
        trend=[]
        for i in range(14):
            day=(beginning+timedelta(days=i)).isoformat()
            trend.append({"date":day,"signups":signups.get(day,0),"active":active.get(day,0)})

        result={
            "as_of":_utc(now),
            "timezone":"EAT (UTC+03:00)",
            "online_definition":"Distinct signed-in, active member accounts with activity within 5 minutes",
            "history_note":"Daily activity tracking starts when analytics was deployed; earlier days may be incomplete.",
            "trend":trend,
        }
        for data in (basic,activity,external,wallet,referrals):
            result.update({key:int(data[key] or 0) for key in data.keys()})
        return result
    finally:
        con.close()
