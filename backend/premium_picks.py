"""Administrator-curated premium fixtures for 13 November 2026.

These records are manually supplied research selections, not bookmaker offers,
prediction-engine signals, verified odds, or automatically placed bets.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
