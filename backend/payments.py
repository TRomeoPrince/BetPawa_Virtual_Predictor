"""Payment orders and verified, idempotent subscription activation.

Flutterwave Standard is the first live adapter (UGX mobile money/card).
Crypto and Binance Pay are intentionally unavailable until merchant API
integration can independently verify settlement. Never activate from a
screenshot, redirect query string, or unverified webhook payload.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from . import access

FLW_API = "https://api.flutterwave.com/v3"
METHODS = {
    "mtn_momo": {"label": "MTN MoMo", "provider": "flutterwave", "options": "mobilemoneyuganda"},
    "airtel_money": {"label": "Airtel Money", "provider": "flutterwave", "options": "mobilemoneyuganda"},
    "flutterwave": {"label": "Flutterwave (card or mobile money)", "provider": "flutterwave", "options": "card,mobilemoneyuganda"},
    "crypto": {"label": "Cryptocurrency", "provider": None},
    "binance_pay": {"label": "Binance Pay", "provider": None},
}


class PaymentError(ValueError):
    pass


class ProviderError(RuntimeError):
    pass


def _utcnow():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.astimezone(timezone.utc).isoformat()


def _price(plan_code):
    if plan_code not in access.PLAN_DEFINITIONS:
        return None
    value = os.environ.get("PREDICTOR_PRICE_" + plan_code.upper() + "_UGX", "").strip()
    try:
        price = int(value)
    except (ValueError, TypeError):
        return None
    return price if 0 < price <= 100_000_000 else None


def public_plans():
    return [{**plan, "price_ugx": _price(plan["code"])} for plan in access.public_plans()]


def _public_base():
    base = os.environ.get("PREDICTOR_PUBLIC_BASE_URL", "").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        return None
    return base


def flutterwave_ready():
    return bool(
        os.environ.get("FLW_SECRET_KEY", "").strip()
        and os.environ.get("FLW_WEBHOOK_HASH", "").strip()
        and _public_base()
    )


def public_methods():
    return [
        {"code": code, "label": info["label"],
         "available": bool(info["provider"] == "flutterwave" and flutterwave_ready()),
         "provider": info["provider"]}
        for code, info in METHODS.items()
    ]


def connect():
    con = access.connect()
    con.execute("""
    CREATE TABLE IF NOT EXISTS payment_orders (
        reference TEXT PRIMARY KEY,
        account_id INTEGER NOT NULL,
        plan_code TEXT NOT NULL,
        amount_ugx INTEGER NOT NULL,
        currency TEXT NOT NULL DEFAULT 'UGX',
        method TEXT NOT NULL,
        provider TEXT NOT NULL,
        email TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'created',
        checkout_url TEXT,
        provider_tx_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        paid_at TEXT,
        FOREIGN KEY(account_id) REFERENCES accounts(id)
    )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS payment_orders_account_idx ON payment_orders(account_id, created_at)")
    con.commit()
    return con


def _public_order(row):
    return {
        "reference": row["reference"], "plan_code": row["plan_code"],
        "amount_ugx": row["amount_ugx"], "currency": row["currency"],
        "method": row["method"], "status": row["status"],
        "created_at": row["created_at"], "paid_at": row["paid_at"],
    }


def list_orders(account_id):
    con = connect()
    try:
        rows = con.execute(
            "SELECT * FROM payment_orders WHERE account_id=? ORDER BY created_at DESC LIMIT 15",
            (account_id,),
        ).fetchall()
        return [_public_order(row) for row in rows]
    finally:
        con.close()


def list_all_orders():
    con = connect()
    try:
        rows = con.execute(
            """SELECT o.*, a.username, a.display_name
               FROM payment_orders o JOIN accounts a ON a.id=o.account_id
               ORDER BY o.created_at DESC LIMIT 100"""
        ).fetchall()
        return [{**_public_order(row), "username": row["username"],
                 "display_name": row["display_name"]} for row in rows]
    finally:
        con.close()


def get_order(reference, account_id=None):
    con = connect()
    try:
        if account_id is None:
            row = con.execute("SELECT * FROM payment_orders WHERE reference=?", (reference,)).fetchone()
        else:
            row = con.execute(
                "SELECT * FROM payment_orders WHERE reference=? AND account_id=?",
                (reference, account_id),
            ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def _flutterwave_request(path, payload=None):
    key = os.environ.get("FLW_SECRET_KEY", "").strip()
    if not key:
        raise ProviderError("Flutterwave is not configured.")
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(FLW_API + path, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urlopen(request, timeout=15) as response:
            body = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        raise ProviderError("Payment provider is temporarily unavailable.") from exc
    if not isinstance(body, dict) or body.get("status") != "success":
        raise ProviderError("Payment provider did not confirm the request.")
    return body


def start_checkout(account_id, plan_code, method, email, age_confirmed):
    if not age_confirmed:
        raise PaymentError("You must confirm you are at least 25 years old.")
    if method not in METHODS:
        raise PaymentError("Unknown payment method.")
    info = METHODS[method]
    if info["provider"] != "flutterwave":
        raise PaymentError("This payment method is not yet enabled for automatic verification.")
    if not flutterwave_ready():
        raise PaymentError("Online payments are not configured yet.")
    price = _price(plan_code)
    if price is None:
        raise PaymentError("This plan is not yet available for online payment.")
    email = email.strip()
    if len(email) > 254 or len(email) < 5 or "@" not in email or " " in email or email.startswith("@"):
        raise PaymentError("Enter a valid payment receipt email address.")
    account = access.get_account(account_id)
    if not account or account.get("role") != "client" or account.get("status") != "active":
        raise PaymentError("Only active client accounts can purchase access.")

    reference = "BP-" + secrets.token_hex(16)
    now = _iso(_utcnow())
    con = connect()
    try:
        con.execute(
            """INSERT INTO payment_orders
            (reference, account_id, plan_code, amount_ugx, currency, method, provider,
             email, status, created_at, updated_at)
            VALUES(?,?,?,?, 'UGX', ?, 'flutterwave', ?, 'created', ?, ?)""",
            (reference, account_id, plan_code, price, method, email, now, now),
        )
        con.commit()
    finally:
        con.close()

    payload = {
        "tx_ref": reference, "amount": price, "currency": "UGX",
        "redirect_url": _public_base() + "/api/payments/flutterwave/return",
        "payment_options": info["options"],
        "customer": {"email": email, "name": account["display_name"]},
        "customizations": {"title": "BetPawa Predictor", "description": access.PLAN_DEFINITIONS[plan_code]["label"] + " access"},
        "meta": {"order_reference": reference},
    }
    try:
        response = _flutterwave_request("/payments", payload)
        link = (response.get("data") or {}).get("link", "")
        parsed = urlparse(link)
        if parsed.scheme != "https" or parsed.hostname != "checkout.flutterwave.com":
            raise ProviderError("Payment provider returned an invalid checkout link.")
    except ProviderError:
        con = connect()
        try:
            con.execute("UPDATE payment_orders SET status='failed', updated_at=? WHERE reference=?", (_iso(_utcnow()), reference))
            con.commit()
        finally:
            con.close()
        raise

    con = connect()
    try:
        con.execute("UPDATE payment_orders SET status='checkout_ready', checkout_url=?, updated_at=? WHERE reference=?", (link, _iso(_utcnow()), reference))
        con.commit()
    finally:
        con.close()
    return {"reference": reference, "checkout_url": link, "amount_ugx": price, "currency": "UGX"}


def verify_and_activate(reference):
    """Re-query Flutterwave; atomically credit an order at most once."""
    order = get_order(reference)
    if not order:
        raise PaymentError("Payment order not found.")
    if order["status"] == "paid":
        return True
    if order["status"] not in ("created", "checkout_ready"):
        return False

    response = _flutterwave_request("/transactions/verify_by_reference?tx_ref=" + quote(reference, safe=""))
    data = response.get("data") or {}
    if not isinstance(data, dict) or data.get("tx_ref") != reference:
        return False
    if data.get("status") != "successful" or data.get("currency") != "UGX":
        return False
    try:
        amount = Decimal(str(data.get("amount")))
        transaction_id = str(int(data.get("id")))
    except (InvalidOperation, ValueError, TypeError):
        return False
    if not amount.is_finite() or amount < Decimal(order["amount_ugx"]) or transaction_id == "0":
        return False

    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        current = con.execute("SELECT * FROM payment_orders WHERE reference=?", (reference,)).fetchone()
        if not current or current["status"] == "paid":
            con.rollback()
            return bool(current and current["status"] == "paid")
        if current["status"] not in ("created", "checkout_ready"):
            con.rollback()
            return False
        if (current["amount_ugx"] != order["amount_ugx"] or current["plan_code"] != order["plan_code"]
                or current["account_id"] != order["account_id"]):
            con.rollback()
            return False
        if con.execute("SELECT 1 FROM payment_orders WHERE provider_tx_id=? AND reference!=?", (transaction_id, reference)).fetchone():
            con.rollback()
            return False
        account = con.execute("SELECT role,status FROM accounts WHERE id=?", (current["account_id"],)).fetchone()
        if not account or account["role"] != "client" or account["status"] != "active":
            con.rollback()
            return False

        sub = con.execute("SELECT expires_at,status FROM subscriptions WHERE account_id=?", (current["account_id"],)).fetchone()
        now = _utcnow()
        expiry = None
        if sub and sub["status"] == "active" and sub["expires_at"]:
            try:
                expiry = datetime.fromisoformat(sub["expires_at"])
            except ValueError:
                expiry = None
        start = expiry if expiry and expiry > now else now
        expires = start + timedelta(days=int(access.PLAN_DEFINITIONS[current["plan_code"]]["days"]))
        stamp = _iso(now)
        con.execute(
            """INSERT INTO subscriptions(account_id,plan_code,starts_at,expires_at,status,updated_at)
               VALUES(?,?,?,?, 'active', ?)
               ON CONFLICT(account_id) DO UPDATE SET plan_code=excluded.plan_code,
                 starts_at=excluded.starts_at, expires_at=excluded.expires_at,
                 status='active', updated_at=excluded.updated_at""",
            (current["account_id"], current["plan_code"], _iso(start), _iso(expires), stamp),
        )
        con.execute(
            "UPDATE payment_orders SET status='paid', provider_tx_id=?, paid_at=?, updated_at=? WHERE reference=?",
            (transaction_id, stamp, stamp, reference),
        )
        con.execute(
            "INSERT INTO access_audit(actor_account_id,target_account_id,action,details,created_at) VALUES(NULL,?,'PAYMENT_ACTIVATION',?,?)",
            (current["account_id"], reference + " / " + current["plan_code"], stamp),
        )
        con.execute(
            """UPDATE subscription_requests SET status='approved', reviewed_at=?
               WHERE account_id=? AND plan_code=? AND status='pending'""",
            (stamp, current["account_id"], current["plan_code"]),
        )
        con.commit()
        return True
    except sqlite3.IntegrityError:
        con.rollback()
        return False
    finally:
        con.close()
