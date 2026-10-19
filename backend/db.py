from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path(__file__).resolve().parent.parent / "data" / "predictor.db"


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")

    # New v0.3 tables. The old predictions table is intentionally left alone so
    # existing installations migrate without destructive schema changes.
    con.execute("""
    CREATE TABLE IF NOT EXISTS user_prediction_batches (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id TEXT NOT NULL,
      season TEXT NOT NULL,
      matchday TEXT NOT NULL,
      target_round_id TEXT,
      candidate_count INTEGER NOT NULL DEFAULT 0,
      checked_at TEXT NOT NULL,
      UNIQUE(user_id, season, matchday)
    )
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS user_predictions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id TEXT NOT NULL,
      season TEXT NOT NULL,
      matchday TEXT NOT NULL,
      target_round_id TEXT,
      prediction_key TEXT NOT NULL,
      league TEXT NOT NULL,
      selected_team TEXT,
      target_position INTEGER,
      target_home TEXT NOT NULL,
      target_away TEXT NOT NULL,
      confidence REAL,
      alignment TEXT,
      recent_wins INTEGER,
      recent_tests INTEGER,
      expected TEXT NOT NULL DEFAULT 'Over 2.5 FT',
      outcome TEXT NOT NULL DEFAULT 'PENDING',
      ft_home INTEGER,
      ft_away INTEGER,
      graded_at TEXT,
      created_at TEXT NOT NULL,
      UNIQUE(user_id, season, matchday, prediction_key)
    )
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS round_cache (
      round_id TEXT PRIMARY KEY,
      season_id TEXT,
      matchday INTEGER,
      payload_json TEXT NOT NULL,
      settled INTEGER NOT NULL DEFAULT 0,
      updated_epoch REAL NOT NULL
    )
    """)
    con.commit()
    return con


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prediction_key(p: dict[str, Any]) -> str:
    return "|".join([
        str(p.get("league") or ""),
        str(p.get("selected_team") or ""),
        str(p.get("target_position") or ""),
        str(p.get("target_home") or ""),
        str(p.get("target_away") or ""),
        str(p.get("expected") or "Over 2.5 FT"),
    ])


def save_user_prediction_batch(user_id: str, result: dict[str, Any]):
    con = connect()
    season = str(result.get("season"))
    matchday = str(result.get("next_matchday"))
    now = _utc_now()
    predictions = result.get("predictions", [])

    con.execute("""
    INSERT INTO user_prediction_batches
      (user_id, season, matchday, target_round_id, candidate_count, checked_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id, season, matchday) DO UPDATE SET
      target_round_id=excluded.target_round_id,
      candidate_count=excluded.candidate_count,
      checked_at=excluded.checked_at
    """, (
        user_id, season, matchday, result.get("next_round_id"),
        len(predictions), now,
    ))

    for p in predictions:
        con.execute("""
        INSERT OR IGNORE INTO user_predictions
          (user_id, season, matchday, target_round_id, prediction_key, league,
           selected_team, target_position, target_home, target_away, confidence,
           alignment, recent_wins, recent_tests, expected, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, season, matchday, result.get("next_round_id"),
            _prediction_key(p), p.get("league"), p.get("selected_team"),
            p.get("target_position"), p.get("target_home"), p.get("target_away"),
            p.get("confidence"), p.get("alignment"), p.get("recent_wins"),
            p.get("recent_tests"), p.get("expected") or "Over 2.5 FT", now,
        ))

    con.commit()
    con.close()


def grade_user_predictions(user_id: str, completed_rounds: list[dict[str, Any]]) -> int:
    lookup: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for item in completed_rounds or []:
        lookup[(str(item.get("season")), str(item.get("matchday")))] = item.get("leagues") or {}

    if not lookup:
        return 0

    con = connect()
    rows = con.execute(
        "SELECT * FROM user_predictions WHERE user_id=? AND outcome='PENDING'",
        (user_id,),
    ).fetchall()

    graded = 0
    now = _utc_now()
    for row in rows:
        leagues = lookup.get((str(row["season"]), str(row["matchday"])))
        if not leagues:
            continue

        fixtures = leagues.get(row["league"]) or []
        fixture = next((
            x for x in fixtures
            if x.get("home") == row["target_home"]
            and x.get("away") == row["target_away"]
        ), None)
        if not fixture:
            continue

        ft_home = fixture.get("ft_home")
        ft_away = fixture.get("ft_away")
        if not isinstance(ft_home, int) or not isinstance(ft_away, int):
            continue

        outcome = "WON" if ft_home + ft_away >= 3 else "LOST"
        con.execute("""
        UPDATE user_predictions
        SET outcome=?, ft_home=?, ft_away=?, graded_at=?
        WHERE id=?
        """, (outcome, ft_home, ft_away, now, row["id"]))
        graded += 1

    con.commit()
    con.close()
    return graded


def _batch_predictions(con, user_id: str, season: str, matchday: str):
    rows = con.execute("""
      SELECT league, selected_team, target_position, target_home, target_away,
             confidence, alignment, recent_wins, recent_tests, expected,
             outcome, ft_home, ft_away, graded_at, created_at
      FROM user_predictions
      WHERE user_id=? AND season=? AND matchday=?
      ORDER BY confidence DESC, league, id
    """, (user_id, season, matchday)).fetchall()
    return [dict(r) for r in rows]


def get_user_history(user_id: str, limit_batches: int = 6) -> dict[str, Any]:
    con = connect()

    totals = con.execute("""
      SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN outcome='WON' THEN 1 ELSE 0 END) AS wins,
        SUM(CASE WHEN outcome='LOST' THEN 1 ELSE 0 END) AS losses,
        SUM(CASE WHEN outcome='PENDING' THEN 1 ELSE 0 END) AS pending
      FROM user_predictions WHERE user_id=?
    """, (user_id,)).fetchone()

    batch_rows = con.execute("""
      SELECT season, matchday, target_round_id, candidate_count, checked_at
      FROM user_prediction_batches
      WHERE user_id=?
      ORDER BY id DESC
      LIMIT ?
    """, (user_id, max(1, min(limit_batches, 20)))).fetchall()

    batches = []
    for b in batch_rows:
        item = dict(b)
        preds = _batch_predictions(con, user_id, item["season"], item["matchday"])
        wins = sum(p["outcome"] == "WON" for p in preds)
        losses = sum(p["outcome"] == "LOST" for p in preds)
        pending = sum(p["outcome"] == "PENDING" for p in preds)
        graded = wins + losses
        item.update({
            "predictions": preds,
            "wins": wins,
            "losses": losses,
            "pending": pending,
            "graded": graded,
            "win_rate": (wins / graded) if graded else None,
        })
        batches.append(item)

    con.close()

    wins = int(totals["wins"] or 0)
    losses = int(totals["losses"] or 0)
    pending = int(totals["pending"] or 0)
    graded = wins + losses

    return {
        "overall": {
            "wins": wins,
            "losses": losses,
            "pending": pending,
            "graded": graded,
            "win_rate": (wins / graded) if graded else None,
        },
        "last_batch": batches[0] if batches else None,
        "recent_batches": batches,
    }


def get_cached_round(
    round_id: str,
    require_settled: bool = False,
    max_age_seconds: int | None = None,
):
    con = connect()
    row = con.execute(
        "SELECT payload_json, settled, updated_epoch FROM round_cache WHERE round_id=?",
        (str(round_id),),
    ).fetchone()
    con.close()

    if not row:
        return None
    if require_settled and not bool(row["settled"]):
        return None
    if max_age_seconds is not None and time.time() - float(row["updated_epoch"]) > max_age_seconds:
        return None

    try:
        return json.loads(row["payload_json"])
    except Exception:
        return None


def save_cached_round(
    round_id: str,
    season_id: str,
    matchday: int,
    payload: Any,
    settled: bool,
):
    con = connect()
    con.execute("""
    INSERT INTO round_cache
      (round_id, season_id, matchday, payload_json, settled, updated_epoch)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(round_id) DO UPDATE SET
      season_id=excluded.season_id,
      matchday=excluded.matchday,
      payload_json=excluded.payload_json,
      settled=MAX(round_cache.settled, excluded.settled),
      updated_epoch=excluded.updated_epoch
    """, (
        str(round_id), str(season_id), int(matchday),
        json.dumps(payload, separators=(",", ":")),
        1 if settled else 0, time.time(),
    ))
    con.commit()
    con.close()
