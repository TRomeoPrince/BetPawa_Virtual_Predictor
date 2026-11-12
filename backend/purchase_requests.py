"""Manual payment-proof requests; admin verified activation, never auto-approved.

No payment credentials are needed. Transfer proofs are untrusted and never
establish settlement. Only the administrator may approve, after independently
checking the receiving wallet or mobile-money transaction.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlparse

from . import access, access_links

MAX_PROOF_BYTES = 2_000_000
METHODS = {
    "mtn": {"label": "MTN Mobile Money", "account": "0781920398", "name": "ROMEO"},
    "usdt_trc20": {"label": "USDT · TRC20", "address": "TCcR54xQu4dE3aKQao8PrUn3Nb7d2DVucG"},
    "usdt_bep20": {"label": "USDT · BEP20", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
    "usdt_erc20": {"label": "USDT · ERC20", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
    "usdt_polygon": {"label": "USDT · Polygon PoS", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
    "usdt_solana": {"label": "USDT · Solana", "address": "DDq3v8aj28dUw4mMcGUob94YgNQx9qn8XrNUnmQGpgPs"},
    "btc_bitcoin": {"label": "BTC · Bitcoin", "address": "14QTD6Eao9TMeuvStxjgrhyr9Qr4PSQ3rR"},
    "btc_bep20": {"label": "BTC · BEP20 token", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
    "btc_erc20": {"label": "BTC · ERC20 token", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
    "eth_erc20": {"label": "ETH · ERC20", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
    "eth_bep20": {"label": "ETH · BEP20", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
    "usdc_bep20": {"label": "USDC · BEP20", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
    "usdc_erc20": {"label": "USDC · ERC20", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
    "usdc_solana": {"label": "USDC · Solana", "address": "DDq3v8aj28dUw4mMcGUob94YgNQx9qn8XrNUnmQGpgPs"},
    "usdc_base": {"label": "USDC · Base", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
    "usdc_polygon": {"label": "USDC · Polygon", "address": "0x37e801c682cc4fb65cd501ae450149c274b6ba6c"},
}
PRICE_ENV = {
    "daily":"PREDICTOR_PRICE_DAILY_UGX",
    "weekly":"PREDICTOR_PRICE_WEEKLY_UGX",
    "monthly":"PREDICTOR_PRICE_MONTHLY_UGX",
    "annual":"PREDICTOR_PRICE_ANNUAL_UGX",
    "lifetime":"PREDICTOR_PRICE_LIFETIME_UGX",
}

def connect():
    con=access.connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS purchase_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            requested_username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            plan_code TEXT NOT NULL,
            expected_ugx INTEGER,
            payment_method TEXT NOT NULL,
            transaction_ref TEXT NOT NULL,
            proof_mime TEXT NOT NULL,
            proof_blob BLOB NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by INTEGER,
            client_account_id INTEGER,
            email_status TEXT NOT NULL DEFAULT 'not_sent',
            rejection_reason TEXT,
            CHECK(status IN ('pending','processing','approved','rejected'))
        )
    """)
    columns={r["name"] for r in con.execute("PRAGMA table_info(purchase_requests)")}
    for name,kind in (("buyer_account_id","INTEGER"),("promo_code","TEXT"),("promotion_id","INTEGER"),("proof_sha256","TEXT")):
        if name not in columns:
            con.execute(f"ALTER TABLE purchase_requests ADD COLUMN {name} {kind}")
    # Populate digest for older receipts so repeat submissions cannot reuse them.
    for row in con.execute(
        "SELECT id,proof_blob FROM purchase_requests WHERE proof_sha256 IS NULL AND LENGTH(proof_blob)>0"
    ).fetchall():
        con.execute(
            "UPDATE purchase_requests SET proof_sha256=? WHERE id=?",
            (hashlib.sha256(bytes(row["proof_blob"])).hexdigest(), row["id"]),
        )
    con.execute("CREATE INDEX IF NOT EXISTS purchase_proof_digest_idx ON purchase_requests(proof_sha256)")
    con.execute("CREATE INDEX IF NOT EXISTS purchase_status_idx ON purchase_requests(status,submitted_at)")
    con.commit()
    return con

DEFAULT_PRICES = {
    "daily": 5000,
    "weekly": 20000,
    "monthly": 60000,
    "annual": 500000,
    "lifetime": 1000000,
}


def prices():
    result={}
    for code,env in PRICE_ENV.items():
        raw=os.getenv(env,str(DEFAULT_PRICES[code])).strip()
        try:
            value=int(raw)
            result[code]=value if 0<value<=100_000_000 else None
        except ValueError:
            result[code]=None
    return result

def purchase_enabled():
    return os.getenv("PREDICTOR_PURCHASE_ENABLED", "false" if os.getenv("RAILWAY_PROJECT_ID") else "true").strip().lower() in ("1","true","yes","on")


def catalog():
    from . import growth
    return {"accepting_requests": purchase_enabled(), "plans":[{"code":c,"label":access.PLAN_DEFINITIONS[c]["label"],
                      "days":access.PLAN_DEFINITIONS[c]["days"],
                      "price_ugx":growth.quote(c)["price_ugx"] if p is not None else None,
                      "regular_ugx":p} for c,p in prices().items()],
            "methods":[{"code":c,**v} for c,v in METHODS.items()]}

def _mime(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):return "image/png"
    if data.startswith(b"\xff\xd8\xff"):return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12]==b"WEBP":return "image/webp"
    if data.startswith(b"%PDF-"):return "application/pdf"
    raise ValueError("Payment proof must be PNG, JPG, WebP or PDF.")

def submit(email, username, display_name, plan, method, txref, proof_b64, age_confirmed, account_id=None, promo_code=''):
    if not purchase_enabled():raise ValueError("Purchase requests are not open yet.")
    if not age_confirmed:raise ValueError("Confirm you are at least 25 years old.")
    email=email.strip().lower()
    username=username.strip()
    display_name=display_name.strip() or username
    txref=(txref or "").strip()
    proof_b64=(proof_b64 or "").strip()
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,200}\.[^@\s]{2,}",email):
        raise ValueError("Enter a valid email address.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}",username):
        raise ValueError("Username must have 3–40 letters, numbers, dots, underscores or hyphens.")
    if len(display_name)>100:raise ValueError("Display name too long.")
    if plan not in PRICE_ENV or prices()[plan] is None:
        raise ValueError("That plan is not priced yet. Select another plan.")
    if method not in METHODS:raise ValueError("Unsupported payment method.")
    if txref and not 5<=len(txref)<=160:
        raise ValueError("Transaction reference must contain 5–160 characters.")
    if not txref and not proof_b64:
        raise ValueError("Enter valid payment confirmation details.")
    if len(proof_b64)>2_800_000:
        raise ValueError("Proof exceeds the 2 MB limit.")
    data=b""
    mime=""
    digest=None
    if proof_b64:
        try:
            data=base64.b64decode(proof_b64,validate=True)
        except (binascii.Error,ValueError):
            raise ValueError("Invalid proof attachment.")
        if not 50<=len(data)<=MAX_PROOF_BYTES:
            raise ValueError("Attach a proof file up to 2 MB.")
        mime=_mime(data)
        digest=hashlib.sha256(data).hexdigest()
    from . import growth
    offer=growth.quote(plan,promo_code)
    now=datetime.now(timezone.utc).isoformat()
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        # Throttle repeated requests to limit bot abuse without leaking request details.
        recent=con.execute(
            "SELECT COUNT(*) FROM purchase_requests WHERE email=? AND submitted_at>?",
            (email,(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()),
        ).fetchone()[0]
        if recent>=3:raise ValueError("Too many requests. Try again later.")
        if account_id is not None:
            owner=con.execute("SELECT username,email,role,status FROM accounts WHERE id=?",(account_id,)).fetchone()
            if not owner or owner["role"]!="client" or owner["status"]!="active" or owner["username"].lower()!=username.lower():
                raise ValueError("Sign in to your own account to request a VIP upgrade.")
            if owner["email"] and owner["email"].lower()!=email:
                raise ValueError("Use your account email for the VIP upgrade.")
            if con.execute("SELECT 1 FROM purchase_requests WHERE buyer_account_id=? AND status IN ('pending','processing')",(account_id,)).fetchone():
                raise ValueError("You already have a payment awaiting review.")
        elif con.execute("SELECT 1 FROM accounts WHERE lower(username)=lower(?)",(username,)).fetchone():
            raise ValueError("This username is already in use. Sign in to upgrade.")
        if account_id is None and con.execute(
            "SELECT 1 FROM purchase_requests WHERE lower(requested_username)=lower(?) AND status IN ('pending','processing','approved')",
            (username,),
        ).fetchone():
            raise ValueError("This username is already requested. Choose another.")
        if txref and con.execute(
            "SELECT 1 FROM purchase_requests WHERE payment_method=? AND transaction_ref=?",
            (method,txref),
        ).fetchone():
            raise ValueError("This transaction reference has already been submitted.")
        if digest and con.execute(
            "SELECT 1 FROM purchase_requests WHERE proof_sha256=?",
            (digest,),
        ).fetchone():
            raise ValueError("This payment proof has already been submitted.")
        reference="BP-"+secrets.token_hex(6).upper()
        con.execute("""
            INSERT INTO purchase_requests
              (reference,email,requested_username,display_name,plan_code,expected_ugx,
               payment_method,transaction_ref,proof_mime,proof_blob,submitted_at,buyer_account_id,promo_code,promotion_id,proof_sha256)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(reference,email,username,display_name,plan,offer["price_ugx"],method,txref,mime,data,now,
             account_id,offer["promo_code"],offer["promotion_id"],digest))
        con.commit()
        return reference
    finally:
        con.close()

def pending():
    con=connect()
    try:
        rows=con.execute("""
            SELECT id,reference,email,requested_username,display_name,plan_code,
                   expected_ugx,payment_method,transaction_ref,status,submitted_at,
                   buyer_account_id,promo_code,promotion_id,
                   reviewed_at,client_account_id,email_status,rejection_reason,
                   LENGTH(proof_blob) AS proof_size,proof_mime
            FROM purchase_requests ORDER BY
            CASE status WHEN 'pending' THEN 0 WHEN 'processing' THEN 1 ELSE 2 END,id DESC
            LIMIT 200
        """).fetchall()
        return [dict(row) for row in rows]
    finally:con.close()

def proof(request_id):
    con=connect()
    try:
        row=con.execute("SELECT proof_blob,proof_mime FROM purchase_requests WHERE id=?",(request_id,)).fetchone()
        return (bytes(row["proof_blob"]),row["proof_mime"]) if row and row["proof_blob"] else None
    finally:con.close()

def needs_activation_origin(request_id):
    """A public HTTPS activation link is needed only when creating a new account."""
    con=connect()
    try:
        row=con.execute(
            "SELECT buyer_account_id FROM purchase_requests WHERE id=? AND status='pending'",
            (request_id,),
        ).fetchone()
        if not row:
            raise ValueError("Pending request not found.")
        return row["buyer_account_id"] is None
    finally:
        con.close()


def approve_or_reject(request_id,admin_id,approve,verified=False,reason=""):
    """Reserve pending request once. Only a manually confirmed payment can grant access."""
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("SELECT * FROM purchase_requests WHERE id=? AND status='pending'",(request_id,)).fetchone()
        if not row:raise ValueError("Pending request not found.")
        if approve and not verified:
            raise ValueError("Check the actual received payment and confirm verification first.")
        con.execute(
            "UPDATE purchase_requests SET status=?,reviewed_at=?,reviewed_by=?,rejection_reason=? WHERE id=?",
            ("processing" if approve else "rejected",datetime.now(timezone.utc).isoformat(),
             admin_id,None if approve else (reason.strip()[:500] or "Payment not verified"),request_id),
        )
        con.commit()
        return dict(row) if approve else None
    finally:con.close()

def activate_existing_verified(request_id, account_id, plan_code, admin_id):
    """Grant VIP and finalize approved payment in one SQLite transaction."""
    from datetime import timedelta
    meta=access.PLAN_DEFINITIONS.get(plan_code)
    if not meta or plan_code not in PRICE_ENV:
        raise ValueError("Unknown paid plan.")
    from . import referral_wallet
    wallet_con=referral_wallet.connect()
    wallet_con.close()
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        proof=con.execute(
            "SELECT id FROM purchase_requests WHERE id=? AND status='processing' AND buyer_account_id=? AND plan_code=?",
            (request_id, account_id, plan_code),
        ).fetchone()
        if not proof:
            raise ValueError("Verified payment reservation not found.")
        sub=con.execute("SELECT plan_code,status,expires_at FROM subscriptions WHERE account_id=?",(account_id,)).fetchone()
        if sub and sub["plan_code"]=="lifetime" and sub["status"]=="active":
            raise ValueError("This member already has lifetime VIP access.")
        now=datetime.now(timezone.utc)
        expiry=None
        if sub and sub["status"]=="active" and sub["expires_at"]:
            try:
                expiry=datetime.fromisoformat(sub["expires_at"])
            except ValueError:
                pass
        start=expiry if expiry and expiry>now else now
        ends=start+timedelta(days=int(meta["days"])) if meta["days"] is not None else None
        con.execute("""
            INSERT INTO subscriptions(account_id,plan_code,starts_at,expires_at,status,updated_at)
            VALUES(?,?,?,?, 'active',?)
            ON CONFLICT(account_id) DO UPDATE SET
                plan_code=excluded.plan_code,starts_at=excluded.starts_at,
                expires_at=excluded.expires_at,status='active',updated_at=excluded.updated_at
        """,(account_id,plan_code,start.isoformat(),ends.isoformat() if ends else None,now.isoformat()))
        con.execute(
            "UPDATE purchase_requests SET status='approved',client_account_id=?,email_status='not_needed' WHERE id=?",
            (account_id,request_id),
        )
        con.execute(
            "INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at) VALUES(?,?,'VIP_PAID_UPGRADE',?,?)",
            (admin_id,account_id,plan_code,now.isoformat()),
        )
        referral_wallet.record_verified_purchase(con,request_id,account_id)
        con.execute(
            "UPDATE referral_profiles SET vip_converted_at=COALESCE(vip_converted_at,?) "
            "WHERE account_id=? AND referred_by IS NOT NULL",
            (now.isoformat(),account_id),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def mark_approved(request_id,account_id):
    con=connect()
    try:
        con.execute("UPDATE purchase_requests SET status='approved',client_account_id=? WHERE id=? AND status='processing'",
                    (account_id,request_id))
        con.commit()
    finally:con.close()

def reset_processing(request_id):
    con=connect()
    try:
        con.execute("UPDATE purchase_requests SET status='pending',reviewed_at=NULL,reviewed_by=NULL WHERE id=? AND status='processing'",
                    (request_id,))
        con.commit()
    finally:con.close()

def email_activation(email,username,raw_token,base_url):
    """Only SMTP-delivered mail; no simulation or false sent state."""
    host=os.getenv("PREDICTOR_SMTP_HOST","").strip()
    sender=os.getenv("PREDICTOR_SMTP_FROM","").strip()
    if not host or not sender:raise RuntimeError("Email not configured. Copy the invitation link manually.")
    url=urlparse(base_url)
    if url.scheme!="https" or not url.netloc or url.username or url.password:
        raise RuntimeError("Set PREDICTOR_PUBLIC_BASE_URL to the HTTPS website origin.")
    port=int(os.getenv("PREDICTOR_SMTP_PORT","587"))
    user=os.getenv("PREDICTOR_SMTP_USER","")
    password=os.getenv("PREDICTOR_SMTP_PASSWORD","")
    if user and not password:raise RuntimeError("SMTP password not configured.")
    link=url.scheme+"://"+url.netloc+"/activate#"+raw_token
    message=EmailMessage()
    message["Subject"]="Activate your BetPawa Predictor subscription"
    message["From"]=sender
    message["To"]=email
    message.set_content(
        "Your subscription request was approved.\n"
        "Username: "+username+"\n"
        "Activate your account using this private one-use link (24 hours):\n"+link+
        "\n\nKeep this link private. If it expires, contact support."
    )
    if port==465:
        with smtplib.SMTP_SSL(host,port,timeout=15,context=ssl.create_default_context()) as server:
            if user:server.login(user,password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host,port,timeout=15) as server:
            server.starttls(context=ssl.create_default_context())
            if user:server.login(user,password)
            server.send_message(message)
    return True

def set_email_status(request_id,status):
    con=connect()
    try:
        con.execute("UPDATE purchase_requests SET email_status=? WHERE id=?",(status,request_id))
        con.commit()
    finally:con.close()

def approved_account(request_id):
    con=connect()
    try:
        row=con.execute(
            "SELECT client_account_id,email,requested_username FROM purchase_requests WHERE id=? AND status='approved'",
            (request_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:con.close()
