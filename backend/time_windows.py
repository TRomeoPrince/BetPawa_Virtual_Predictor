from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

EAT = timezone(timedelta(hours=3))
ANCHOR_SEASON = 139222
ANCHOR_MATCHDAY = 33
ANCHOR_DATETIME_EAT = datetime(2026, 10, 18, 15, 5, tzinfo=EAT)
MATCHDAY_MINUTES = 5
MATCHDAYS_PER_SEASON = 34
SEASON_MINUTES = MATCHDAY_MINUTES * MATCHDAYS_PER_SEASON

TIME_SOURCE = "estimated"
TIMEZONE_NAME = "EAT"
UTC_OFFSET = "+03:00"

TIME_STATUS_PRIORITY = {
    "NO ALIGNMENT": -1,
    "UNCONFIRMED": 0,
    "NORMAL": 1,
    "MODERATE-STRONG": 2,
    "STRONG": 3,
    "VERY STRONG": 4,
}

# Historical reconstructed EAT windows. Keys are exact
# (league, market, rule_id) tuples so time evidence never leaks across rules.
TIME_WINDOW_HISTORY: dict[tuple[str, str, str], dict[str, Any]] = {
    # Dutch HT draw -> decisive FT -> follow winner.
    ("Dutch", "Over 2.5 FT", "P7.htdrawdecisive.winner"): {
        "default_status": "NORMAL",
        "windows": {
            0: {"status": "STRONG", "wins": 37, "tests": 46},
        },
    },

    # Pattern 2 Over 2.5
    ("Dutch", "Over 2.5 FT", "P2-O25-01"): {
        "default_status": "NORMAL",
        "windows": {
            1: {"status": "STRONG", "wins": 28, "tests": 36},
        },
    },
    ("French", "Over 2.5 FT", "P2-O25-02"): {
        "default_status": "NORMAL",
        "windows": {
            7: {"status": "STRONG", "wins": 41, "tests": 56},
        },
    },
    ("French", "Over 2.5 FT", "P2-O25-03"): {
        "default_status": "NORMAL",
        "windows": {
            1: {"status": "STRONG", "wins": 29, "tests": 41},
        },
    },
    ("Spanish", "Over 2.5 FT", "P2-O25-04"): {
        "default_status": "NORMAL",
        "windows": {
            20: {"status": "STRONG", "wins": 26, "tests": 35},
        },
    },
    ("Italian", "Over 2.5 FT", "P2-O25-05"): {
        "default_status": "UNCONFIRMED",
        "windows": {},
    },

    # Pattern 2 BTTS
    ("Dutch", "BTTS YES", "P2-BTTS-01"): {
        "default_status": "NORMAL",
        "windows": {
            0: {"status": "MODERATE-STRONG", "wins": 18, "tests": 25},
        },
    },
    ("French", "BTTS YES", "P2-BTTS-02"): {
        "default_status": "NORMAL",
        "windows": {
            21: {"status": "STRONG", "wins": 31, "tests": 44},
        },
    },
    ("Spanish", "BTTS YES", "P2-BTTS-03"): {
        "default_status": "NORMAL",
        "windows": {
            22: {"status": "VERY STRONG", "wins": 61, "tests": 74},
        },
    },

    # Other qualified rules with reconstructed time research.
    ("Spanish", "BTTS YES", "P3.sh3.loser"): {
        "default_status": "NORMAL",
        "windows": {
            22: {"status": "STRONG", "wins": 35, "tests": 47},
        },
    },
    ("Italian", "BTTS YES", "P6.ge6.winner"): {
        "default_status": "UNCONFIRMED",
        "windows": {},
    },
    ("German", "Over 2.5 FT", "P6.ge6.winner"): {
        "default_status": "NORMAL",
        "windows": {
            0: {"status": "MODERATE-STRONG", "wins": 16, "tests": 22},
        },
    },
    ("Spanish", "Over 2.5 FT", "P7.ht00over.loser"): {
        "default_status": "UNCONFIRMED",
        "windows": {},
    },
}


def estimate_target_datetime_eat(season: int | str, matchday: int | str) -> datetime:
    season_i = int(season)
    matchday_i = int(matchday)
    if not 1 <= matchday_i <= MATCHDAYS_PER_SEASON:
        raise ValueError(f"matchday must be 1..{MATCHDAYS_PER_SEASON}")
    delta_minutes = (
        SEASON_MINUTES * (season_i - ANCHOR_SEASON)
        + MATCHDAY_MINUTES * (matchday_i - ANCHOR_MATCHDAY)
    )
    return ANCHOR_DATETIME_EAT + timedelta(minutes=delta_minutes)


def hour_window(hour: int) -> str:
    h = int(hour) % 24
    return f"{h:02d}:00-{h:02d}:59"


def estimated_time_context(season: int | str, matchday: int | str) -> dict[str, Any]:
    dt = estimate_target_datetime_eat(season, matchday)
    return {
        "estimated_target_datetime_eat": dt.isoformat(),
        "estimated_target_time_eat": dt.strftime("%H:%M"),
        "time_window": hour_window(dt.hour),
        "time_hour": dt.hour,
        "time_source": TIME_SOURCE,
        "timezone": TIMEZONE_NAME,
        "utc_offset": UTC_OFFSET,
    }


def _historical_window_rows(config: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not config:
        return []
    rows: list[dict[str, Any]] = []
    for hour, window in sorted((config.get("windows") or {}).items()):
        wins = int(window.get("wins") or 0)
        tests = int(window.get("tests") or 0)
        rows.append({
            "time_window": hour_window(int(hour)),
            "time_hour": int(hour),
            "time_status": str(window.get("status") or "NORMAL"),
            "wins": wins,
            "tests": tests,
            "rate": (wins / tests) if tests else None,
        })
    return rows


def annotate_support_time(
    support: dict[str, Any],
    season: int | str,
    matchday: int | str,
) -> dict[str, Any]:
    out = deepcopy(support)
    base = estimated_time_context(season, matchday)
    out.update(base)

    rule_id = str(out.get("rule_id") or out.get("strategy_id") or "")
    key = (
        str(out.get("league") or ""),
        str(out.get("target_market") or ""),
        rule_id,
    )
    config = TIME_WINDOW_HISTORY.get(key)
    historical_windows = _historical_window_rows(config)
    matching = next(
        (row for row in historical_windows if row["time_hour"] == base["time_hour"]),
        None,
    )

    status = "UNCONFIRMED"
    wins = tests = None
    rate = None
    alignment = "UNCONFIRMED"
    alignment_note = "No historical time window is available for this strategy."
    matching_window = None

    if config and historical_windows:
        if matching:
            status = matching["time_status"]
            wins = matching["wins"]
            tests = matching["tests"]
            rate = matching["rate"]
            alignment = "MATCH"
            matching_window = matching["time_window"]
            alignment_note = (
                f"Estimated {base['estimated_target_time_eat']} EAT falls inside "
                f"the historical {matching_window} EAT window."
            )
        else:
            status = "NO ALIGNMENT"
            alignment = "NO MATCH"
            historical_labels = ", ".join(
                f"{row['time_window']} EAT" for row in historical_windows
            )
            alignment_note = (
                f"Estimated {base['estimated_target_time_eat']} EAT does not match "
                f"the historical successful window(s): {historical_labels}."
            )

    out.update({
        "time_status": status,
        "time_alignment": alignment,
        "time_alignment_window": matching_window,
        "time_alignment_note": alignment_note,
        "time_historical_wins": wins,
        "time_historical_tests": tests,
        "time_historical_rate": rate,
        "time_historical_windows": historical_windows,
    })
    return out


def apply_time_confirmation(
    prediction: dict[str, Any],
    season: int | str,
    matchday: int | str,
) -> dict[str, Any]:
    """Add time confirmation only after a valid strategy prediction exists."""
    item = deepcopy(prediction)
    supports = [
        annotate_support_time(s, season, matchday)
        for s in (item.get("supports") or [])
    ]
    item["supports"] = supports

    base = estimated_time_context(season, matchday)
    item.update(base)

    if not supports:
        item.update({
            "time_status": "UNCONFIRMED",
            "time_alignment": "UNCONFIRMED",
            "time_alignment_window": None,
            "time_alignment_note": "No strategy support is available for time confirmation.",
            "time_historical_wins": None,
            "time_historical_tests": None,
            "time_historical_rate": None,
            "time_historical_windows": [],
            "time_supports": [],
        })
        return item

    # Never average percentages. Pick the strongest support record only for the
    # combined display while preserving every individual support internally.
    strongest = max(
        supports,
        key=lambda s: (
            TIME_STATUS_PRIORITY.get(str(s.get("time_status")), -1),
            1 if s.get("time_alignment") == "MATCH" else 0,
            s.get("time_historical_rate") if s.get("time_historical_rate") is not None else -1.0,
        ),
    )

    item["time_status"] = strongest.get("time_status") or "UNCONFIRMED"
    item["time_alignment"] = strongest.get("time_alignment") or "UNCONFIRMED"
    item["time_alignment_window"] = strongest.get("time_alignment_window")
    item["time_alignment_note"] = strongest.get("time_alignment_note")
    item["time_historical_wins"] = strongest.get("time_historical_wins")
    item["time_historical_tests"] = strongest.get("time_historical_tests")
    item["time_historical_rate"] = strongest.get("time_historical_rate")
    item["time_historical_windows"] = strongest.get("time_historical_windows") or []
    item["time_supports"] = [
        {
            "time_status": s.get("time_status") or "UNCONFIRMED",
            "time_alignment": s.get("time_alignment") or "UNCONFIRMED",
            "time_alignment_window": s.get("time_alignment_window"),
            "time_alignment_note": s.get("time_alignment_note"),
            "time_historical_wins": s.get("time_historical_wins"),
            "time_historical_tests": s.get("time_historical_tests"),
            "time_historical_rate": s.get("time_historical_rate"),
            "time_historical_windows": s.get("time_historical_windows") or [],
        }
        for s in supports
    ]
    return item


def time_priority(value: str | None) -> int:
    return TIME_STATUS_PRIORITY.get(str(value or "UNCONFIRMED"), -1)
