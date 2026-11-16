"""Admin-controlled, non-recurring Free prediction release windows.

Admin chooses a start/end (up to one year) and which of Overs, Unders, BTTS
is free. Legacy releases keep their original five-round time windows. A free
member never receives VIP history, private rule metadata or unapproved markets.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

from . import access
from .time_windows import ANCHOR_DATETIME_EAT, EAT, MATCHDAY_MINUTES, estimate_target_datetime_eat

FREE_ROUNDS = 5
ROUND_DELTA = timedelta(minutes=MATCHDAY_MINUTES)
MAX_WINDOW = timedelta(days=365)
FREE_MARKETS = ("overs", "unders", "btts")


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
    """First estimated 5-minute target strictly after release starts."""
    dt = start.astimezone(EAT)
    intervals = math.floor((dt - ANCHOR_DATETIME_EAT).total_seconds() / ROUND_DELTA.total_seconds()) + 1
    return ANCHOR_DATETIME_EAT + intervals * ROUND_DELTA


def _validate_window(start, end):
    first = _first_target(start)
    if end <= start:
        raise ValueError("End time must be after the start time.")
    if end <= first.astimezone(timezone.utc):
        raise ValueError("End time must include at least one upcoming estimated matchday (5 minutes).")
    if end - start > MAX_WINDOW:
        raise ValueError("One Free release cannot exceed 365 days. Choose a shorter end time.")
    return first


def _normalise_markets(markets):
    if markets is None:
        return list(FREE_MARKETS)
    if not isinstance(markets, (list, tuple)):
        raise ValueError("Choose Free markets as a list.")
    selected = []
    for code in markets:
        if not isinstance(code, str) or code not in FREE_MARKETS:
            raise ValueError("Allowed Free markets: Overs, Unders, BTTS.")
        if code not in selected:
            selected.append(code)
    if not selected:
        raise ValueError("Select at least one Free market.")
    return selected


def _stored_markets(raw):
    """Fail closed if a stored release has invalid or tampered market codes."""
    try:
        markets = json.loads(raw)
        if not isinstance(markets, list) or not markets or any(m not in FREE_MARKETS for m in markets):
            return []
        return list(dict.fromkeys(markets))
    except (ValueError, TypeError):
        return []


def _round_count(first, end):
    return max(0, int(math.ceil((end.astimezone(EAT) - first.astimezone(EAT)) / ROUND_DELTA)))


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
    # Additive migration: the existing database's original CHECK(round_count=5)
    # remains untouched; API round_count is derived from each release's window.
    columns = {row["name"] for row in con.execute("PRAGMA table_info(free_release_windows)")}
    if "market_codes" not in columns:
        con.execute("""ALTER TABLE free_release_windows ADD COLUMN market_codes TEXT NOT NULL
                       DEFAULT '["overs","unders","btts"]'""")
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


def create_release(starts_at=None, admin_id=None, enabled=True, ends_at=None, markets=None):
    start = _datetime(starts_at) if starts_at is not None else _now()
    first = _first_target(start)
    end = _datetime(ends_at) if ends_at is not None else (first + FREE_ROUNDS * ROUND_DELTA).astimezone(timezone.utc)
    _validate_window(start, end)
    chosen = _normalise_markets(markets)
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        if enabled:
            _check_overlap(con, start, end)
        cur = con.execute("""
            INSERT INTO free_release_windows(
                starts_at,ends_at,first_target_eat,round_count,enabled,actor_account_id,
                created_at,market_codes
            ) VALUES(?,?,?,?,?,?,?,?)
        """,(start.isoformat(),end.isoformat(),first.isoformat(),FREE_ROUNDS,
             int(bool(enabled)),admin_id,_now().isoformat(),json.dumps(chosen)))
        con.commit()
        return int(cur.lastrowid)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def update_release(release_id, starts_at=None, ends_at=None, markets=None, enabled=None, admin_id=None):
    """Editable start/end/markets for scheduled or disabled releases, not past releases."""
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM free_release_windows WHERE id=?",(release_id,)).fetchone()
        if not row:
            raise ValueError("Free release not found.")
        start = _datetime(starts_at) if starts_at is not None else _datetime(row["starts_at"])
        end = _datetime(ends_at) if ends_at is not None else _datetime(row["ends_at"])
        first = _validate_window(start,end)
        chosen = _normalise_markets(markets) if markets is not None else _stored_markets(row["market_codes"])
        if not chosen:
            raise ValueError("Choose at least one valid Free market.")
        is_enabled = bool(row["enabled"]) if enabled is None else bool(enabled)
        if is_enabled:
            if end <= _now():
                raise ValueError("This release has already ended. Choose a new future end time before enabling it.")
            _check_overlap(con,start,end,exclude=release_id)
        con.execute("""
            UPDATE free_release_windows SET starts_at=?,ends_at=?,first_target_eat=?,
                market_codes=?,enabled=?,actor_account_id=?
            WHERE id=?
        """,(start.isoformat(),end.isoformat(),first.isoformat(),json.dumps(chosen),
             int(is_enabled),admin_id if admin_id is not None else row["actor_account_id"],release_id))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def set_enabled(release_id, enabled):
    return update_release(release_id,enabled=enabled)


def delete_release(release_id):
    con = connect()
    try:
        count = con.execute("DELETE FROM free_release_windows WHERE id=?",(release_id,)).rowcount
        con.commit()
        if not count:
            raise ValueError("Free release not found.")
    finally:
        con.close()


def _release_dict(row, moment=None):
    item = dict(row)
    first = _datetime(item["first_target_eat"])
    end = _datetime(item["ends_at"])
    item["round_count"] = _round_count(first,end)
    item["markets"] = _stored_markets(item["market_codes"])
    if moment is not None:
        item["state"] = ("disabled" if not item["enabled"] else
                         "scheduled" if moment < _datetime(item["starts_at"]) else
                         "ended" if moment >= end else "open")
    return item


def list_releases(now=None):
    moment = _datetime(now) if now is not None else _now()
    con = connect()
    try:
        rows = con.execute("SELECT * FROM free_release_windows ORDER BY starts_at DESC, id DESC LIMIT 150").fetchall()
        return [_release_dict(row,moment) for row in rows]
    finally:
        con.close()


def active_release(now=None):
    moment = _datetime(now) if now is not None else _now()
    con = connect()
    try:
        # Compare real datetime values, never rely on timezone string equality.
        rows = con.execute(
            "SELECT * FROM free_release_windows WHERE enabled=1 ORDER BY id DESC LIMIT 150"
        ).fetchall()
        return next((_release_dict(r) for r in rows
                     if _datetime(r["starts_at"]) <= moment < _datetime(r["ends_at"])),None)
    finally:
        con.close()


def allowed_market(category, now=None):
    release = active_release(now)
    return bool(release and category in release["markets"])


def allowed_round(context, now=None):
    release = active_release(now)
    if not release:
        return False
    try:
        target = estimate_target_datetime_eat(context["season"],context["next_matchday"])
    except (ValueError,TypeError,KeyError,OverflowError):
        return False
    first = _datetime(release["first_target_eat"]).astimezone(EAT)
    end = _datetime(release["ends_at"]).astimezone(EAT)
    step = (target - first).total_seconds() / ROUND_DELTA.total_seconds()
    return float(step).is_integer() and target >= first and target < end
