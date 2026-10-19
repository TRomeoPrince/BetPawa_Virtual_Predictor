from __future__ import annotations
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB = Path(__file__).resolve().parent.parent / "data" / "predictor.db"


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      season TEXT,
      matchday TEXT,
      league TEXT NOT NULL,
      selected_team TEXT,
      target_position INTEGER,
      target_home TEXT,
      target_away TEXT,
      confidence REAL,
      alignment TEXT,
      recent_wins INTEGER,
      recent_tests INTEGER,
      expected TEXT NOT NULL DEFAULT 'Over 2.5 FT',
      created_at TEXT NOT NULL,
      UNIQUE(season, matchday, league, selected_team, target_position, target_home, target_away)
    )
    """)
    con.commit()
    return con


def save_public_predictions(result: dict):
    con = connect()
    now = datetime.now(timezone.utc).isoformat()
    for p in result.get("predictions", []):
        con.execute("""
        INSERT OR IGNORE INTO predictions
        (season, matchday, league, selected_team, target_position, target_home, target_away,
         confidence, alignment, recent_wins, recent_tests, expected, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(result.get("season")), str(result.get("next_matchday")), p["league"],
            p.get("selected_team"), p.get("target_position"), p.get("target_home"), p.get("target_away"),
            p.get("confidence"), p.get("alignment"), p.get("recent_wins"), p.get("recent_tests"),
            p.get("expected") or "Over 2.5 FT", now,
        ))
    con.commit(); con.close()


def list_predictions(limit: int = 100):
    con = connect()
    rows = con.execute("SELECT * FROM predictions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    return [dict(r) for r in rows]
