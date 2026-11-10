from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import DB

SESSION_COOKIE = "bp_session"
SESSION_DAYS = 30
PBKDF2_ITERATIONS = 260_000

PLAN_DEFINITIONS = {
    "daily": {"label": "Daily", "days": 1, "public": True},
    "weekly": {"label": "Weekly", "days": 7, "public": True},
    "monthly": {"label": "Monthly", "days": 30, "public": True},
    "quarterly": {"label": "3 Months", "days": 90, "public": True},
    "half_year": {"label": "6 Months", "days": 180, "public": True},
    "annual": {"label": "Yearly", "days": 365, "public": True},
    "lifetime": {"label": "Lifetime", "days": None, "public": True},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_key TEXT NOT NULL UNIQUE,
      username TEXT NOT NULL UNIQUE,
      display_name TEXT NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'client',
      status TEXT NOT NULL DEFAULT 'active',
      must_change_password INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      last_login TEXT
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
      account_id INTEGER PRIMARY KEY,
      plan_code TEXT,
      starts_at TEXT,
      expires_at TEXT,
      status TEXT NOT NULL DEFAULT 'inactive',
      updated_at TEXT NOT NULL,
      FOREIGN KEY(account_id) REFERENCES accounts(id)
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
      token_hash TEXT PRIMARY KEY,
      account_id INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      last_seen TEXT NOT NULL,
      FOREIGN KEY(account_id) REFERENCES accounts(id)
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS subscription_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      account_id INTEGER NOT NULL,
      plan_code TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      requested_at TEXT NOT NULL,
      reviewed_at TEXT,
      reviewed_by INTEGER,
      FOREIGN KEY(account_id) REFERENCES accounts(id)
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS access_audit (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      actor_account_id INTEGER,
      target_account_id INTEGER,
      action TEXT NOT NULL,
      details TEXT,
      created_at TEXT NOT NULL
    )
    """)
    con.commit()
    return con


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256$" + str(PBKDF2_ITERATIONS) + "$" + salt.hex() + "$" + digest.hex()


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def _account_with_subscription(con, row) -> dict[str, Any] | None:
    if not row:
        return None
    account = dict(row)
    sub = con.execute(
        "SELECT plan_code, starts_at, expires_at, status, updated_at FROM subscriptions WHERE account_id=?",
        (account["id"],),
    ).fetchone()
    subscription = dict(sub) if sub else {
        "plan_code": None,
        "starts_at": None,
        "expires_at": None,
        "status": "inactive",
        "updated_at": None,
    }

    expires = _parse(subscription.get("expires_at"))
    is_lifetime = subscription.get("plan_code") == "lifetime"
    active = (
        account.get("status") == "active"
        and subscription.get("status") == "active"
        and ((is_lifetime and subscription.get("expires_at") is None)
             or (expires is not None and expires > _now()))
    )
    if account.get("role") == "admin" and account.get("status") == "active":
        active = True

    remaining_seconds = None
    if expires:
        remaining_seconds = max(0, int((expires - _now()).total_seconds()))

    plan_code = subscription.get("plan_code")
    plan = PLAN_DEFINITIONS.get(plan_code or "")
    subscription.update({
        "is_active": active,
        "remaining_seconds": remaining_seconds,
        "plan_label": plan["label"] if plan else ("Custom expiry" if plan_code == "custom_date" else (plan_code or "No plan")),
    })
    account["subscription"] = subscription
    account["must_change_password"] = bool(account.get("must_change_password"))
    return account


def ensure_bootstrap_admin() -> str | None:
    con = connect()
    existing = con.execute(
        "SELECT id FROM accounts WHERE role='admin' ORDER BY id LIMIT 1"
    ).fetchone()
    if existing:
        con.close()
        return None

    password = os.getenv("PREDICTOR_ADMIN_PASSWORD") or secrets.token_urlsafe(10)
    now = _iso(_now())
    con.execute(
        """
        INSERT INTO accounts
          (user_key, username, display_name, password_hash, role, status,
           must_change_password, created_at)
        VALUES (?, 'admin', 'Administrator', ?, 'admin', 'active', 1, ?)
        """,
        (secrets.token_hex(16), hash_password(password), now),
    )
    con.commit()
    con.close()
    return password


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    con = connect()
    row = con.execute(
        "SELECT * FROM accounts WHERE lower(username)=lower(?) LIMIT 1",
        (username.strip(),),
    ).fetchone()
    if not row or row["status"] != "active" or not verify_password(password, row["password_hash"]):
        con.close()
        return None
    con.execute("UPDATE accounts SET last_login=? WHERE id=?", (_iso(_now()), row["id"]))
    con.commit()
    row = con.execute("SELECT * FROM accounts WHERE id=?", (row["id"],)).fetchone()
    account = _account_with_subscription(con, row)
    con.close()
    return account


def create_session(account_id: int) -> str:
    raw = secrets.token_urlsafe(36)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    now = _now()
    con = connect()
    con.execute(
        "INSERT INTO sessions(token_hash, account_id, created_at, expires_at, last_seen) VALUES(?,?,?,?,?)",
        (token_hash, account_id, _iso(now), _iso(now + timedelta(days=SESSION_DAYS)), _iso(now)),
    )
    con.commit()
    con.close()
    return raw


def account_from_session(raw_token: str | None) -> dict[str, Any] | None:
    if not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    con = connect()
    session = con.execute(
        "SELECT * FROM sessions WHERE token_hash=? LIMIT 1", (token_hash,)
    ).fetchone()
    if not session:
        con.close()
        return None
    expires = _parse(session["expires_at"])
    if not expires or expires <= _now():
        con.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
        con.commit()
        con.close()
        return None
    con.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (_iso(_now()), token_hash))
    row = con.execute("SELECT * FROM accounts WHERE id=?", (session["account_id"],)).fetchone()
    account = _account_with_subscription(con, row)
    con.commit()
    con.close()
    return account


def delete_session(raw_token: str | None):
    if not raw_token:
        return
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    con = connect()
    con.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
    con.commit()
    con.close()


def change_password(account_id: int, current_password: str, new_password: str):
    """Complete first-login setup or rotate a password; invalidate old sessions."""
    if not 12 <= len(new_password) <= 128:
        raise ValueError("New password must be 12 to 128 characters long.")
    con = connect()
    try:
        row = con.execute(
            "SELECT password_hash FROM accounts WHERE id=? AND status='active'",
            (account_id,),
        ).fetchone()
        if not row or not verify_password(current_password, row["password_hash"]):
            raise ValueError("Current password is incorrect.")
        if hmac.compare_digest(current_password, new_password):
            raise ValueError("Choose a different password from your temporary one.")
        con.execute(
            "UPDATE accounts SET password_hash=?, must_change_password=0 WHERE id=?",
            (hash_password(new_password), account_id),
        )
        con.execute("DELETE FROM sessions WHERE account_id=?", (account_id,))
        con.execute(
            "INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at) "
            "VALUES(?,?,?,?,?)",
            (account_id, account_id, "CHANGE_PASSWORD", None, _iso(_now())),
        )
        con.commit()
    finally:
        con.close()


def reset_client_password(account_id: int, admin_id: int) -> str:
    """Admin issues a new one-time temporary password, never stored in plaintext."""
    temp_password = secrets.token_urlsafe(18)
    con = connect()
    try:
        row = con.execute(
            "SELECT id FROM accounts WHERE id=? AND role='client'",
            (account_id,),
        ).fetchone()
        if not row:
            raise ValueError("Client not found.")
        con.execute(
            "UPDATE accounts SET password_hash=?, must_change_password=1 WHERE id=?",
            (hash_password(temp_password), account_id),
        )
        con.execute("DELETE FROM sessions WHERE account_id=?", (account_id,))
        con.execute(
            "INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at) "
            "VALUES(?,?,?,?,?)",
            (admin_id, account_id, "RESET_CLIENT_PASSWORD", None, _iso(_now())),
        )
        con.commit()
    finally:
        con.close()
    return temp_password


def create_client(
    username: str,
    display_name: str,
    plan_code: str | None = None,
    created_by: int | None = None,
    chosen_password: str | None = None,
    expires_at: str | None = None,
) -> tuple[dict[str, Any], str]:
    username = username.strip()
    display_name = display_name.strip() or username
    # Only the explicitly named shared trial account may contain a space.
    if username != "PUBLIC TRIAL" and not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username):
        raise ValueError("Username must be 3–40 characters: letters, numbers, dots, underscores or hyphens (or PUBLIC TRIAL).")
    if chosen_password is not None:
        if username != "PUBLIC TRIAL":
            raise ValueError("Admin-set passwords are available only for PUBLIC TRIAL.")
        if not 12 <= len(chosen_password) <= 128:
            raise ValueError("Public trial password must contain 12 to 128 characters.")
    if username == "PUBLIC TRIAL" and chosen_password is None:
        raise ValueError("Set a password for PUBLIC TRIAL.")
    if len(display_name) > 100:
        raise ValueError("Display name must be 100 characters or less.")
    if plan_code and plan_code not in PLAN_DEFINITIONS:
        raise ValueError("Unknown subscription plan.")
    # Validate before inserting an account.
    if expires_at is not None:
        _validate_expiry(expires_at)
    temp_password = chosen_password if chosen_password is not None else secrets.token_urlsafe(18)
    now = _iso(_now())
    con = connect()
    try:
        if con.execute(
            "SELECT 1 FROM accounts WHERE lower(username)=lower(?) LIMIT 1", (username,),
        ).fetchone():
            raise ValueError("That username already exists.")
        cur = con.execute(
            """
            INSERT INTO accounts
              (user_key, username, display_name, password_hash, role, status,
               must_change_password, created_at)
            VALUES (?, ?, ?, ?, 'client', 'active', ?, ?)
            """,
            (
                secrets.token_hex(16), username, display_name,
                hash_password(temp_password), 0 if chosen_password is not None else 1, now,
            ),
        )
        account_id = int(cur.lastrowid)
        con.execute(
            "INSERT INTO subscriptions(account_id, status, updated_at) VALUES(?, 'inactive', ?)",
            (account_id, now),
        )
        con.execute(
            "INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at) VALUES(?,?,?,?,?)",
            (created_by, account_id, "CREATE_CLIENT", username, now),
        )
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback()
        raise ValueError("That username already exists.")
    finally:
        con.close()

    if expires_at is not None:
        set_subscription_expiry(account_id, expires_at, plan_code or "custom_date",
                                actor_account_id=created_by)
    elif plan_code:
        grant_subscription(account_id, plan_code, actor_account_id=created_by)
    return get_account(account_id), temp_password


def delete_client(account_id: int, admin_id: int) -> None:
    """Permanently delete only one client and all account-scoped private data."""
    from . import db, picks
    # Ensure optional journal and predictor tables exist before transaction.
    jcon = picks.connect_journal()
    jcon.close()
    dcon = db.connect()
    dcon.close()
    from . import access_links, growth, purchase_requests
    lcon = access_links.connect()
    lcon.close()
    gcon = growth.connect()
    gcon.close()
    pcon = purchase_requests.connect()
    pcon.close()
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT user_key FROM accounts WHERE id=? AND role='client'",
            (account_id,),
        ).fetchone()
        if not row:
            raise ValueError("Client not found.")
        for table in ("user_prediction_batches", "user_predictions",
                      "prediction_supports", "client_bet_journal"):
            con.execute(f"DELETE FROM {table} WHERE user_id=?", (row["user_key"],))
        con.execute("UPDATE referral_profiles SET referred_by=NULL WHERE referred_by=?", (account_id,))
        con.execute("DELETE FROM referral_profiles WHERE account_id=?", (account_id,))
        con.execute("UPDATE purchase_requests SET buyer_account_id=NULL WHERE buyer_account_id=?", (account_id,))
        con.execute("UPDATE purchase_requests SET client_account_id=NULL WHERE client_account_id=?", (account_id,))
        for table in ("sessions", "subscriptions", "subscription_requests",
                      "client_access_links"):
            con.execute(f"DELETE FROM {table} WHERE account_id=?", (account_id,))
        con.execute("UPDATE access_audit SET actor_account_id=NULL WHERE actor_account_id=?", (account_id,))
        con.execute("UPDATE access_audit SET target_account_id=NULL,details=NULL WHERE target_account_id=?", (account_id,))
        con.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        con.execute(
            "INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at) "
            "VALUES(?,NULL,'DELETE_CLIENT',NULL,?)",
            (admin_id, _iso(_now())),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def get_account(account_id: int) -> dict[str, Any] | None:
    con = connect()
    row = con.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    account = _account_with_subscription(con, row)
    con.close()
    return account


def list_clients() -> list[dict[str, Any]]:
    con = connect()
    rows = con.execute(
        "SELECT * FROM accounts WHERE role='client' ORDER BY id DESC"
    ).fetchall()
    out = [_account_with_subscription(con, row) for row in rows]
    con.close()
    return [x for x in out if x]


def _validate_expiry(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Enter a valid expiry date with a timezone.")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Expiry date must include a timezone offset.")
    dt = dt.astimezone(timezone.utc)
    now = _now()
    if dt <= now:
        raise ValueError("Expiry date must be in the future.")
    if dt > now + timedelta(days=3650):
        raise ValueError("Expiry date cannot be more than 10 years ahead.")
    return dt


def set_subscription_expiry(
    account_id: int,
    expires_at: str,
    plan_code: str = "custom_date",
    actor_account_id: int | None = None,
):
    """Set a precise absolute expiry, replacing—not extending—the current one."""
    expires = _validate_expiry(expires_at)
    if plan_code != "custom_date" and plan_code not in PLAN_DEFINITIONS:
        raise ValueError("Unknown subscription plan.")
    now = _now()
    con = connect()
    try:
        row = con.execute("SELECT role FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not row or row["role"] != "client":
            raise ValueError("Client not found.")
        con.execute("""
            INSERT INTO subscriptions(account_id,plan_code,starts_at,expires_at,status,updated_at)
            VALUES(?,?,?,?, 'active', ?)
            ON CONFLICT(account_id) DO UPDATE SET
              plan_code=excluded.plan_code,
              starts_at=excluded.starts_at,
              expires_at=excluded.expires_at,
              status='active',
              updated_at=excluded.updated_at
        """, (account_id, plan_code, _iso(now), _iso(expires), _iso(now)))
        con.execute(
            "INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at) "
            "VALUES(?,?,?,?,?)",
            (actor_account_id, account_id, "SET_SUBSCRIPTION_EXPIRY", _iso(expires), _iso(now)),
        )
        con.commit()
    finally:
        con.close()


def grant_subscription(
    account_id: int,
    plan_code: str,
    custom_days: int | None = None,
    actor_account_id: int | None = None,
):
    if plan_code == "custom":
        if not custom_days or not 1 <= int(custom_days) <= 3650:
            raise ValueError("Custom access must be between 1 and 3650 days.")
        days = int(custom_days)
        label = f"Custom {days} days"
    else:
        plan = PLAN_DEFINITIONS.get(plan_code)
        if not plan:
            raise ValueError("Unknown subscription plan.")
        days = int(plan["days"]) if plan["days"] is not None else None
        label = plan["label"]

    con = connect()
    account = con.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone()
    if not account:
        con.close()
        raise ValueError("Client not found.")

    row = con.execute("SELECT expires_at FROM subscriptions WHERE account_id=?", (account_id,)).fetchone()
    current_expiry = _parse(row["expires_at"]) if row else None
    now = _now()
    starts = current_expiry if days is not None and current_expiry and current_expiry > now else now
    expires = starts + timedelta(days=days) if days is not None else None
    con.execute(
        """
        INSERT INTO subscriptions(account_id,plan_code,starts_at,expires_at,status,updated_at)
        VALUES(?,?,?,?, 'active', ?)
        ON CONFLICT(account_id) DO UPDATE SET
          plan_code=excluded.plan_code,
          starts_at=excluded.starts_at,
          expires_at=excluded.expires_at,
          status='active',
          updated_at=excluded.updated_at
        """,
        (account_id, plan_code, _iso(starts), _iso(expires) if expires else None, _iso(now)),
    )
    con.execute(
        "INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at) VALUES(?,?,?,?,?)",
        (actor_account_id, account_id, "GRANT_SUBSCRIPTION", label, _iso(now)),
    )
    con.commit()
    con.close()


def revoke_subscription(account_id: int, actor_account_id: int | None = None):
    con = connect()
    now = _iso(_now())
    con.execute(
        "UPDATE subscriptions SET status='revoked', updated_at=? WHERE account_id=?",
        (now, account_id),
    )
    con.execute(
        "INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at) VALUES(?,?,?,?,?)",
        (actor_account_id, account_id, "REVOKE_SUBSCRIPTION", None, now),
    )
    con.commit()
    con.close()


def request_subscription(account_id: int, plan_code: str) -> dict[str, Any]:
    if plan_code not in PLAN_DEFINITIONS:
        raise ValueError("Unknown subscription plan.")
    con = connect()
    existing = con.execute(
        "SELECT id FROM subscription_requests WHERE account_id=? AND status='pending' LIMIT 1",
        (account_id,),
    ).fetchone()
    if existing:
        con.close()
        raise ValueError("You already have a pending subscription request.")
    now = _iso(_now())
    cur = con.execute(
        "INSERT INTO subscription_requests(account_id,plan_code,status,requested_at) VALUES(?,?, 'pending', ?)",
        (account_id, plan_code, now),
    )
    con.commit()
    req = con.execute("SELECT * FROM subscription_requests WHERE id=?", (cur.lastrowid,)).fetchone()
    con.close()
    return dict(req)


def list_account_subscription_requests(account_id: int) -> list[dict[str, Any]]:
    """Return only the signed-in account's recent requests."""
    con = connect()
    rows = con.execute(
        """
        SELECT id, plan_code, status, requested_at, reviewed_at
        FROM subscription_requests
        WHERE account_id=?
        ORDER BY id DESC LIMIT 5
        """,
        (account_id,),
    ).fetchall()
    con.close()
    return [dict(row) for row in rows]


def list_subscription_requests() -> list[dict[str, Any]]:
    con = connect()
    rows = con.execute(
        """
        SELECT r.*, a.username, a.display_name
        FROM subscription_requests r
        JOIN accounts a ON a.id=r.account_id
        ORDER BY CASE r.status WHEN 'pending' THEN 0 ELSE 1 END, r.id DESC
        """
    ).fetchall()
    out = [dict(r) for r in rows]
    con.close()
    return out


def review_subscription_request(request_id: int, approve: bool, admin_id: int):
    con = connect()
    row = con.execute(
        "SELECT * FROM subscription_requests WHERE id=? AND status='pending'", (request_id,)
    ).fetchone()
    if not row:
        con.close()
        raise ValueError("Pending request not found.")
    con.close()

    if approve:
        grant_subscription(int(row["account_id"]), str(row["plan_code"]), actor_account_id=admin_id)

    con = connect()
    con.execute(
        "UPDATE subscription_requests SET status=?, reviewed_at=?, reviewed_by=? WHERE id=?",
        ("approved" if approve else "rejected", _iso(_now()), admin_id, request_id),
    )
    con.commit()
    con.close()


def public_account(account: dict[str, Any]) -> dict[str, Any]:
    sub = dict(account.get("subscription") or {})
    return {
        "id": account.get("id"),
        "username": account.get("username"),
        "display_name": account.get("display_name"),
        "role": account.get("role"),
        "status": account.get("status"),
        "must_change_password": bool(account.get("must_change_password")),
        "subscription": sub,
    }


def public_plans() -> list[dict[str, Any]]:
    return [
        {"code": code, "label": meta["label"], "days": meta["days"]}
        for code, meta in PLAN_DEFINITIONS.items()
        if meta.get("public")
    ]
