"""Single-use activation links and revocable personal sign-in links.

Raw tokens are returned once to an administrator; only SHA-256 digests are stored.
The browser puts secrets in URL fragments, not paths or queries.
"""
import hashlib
import secrets
from datetime import timedelta
from . import access

def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def connect():
    con = access.connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS client_access_links (
            account_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('activation', 'login')),
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (account_id, kind)
        )""")
    con.commit()
    return con

def issue(account_id, kind, admin_id):
    if kind not in ("activation", "login"):
        raise ValueError("Invalid link type.")
    token = secrets.token_urlsafe(48)
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT role,status,must_change_password FROM accounts WHERE id=?",
                          (account_id,)).fetchone()
        if not row or row["role"] != "client" or row["status"] != "active":
            raise ValueError("Active client not found.")
        if (kind == "activation") != bool(row["must_change_password"]):
            raise ValueError("The account's activation state does not allow this link.")
        now = access._now()
        expiry = access._iso(now + (timedelta(hours=24) if kind=="activation" else timedelta(days=90)))
        con.execute("""
            INSERT INTO client_access_links(account_id,kind,token_hash,expires_at,created_at)
            VALUES(?,?,?,?,?) ON CONFLICT(account_id,kind) DO UPDATE SET
            token_hash=excluded.token_hash, expires_at=excluded.expires_at,
            created_at=excluded.created_at
        """, (account_id,kind,_hash(token),expiry,access._iso(now)))
        con.execute("""
            INSERT INTO access_audit(actor_account_id,target_account_id,action,created_at)
            VALUES(?,?,?,?)
        """, (admin_id,account_id,"ISSUE_"+kind.upper()+"_LINK",access._iso(now)))
        con.commit()
        return {"token":token,"expires_at":expiry}
    finally:
        con.close()

def revoke(account_id,kind,admin_id):
    if kind not in ("activation","login"):
        raise ValueError("Invalid link type.")
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        if not con.execute("SELECT 1 FROM accounts WHERE id=? AND role='client'",(account_id,)).fetchone():
            raise ValueError("Client not found.")
        con.execute("DELETE FROM client_access_links WHERE account_id=? AND kind=?",(account_id,kind))
        con.execute("INSERT INTO access_audit(actor_account_id,target_account_id,action,created_at) VALUES(?,?,?,?)",
                    (admin_id,account_id,"REVOKE_"+kind.upper()+"_LINK",access._iso(access._now())))
        con.commit()
    finally:
        con.close()

def invalidate(account_id):
    con=connect()
    try:
        con.execute("DELETE FROM client_access_links WHERE account_id=?",(account_id,))
        con.commit()
    finally:
        con.close()

def redeem_login(token):
    if not token or len(token)>256:
        return None
    con=connect()
    try:
        row=con.execute("""
            SELECT a.* FROM client_access_links l
            JOIN accounts a ON a.id=l.account_id
            WHERE l.kind='login' AND l.token_hash=? AND l.expires_at>?
            AND a.role='client' AND a.status='active' AND a.must_change_password=0
        """,(_hash(token),access._iso(access._now()))).fetchone()
        if not row:
            return None
        account=access._account_with_subscription(con,row)
        if not account["subscription"]["is_active"]:
            return None
        con.execute("UPDATE accounts SET last_login=? WHERE id=?",(access._iso(access._now()),row["id"]))
        con.commit()
        return account
    finally:
        con.close()

def activate(token,new_password,age_confirmed):
    if not token or len(token)>256 or not age_confirmed:
        raise ValueError("Missing, expired or invalid invitation or age confirmation.")
    if not 12<=len(new_password)<=128:
        raise ValueError("New password must have 12 to 128 characters.")
    con=connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row=con.execute("""
            SELECT a.* FROM client_access_links l
            JOIN accounts a ON a.id=l.account_id
            WHERE l.kind='activation' AND l.token_hash=? AND l.expires_at>?
            AND a.role='client' AND a.status='active' AND a.must_change_password=1
        """,(_hash(token),access._iso(access._now()))).fetchone()
        if not row:
            raise ValueError("This invitation has expired, was revoked, or has been used.")
        con.execute("UPDATE accounts SET password_hash=?,must_change_password=0 WHERE id=?",
                    (access.hash_password(new_password),row["id"]))
        con.execute("DELETE FROM client_access_links WHERE account_id=? AND kind='activation'",(row["id"],))
        con.execute("DELETE FROM sessions WHERE account_id=?",(row["id"],))
        con.execute("INSERT INTO access_audit(actor_account_id,target_account_id,action,created_at) VALUES(?,?,?,?)",
                    (row["id"],row["id"],"ACTIVATE_WITH_LINK",access._iso(access._now())))
        con.commit()
        return access.get_account(row["id"])
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
