"""Free registration, referral attribution and administrator-controlled promotional prices.

Database-backed promotions are quoted when a payment request is submitted.
A screenshot or promo code never grants VIP access.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import datetime, timezone
from urllib.parse import quote as url_quote

from . import access

PUBLIC_PLANS = frozenset({"daily", "weekly", "monthly", "annual", "lifetime"})


def _now():
    return datetime.now(timezone.utc)


def _iso():
    return _now().isoformat()


def connect():
    con = access.connect()
    columns = {r["name"] for r in con.execute("PRAGMA table_info(accounts)")}
    if "email" not in columns:
        con.execute("ALTER TABLE accounts ADD COLUMN email TEXT")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS account_email_unique ON accounts(lower(email)) WHERE email IS NOT NULL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS referral_profiles (
            account_id INTEGER PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            referred_by INTEGER,
            visits INTEGER NOT NULL DEFAULT 0,
            joined_at TEXT NOT NULL,
            vip_converted_at TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS referral_by_idx ON referral_profiles(referred_by)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS promotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_code TEXT NOT NULL,
            code TEXT,
            price_ugx INTEGER NOT NULL,
            starts_at TEXT,
            ends_at TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            CHECK(price_ugx > 0)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS promotions_plan_idx ON promotions(plan_code,enabled)")
    con.commit()
    return con


def _new_code(con):
    for _ in range(10):
        code = "BP" + secrets.token_hex(5).upper()
        if not con.execute("SELECT 1 FROM referral_profiles WHERE code=?", (code,)).fetchone():
            return code
    raise ValueError("Unable to generate a referral link. Try again.")


def signup(username, display_name, email, password, age_confirmed, referral_code=None):
    if not age_confirmed:
        raise ValueError("Confirm that you are at least 25 years old.")
    username = username.strip()
    display_name = display_name.strip() or username
    email = email.strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username) or username.upper() == "PUBLIC TRIAL":
        raise ValueError("Choose a username of 3-40 letters, numbers, dots, underscores or hyphens.")
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,200}\.[^@\s]{2,}", email):
        raise ValueError("Enter a valid email address.")
    if not 1 <= len(display_name) <= 100:
        raise ValueError("Display name must be at most 100 characters.")
    if not 8 <= len(password) <= 128:
        raise ValueError("Password must contain 8 to 128 characters.")
    referral_code = (referral_code or "").strip().upper()
    if referral_code and not re.fullmatch(r"BP[A-F0-9]{10}", referral_code):
        raise ValueError("Invalid referral link.")
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM accounts WHERE lower(username)=lower(?)", (username,)).fetchone():
            raise ValueError("Username already taken.")
        if con.execute("SELECT 1 FROM accounts WHERE lower(email)=?", (email,)).fetchone():
            raise ValueError("Email already registered. Please sign in.")
        referrer = None
        if referral_code:
            row = con.execute(
                "SELECT account_id FROM referral_profiles WHERE code=?", (referral_code,)
            ).fetchone()
            if not row:
                raise ValueError("Invalid referral link.")
            referrer = int(row["account_id"])
            owner = con.execute("SELECT role,status FROM accounts WHERE id=?", (referrer,)).fetchone()
            if not owner or owner["role"] != "client" or owner["status"] != "active":
                raise ValueError("Referral link is no longer available.")
        cur = con.execute(
            """INSERT INTO accounts
               (user_key,username,display_name,password_hash,role,status,
                must_change_password,created_at,email)
               VALUES (?,?,?,?,'client','active',0,?,?)""",
            (secrets.token_hex(16), username, display_name, access.hash_password(password), _iso(), email),
        )
        account_id = int(cur.lastrowid)
        con.execute("INSERT INTO subscriptions(account_id,status,updated_at) VALUES(?,'inactive',?)", (account_id, _iso()))
        if referrer == account_id:
            raise ValueError("Self-referrals are not permitted.")
        con.execute(
            "INSERT INTO referral_profiles(account_id,code,referred_by,joined_at) VALUES(?,?,?,?)",
            (account_id, _new_code(con), referrer, _iso()),
        )
        con.execute(
            "INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at) VALUES(NULL,?,'PUBLIC_SIGNUP',NULL,?)",
            (account_id, _iso()),
        )
        con.commit()
        return access.get_account(account_id)
    except sqlite3.IntegrityError:
        con.rollback()
        raise ValueError("Username or email already in use.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def track_visit(code):
    code = code.strip().upper()
    con = connect()
    try:
        found = con.execute("UPDATE referral_profiles SET visits=visits+1 WHERE code=?", (code,)).rowcount
        con.commit()
        return bool(found)
    finally:
        con.close()


def referral_stats(account_id, origin):
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT code,visits,referred_by FROM referral_profiles WHERE account_id=?", (account_id,)).fetchone()
        if not row:
            con.execute(
                "INSERT INTO referral_profiles(account_id,code,joined_at) VALUES(?,?,?)",
                (account_id, _new_code(con), _iso()),
            )
            row = con.execute("SELECT code,visits,referred_by FROM referral_profiles WHERE account_id=?", (account_id,)).fetchone()
        counts = con.execute("""
            SELECT COUNT(*) AS signups, SUM(CASE WHEN vip_converted_at IS NOT NULL THEN 1 ELSE 0 END) AS conversions
            FROM referral_profiles WHERE referred_by=?
        """, (account_id,)).fetchone()
        con.commit()
        return {
            "code": row["code"],
            "url": origin.rstrip("/") + "/r/" + url_quote(row["code"]),
            "visits": int(row["visits"]),
            "signups": int(counts["signups"] or 0),
            "vip_conversions": int(counts["conversions"] or 0),
            "rewards_enabled": True,
        }
    finally:
        con.close()


def mark_vip_conversion(account_id):
    con = connect()
    try:
        con.execute(
            "UPDATE referral_profiles SET vip_converted_at=? WHERE account_id=? AND referred_by IS NOT NULL AND vip_converted_at IS NULL",
            (_iso(), account_id),
        )
        con.commit()
    finally:
        con.close()


def _datetime(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("Timezone required")
        return dt.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        raise ValueError("Promotion dates must be timezone-aware ISO timestamps.")


def _base_prices():
    # Import lazily to avoid a cycle with purchase_requests.
    from .purchase_requests import prices
    return prices()


def create_promotion(plan_code, price_ugx, code=None, starts_at=None, ends_at=None, enabled=True):
    base = _base_prices()
    if plan_code not in PUBLIC_PLANS or base.get(plan_code) is None:
        raise ValueError("Select a supported plan.")
    price_ugx = int(price_ugx)
    if price_ugx < 1 or price_ugx >= base[plan_code]:
        raise ValueError("Promotional price must be positive and lower than the regular price.")
    code = (code or "").strip().upper() or None
    if code is not None and not re.fullmatch(r"[A-Z0-9_-]{3,32}", code):
        raise ValueError("Promo codes must contain 3-32 letters, numbers, underscores or hyphens.")
    start = _datetime(starts_at)
    end = _datetime(ends_at)
    if start and end and end <= start:
        raise ValueError("End date must be after the start date.")
    con = connect()
    try:
        cur = con.execute(
            "INSERT INTO promotions(plan_code,code,price_ugx,starts_at,ends_at,enabled,created_at) VALUES(?,?,?,?,?,?,?)",
            (plan_code, code, price_ugx, start.isoformat() if start else None,
             end.isoformat() if end else None, int(bool(enabled)), _iso()),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def set_promotion_enabled(promo_id, enabled):
    con = connect()
    try:
        changed = con.execute("UPDATE promotions SET enabled=? WHERE id=?", (int(bool(enabled)), promo_id)).rowcount
        con.commit()
        if not changed:
            raise ValueError("Promotion not found.")
    finally:
        con.close()


def list_promotions():
    con = connect()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM promotions ORDER BY id DESC LIMIT 200").fetchall()]
    finally:
        con.close()


def quote(plan_code, promo_code=None):
    prices = _base_prices()
    if plan_code not in PUBLIC_PLANS or prices.get(plan_code) is None:
        raise ValueError("Unknown or unpriced plan.")
    code = (promo_code or "").strip().upper() or None
    if code and not re.fullmatch(r"[A-Z0-9_-]{3,32}", code):
        raise ValueError("Invalid promo code.")
    con = connect()
    try:
        rows = con.execute(
            "SELECT id,code,price_ugx,starts_at,ends_at FROM promotions WHERE plan_code=? AND enabled=1 AND code IS ? ORDER BY id DESC",
            (plan_code, code),
        ).fetchall()
        now = _now()
        selected = next((r for r in rows
                         if (_datetime(r["starts_at"]) is None or _datetime(r["starts_at"]) <= now)
                         and (_datetime(r["ends_at"]) is None or _datetime(r["ends_at"]) > now)), None)
        if code and selected is None:
            raise ValueError("This promo code is invalid, expired, or not active for that plan.")
        regular = int(prices[plan_code])
        discounted = int(selected["price_ugx"]) if selected else regular
        return {
            "plan_code": plan_code,
            "regular_ugx": regular,
            "price_ugx": min(regular, discounted),
            "discount_ugx": max(0, regular - discounted),
            "promo_code": code if selected else None,
            "promotion_id": int(selected["id"]) if selected else None,
        }
    finally:
        con.close()
