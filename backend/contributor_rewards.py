"""Capped, auditable contributor rewards for verified paid predictor subscriptions.

Every external payment creates at most one eligible reward period. Once that
period ends, 5% of its locked UGX price is divided across unique user-selected
picks. Picks without an approved attributable rule retain their share for the
platform. All accounting uses integer UGX; PC is a display denomination only.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fractions import Fraction

from . import db

RATE_BPS = 500
COINS_PER_UGX = 100


def _now():
    return datetime.now(timezone.utc).isoformat()


def enabled():
    return os.getenv("PREDICTOR_CONTRIBUTOR_REWARDS_ENABLED", "false").lower().strip() in (
        "1", "true", "yes", "on"
    )


def ensure_tables(con):
    # Also initialize attribution before the first submission is received.
    con.execute("""
        CREATE TABLE IF NOT EXISTS pattern_partner_attributions (
            submission_id INTEGER PRIMARY KEY,
            contributor_account_id INTEGER NOT NULL,
            strategy_family TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            approved_by INTEGER NOT NULL,
            activated_at TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS contributor_reward_periods (
            purchase_request_id INTEGER PRIMARY KEY,
            buyer_account_id INTEGER NOT NULL,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            purchase_ugx INTEGER NOT NULL CHECK(purchase_ugx>0),
            reward_cap_ugx INTEGER NOT NULL CHECK(reward_cap_ugx>=0),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','settled','cancelled')),
            settled_at TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS contributor_period_due ON contributor_reward_periods(status,end_at)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS contributor_reward_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT NOT NULL UNIQUE,
            contributor_account_id INTEGER,
            purchase_request_id INTEGER NOT NULL,
            amount_ugx INTEGER NOT NULL CHECK(amount_ugx<>0),
            entry_type TEXT NOT NULL CHECK(entry_type IN ('contributor_reward','contributor_reversal')),
            pick_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            note TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS contributor_reward_owner ON contributor_reward_ledger(contributor_account_id,id DESC)")
    con.execute("CREATE INDEX IF NOT EXISTS contributor_reward_source ON contributor_reward_ledger(purchase_request_id)")


def _as_utc(value):
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).astimezone(timezone.utc)


def reserve_verified_purchase(con, purchase_id, buyer_id, start_at, end_at, plan_code):
    """Called within VIP approval's transaction, never for wallet purchases."""
    if not enabled():
        return
    row=con.execute("""
        SELECT status,expected_ugx,COALESCE(buyer_account_id,client_account_id) AS buyer
        FROM purchase_requests WHERE id=?
    """,(purchase_id,)).fetchone()
    if not row or row["status"]!="approved" or row["buyer"]!=int(buyer_id):
        raise ValueError("Contributor rewards require independently verified approved payment.")
    price=int(row["expected_ugx"] or 0)
    if price<=0:
        raise ValueError("Cannot reward an unpriced subscription.")
    start=_as_utc(start_at)
    end=_as_utc(end_at) if end_at else start+timedelta(days=30)
    if end<=start:
        raise ValueError("Reward period must end after its start.")
    cap=(price*RATE_BPS)//10000
    con.execute("""
        INSERT OR IGNORE INTO contributor_reward_periods(
          purchase_request_id,buyer_account_id,start_at,end_at,purchase_ugx,reward_cap_ugx
        ) VALUES(?,?,?,?,?,?)
    """,(int(purchase_id),int(buyer_id),start.isoformat(),end.isoformat(),price,cap))


def _allocations(con,period):
    buyer=con.execute("SELECT user_key FROM accounts WHERE id=? AND role='client'",
                      (period["buyer_account_id"],)).fetchone()
    if not buyer:
        return {}, 0
    selected=con.execute("""
        SELECT p.id, a.contributor_account_id
        FROM user_predictions p
        LEFT JOIN prediction_supports s
          ON s.user_id=p.user_id AND s.season=p.season
         AND s.matchday=p.matchday AND s.prediction_key=p.prediction_key
        LEFT JOIN pattern_partner_attributions a
          ON a.strategy_family=s.strategy_family AND a.rule_id=s.rule_id
         AND a.activated_at<=p.selected_at
        LEFT JOIN accounts contributor
          ON contributor.id=a.contributor_account_id
        WHERE p.user_id=? AND p.selected=1 AND p.selected_at>=?
          AND p.selected_at<? AND p.selected_at IS NOT NULL
    """,(buyer["user_key"],period["start_at"],period["end_at"])).fetchall()
    # A left join can duplicate support rows. Count each selected pick once.
    owners=defaultdict(set)
    for row in selected:
        owners[int(row["id"])]
        if row["contributor_account_id"] is not None:
            owner=int(row["contributor_account_id"])
            if owner!=int(period["buyer_account_id"]):
                valid=con.execute("SELECT 1 FROM accounts WHERE id=? AND role='client' AND status='active'",(owner,)).fetchone()
                if valid:
                    owners[int(row["id"])].add(owner)
    total=len(owners)
    if not total or period["reward_cap_ugx"]<=0:
        return {},total
    weights=defaultdict(Fraction)
    contributions=defaultdict(int)
    for people in owners.values():
        if not people:
            continue
        piece=Fraction(1,total*len(people))
        for account_id in people:
            weights[account_id]+=piece
            contributions[account_id]+=1
    # Floor, not round upward: unused fractions and unattributed shares remain
    # with the platform. No combination can exceed the original 5% cap.
    credits={owner:(int(period["reward_cap_ugx"]*share),contributions[owner])
             for owner,share in weights.items()}
    return {k:v for k,v in credits.items() if v[0]>0},total


def settle_due(limit=100):
    """Safe idempotent admin-triggered settlement after the entire period ends."""
    if not enabled():
        raise ValueError("Contributor payouts are disabled.")
    init=db.connect()
    init.close()
    from . import referral_wallet
    con=referral_wallet.connect()
    completed=0
    credited=0
    try:
        con.execute("BEGIN IMMEDIATE")
        periods=con.execute("""
            SELECT p.* FROM contributor_reward_periods p
            JOIN purchase_requests r ON r.id=p.purchase_request_id
            WHERE p.status='pending' AND p.end_at<=? AND r.status='approved'
            ORDER BY p.end_at,p.purchase_request_id LIMIT ?
        """,(_now(),max(1,min(int(limit),100)))).fetchall()
        for period in periods:
            amounts,total=_allocations(con,period)
            for account_id,(value,picks) in sorted(amounts.items()):
                con.execute("""
                    INSERT OR IGNORE INTO contributor_reward_ledger(
                      event_key,contributor_account_id,purchase_request_id,amount_ugx,
                      entry_type,pick_count,created_at,note
                    ) VALUES(?,?,?,?,?,?,?,?)
                """,(f"contributor:{period['purchase_request_id']}:{account_id}",
                     account_id,period["purchase_request_id"],value,
                     "contributor_reward",picks,_now(),
                     f"5% pool shared across {total} distinct subscriber-selected picks"))
                credited+=value
            con.execute("""
                UPDATE contributor_reward_periods
                SET status='settled',settled_at=? WHERE purchase_request_id=? AND status='pending'
            """,(_now(),period["purchase_request_id"]))
            completed+=1
        con.commit()
        return {"settled_periods":completed,"credited_ugx":credited,
                "credited_coins":credited*COINS_PER_UGX}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def reverse_purchase(con,purchase_id,admin_id,reason):
    """Apply refund reversal in the same admin transaction, including after payout."""
    period=con.execute("""
        SELECT * FROM contributor_reward_periods WHERE purchase_request_id=?
    """,(purchase_id,)).fetchone()
    if not period:
        raise ValueError("No contributor reward period exists for this purchase.")
    if period["status"]=="cancelled":
        raise ValueError("Contributor rewards already reversed for this purchase.")
    rows=con.execute("""
        SELECT * FROM contributor_reward_ledger
        WHERE purchase_request_id=? AND entry_type='contributor_reward'
    """,(purchase_id,)).fetchall()
    for row in rows:
        con.execute("""
            INSERT INTO contributor_reward_ledger(
              event_key,contributor_account_id,purchase_request_id,amount_ugx,
              entry_type,pick_count,created_at,note
            ) VALUES(?,?,?,?,?,?,?,?)
        """,(f"contributor_reversal:{purchase_id}:{row['contributor_account_id']}",
             row["contributor_account_id"],purchase_id,-int(row["amount_ugx"]),
             "contributor_reversal",row["pick_count"],_now(),reason))
    con.execute("""
        UPDATE contributor_reward_periods SET status='cancelled' WHERE purchase_request_id=?
    """,(purchase_id,))
    con.execute("""
        INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at)
        VALUES(?,?,'CONTRIBUTOR_REWARDS_REVERSED',?,?)
    """,(admin_id,period["buyer_account_id"],f"purchase:{purchase_id}",_now()))
    return len(rows)


def admin_status():
    from . import referral_wallet
    con=referral_wallet.connect()
    try:
        counts=[dict(x) for x in con.execute("""
            SELECT status,COUNT(*) AS periods,COALESCE(SUM(reward_cap_ugx),0) AS reserved_ugx
            FROM contributor_reward_periods GROUP BY status
        """)]
        due=con.execute("""
            SELECT COUNT(*) FROM contributor_reward_periods
            WHERE status='pending' AND end_at<=?
        """,(_now(),)).fetchone()[0]
        return {"enabled":enabled(),"rate_bps":RATE_BPS,"coins_per_ugx":COINS_PER_UGX,
                "statuses":counts,"due_periods":int(due)}
    finally:
        con.close()
