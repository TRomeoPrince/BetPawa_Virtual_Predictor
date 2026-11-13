"""Member-submitted win screenshots: private moderation and safe public gallery.

Submissions are claims by members. Approval confirms suitability for publication,
not independent verification of bets, amounts, winnings or payouts.
Uploaded image EXIF/metadata is stripped before persistence.
"""
from __future__ import annotations

import base64
import binascii
import io
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from . import access

MAX_UPLOAD_BYTES = 3 * 1024 * 1024
MAX_PIXELS = 10_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
IMAGE_NAME = re.compile(r"^[a-f0-9]{32}\.webp$")
DECISIONS = {"approved", "rejected"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _folder() -> Path:
    # In production PREDICTOR_DB_PATH lives on the persistent Railway volume.
    return Path(os.getenv("PREDICTOR_WIN_PROOF_DIR") or (access.DB.parent / "win_proofs"))


def connect():
    con = access.connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS win_proofs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            image_name TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by INTEGER,
            CHECK(status IN ('pending','approved','rejected'))
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS win_proofs_public_idx ON win_proofs(status, reviewed_at DESC, id DESC)")
    con.execute("CREATE INDEX IF NOT EXISTS win_proofs_owner_idx ON win_proofs(account_id, created_at DESC)")
    con.commit()
    return con


def _decode_image(image_base64: str) -> bytes:
    if not isinstance(image_base64, str) or len(image_base64) > 4_250_000:
        raise ValueError("The screenshot exceeds 3 MB.")
    if "," in image_base64:
        prefix, image_base64 = image_base64.split(",", 1)
        if prefix.lower() not in ("data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64"):
            raise ValueError("Upload a PNG, JPEG, or WebP screenshot.")
    try:
        original = base64.b64decode(image_base64, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("The screenshot could not be read.")
    if not original or len(original) > MAX_UPLOAD_BYTES:
        raise ValueError("Upload a screenshot no larger than 3 MB.")

    try:
        with Image.open(io.BytesIO(original)) as source:
            if source.format not in ("PNG", "JPEG", "WEBP"):
                raise ValueError("Only PNG, JPEG, and WebP screenshots are allowed.")
            w, h = source.size
            if w < 100 or h < 100 or w * h > MAX_PIXELS:
                raise ValueError("Screenshot dimensions are not supported.")
            # Re-encode to a non-active image format, remove EXIF and ancillary data.
            converted = ImageOps.exif_transpose(source).convert("RGB")
            output = io.BytesIO()
            converted.save(output, format="WEBP", quality=82, method=4)
            converted.close()
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("Please upload a valid PNG, JPEG, or WebP screenshot.")


def submit(account_id: int, image_base64: str, consent: bool) -> int:
    if consent is not True:
        raise ValueError("Confirm that the screenshot is yours and that you consent to public display if approved.")
    sanitized = _decode_image(image_base64)
    con = connect()
    filename = secrets.token_hex(16) + ".webp"
    filepath = _folder() / filename
    try:
        con.execute("BEGIN IMMEDIATE")
        pending = con.execute(
            "SELECT COUNT(*) FROM win_proofs WHERE account_id=? AND status='pending'",
            (account_id,),
        ).fetchone()[0]
        submitted_today = con.execute(
            "SELECT COUNT(*) FROM win_proofs WHERE account_id=? AND created_at>=?",
            (account_id, datetime.now(timezone.utc).date().isoformat()),
        ).fetchone()[0]
        if pending >= 3 or submitted_today >= 5:
            raise ValueError("Submission limit reached. Review or remove existing screenshots before posting more.")
        filepath.parent.mkdir(parents=True, exist_ok=True)
        # Random server filename; user input never becomes a path component.
        with filepath.open("xb") as target:
            target.write(sanitized)
        cur = con.execute(
            "INSERT INTO win_proofs(account_id,image_name,status,created_at) VALUES (?,?,?,?)",
            (account_id, filename, "pending", _now()),
        )
        con.commit()
        return int(cur.lastrowid)
    except Exception:
        con.rollback()
        filepath.unlink(missing_ok=True)
        raise
    finally:
        con.close()


def _item(row):
    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
        "caption": "Won by @" + str(row["username"]),
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
        "image_url": f"/api/win-proofs/{int(row['id'])}/image",
    }


def public_gallery(limit=25):
    con = connect()
    try:
        rows = con.execute("""
            SELECT p.*, a.username FROM win_proofs p
            JOIN accounts a ON a.id=p.account_id AND a.status='active'
            WHERE p.status='approved'
            ORDER BY p.reviewed_at DESC, p.id DESC LIMIT ?
        """, (max(1, min(int(limit), 40)),)).fetchall()
        return [_item(r) for r in rows]
    finally:
        con.close()


def mine(account_id: int):
    con = connect()
    try:
        rows = con.execute("""
            SELECT p.*,a.username FROM win_proofs p
            JOIN accounts a ON a.id=p.account_id
            WHERE p.account_id=? ORDER BY p.id DESC LIMIT 100
        """, (account_id,)).fetchall()
        return [_item(r) for r in rows]
    finally:
        con.close()


def admin_list(status="all"):
    if status not in ("all", "pending", "approved", "rejected"):
        raise ValueError("Invalid proof status.")
    con = connect()
    try:
        where = "" if status == "all" else "WHERE p.status=?"
        params = [] if status == "all" else [status]
        rows = con.execute(f"""
            SELECT p.*,a.username FROM win_proofs p
            JOIN accounts a ON a.id=p.account_id
            {where} ORDER BY CASE WHEN p.status='pending' THEN 0 ELSE 1 END,
            p.id DESC LIMIT 200
        """, params).fetchall()
        return [_item(r) for r in rows]
    finally:
        con.close()


def review(proof_id: int, decision: str, admin_id: int):
    if decision not in DECISIONS:
        raise ValueError("Choose approved or rejected.")
    con = connect()
    try:
        changed = con.execute(
            "UPDATE win_proofs SET status=?,reviewed_at=?,reviewed_by=? WHERE id=?",
            (decision, _now(), admin_id, proof_id),
        ).rowcount
        if not changed:
            raise ValueError("Win proof not found.")
        con.commit()
    finally:
        con.close()


def delete_own(proof_id: int, account_id: int):
    con = connect()
    try:
        row = con.execute(
            "SELECT image_name FROM win_proofs WHERE id=? AND account_id=?", (proof_id, account_id)
        ).fetchone()
        if not row:
            raise ValueError("Win proof not found.")
        con.execute("DELETE FROM win_proofs WHERE id=? AND account_id=?", (proof_id, account_id))
        con.commit()
        if IMAGE_NAME.fullmatch(str(row["image_name"])):
            (_folder() / str(row["image_name"])).unlink(missing_ok=True)
    finally:
        con.close()


def image_path(proof_id: int, viewer_id: int | None = None, is_admin: bool = False) -> Path | None:
    con = connect()
    try:
        row = con.execute("SELECT account_id,image_name,status FROM win_proofs WHERE id=?", (proof_id,)).fetchone()
        if row is None:
            return None
        if row["status"] != "approved" and not (is_admin or viewer_id == row["account_id"]):
            return None
        name = str(row["image_name"])
        if not IMAGE_NAME.fullmatch(name):
            return None
        path = _folder() / name
        return path if path.is_file() else None
    finally:
        con.close()
