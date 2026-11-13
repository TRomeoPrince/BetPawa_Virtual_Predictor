"""Administrator-curated premium fixtures for 13 November 2026.

These records are manually supplied research selections, not bookmaker offers,
prediction-engine signals, verified odds, or automatically placed bets.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import threading
import time

EAT = ZoneInfo("Africa/Kampala")
PICK_DATE = "2026-11-13"

# The user's 13 November schedule, with home/away order preserved.
# 'watch' deliberately has no definitive betting selection.
PICKS = (
    ("139445", 7,  "BRE – SUN", "BRE WIN",           "20:37", "20:40", "20:45", "pick"),
    ("139445", 11, "CHE – TOT", "BTTS / Over 2.5",   "20:57", "21:00", "21:05", "pick"),
    ("139445", 13, "AST – CRY", "AST WIN",           "21:07", "21:10", "21:15", "pick"),
    ("139445", 20, "CRY – TOT", "Win/loss pattern",  "21:42", "21:45", "21:50", "watch"),
    ("139445", 26, "SUN – BRE", "BRE WIN",           "22:12", "22:15", "22:20", "pick"),
    ("139445", 30, "TOT – CHE", "BTTS / Over 2.5",   "22:32", "22:35", "22:40", "pick"),
    ("139445", 32, "CRY – AST", "AST WIN",           "22:42", "22:45", "22:50", "pick"),
    ("139446", 1,  "BRE – SUN", "BRE WIN",           "22:57", "23:00", "23:05", "pick"),
    ("139446", 5,  "CHE – TOT", "BTTS / Over 2.5",   "23:17", "23:20", "23:25", "pick"),
)


def _datetime(local_time: str) -> datetime:
    return datetime.fromisoformat(f"{PICK_DATE}T{local_time}:00").replace(tzinfo=EAT)


def snapshot(now: datetime | None = None) -> dict:
    """Return time-labelled picks; retain one day of closed entries for review."""
    current = (now or datetime.now(EAT)).astimezone(EAT)
    output = []
    for season, matchday, fixture, selection, alarm, opening, closing, kind in PICKS:
        alarm_at, opens_at, closes_at = map(_datetime, (alarm, opening, closing))
        # Old, closed picks should not be promoted as new recommendations indefinitely.
        if current >= closes_at + timedelta(days=1):
            continue
        if current >= closes_at:
            status = "closed"
        elif current >= opens_at:
            status = "window"
        elif current >= alarm_at:
            status = "soon"
        else:
            status = "upcoming"
        output.append({
            "date_eat": PICK_DATE,
            "season": season,
            "matchday": matchday,
            "fixture": fixture,
            "selection": selection,
            "kind": kind,
            "alarm_eat": alarm,
            "window_open_eat": opening,
            "window_close_eat": closing,
            "status": status,
        })
    return {
        "timezone": "Africa/Kampala",
        "source": "admin-curated; based on submitted fixture schedule",
        "items": output,
    }


# Official scores are read from the existing betPawa provider and held in memory
# after settlement; unresolved rounds retry at most once a minute per process.
_RESULTS: dict[tuple[str, int, str], dict] = {}
_ATTEMPTS: dict[tuple[str, int], float] = {}
_LOCK = threading.RLock()
RETRY_SECONDS = 60

_ALIASES = {
    "BRE": {"bre", "brentford"},
    "SUN": {"sun", "sunderland"},
    "CHE": {"che", "chelsea"},
    "TOT": {"tot", "tottenham", "tottenhamhotspur", "spurs"},
    "CRY": {"cry", "crystalpalace"},
    "AST": {"ast", "astonvilla", "astonvillafc"},
}


def _team_matches(abbreviation: str, feed_name: str) -> bool:
    clean = "".join(c for c in str(feed_name).lower() if c.isalnum())
    return clean in _ALIASES.get(abbreviation, set())


def _grade(item: dict, league_fixtures: list[dict]) -> dict | None:
    codes = item["fixture"].replace("–", "-").split("-")
    if len(codes) != 2:
        return None
    home_code, away_code = (v.strip().upper() for v in codes)
    matches = [
        x for x in league_fixtures
        if _team_matches(home_code, x.get("home", ""))
        and _team_matches(away_code, x.get("away", ""))
    ]
    if len(matches) != 1:
        return None
    match = matches[0]
    h, a = match.get("ft_home"), match.get("ft_away")
    if not isinstance(h, int) or not isinstance(a, int) or min(h, a) < 0:
        return None
    score = f"{h}–{a}"
    if item["kind"] == "watch":
        return {"ft_score": score, "result_summary": "FT recorded · pattern watch",
                "status": "watch-result"}
    if item["selection"] == "BTTS / Over 2.5":
        btts = "WON" if h > 0 and a > 0 else "LOST"
        over = "WON" if h + a >= 3 else "LOST"
        label = (f"BTTS {btts} · Over 2.5 {over}")
        kind = ("mixed" if btts != over else "won" if btts == "WON" else "lost")
        return {"ft_score": score, "result_summary": label, "status": kind,
                "market_results": {"btts": btts, "over_2_5": over}}
    selected = item["selection"].split(" ", 1)[0].upper()
    if selected not in (home_code, away_code) or not item["selection"].endswith(" WIN"):
        return None
    won = (h > a) if selected == home_code else (a > h)
    return {"ft_score": score, "result_summary": "WON" if won else "LOST",
            "status": "won" if won else "lost"}


def attach_results(snapshot_payload: dict, feed, now: datetime | None = None) -> dict:
    """Best-effort score check starting one minute after the scheduled close.

    A missing result remains pending; no historical winning rate is inserted
    as an actual outcome. Server and existing access checks remain separate.
    """
    current = (now or datetime.now(EAT)).astimezone(EAT)
    rows = snapshot_payload.get("items") or []
    eligible = [
        row for row in rows
        if row.get("status") == "closed"
        and current >= _datetime(row["window_close_eat"]) + timedelta(minutes=1)
    ]
    with _LOCK:
        # Throttle costly live browser-assisted reads across simultaneous users.
        due = sorted({
            (row["season"], int(row["matchday"])) for row in eligible
            if (row["season"], int(row["matchday"]), row["fixture"]) not in _RESULTS
            and current.timestamp() - _ATTEMPTS.get((row["season"], int(row["matchday"])), 0)
            >= RETRY_SECONDS
        })
        if due:
            for key in due:
                _ATTEMPTS[key] = current.timestamp()
            try:
                completed = feed.completed_premium_rounds(due)
            except Exception:
                completed = {}
            for row in eligible:
                key = (row["season"], int(row["matchday"]))
                cache_key = key + (row["fixture"],)
                if cache_key not in _RESULTS and key in completed:
                    grade = _grade(row, completed[key])
                    if grade:
                        _RESULTS[cache_key] = grade
        for row in eligible:
            grade = _RESULTS.get((row["season"], int(row["matchday"]), row["fixture"]))
            if grade:
                row.update(grade)
            else:
                row["status"] = "awaiting"
                row["result_summary"] = "Awaiting official FT score"
    return snapshot_payload
