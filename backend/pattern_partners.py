"""Public pattern partner applications and auditable, manually approved Lifetime VIP rewards.

An application is NEVER a verified prediction, a subscription, or entitlement.
Admin explicitly accepts/adopts a pattern before rewarding a verified member.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from . import growth


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect():
    con=growth.connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS pattern_partner_submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applicant_name TEXT NOT NULL,
            email TEXT NOT NULL,
            username TEXT,
            league TEXT NOT NULL,
            market TEXT NOT NULL,
            pattern_details TEXT NOT NULL,
            evidence_url TEXT,
            submitted_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','accepted','rejected','rewarded')),
            review_note TEXT,
            reviewed_at TEXT,
            reviewed_by INTEGER,
            rewarded_account_id INTEGER,
            rewarded_at TEXT,
            submission_digest TEXT NOT NULL UNIQUE
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS partner_review_queue ON pattern_partner_submissions(status,id DESC)")
    con.execute("CREATE INDEX IF NOT EXISTS partner_email_time ON pattern_partner_submissions(email,submitted_at)")
    con.commit()
    return con


def submit(name, email, username, league, market, details, evidence_url, age_confirmed):
    name=(name or "").strip()
    email=(email or "").strip().lower()
    username=(username or "").strip()
    league=(league or "").strip().lower()
    market=(market or "").strip().lower()
    details=(details or "").strip()
    evidence_url=(evidence_url or "").strip()
    if not age_confirmed:
        raise ValueError("You must confirm that you are at least 25 years old.")
    if not 3<=len(name)<=100 or any(ord(x)<32 for x in name):
        raise ValueError("Enter your name (3–100 characters).")
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,200}\.[^@\s]{2,}",email):
        raise ValueError("Enter a valid email address.")
    if username and not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}",username):
        raise ValueError("Enter a valid existing member username or leave it blank.")
    if league not in ("epl","dutch","both"):
        raise ValueError("Select the EPL, Dutch league, or both.")
    if market not in ("overs","unders","btts","wins","multiple"):
        raise ValueError("Choose a valid pattern market.")
    if not 60<=len(details)<=5000 or any(ord(x)==0 for x in details):
        raise ValueError("Describe your pattern, supporting results and test method (60–5,000 characters).")
    if evidence_url:
        u=urlparse(evidence_url)
        if len(evidence_url)>400 or u.scheme!="https" or not u.hostname or u.username or u.password:
            raise ValueError("Evidence must be a valid HTTPS link.")
    digest=hashlib.sha256((email+"\n"+details.casefold()).encode("utf-8")).hexdigest()
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        recent=con.execute("SELECT COUNT(*) FROM pattern_partner_submissions WHERE email=? AND submitted_at>?",
                           (email,(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat())).fetchone()[0]
        if recent>=3:
            raise ValueError("Too many pattern submissions. Please try again tomorrow.")
        existing=con.execute("SELECT 1 FROM pattern_partner_submissions WHERE submission_digest=?",(digest,)).fetchone()
        if existing:
            raise ValueError("This pattern has already been submitted.")
        cur=con.execute("""
            INSERT INTO pattern_partner_submissions(
                applicant_name,email,username,league,market,pattern_details,
                evidence_url,submitted_at,submission_digest
            ) VALUES(?,?,?,?,?,?,?,?,?)
        """,(name,email,username or None,league,market,details,evidence_url or None,_now(),digest))
        con.commit()
        return int(cur.lastrowid)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def list_submissions():
    con=connect()
    try:
        return [dict(x) for x in con.execute("""
            SELECT id,applicant_name,email,username,league,market,pattern_details,
                   evidence_url,submitted_at,status,review_note,reviewed_at,
                   reviewed_by,rewarded_at,rewarded_account_id
            FROM pattern_partner_submissions
            ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'accepted' THEN 1 ELSE 2 END,id DESC
            LIMIT 200
        """).fetchall()]
    finally:
        con.close()


def review(submission_id, decision, admin_id, verified, review_note):
    if decision not in ("accept","reject"):
        raise ValueError("Select accept or reject.")
    if decision=="accept" and not verified:
        raise ValueError("Confirm that the pattern has been reviewed, validated and adopted before accepting.")
    note=(review_note or "").strip()
    if not 8<=len(note)<=1000:
        raise ValueError("Add a review explanation of 8–1,000 characters.")
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        record=con.execute("SELECT status FROM pattern_partner_submissions WHERE id=?",(submission_id,)).fetchone()
        if not record or record["status"]!="pending":
            raise ValueError("Only pending submissions may be reviewed.")
        con.execute("""
            UPDATE pattern_partner_submissions SET status=?,review_note=?,reviewed_at=?,reviewed_by=?
            WHERE id=? AND status='pending'
        """,("accepted" if decision=="accept" else "rejected",note,_now(),admin_id,submission_id))
        con.commit()
        return "accepted" if decision=="accept" else "rejected"
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def reward_lifetime(submission_id, admin_id, username, contributor_verified):
    """Admin-issued one-time reward to a client with matching verified email.

    Grant subscription and mark rewarded atomically. No automatic rewards for
    pending/rejected submissions or a mismatched customer's email.
    """
    if not contributor_verified:
        raise ValueError("Independently verify contributor ownership before rewarding.")
    username=(username or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}",username):
        raise ValueError("Enter the contributor's existing member username.")
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        item=con.execute("SELECT * FROM pattern_partner_submissions WHERE id=?",(submission_id,)).fetchone()
        if not item or item["status"]!="accepted":
            raise ValueError("The pattern must be accepted and adopted, and not previously rewarded.")
        account=con.execute(
            "SELECT id,role,status,email FROM accounts WHERE lower(username)=lower(?)",(username,)
        ).fetchone()
        if not account or account["role"]!="client" or account["status"]!="active":
            raise ValueError("A registered, active client account is required for the Lifetime VIP reward.")
        if not account["email"] or account["email"].lower()!=item["email"]:
            raise ValueError("The client account email does not match the pattern contributor. Verify identity before issuing the reward.")
        now=_now()
        con.execute("""
            INSERT INTO subscriptions(account_id,plan_code,starts_at,expires_at,status,updated_at)
            VALUES(?,'lifetime',?,NULL,'active',?)
            ON CONFLICT(account_id) DO UPDATE SET
                plan_code='lifetime',starts_at=excluded.starts_at,expires_at=NULL,
                status='active',updated_at=excluded.updated_at
        """,(int(account["id"]),now,now))
        con.execute("""
            UPDATE pattern_partner_submissions SET status='rewarded',
              rewarded_account_id=?,rewarded_at=? WHERE id=? AND status='accepted'
        """,(int(account["id"]),now,submission_id))
        con.execute("""
            INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at)
            VALUES(?,?,'PATTERN_PARTNER_LIFETIME',?,?)
        """,(admin_id,int(account["id"]),f"submission:{submission_id}",now))
        con.commit()
        return {"status":"rewarded","account_id":int(account["id"])}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
