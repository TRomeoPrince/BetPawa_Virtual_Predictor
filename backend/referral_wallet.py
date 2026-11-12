"""Auditable UGX referral commissions and manually processed withdrawals.

Commission policy: 20% for verified purchases occurring within the first 30
elapsed days after a referral's first VERIFIED VIP payment, 15% thereafter.
All amounts are INTEGER Uganda shillings. Round percentages half up.
No money transfer is performed by this application.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from . import growth

MONTH = timedelta(days=30)


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _timestamp(value):
    if not value:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def connect():
    con = growth.connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS referral_wallet_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT NOT NULL UNIQUE,
            referrer_account_id INTEGER,
            referred_account_id INTEGER,
            purchase_request_id INTEGER,
            withdrawal_id INTEGER,
            entry_type TEXT NOT NULL CHECK(entry_type IN ('commission','reversal','payout')),
            amount_ugx INTEGER NOT NULL CHECK(amount_ugx<>0),
            purchase_amount_ugx INTEGER,
            commission_rate_bps INTEGER,
            created_at TEXT NOT NULL,
            note TEXT
        )
    """)
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS referral_one_commission_per_purchase
        ON referral_wallet_ledger(purchase_request_id)
        WHERE entry_type='commission'
    """)
    con.execute("CREATE INDEX IF NOT EXISTS referral_wallet_account_entries ON referral_wallet_ledger(referrer_account_id,id DESC)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS referral_withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            amount_ugx INTEGER NOT NULL CHECK(amount_ugx>0),
            destination_method TEXT NOT NULL,
            destination_details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
              CHECK(status IN ('pending','paid','rejected')),
            requested_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by INTEGER,
            payout_reference TEXT,
            review_note TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS referral_withdrawal_accounts ON referral_withdrawals(account_id,status,id DESC)")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS referral_payout_unique_reference ON referral_withdrawals(payout_reference) WHERE status='paid' AND payout_reference IS NOT NULL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS referral_wallet_spends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            account_id INTEGER,
            plan_code TEXT NOT NULL,
            amount_ugx INTEGER NOT NULL CHECK(amount_ugx>0),
            promo_code TEXT,
            promotion_id INTEGER,
            purchased_at TEXT NOT NULL,
            subscription_expires_at TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS referral_wallet_spends_owner ON referral_wallet_spends(account_id,id DESC)")
    con.commit()
    return con


def _summary_in_transaction(con, account_id):
    entries = con.execute("""
        SELECT
          COALESCE(SUM(amount_ugx),0) AS balance,
          COALESCE(SUM(CASE WHEN entry_type='commission' THEN amount_ugx ELSE 0 END),0) AS earned,
          COALESCE(SUM(CASE WHEN entry_type='reversal' THEN -amount_ugx ELSE 0 END),0) AS reversed,
          COALESCE(SUM(CASE WHEN entry_type='payout' THEN -amount_ugx ELSE 0 END),0) AS withdrawn
        FROM referral_wallet_ledger WHERE referrer_account_id=?
    """, (account_id,)).fetchone()
    reserved = int(con.execute(
        "SELECT COALESCE(SUM(amount_ugx),0) FROM referral_withdrawals WHERE account_id=? AND status='pending'",
        (account_id,),
    ).fetchone()[0])
    spent = int(con.execute(
        "SELECT COALESCE(SUM(amount_ugx),0) FROM referral_wallet_spends WHERE account_id=?",
        (account_id,),
    ).fetchone()[0])
    balance = int(entries["balance"]) - spent
    return {
        "currency": "UGX",
        "earned_ugx": int(entries["earned"]),
        "reversed_ugx": int(entries["reversed"]),
        "withdrawn_ugx": int(entries["withdrawn"]),
        "spent_on_vip_ugx": spent,
        "balance_ugx": balance,
        "reserved_ugx": reserved,
        "available_ugx": max(0, balance-reserved),
    }


def wallet(account_id, limit=50):
    con=connect()
    try:
        owner=con.execute("SELECT id,role,status FROM accounts WHERE id=?",(account_id,)).fetchone()
        if not owner or owner["role"]!="client" or owner["status"]!="active":
            raise ValueError("Member wallet unavailable.")
        result = _summary_in_transaction(con,account_id)
        result["withdrawals_enabled"] = withdrawals_enabled()
        result["minimum_withdrawal_ugx"] = minimum_withdrawal()
        result["entries"] = [
            dict(x) for x in con.execute("""
                SELECT id, entry_type, amount_ugx, purchase_amount_ugx,
                       commission_rate_bps, created_at, purchase_request_id, note
                FROM referral_wallet_ledger WHERE referrer_account_id=?
                ORDER BY id DESC LIMIT ?
            """,(account_id,max(1,min(int(limit),100)))).fetchall()
        ]
        spends = [
            dict(x) for x in con.execute("""
                SELECT id,plan_code,amount_ugx,purchased_at FROM referral_wallet_spends
                WHERE account_id=? ORDER BY id DESC LIMIT ?
            """,(account_id,max(1,min(int(limit),100)))).fetchall()
        ]
        result["entries"].extend({
            "id":x["id"],"entry_type":"vip_wallet_purchase",
            "amount_ugx":-int(x["amount_ugx"]),"created_at":x["purchased_at"],
            "purchase_amount_ugx":x["amount_ugx"],"commission_rate_bps":None,
            "purchase_request_id":None,"note":"VIP "+x["plan_code"]
        } for x in spends)
        result["entries"].sort(key=lambda item:(item["created_at"],item["id"]),reverse=True)
        result["entries"]=result["entries"][:max(1,min(int(limit),100))]
        result["withdrawals"] = [
            dict(x) for x in con.execute("""
                SELECT id, amount_ugx, destination_method, status, requested_at,
                       reviewed_at, payout_reference, review_note
                FROM referral_withdrawals WHERE account_id=?
                ORDER BY id DESC LIMIT 40
            """,(account_id,)).fetchall()
        ]
        return result
    finally:
        con.close()


def withdrawals_enabled():
    return os.getenv("PREDICTOR_REFERRAL_WITHDRAWALS_ENABLED", "false").strip().lower() in ("1","true","yes","on")


def minimum_withdrawal():
    try:
        amount=int(os.getenv("PREDICTOR_REFERRAL_MIN_WITHDRAWAL_UGX", "1000"))
    except ValueError:
        amount=1
    return max(1,amount)


def record_verified_purchase(con, purchase_request_id, buyer_account_id, approved_at=None):
    """Add one commission INSIDE the same transaction that approves a VIP purchase.

    Requires approved payment linked to a signed-in client; ignored on retry,
    unverified/pending claims, self referrals and accounts without attribution.
    Wallet tables must already be initialized before the caller begins its txn.
    """
    purchase=con.execute("""
        SELECT id,buyer_account_id,expected_ugx,status,reviewed_at
        FROM purchase_requests WHERE id=? AND buyer_account_id=?
    """,(purchase_request_id,buyer_account_id)).fetchone()
    if not purchase or purchase["status"]!="approved" or not purchase["reviewed_at"]:
        raise ValueError("Only independently verified approved VIP purchases earn commissions.")
    buyer=con.execute(
        "SELECT referred_by,joined_at FROM referral_profiles WHERE account_id=?",
        (buyer_account_id,),
    ).fetchone()
    if not buyer or buyer["referred_by"] is None:
        return None
    referrer=int(buyer["referred_by"])
    if referrer==int(buyer_account_id):
        return None
    eligible=con.execute(
        "SELECT role FROM accounts WHERE id=?", (referrer,)
    ).fetchone()
    if not eligible or eligible["role"]!="client":
        return None
    if not purchase["expected_ugx"] or int(purchase["expected_ugx"])<=0:
        raise ValueError("Verified VIP purchase does not have a positive amount.")
    now=_timestamp(approved_at or purchase["reviewed_at"])
    if _timestamp(buyer["joined_at"])>now:
        return None
    first=con.execute("""
        SELECT MIN(reviewed_at) AS first_approved FROM purchase_requests
        WHERE buyer_account_id=? AND status='approved' AND reviewed_at IS NOT NULL
    """,(buyer_account_id,)).fetchone()
    first_at=_timestamp(first["first_approved"]) if first and first["first_approved"] else now
    rate=2000 if now < first_at + MONTH else 1500
    amount=int(purchase["expected_ugx"])
    commission=(amount*rate+5000)//10000
    if commission<1:
        return None
    con.execute("""
        INSERT OR IGNORE INTO referral_wallet_ledger(
            event_key,referrer_account_id,referred_account_id,purchase_request_id,
            entry_type,amount_ugx,purchase_amount_ugx,commission_rate_bps,created_at,note
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
    """,(f"commission:{purchase_request_id}",referrer,int(buyer_account_id),
         int(purchase_request_id),"commission",commission,amount,rate,now.isoformat(),
         "First 30 days" if rate==2000 else "Subsequent purchase"))
    return commission


def request_withdrawal(account_id, amount_ugx, method, destination):
    if not withdrawals_enabled():
        raise ValueError("Withdrawal requests are not yet available.")
    if isinstance(amount_ugx,bool) or not isinstance(amount_ugx,int) or amount_ugx<minimum_withdrawal():
        raise ValueError(f"Withdrawal amount must be at least UGX {minimum_withdrawal():,}.")
    method=(method or "").strip().lower()
    destination=(destination or "").strip()
    if method not in ("mtn","crypto"):
        raise ValueError("Select an available payout method.")
    if not 8<=len(destination)<=180 or any(ord(char)<32 for char in destination):
        raise ValueError("Enter valid payment destination details.")
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        owner=con.execute("SELECT role,status FROM accounts WHERE id=?",(account_id,)).fetchone()
        if not owner or owner["role"]!="client" or owner["status"]!="active":
            raise ValueError("Wallet account unavailable.")
        if con.execute("SELECT 1 FROM referral_withdrawals WHERE account_id=? AND status='pending'",(account_id,)).fetchone():
            raise ValueError("You already have a withdrawal awaiting review.")
        summary=_summary_in_transaction(con,account_id)
        if amount_ugx>summary["available_ugx"]:
            raise ValueError("Withdrawal exceeds available balance.")
        cur=con.execute("""
            INSERT INTO referral_withdrawals(account_id,amount_ugx,destination_method,destination_details,requested_at)
            VALUES(?,?,?,?,?)
        """,(account_id,amount_ugx,method,destination,_iso()))
        con.commit()
        return int(cur.lastrowid)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def admin_withdrawals(status=None):
    con=connect()
    try:
        if status and status not in ("pending","paid","rejected"):
            raise ValueError("Invalid withdrawal status.")
        q="""SELECT w.id,w.account_id,a.username,w.amount_ugx,w.destination_method,
                  w.destination_details,w.status,w.requested_at,w.reviewed_at,
                  w.reviewed_by,w.payout_reference,w.review_note
             FROM referral_withdrawals w LEFT JOIN accounts a ON a.id=w.account_id"""
        if status:
            q+=" WHERE w.status=?"
        q+=" ORDER BY CASE w.status WHEN 'pending' THEN 0 ELSE 1 END,w.id DESC LIMIT 200"
        return [dict(x) for x in con.execute(q, (status,) if status else ()).fetchall()]
    finally:
        con.close()


def admin_wallets():
    con=connect()
    try:
        accounts=con.execute("""
            SELECT DISTINCT a.id,a.username FROM accounts a
            JOIN referral_wallet_ledger l ON l.referrer_account_id=a.id
            WHERE a.role='client' ORDER BY a.username LIMIT 300
        """).fetchall()
        return [{**dict(x),**_summary_in_transaction(con,int(x["id"]))} for x in accounts]
    finally:
        con.close()


def review_withdrawal(withdrawal_id,admin_id,paid=False,reference="",reason="",verified=False):
    reference=(reference or "").strip()
    reason=(reason or "").strip()
    if paid and (not verified or not 5<=len(reference)<=160):
        raise ValueError("Independently confirm the payout and supply its unique transfer reference.")
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute(
            "SELECT * FROM referral_withdrawals WHERE id=? AND status='pending'",(withdrawal_id,)
        ).fetchone()
        if not row:
            raise ValueError("Pending withdrawal not found.")
        if paid:
            current=_summary_in_transaction(con,int(row["account_id"]))
            if current["balance_ugx"]<int(row["amount_ugx"]):
                raise ValueError("Insufficient wallet balance after adjustments. Reject or resolve this request.")
            existing=con.execute(
                "SELECT 1 FROM referral_withdrawals WHERE payout_reference=? AND status='paid'",(reference,)
            ).fetchone()
            if existing:
                raise ValueError("This payout reference is already recorded.")
            con.execute("""
                INSERT INTO referral_wallet_ledger(
                  event_key,referrer_account_id,withdrawal_id,entry_type,amount_ugx,created_at,note
                ) VALUES(?,?,?,'payout',?,?,?)
            """,(f"payout:{withdrawal_id}",int(row["account_id"]),int(withdrawal_id),
                 -int(row["amount_ugx"]),_iso(),"Manually confirmed payout"))
        else:
            if len(reason)>500:
                raise ValueError("Rejection reason too long.")
        con.execute("""
            UPDATE referral_withdrawals
            SET status=?,reviewed_at=?,reviewed_by=?,payout_reference=?,review_note=?
            WHERE id=? AND status='pending'
        """,("paid" if paid else "rejected",_iso(),admin_id,reference if paid else None,
             "Payout verified" if paid else (reason or "Request rejected"),withdrawal_id))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def reverse_commission(purchase_id,admin_id,reason,confirmed):
    if not confirmed:
        raise ValueError("Confirm an actual refund or reversed payment first.")
    reason=(reason or "").strip()
    if len(reason)<5 or len(reason)>500:
        raise ValueError("Enter a refund or chargeback reason of 5–500 characters.")
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        original=con.execute("""
            SELECT * FROM referral_wallet_ledger
            WHERE event_key=? AND entry_type='commission'
        """,(f"commission:{purchase_id}",)).fetchone()
        if not original:
            raise ValueError("No credited referral commission for this payment.")
        already=con.execute(
            "SELECT 1 FROM referral_wallet_ledger WHERE event_key=?",(f"reversal:{purchase_id}",)
        ).fetchone()
        if already:
            raise ValueError("Commission already reversed.")
        con.execute("""
            INSERT INTO referral_wallet_ledger(
              event_key,referrer_account_id,referred_account_id,purchase_request_id,
              entry_type,amount_ugx,purchase_amount_ugx,commission_rate_bps,created_at,note
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,(f"reversal:{purchase_id}",original["referrer_account_id"],
             original["referred_account_id"],int(purchase_id),
             "reversal",-int(original["amount_ugx"]),
             original["purchase_amount_ugx"],original["commission_rate_bps"],_iso(),reason))
        con.execute("""
            INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at)
            VALUES(?,?,'REFERRAL_COMMISSION_REVERSED',?,?)
        """,(admin_id,original["referrer_account_id"],f"payment:{purchase_id}",_iso()))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def detach_deleted_client(con,account_id):
    """Keep financial events for audit; prevent deleting unpaid referral liabilities."""
    is_referrer=con.execute(
        "SELECT 1 FROM referral_wallet_ledger WHERE referrer_account_id=? LIMIT 1",(account_id,)
    ).fetchone()
    if is_referrer:
        summary=_summary_in_transaction(con,account_id)
        if summary["balance_ugx"]!=0 or summary["reserved_ugx"]!=0:
            raise ValueError("Settle or reverse the referral wallet before deleting this account.")
    con.execute("UPDATE referral_wallet_ledger SET referred_account_id=NULL WHERE referred_account_id=?",(account_id,))
    con.execute("UPDATE referral_wallet_ledger SET referrer_account_id=NULL WHERE referrer_account_id=?",(account_id,))
    con.execute("UPDATE referral_withdrawals SET account_id=NULL,destination_details='' WHERE account_id=?",(account_id,))
