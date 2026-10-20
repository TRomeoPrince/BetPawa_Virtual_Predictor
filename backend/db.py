from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path(__file__).resolve().parent.parent / "data" / "predictor.db"


def _ensure_column(con, table: str, column: str, definition: str):
    cols = {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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
      ht_home INTEGER,
      ht_away INTEGER,
      ft_home INTEGER,
      ft_away INTEGER,
      graded_at TEXT,
      created_at TEXT NOT NULL,
      UNIQUE(user_id, season, matchday, prediction_key)
    )
    """)

    _ensure_column(con, "user_predictions", "ht_home", "INTEGER")
    _ensure_column(con, "user_predictions", "ht_away", "INTEGER")
    _ensure_column(con, "user_predictions", "supports_json", "TEXT")
    _ensure_column(con, "user_predictions", "selected", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(con, "user_predictions", "time_historical_rate", "REAL")
    _ensure_column(con, "user_predictions", "time_historical_tests", "INTEGER")
    _ensure_column(con, "user_predictions", "time_historical_wins", "INTEGER")
    _ensure_column(con, "user_predictions", "time_status", "TEXT")
    _ensure_column(con, "user_predictions", "utc_offset", "TEXT")
    _ensure_column(con, "user_predictions", "timezone", "TEXT")
    _ensure_column(con, "user_predictions", "time_source", "TEXT")
    _ensure_column(con, "user_predictions", "time_window", "TEXT")
    _ensure_column(con, "user_predictions", "estimated_target_time_eat", "TEXT")

    con.execute("""
    CREATE TABLE IF NOT EXISTS prediction_supports (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id TEXT NOT NULL,
      season TEXT NOT NULL,
      matchday TEXT NOT NULL,
      prediction_key TEXT NOT NULL,
      strategy_family TEXT NOT NULL,
      rule_id TEXT NOT NULL,
      league TEXT NOT NULL,
      target_home TEXT NOT NULL,
      target_away TEXT NOT NULL,
      market TEXT NOT NULL,
      historical_win_rate REAL,
      baseline REAL,
      edge_pp REAL,
      positive_seasons TEXT,
      outcome TEXT NOT NULL DEFAULT 'PENDING',
      created_at TEXT NOT NULL,
      graded_at TEXT,
      UNIQUE(user_id, season, matchday, prediction_key, strategy_family, rule_id)
    )
    """)

    _ensure_column(con, "prediction_supports", "estimated_target_time_eat", "TEXT")
    _ensure_column(con, "prediction_supports", "time_window", "TEXT")
    _ensure_column(con, "prediction_supports", "time_source", "TEXT")
    _ensure_column(con, "prediction_supports", "timezone", "TEXT")
    _ensure_column(con, "prediction_supports", "utc_offset", "TEXT")
    _ensure_column(con, "prediction_supports", "time_status", "TEXT")
    _ensure_column(con, "prediction_supports", "time_historical_wins", "INTEGER")
    _ensure_column(con, "prediction_supports", "time_historical_tests", "INTEGER")
    _ensure_column(con, "prediction_supports", "time_historical_rate", "REAL")

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
        prediction_key = _prediction_key(p)
        con.execute("""
        INSERT INTO user_predictions
          (user_id, season, matchday, target_round_id, prediction_key, league,
           selected_team, target_position, target_home, target_away, confidence,
           alignment, recent_wins, recent_tests, expected, supports_json,
           estimated_target_time_eat, time_window, time_source, timezone, utc_offset,
           time_status, time_historical_wins, time_historical_tests,
           time_historical_rate, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, season, matchday, prediction_key) DO UPDATE SET
          target_round_id=excluded.target_round_id,
          selected_team=excluded.selected_team,
          target_position=excluded.target_position,
          target_home=excluded.target_home,
          target_away=excluded.target_away,
          confidence=excluded.confidence,
          alignment=excluded.alignment,
          recent_wins=excluded.recent_wins,
          recent_tests=excluded.recent_tests,
          expected=excluded.expected,
          supports_json=excluded.supports_json,
          estimated_target_time_eat=excluded.estimated_target_time_eat,
          time_window=excluded.time_window,
          time_source=excluded.time_source,
          timezone=excluded.timezone,
          utc_offset=excluded.utc_offset,
          time_status=excluded.time_status,
          time_historical_wins=excluded.time_historical_wins,
          time_historical_tests=excluded.time_historical_tests,
          time_historical_rate=excluded.time_historical_rate
        """, (
            user_id, season, matchday, result.get("next_round_id"),
            prediction_key, p.get("league"), p.get("selected_team"),
            p.get("target_position"), p.get("target_home"), p.get("target_away"),
            p.get("confidence"), p.get("alignment"), p.get("recent_wins"),
            p.get("recent_tests"), p.get("expected") or "Over 2.5 FT",
            json.dumps(p.get("supports") or [], separators=(",", ":")),
            p.get("estimated_target_time_eat"), p.get("time_window"),
            p.get("time_source"), p.get("timezone"), p.get("utc_offset"),
            p.get("time_status"), p.get("time_historical_wins"),
            p.get("time_historical_tests"), p.get("time_historical_rate"), now,
        ))

        for support in p.get("supports") or []:
            family = str(support.get("strategy_family") or "Pattern 1")
            rule_id = str(support.get("rule_id") or support.get("strategy_id") or "")
            if not rule_id:
                continue
            con.execute("""
            INSERT INTO prediction_supports
              (user_id, season, matchday, prediction_key, strategy_family, rule_id,
               league, target_home, target_away, market, historical_win_rate,
               baseline, edge_pp, positive_seasons,
               estimated_target_time_eat, time_window, time_source, timezone,
               utc_offset, time_status, time_historical_wins,
               time_historical_tests, time_historical_rate, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, season, matchday, prediction_key, strategy_family, rule_id)
            DO UPDATE SET
              league=excluded.league,
              target_home=excluded.target_home,
              target_away=excluded.target_away,
              market=excluded.market,
              historical_win_rate=excluded.historical_win_rate,
              baseline=excluded.baseline,
              edge_pp=excluded.edge_pp,
              positive_seasons=excluded.positive_seasons,
              estimated_target_time_eat=excluded.estimated_target_time_eat,
              time_window=excluded.time_window,
              time_source=excluded.time_source,
              timezone=excluded.timezone,
              utc_offset=excluded.utc_offset,
              time_status=excluded.time_status,
              time_historical_wins=excluded.time_historical_wins,
              time_historical_tests=excluded.time_historical_tests,
              time_historical_rate=excluded.time_historical_rate
            """, (
                user_id, season, matchday, prediction_key, family, rule_id,
                p.get("league"), p.get("target_home"), p.get("target_away"),
                p.get("expected") or "Over 2.5 FT",
                support.get("historical_win_rate"), support.get("baseline"),
                support.get("edge_pp"), support.get("positive_seasons"),
                support.get("estimated_target_time_eat"), support.get("time_window"),
                support.get("time_source"), support.get("timezone"),
                support.get("utc_offset"), support.get("time_status"),
                support.get("time_historical_wins"),
                support.get("time_historical_tests"),
                support.get("time_historical_rate"), now,
            ))

    con.commit()
    con.close()


def set_prediction_selected(
    user_id: str,
    season: str,
    matchday: str,
    league: str,
    target_home: str,
    target_away: str,
    expected: str,
    selected: bool,
) -> bool:
    """Persist one browser user's choice without changing the prediction itself."""
    con = connect()
    cur = con.execute("""
      UPDATE user_predictions
      SET selected=?
      WHERE user_id=? AND season=? AND matchday=? AND league=?
        AND target_home=? AND target_away=? AND expected=?
    """, (
        1 if selected else 0,
        str(user_id), str(season), str(matchday), str(league),
        str(target_home), str(target_away), str(expected),
    ))
    con.commit()
    changed = cur.rowcount > 0
    con.close()
    return changed


def _result_side(home: int, away: int) -> str:
    if home > away:
        return "HOME"
    if home < away:
        return "AWAY"
    return "DRAW"


def _grade_market(expected: str, fixture: dict[str, Any]) -> bool | None:
    """Grade supported public market labels without exposing strategy internals.

    This prepares v0.3 for future approved strategies across Overs, Unders,
    BTTS, 1X2, Draws and HT/FT. Unknown labels stay pending instead of being
    incorrectly graded.
    """
    import re

    label = " ".join(str(expected or "").strip().upper().split())
    ht_home = fixture.get("ht_home")
    ht_away = fixture.get("ht_away")
    ft_home = fixture.get("ft_home")
    ft_away = fixture.get("ft_away")

    if not isinstance(ft_home, int) or not isinstance(ft_away, int):
        return None

    ft_total = ft_home + ft_away

    m = re.search(r"\b(OVER|UNDER)\s+(\d+(?:\.5)?)\s*(?:FT)?\b", label)
    if m:
        side, threshold = m.group(1), float(m.group(2))
        return ft_total > threshold if side == "OVER" else ft_total < threshold

    if "BTTS" in label:
        yes = ("YES" in label) or label.endswith("BTTS")
        no = "NO" in label
        if yes and not no:
            return ft_home > 0 and ft_away > 0
        if no:
            return not (ft_home > 0 and ft_away > 0)

    ft_side = _result_side(ft_home, ft_away)

    if label in {"HOME WIN", "HOME FT", "1", "FT HOME"}:
        return ft_side == "HOME"
    if label in {"AWAY WIN", "AWAY FT", "2", "FT AWAY"}:
        return ft_side == "AWAY"
    if label in {"DRAW", "FT DRAW", "FULL-TIME DRAW", "FULL TIME DRAW", "X"}:
        return ft_side == "DRAW"

    if label in {"HT DRAW", "HALF-TIME DRAW", "HALF TIME DRAW"}:
        if not isinstance(ht_home, int) or not isinstance(ht_away, int):
            return None
        return ht_home == ht_away

    # HT/FT labels accepted in either form:
    # "HT/FT DRAW/HOME" or "DRAW/HOME HT/FT".
    if "HT/FT" in label or "HT FT" in label:
        if not isinstance(ht_home, int) or not isinstance(ht_away, int):
            return None
        cleaned = label.replace("HT/FT", " ").replace("HT FT", " ")
        tokens = re.findall(r"\b(HOME|DRAW|AWAY)\b", cleaned)
        if len(tokens) >= 2:
            return _result_side(ht_home, ht_away) == tokens[0] and ft_side == tokens[1]

    return None


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

        graded_value = _grade_market(row["expected"], fixture)
        if graded_value is None:
            continue

        ht_home = fixture.get("ht_home")
        ht_away = fixture.get("ht_away")
        outcome = "WON" if graded_value else "LOST"
        con.execute("""
        UPDATE user_predictions
        SET outcome=?, ht_home=?, ht_away=?, ft_home=?, ft_away=?, graded_at=?
        WHERE id=?
        """, (
            outcome,
            ht_home if isinstance(ht_home, int) else None,
            ht_away if isinstance(ht_away, int) else None,
            ft_home, ft_away, now, row["id"],
        ))
        con.execute("""
        UPDATE prediction_supports
        SET outcome=?, graded_at=?
        WHERE user_id=? AND season=? AND matchday=? AND prediction_key=?
        """, (
            outcome, now, user_id, str(row["season"]), str(row["matchday"]),
            str(row["prediction_key"]),
        ))
        graded += 1

    con.commit()
    con.close()
    return graded


def _batch_predictions(con, user_id: str, season: str, matchday: str):
    rows = con.execute("""
      SELECT league, selected_team, target_position, target_home, target_away,
             confidence, alignment, recent_wins, recent_tests, expected,
             outcome, ht_home, ht_away, ft_home, ft_away, graded_at, created_at,
             supports_json, selected, estimated_target_time_eat, time_window,
             time_source, timezone, utc_offset, time_status,
             time_historical_wins, time_historical_tests, time_historical_rate
      FROM user_predictions
      WHERE user_id=? AND season=? AND matchday=?
      ORDER BY confidence DESC, league, id
    """, (user_id, season, matchday)).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        raw = item.pop("supports_json", None)
        try:
            item["supports"] = json.loads(raw) if raw else []
        except Exception:
            item["supports"] = []
        out.append(item)
    return out


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

    market_rows = con.execute("""
      SELECT expected,
             SUM(CASE WHEN outcome='WON' THEN 1 ELSE 0 END) AS wins,
             SUM(CASE WHEN outcome='LOST' THEN 1 ELSE 0 END) AS losses,
             SUM(CASE WHEN outcome='PENDING' THEN 1 ELSE 0 END) AS pending
      FROM user_predictions
      WHERE user_id=?
      GROUP BY expected
      ORDER BY expected
    """, (user_id,)).fetchall()

    by_market = []
    for row in market_rows:
        mw = int(row["wins"] or 0)
        ml = int(row["losses"] or 0)
        mp = int(row["pending"] or 0)
        mg = mw + ml
        by_market.append({
            "market": row["expected"],
            "wins": mw,
            "losses": ml,
            "pending": mp,
            "graded": mg,
            "win_rate": (mw / mg) if mg else None,
        })

    family_market_rows = con.execute("""
      WITH family_picks AS (
        SELECT DISTINCT user_id, season, matchday, prediction_key,
               strategy_family, market, outcome
        FROM prediction_supports
        WHERE user_id=?
      )
      SELECT strategy_family, market,
             SUM(CASE WHEN outcome='WON' THEN 1 ELSE 0 END) AS wins,
             SUM(CASE WHEN outcome='LOST' THEN 1 ELSE 0 END) AS losses,
             SUM(CASE WHEN outcome='PENDING' THEN 1 ELSE 0 END) AS pending
      FROM family_picks
      GROUP BY strategy_family, market
      ORDER BY strategy_family, market
    """, (user_id,)).fetchall()

    by_family_market = []
    for row in family_market_rows:
        fw = int(row["wins"] or 0)
        fl = int(row["losses"] or 0)
        fp = int(row["pending"] or 0)
        fg = fw + fl
        by_family_market.append({
            "strategy_family": row["strategy_family"],
            "market": row["market"],
            "wins": fw,
            "losses": fl,
            "pending": fp,
            "graded": fg,
            "win_rate": (fw / fg) if fg else None,
        })

    rule_rows = con.execute("""
      SELECT strategy_family, rule_id, league, market,
             COUNT(*) AS predictions,
             SUM(CASE WHEN outcome='WON' THEN 1 ELSE 0 END) AS wins,
             SUM(CASE WHEN outcome='LOST' THEN 1 ELSE 0 END) AS losses,
             SUM(CASE WHEN outcome='PENDING' THEN 1 ELSE 0 END) AS pending,
             MAX(historical_win_rate) AS historical_win_rate,
             MAX(edge_pp) AS edge_pp
      FROM prediction_supports
      WHERE user_id=?
      GROUP BY strategy_family, rule_id, league, market
      ORDER BY strategy_family, rule_id
    """, (user_id,)).fetchall()

    by_rule_internal = []
    for row in rule_rows:
        item = dict(row)
        graded_count = int(item["wins"] or 0) + int(item["losses"] or 0)
        item["live_win_rate"] = (
            int(item["wins"] or 0) / graded_count if graded_count else None
        )
        by_rule_internal.append(item)

    time_rows = con.execute("""
      SELECT strategy_family, rule_id, league, market, time_window,
             COUNT(*) AS predictions,
             SUM(CASE WHEN outcome='WON' THEN 1 ELSE 0 END) AS wins,
             SUM(CASE WHEN outcome='LOST' THEN 1 ELSE 0 END) AS losses,
             SUM(CASE WHEN outcome='PENDING' THEN 1 ELSE 0 END) AS pending
      FROM prediction_supports
      WHERE user_id=? AND time_window IS NOT NULL
      GROUP BY strategy_family, rule_id, league, market, time_window
      ORDER BY strategy_family, rule_id, time_window
    """, (user_id,)).fetchall()

    by_rule_time_internal = []
    for row in time_rows:
        item = dict(row)
        graded_count = int(item["wins"] or 0) + int(item["losses"] or 0)
        item["live_win_rate"] = (
            int(item["wins"] or 0) / graded_count if graded_count else None
        )
        item["sample_status"] = (
            "stronger evidence" if graded_count >= 50
            else "usable" if graded_count >= 30
            else "provisional" if graded_count >= 20
            else "early"
        )
        by_rule_time_internal.append(item)

    con.close()

    wins = int(totals["wins"] or 0)
    losses = int(totals["losses"] or 0)
    pending = int(totals["pending"] or 0)
    graded = wins + losses

    last_completed_batch = next(
        (
            b for b in batches
            if b.get("predictions")
            and b.get("graded", 0) > 0
            and b.get("pending", 0) == 0
        ),
        None,
    )

    return {
        "overall": {
            "wins": wins,
            "losses": losses,
            "pending": pending,
            "graded": graded,
            "win_rate": (wins / graded) if graded else None,
        },
        "last_batch": batches[0] if batches else None,
        "last_completed_batch": last_completed_batch,
        "by_market": by_market,
        "by_family_market": by_family_market,
        "by_rule_internal": by_rule_internal,
        "by_rule_time_internal": by_rule_time_internal,
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
