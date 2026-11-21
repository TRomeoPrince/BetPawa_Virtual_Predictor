"""Convert current, eligible E011 Double Chance quotes into private 1X2-page picks.

The 1X2 page combines *distinct sportsbook markets*: 1/X/2 are full-time
result selections; 1X/X2/12 belong to Double Chance. Only research-approved
12 and 1X can be produced here, and only if a real current-round quote passed
the existing E011 odds-band filter. The strategy's negative ROI is not a gate.
"""
from __future__ import annotations

import math

from .double_chance_research import HISTORICAL

_ALLOWED = {"12", "1X"}


def from_context(context: dict) -> list[dict]:
    fixtures = context.get("next_target") or {}
    candidates = context.get("double_chance_research") or []
    lookup: dict[tuple[str, str, str], int] = {}
    for league, rows in fixtures.items():
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            home, away = row.get("home"), row.get("away")
            if home and away and isinstance(row.get("position"), int):
                lookup[(str(league), str(home), str(away))] = row["position"]

    predictions: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for candidate in candidates:
        choice = str(candidate.get("selection") or "").upper()
        if choice not in _ALLOWED:
            continue
        league = str(candidate.get("league") or "")
        home = str(candidate.get("home") or "")
        away = str(candidate.get("away") or "")
        key = (league, home, away, choice)
        if key in seen:
            continue
        position = lookup.get((league, home, away))
        if not position:
            continue  # Only actual next-round fixtures are allowed.
        try:
            odds = float(candidate["decimal_odds"])
            bookmaker_p = float(candidate["bookmaker_probability_pct"])
        except (KeyError, ValueError, TypeError):
            continue
        # The collector already applied the exact [65%, 80%) band before
        # rounding this displayed probability to two decimals. Allow the
        # 0.005-percentage-point boundary rounding here.
        if (not math.isfinite(odds) or odds <= 1 or
                not math.isfinite(bookmaker_p) or not 64.995 <= bookmaker_p <= 80.0):
            continue

        seen.add(key)
        historic = HISTORICAL[choice]
        rate = historic["wins"] / historic["tests"]
        support = {
            "strategy_id": "E011.DC." + choice,
            "rule_id": "E011.DC." + choice,
            "strategy_family": "Experimental Double Chance",
            "strategy_name": historic["name"],
            "target_market": choice,
            "research_status": "experimental",
            "historical_win_rate": rate,
            "wins": historic["wins"],
            "tests": historic["tests"],
            "baseline": historic["market_probability_pct"] / 100,
            "positive_seasons": "Prospective testing in progress",
        }
        predictions.append({
            "league": league,
            "target_position": position,
            "target_home": home,
            "target_away": away,
            "expected": choice,
            "target_market": choice,
            "market_type": "Double Chance",
            "research_status": "experimental",
            "selected_team": None,
            "selected_teams": [],
            "supports": [support],
            "support_count": 1,
            "top_historical_win_rate": rate,
            "top_wins": historic["wins"],
            "top_tests": historic["tests"],
            "confidence": rate,
            "time_status": "UNCONFIRMED",
            "time_alignment": "UNCONFIRMED",
            "time_alignment_note": "No independently validated time window for this odds-band rule.",
            "time_historical_windows": [],
            # Snapshot only. No bookmaker order or wager is made.
            "decimal_odds": odds,
            "bookmaker_probability_pct": bookmaker_p,
        })
    return predictions
