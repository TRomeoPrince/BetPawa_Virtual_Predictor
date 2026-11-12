"""Public submissions and audited, verified contributor-rule attribution.

A submission is never a prediction, payout, or subscription entitlement.
Only validated and deployed rules can be linked to verified member accounts.
Legacy Lifetime VIP grants remain untouched; no new VIP is awarded.
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
    con.execute("""
        CREATE TABLE IF NOT EXISTS pattern_partner_attributions(
            submission_id INTEGER PRIMARY KEY,
            contributor_account_id INTEGER NOT NULL,
            strategy_family TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            approved_by INTEGER NOT NULL,
            activated_at TEXT NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS partner_rule_attribution ON pattern_partner_attributions(strategy_family,rule_id)")
    con.execute("CREATE INDEX IF NOT EXISTS partner_owner_attribution ON pattern_partner_attributions(contributor_account_id)")
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
            SELECT p.id,p.applicant_name,p.email,p.username,p.league,p.market,p.pattern_details,
                   p.evidence_url,p.submitted_at,p.status,p.review_note,p.reviewed_at,
                   p.reviewed_by,p.rewarded_at,p.rewarded_account_id,
                   a.strategy_family AS attributed_family,a.rule_id AS attributed_rule
            FROM pattern_partner_submissions p
            LEFT JOIN pattern_partner_attributions a ON a.submission_id=p.id
            ORDER BY CASE p.status WHEN 'pending' THEN 0 WHEN 'accepted' THEN 1 ELSE 2 END,p.id DESC
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


def activate_contributor(submission_id, admin_id, username, contributor_verified,
                         strategy_family, rule_id, allowed_rules):
    """Link one verified member to an approved, actually deployed private rule.

    This is not a subscription or cash grant. Coin rewards are separately
    capped against paid subscriptions and deduplicated selected picks.
    """
    if not contributor_verified:
        raise ValueError("Independently verify contributor ownership before activation.")
    username=(username or "").strip()
    family=(strategy_family or "").strip()
    rule=(rule_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}",username):
        raise ValueError("Enter the contributor's existing member username.")
    if not family or not rule or (family,rule) not in allowed_rules:
        raise ValueError("Choose an existing deployed rule from the private strategy catalog.")
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        item=con.execute("SELECT * FROM pattern_partner_submissions WHERE id=?",(submission_id,)).fetchone()
        if not item or item["status"]!="accepted":
            raise ValueError("The pattern must be accepted and adopted, and not already activated.")
        account=con.execute(
            "SELECT id,role,status,email FROM accounts WHERE lower(username)=lower(?)",(username,)
        ).fetchone()
        if not account or account["role"]!="client" or account["status"]!="active":
            raise ValueError("An active registered member account is required.")
        if not account["email"] or account["email"].lower()!=item["email"]:
            raise ValueError("The account email must match the contributor's verified submission email.")
        now=_now()
        con.execute("""
            INSERT INTO pattern_partner_attributions(
              submission_id,contributor_account_id,strategy_family,rule_id,approved_by,activated_at
            ) VALUES(?,?,?,?,?,?)
        """,(submission_id,int(account["id"]),family,rule,int(admin_id),now))
        con.execute("""
            UPDATE pattern_partner_submissions SET status='rewarded',
              rewarded_account_id=?,rewarded_at=? WHERE id=? AND status='accepted'
        """,(int(account["id"]),now,submission_id))
        con.execute("""
            INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at)
            VALUES(?,?,'PATTERN_CONTRIBUTOR_ACTIVATED',?,?)
        """,(admin_id,int(account["id"]),f"submission:{submission_id};rule:{family}/{rule}",now))
        con.commit()
        return {"status":"active","account_id":int(account["id"]),
                "submission_id":int(submission_id),"strategy_family":family,"rule_id":rule}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
