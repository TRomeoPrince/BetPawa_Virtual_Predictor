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
COINS_PER_UGX = 100  # Presentation denomination only; UGX ledger remains authoritative.


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
    from . import contributor_rewards
    contributor_rewards.ensure_tables(con)
    con.commit()
    return con



def referral_dashboard(account_id: int, limit: int = 25, offset: int = 0) -> dict:
    """Private, account-scoped referral funnel and credited per-member history.

    A link visit is an anonymous opening, not a uniquely identified person.
    'paid' means at least one verified referral commission remains credited after
    recorded reversals. Cash-outs do not change which member generated a credit.
    Never expose referred members' email, password, session or payment details.
    """
    account_id = int(account_id)
    limit = min(100, max(1, int(limit)))
    offset = max(0, int(offset))
    con = connect()
    try:
        signups = con.execute("""
            SELECT COUNT(*) FROM referral_profiles p
            JOIN accounts a ON a.id=p.account_id
            WHERE p.referred_by=?
        """, (account_id,)).fetchone()[0]
        paid = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT l.referred_account_id
                FROM referral_wallet_ledger l
                JOIN referral_profiles p ON p.account_id=l.referred_account_id
                JOIN accounts a ON a.id=p.account_id
                WHERE p.referred_by=? AND l.referrer_account_id=?
                  AND l.entry_type IN ('commission','reversal')
                GROUP BY l.referred_account_id
                HAVING SUM(l.amount_ugx)>0
            )
        """, (account_id, account_id)).fetchone()[0]
        rows = con.execute("""
            SELECT a.username, p.joined_at, p.vip_converted_at,
                COALESCE(SUM(CASE WHEN l.entry_type IN ('commission','reversal')
                                  THEN l.amount_ugx ELSE 0 END),0) AS earned_ugx,
                COUNT(CASE WHEN l.entry_type='commission' THEN 1 END) AS credited_purchases,
                MAX(CASE WHEN l.entry_type='commission' THEN l.created_at END) AS last_paid_at
            FROM referral_profiles p
            JOIN accounts a ON a.id=p.account_id
            LEFT JOIN referral_wallet_ledger l
              ON l.referred_account_id=p.account_id AND l.referrer_account_id=?
            WHERE p.referred_by=?
            GROUP BY p.account_id, a.username, p.joined_at, p.vip_converted_at
            ORDER BY p.joined_at DESC, p.account_id DESC
            LIMIT ? OFFSET ?
        """, (account_id, account_id, limit, offset)).fetchall()
        people = []
        for row in rows:
            earned = int(row["earned_ugx"] or 0)
            # We do not call a reversed or uncredited conversion a paying referral.
            status = ("paid" if earned > 0 else
                      "uncredited" if row["vip_converted_at"] else "registered")
            people.append({
                "username": row["username"],
                "registered_at": row["joined_at"],
                "status": status,
                "earned_ugx": earned,
                "earned_pc": earned * 100,
                "credited_purchases": int(row["credited_purchases"] or 0),
                "last_paid_at": row["last_paid_at"] if status == "paid" else None,
            })
        return {
            "signups": int(signups),
            "paid_referrals": int(paid),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(people) < int(signups),
            "people": people,
            "note": "Link visits count opens, not unique people. Only verified purchases with non-reversed commissions contribute to referrals.",
        }
    finally:
        con.close()


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
    contributor=con.execute("""
        SELECT COALESCE(SUM(amount_ugx),0) AS net,
               COALESCE(SUM(CASE WHEN entry_type='contributor_reward' THEN amount_ugx ELSE 0 END),0) AS earned,
               COALESCE(SUM(CASE WHEN entry_type='contributor_reversal' THEN -amount_ugx ELSE 0 END),0) AS reversed
        FROM contributor_reward_ledger WHERE contributor_account_id=?
    """,(account_id,)).fetchone()
    balance = int(entries["balance"]) + int(contributor["net"]) - spent
    return {
        "currency": "UGX",
        "earned_ugx": int(entries["earned"]) + int(contributor["earned"]),
        "referral_earned_ugx": int(entries["earned"]),
        "contributor_earned_ugx": int(contributor["earned"]),
        "contributor_reversed_ugx": int(contributor["reversed"]),
        "reversed_ugx": int(entries["reversed"]) + int(contributor["reversed"]),
        "withdrawn_ugx": int(entries["withdrawn"]),
        "spent_on_vip_ugx": spent,
        "balance_ugx": balance,
        "reserved_ugx": reserved,
        "available_ugx": max(0, balance-reserved),
        "coins_per_ugx": COINS_PER_UGX,
        "balance_coins": balance * COINS_PER_UGX,
        "available_coins": max(0, balance-reserved) * COINS_PER_UGX,
        "reserved_coins": reserved * COINS_PER_UGX,
        "withdrawn_coins": int(entries["withdrawn"]) * COINS_PER_UGX,
        "spent_on_vip_coins": spent * COINS_PER_UGX,
    }


def wallet(account_id, limit=50):
    from . import contributor_rewards
    if contributor_rewards.enabled():
        contributor_rewards.settle_due(limit=100)
    con=connect()
    try:
        owner=con.execute("SELECT id,role,status FROM accounts WHERE id=?",(account_id,)).fetchone()
        if not owner or owner["role"]!="client" or owner["status"]!="active":
            raise ValueError("Member wallet unavailable.")
        result = _summary_in_transaction(con,account_id)
        result["withdrawals_enabled"] = withdrawals_enabled()
        result["minimum_withdrawal_ugx"] = minimum_withdrawal()
        result["minimum_withdrawal_coins"] = minimum_withdrawal() * COINS_PER_UGX
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
        result["entries"].extend(dict(x) for x in con.execute("""
            SELECT id,entry_type,amount_ugx,created_at,purchase_request_id,note,
                   NULL AS purchase_amount_ugx,500 AS commission_rate_bps
            FROM contributor_reward_ledger WHERE contributor_account_id=?
            ORDER BY id DESC LIMIT ?
        """,(account_id,max(1,min(int(limit),100)))).fetchall())
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
            WHERE a.role='client' AND (
                EXISTS(SELECT 1 FROM referral_wallet_ledger l WHERE l.referrer_account_id=a.id)
                OR EXISTS(SELECT 1 FROM contributor_reward_ledger c WHERE c.contributor_account_id=a.id)
            ) ORDER BY a.username LIMIT 300
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
        from . import contributor_rewards
        found=con.execute(
            "SELECT 1 FROM contributor_reward_periods WHERE purchase_request_id=?",
            (purchase_id,),
        ).fetchone()
        if found:
            contributor_rewards.reverse_purchase(con,purchase_id,admin_id,reason)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def detach_deleted_client(con,account_id):
    """Keep financial events for audit; prevent deleting unpaid referral liabilities."""
    is_referrer=con.execute(
        """SELECT 1 FROM referral_wallet_ledger WHERE referrer_account_id=?
           UNION SELECT 1 FROM contributor_reward_ledger WHERE contributor_account_id=?
           LIMIT 1""",(account_id,account_id)
    ).fetchone()
    if is_referrer:
        summary=_summary_in_transaction(con,account_id)
        if summary["balance_ugx"]!=0 or summary["reserved_ugx"]!=0:
            raise ValueError("Settle or reverse the referral wallet before deleting this account.")
    con.execute("UPDATE referral_wallet_ledger SET referred_account_id=NULL WHERE referred_account_id=?",(account_id,))
    con.execute("UPDATE referral_wallet_ledger SET referrer_account_id=NULL WHERE referrer_account_id=?",(account_id,))
    con.execute("UPDATE referral_withdrawals SET account_id=NULL,destination_details='' WHERE account_id=?",(account_id,))
    con.execute("UPDATE referral_wallet_spends SET account_id=NULL WHERE account_id=?",(account_id,))
    con.execute("UPDATE contributor_reward_ledger SET contributor_account_id=NULL WHERE contributor_account_id=?",(account_id,))



def purchase_vip_with_wallet(account_id, plan_code, promo_code, idempotency_key, expected_price_ugx):
    """Pay the entire VIP price from available referral earnings in one transaction.

    Commissions and withdrawals remain separate liabilities; a wallet redemption
    is not new external revenue and never earns a new referral commission.
    """
    from . import access
    from .purchase_requests import PRICE_ENV

    key=(idempotency_key or "").strip()
    code=(promo_code or "").strip().upper()
    if not re.fullmatch(r"[a-fA-F0-9-]{16,64}",key):
        raise ValueError("Invalid wallet checkout request key.")
    if plan_code not in PRICE_ENV or plan_code not in access.PLAN_DEFINITIONS:
        raise ValueError("Select a supported VIP plan.")

    con=connect()
    try:
        def replay(row):
            if int(row["account_id"] or 0)!=int(account_id) or row["plan_code"]!=plan_code or (row["promo_code"] or "")!=code:
                raise ValueError("This wallet checkout request key was already used.")
            return {"ok":True,"id":int(row["id"]),"plan_code":row["plan_code"],
                    "amount_ugx":int(row["amount_ugx"]),
                    "expires_at":row["subscription_expires_at"],"already_processed":True}

        previous=con.execute(
            "SELECT * FROM referral_wallet_spends WHERE idempotency_key=?",(key,)
        ).fetchone()
        if previous:
            return replay(previous)

        # Price is determined on the server, using current configured promotions.
        offer=growth.quote(plan_code,code)
        price=int(offer["price_ugx"])
        if price<=0:
            raise ValueError("VIP plan price is unavailable.")
        if isinstance(expected_price_ugx,bool) or not isinstance(expected_price_ugx,int) or price!=expected_price_ugx:
            raise ValueError("The VIP price changed. Refresh the checkout and confirm the latest price.")

        con.execute("BEGIN IMMEDIATE")
        previous=con.execute(
            "SELECT * FROM referral_wallet_spends WHERE idempotency_key=?",(key,)
        ).fetchone()
        if previous:
            return replay(previous)
        owner=con.execute("SELECT role,status FROM accounts WHERE id=?",(account_id,)).fetchone()
        if not owner or owner["role"]!="client" or owner["status"]!="active":
            raise ValueError("An active registered member account is required.")
        current=con.execute(
            "SELECT plan_code,status,expires_at FROM subscriptions WHERE account_id=?",(account_id,)
        ).fetchone()
        if current and current["plan_code"]=="lifetime" and current["status"]=="active":
            raise ValueError("This account already has lifetime VIP access.")
        balance=_summary_in_transaction(con,account_id)
        if balance["available_ugx"]<price:
            raise ValueError("The available referral wallet does not cover this VIP plan.")

        now=datetime.now(timezone.utc)
        start=now
        if current and current["status"]=="active" and current["expires_at"]:
            current_expiry=_timestamp(current["expires_at"])
            if current_expiry>now:
                start=current_expiry
        days=access.PLAN_DEFINITIONS[plan_code]["days"]
        end=start+timedelta(days=int(days)) if days is not None else None
        expiry=end.isoformat() if end else None

        spent=con.execute("""
            INSERT INTO referral_wallet_spends(
                idempotency_key,account_id,plan_code,amount_ugx,
                promo_code,promotion_id,purchased_at,subscription_expires_at
            ) VALUES(?,?,?,?,?,?,?,?)
        """,(key,account_id,plan_code,price,code or None,
             offer["promotion_id"],now.isoformat(),expiry))

        con.execute("""
            INSERT INTO subscriptions(account_id,plan_code,starts_at,expires_at,status,updated_at)
            VALUES(?,?,?,?, 'active',?)
            ON CONFLICT(account_id) DO UPDATE SET
                plan_code=excluded.plan_code,starts_at=excluded.starts_at,
                expires_at=excluded.expires_at,status='active',updated_at=excluded.updated_at
        """,(account_id,plan_code,start.isoformat(),expiry,now.isoformat()))
        con.execute("""
            INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at)
            VALUES(?,?,'VIP_WALLET_PURCHASE',?,?)
        """,(account_id,account_id,f"wallet_spend:{spent.lastrowid}",now.isoformat()))
        con.commit()
        return {"ok":True,"id":int(spent.lastrowid),"plan_code":plan_code,
                "amount_ugx":price,"expires_at":expiry,"already_processed":False}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
