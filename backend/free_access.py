"""Administrator-controlled, one-off Free prediction release windows.

An inactive installation exposes no Free predictions. Admins explicitly select
when a five-matchday release begins; releases do not recur automatically.
Only the five consecutive *estimated* upcoming 5-minute target rounds can pass.
"""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone

from . import access
from .time_windows import ANCHOR_DATETIME_EAT, EAT, MATCHDAY_MINUTES, estimate_target_datetime_eat

FREE_ROUNDS = 5
ROUND_DELTA = timedelta(minutes=MATCHDAY_MINUTES)


def _now():
    return datetime.now(timezone.utc)


def _datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise ValueError("Enter a valid date and time with a timezone.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Release time must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _first_target(start):
    """The first estimated target boundary strictly after a release begins."""
    dt = start.astimezone(EAT)
    intervals = math.floor((dt - ANCHOR_DATETIME_EAT).total_seconds() / ROUND_DELTA.total_seconds()) + 1
    return ANCHOR_DATETIME_EAT + intervals * ROUND_DELTA


def connect():
    con = access.connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS free_release_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            first_target_eat TEXT NOT NULL,
            round_count INTEGER NOT NULL DEFAULT 5,
            enabled INTEGER NOT NULL DEFAULT 1,
            actor_account_id INTEGER,
            created_at TEXT NOT NULL,
            CHECK(round_count=5),
            CHECK(enabled IN (0,1))
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS free_release_dates ON free_release_windows(enabled,starts_at,ends_at)")
    con.commit()
    return con


def _check_overlap(con, start, end, exclude=None):
    for row in con.execute("SELECT id, starts_at, ends_at FROM free_release_windows WHERE enabled=1").fetchall():
        if exclude is not None and int(row["id"]) == int(exclude):
            continue
        prior_start = _datetime(row["starts_at"])
        prior_end = _datetime(row["ends_at"])
        if start < prior_end and end > prior_start:
            raise ValueError("This release overlaps another enabled Free release. Disable the other one first.")


def create_release(starts_at=None, admin_id=None, enabled=True):
    start = _datetime(starts_at) if starts_at is not None else _now()
    first_target = _first_target(start)
    end = (first_target + FREE_ROUNDS * ROUND_DELTA).astimezone(timezone.utc)
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        if enabled:
            _check_overlap(con, start, end)
        cur = con.execute(
            """INSERT INTO free_release_windows
               (starts_at,ends_at,first_target_eat,round_count,enabled,actor_account_id,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (start.isoformat(), end.isoformat(), first_target.isoformat(), FREE_ROUNDS,
             int(bool(enabled)), admin_id, _now().isoformat()),
        )
        con.commit()
        return int(cur.lastrowid)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def set_enabled(release_id, enabled):
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT starts_at,ends_at FROM free_release_windows WHERE id=?", (release_id,)
        ).fetchone()
        if not row:
            raise ValueError("Free release not found.")
        if enabled:
            _check_overlap(con, _datetime(row["starts_at"]), _datetime(row["ends_at"]), exclude=release_id)
        con.execute("UPDATE free_release_windows SET enabled=? WHERE id=?", (int(bool(enabled)), release_id))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def delete_release(release_id):
    con = connect()
    try:
        count = con.execute("DELETE FROM free_release_windows WHERE id=?", (release_id,)).rowcount
        con.commit()
        if not count:
            raise ValueError("Free release not found.")
    finally:
        con.close()


def list_releases(now=None):
    moment = _datetime(now) if now is not None else _now()
    con = connect()
    try:
        rows = con.execute("SELECT * FROM free_release_windows ORDER BY starts_at DESC, id DESC LIMIT 150").fetchall()
        return [
            {**dict(row),
             "state": "disabled" if not row["enabled"] else
                      "scheduled" if moment < _datetime(row["starts_at"]) else
                      "ended" if moment >= _datetime(row["ends_at"]) else "open"}
            for row in rows
        ]
    finally:
        con.close()


def active_release(now=None):
    moment = _datetime(now) if now is not None else _now()
    con = connect()
    try:
        rows = con.execute(
            "SELECT * FROM free_release_windows WHERE enabled=1 AND starts_at<=? AND ends_at>? ORDER BY id DESC",
            (moment.isoformat(), moment.isoformat()),
        ).fetchall()
        # Parse as datetimes so ISO formatting differences can never bypass the bounds.
        return next((dict(r) for r in rows
                     if _datetime(r["starts_at"]) <= moment < _datetime(r["ends_at"])), None)
    finally:
        con.close()


def allowed_round(context, now=None):
    release = active_release(now)
    if not release:
        return False
    try:
        target = estimate_target_datetime_eat(context["season"], context["next_matchday"])
    except (ValueError, TypeError, KeyError, OverflowError):
        return False
    first = _datetime(release["first_target_eat"]).astimezone(EAT)
    step = (target - first).total_seconds() / ROUND_DELTA.total_seconds()
    return float(step).is_integer() and 0 <= step < FREE_ROUNDS
