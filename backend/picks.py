"""Private, account-scoped picks hub and user-reported bet journal.

Selections come from saved predictor choices; journal entries are manually
reported bets and must never be treated as verified bookmaker transactions.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from . import db

CATEGORIES = ("overs", "unders", "btts", "wins")
OUTCOMES = ("PENDING", "WON", "LOST")
BET_STATUSES = ("PENDING", "WON", "LOST", "VOID")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _category_condition(category):
    if category == "all":
        return "1=1"
    if category not in CATEGORIES:
        raise ValueError("Unknown market category.")
    return db._category_sql(category)


def _category_for_market(expected):
    market = (expected or "").upper()
    if "UNDER" in market:
        return "unders"
    if "OVER" in market:
        return "overs"
    if "BTTS" in market:
        return "btts"
    if "HOME WIN" in market or "AWAY WIN" in market:
        return "wins"
    return "other"


def get_picks(user_id, category="all", scope="latest", outcome="all", limit=50, offset=0):
    """Read every selected market in one account; paginate beyond six batches."""
    category_sql = _category_condition(category)
    if scope not in ("latest", "history", "all"):
        raise ValueError("Unknown selection scope.")
    if outcome != "all" and outcome not in OUTCOMES:
        raise ValueError("Unknown outcome.")
    limit = max(1, min(int(limit), 100))
    offset = max(0, min(int(offset), 1_000_000))

    con = db.connect()
    try:
        latest = con.execute("""
            SELECT p.season, p.matchday
            FROM user_predictions p
            LEFT JOIN user_prediction_batches b ON
              b.user_id=p.user_id AND b.season=p.season AND b.matchday=p.matchday
            WHERE p.user_id=? AND p.selected=1
            ORDER BY COALESCE(b.id,0) DESC, p.id DESC LIMIT 1
        """, (user_id,)).fetchone()

        totals = con.execute("""
            SELECT COUNT(*) AS total,
              SUM(CASE WHEN outcome='PENDING' THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN outcome='WON' THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN outcome='LOST' THEN 1 ELSE 0 END) AS losses
            FROM user_predictions WHERE user_id=? AND selected=1
        """, (user_id,)).fetchone()

        by_category = {}
        for cat in CATEGORIES:
            count = con.execute(
                "SELECT COUNT(*) FROM user_predictions WHERE user_id=? AND selected=1 AND (" +
                db._category_sql(cat) + ")", (user_id,),
            ).fetchone()[0]
            by_category[cat] = int(count)

        conditions = ["p.user_id=?", "p.selected=1", "(" + category_sql + ")"]
        args = [user_id]
        if latest and scope != "all":
            conditions.append(
                "(p.season=? AND p.matchday=?)" if scope == "latest" else
                "NOT (p.season=? AND p.matchday=?)"
            )
            args.extend([latest["season"], latest["matchday"]])
        elif not latest and scope != "all":
            conditions.append("1=0")
        if outcome != "all":
            conditions.append("p.outcome=?")
            args.append(outcome)
        where = " AND ".join(conditions)

        count = con.execute(
            "SELECT COUNT(*) FROM user_predictions p WHERE " + where,
            args,
        ).fetchone()[0]
        rows = con.execute("""
            SELECT p.id, p.season, p.matchday, p.league, p.target_home,
              p.target_away, p.expected, p.outcome, p.ht_home, p.ht_away,
              p.ft_home, p.ft_away, p.estimated_target_time_eat,
              p.time_status, p.created_at, p.graded_at
            FROM user_predictions p
            LEFT JOIN user_prediction_batches b ON
              b.user_id=p.user_id AND b.season=p.season AND b.matchday=p.matchday
            WHERE """ + where + """
            ORDER BY COALESCE(b.id,0) DESC, p.id DESC
            LIMIT ? OFFSET ?
        """, [*args, limit, offset]).fetchall()

        wins = int(totals["wins"] or 0)
        losses = int(totals["losses"] or 0)
        items = [{**dict(row), "category": _category_for_market(row["expected"])} for row in rows]
        return {
            "latest_matchday": dict(latest) if latest else None,
            "summary": {
                "total": int(totals["total"] or 0),
                "pending": int(totals["pending"] or 0),
                "wins": wins, "losses": losses,
                "win_rate": wins / (wins + losses) if wins + losses else None,
                "by_category": by_category,
            },
            "items": items, "total": int(count), "limit": limit, "offset": offset,
        }
    finally:
        con.close()


def connect_journal():
    con = db.connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS client_bet_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            bet_date TEXT NOT NULL,
            league TEXT NOT NULL DEFAULT '',
            fixture TEXT NOT NULL,
            category TEXT NOT NULL,
            selection TEXT NOT NULL,
            stake_ugx INTEGER NOT NULL,
            decimal_odds REAL NOT NULL,
            outcome TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.execute(
        "CREATE INDEX IF NOT EXISTS bet_journal_owner_date_idx "
        "ON client_bet_journal(user_id, bet_date DESC, id DESC)"
    )
    con.commit()
    return con


def _validate_bet(item):
    date_value = str(item.get("bet_date", ""))
    try:
        parsed = date.fromisoformat(date_value)
    except (ValueError, TypeError):
        raise ValueError("Enter a valid bet date (YYYY-MM-DD).")
    if parsed > datetime.now(ZoneInfo('Africa/Kampala')).date():
        raise ValueError("Historical bet date cannot be in the future.")

    fixture = str(item.get("fixture") or "").strip()
    selection = str(item.get("selection") or "").strip()
    league = str(item.get("league") or "").strip()
    notes = str(item.get("notes") or "").strip()
    category = str(item.get("category") or "")
    outcome = str(item.get("outcome") or "")
    stake = item.get("stake_ugx")
    odds = item.get("decimal_odds")

    if not fixture or len(fixture) > 180 or not selection or len(selection) > 180:
        raise ValueError("Fixture and selection are required (180 characters max).")
    if len(league) > 100 or len(notes) > 1000:
        raise ValueError("League or notes are too long.")
    if category not in CATEGORIES:
        raise ValueError("Select a valid market category.")
    if outcome not in BET_STATUSES:
        raise ValueError("Select a valid bet outcome.")
    if type(stake) is not int or not 1 <= stake <= 100_000_000:
        raise ValueError("Stake must be a whole UGX amount between 1 and 100,000,000.")
    if type(odds) not in (float, int) or not 1.01 <= odds <= 1000:
        raise ValueError("Decimal odds must be between 1.01 and 1000.")

    return {
        "bet_date": parsed.isoformat(), "league": league, "fixture": fixture,
        "category": category, "selection": selection, "stake_ugx": stake,
        "decimal_odds": round(float(odds), 4), "outcome": outcome,
        "notes": notes,
    }


def _public_bet(row):
    bet = dict(row)
    bet.pop("user_id", None)
    stake = bet["stake_ugx"]
    if bet["outcome"] == "WON":
        net = round(stake * (bet["decimal_odds"] - 1))
    elif bet["outcome"] == "LOST":
        net = -stake
    elif bet["outcome"] == "VOID":
        net = 0
    else:
        net = None
    bet["net_ugx"] = net
    return bet


def create_bet(user_id, payload):
    item = _validate_bet(payload)
    now = _now()
    con = connect_journal()
    try:
        cur = con.execute("""
            INSERT INTO client_bet_journal
              (user_id, bet_date, league, fixture, category, selection,
               stake_ugx, decimal_odds, outcome, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, item["bet_date"], item["league"], item["fixture"],
              item["category"], item["selection"], item["stake_ugx"],
              item["decimal_odds"], item["outcome"], item["notes"], now, now))
        con.commit()
        row = con.execute("SELECT * FROM client_bet_journal WHERE id=? AND user_id=?",
                          (cur.lastrowid, user_id)).fetchone()
        return _public_bet(row)
    finally:
        con.close()


def update_bet(user_id, bet_id, payload):
    item = _validate_bet(payload)
    con = connect_journal()
    try:
        cur = con.execute("""
            UPDATE client_bet_journal SET bet_date=?, league=?, fixture=?,
              category=?, selection=?, stake_ugx=?, decimal_odds=?, outcome=?,
              notes=?, updated_at=? WHERE id=? AND user_id=?
        """, (item["bet_date"], item["league"], item["fixture"], item["category"],
              item["selection"], item["stake_ugx"], item["decimal_odds"],
              item["outcome"], item["notes"], _now(), bet_id, user_id))
        if not cur.rowcount:
            con.rollback()
            raise ValueError("Bet record not found.")
        con.commit()
        row = con.execute("SELECT * FROM client_bet_journal WHERE id=? AND user_id=?",
                          (bet_id, user_id)).fetchone()
        return _public_bet(row)
    finally:
        con.close()


def delete_bet(user_id, bet_id):
    con = connect_journal()
    try:
        cur = con.execute("DELETE FROM client_bet_journal WHERE id=? AND user_id=?",
                          (bet_id, user_id))
        con.commit()
        return bool(cur.rowcount)
    finally:
        con.close()


def get_journal(user_id, category="all", outcome="all", limit=50, offset=0):
    if category != "all" and category not in CATEGORIES:
        raise ValueError("Unknown market category.")
    if outcome != "all" and outcome not in BET_STATUSES:
        raise ValueError("Unknown bet outcome.")
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    con = connect_journal()
    try:
        totals = con.execute("""
            SELECT COUNT(*) AS total,
              SUM(CASE WHEN outcome='WON' THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN outcome='LOST' THEN 1 ELSE 0 END) AS losses,
              SUM(CASE WHEN outcome='PENDING' THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN outcome='VOID' THEN 1 ELSE 0 END) AS void
            FROM client_bet_journal WHERE user_id=?
        """, (user_id,)).fetchone()
        where = ["user_id=?"]
        args = [user_id]
        if category != "all":
            where.append("category=?")
            args.append(category)
        if outcome != "all":
            where.append("outcome=?")
            args.append(outcome)
        clause = " AND ".join(where)
        total = con.execute("SELECT COUNT(*) FROM client_bet_journal WHERE " + clause, args).fetchone()[0]
        rows = con.execute(
            "SELECT * FROM client_bet_journal WHERE " + clause +
            " ORDER BY bet_date DESC, id DESC LIMIT ? OFFSET ?",
            [*args, limit, offset],
        ).fetchall()
        # Net P/L is calculated across all recorded bets, not just one page.
        net = con.execute("""
            SELECT COALESCE(SUM(CASE
              WHEN outcome='WON' THEN ROUND(stake_ugx*(decimal_odds-1))
              WHEN outcome='LOST' THEN -stake_ugx
              ELSE 0 END),0)
            FROM client_bet_journal WHERE user_id=?
        """, (user_id,)).fetchone()[0]
        return {
            "summary": {k: int(totals[k] or 0) for k in ("total", "wins", "losses", "pending", "void")} |
                       {"net_ugx": int(net or 0)},
            "items": [_public_bet(row) for row in rows],
            "total": int(total), "limit": limit, "offset": offset,
        }
    finally:
        con.close()
