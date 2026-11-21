"""Live-quote Double Chance screening, kept separate from validated picks.

BPV-E011 is a historical/prospective RESEARCH protocol, not a profitable
betting system. Only current, complete bookmaker price vectors are eligible.
No result or inferred score is used when producing this research watchlist.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

LOWER = 0.65
UPPER = 0.80
MARKET_ID = "4693"
CHOICES = ("12", "1X")

# Frozen descriptive E011 snapshot, 2026-11-21 06:19 UTC.
# These are not forward-test results, model probabilities, or ROI forecasts.
HISTORICAL = {
    "12": {"name": "No Draw (12)", "wins": 5478, "tests": 7221,
           "win_rate_pct": 75.8621, "roi_pct": -4.7581,
           "market_probability_pct": 75.5928},
    "1X": {"name": "Home or Draw (1X)", "wins": 2804, "tests": 3888,
           "win_rate_pct": 72.1193, "roi_pct": -5.0684,
           "market_probability_pct": 72.1479},
}


def _events(raw):
    """Follow the observed by-round event container, without fabricating rows."""
    if isinstance(raw, list):
        return [event for event in raw if isinstance(event, dict)]
    if isinstance(raw, dict):
        for key in ("responses", "items", "events", "data", "results"):
            value = raw.get(key)
            if isinstance(value, list):
                return [event for event in value if isinstance(event, dict)]
            if isinstance(value, dict):
                items = _events(value)
                if items:
                    return items
    return []


def _teams(event):
    home = away = None
    name = str(event.get("name") or "")
    if " - " in name:
        home, away = name.split(" - ", 1)
    elif " vs " in name.lower():
        idx = name.lower().index(" vs ")
        home, away = name[:idx], name[idx + 4:]
    if not home or not away:
        for p in event.get("participants") or []:
            if not isinstance(p, dict):
                continue
            role = str(p.get("type") or p.get("participantType") or "").upper()
            candidate = p.get("name") or (p.get("participant") or {}).get("name")
            if role == "HOME" and not home:
                home = candidate
            if role == "AWAY" and not away:
                away = candidate
    return str(home or "").strip(), str(away or "").strip()


def _valid_prices(event):
    """Only one complete, non-suspended 1X/X2/12 vector in the same event row."""
    if event.get("suspended") is True:
        return None
    candidates = []
    for market in event.get("markets") or []:
        if not isinstance(market, dict):
            continue
        market_type = market.get("marketType") or {}
        if str(market_type.get("id")) != MARKET_ID:
            continue
        if market.get("suspended") is True:
            continue
        for row in market.get("row") or []:
            if not isinstance(row, dict) or row.get("suspended") is True:
                continue
            prices = row.get("prices") or []
            if not isinstance(prices, list) or len(prices) != 3:
                continue
            selected = {}
            for p in prices:
                if not isinstance(p, dict) or p.get("suspended") is not False:
                    break  # Missing suspension state must fail closed.
                key = str(p.get("name") or "").strip().upper()
                if key not in ("1X", "X2", "12") or key in selected:
                    break
                try:
                    odd = float(p["odds"])
                except (ValueError, TypeError, KeyError):
                    break
                if not math.isfinite(odd) or odd <= 1.0:
                    break
                selected[key] = odd
            if set(selected) == {"1X", "X2", "12"}:
                candidates.append(selected)
    return candidates[0] if len(candidates) == 1 else None


def research_catalog():
    return [
        {"selection": choice, "label": data["name"],
         "wins": data["wins"], "tests": data["tests"],
         "win_rate_pct": data["win_rate_pct"], "roi_pct": data["roi_pct"],
         "average_bookmaker_probability_pct": data["market_probability_pct"],
         "status": "experimental-unprofitable-history",
         "probability_band": [LOWER, UPPER],
         "sample_utc": "2026-11-21T06:19:16Z"}
        for choice, data in HISTORICAL.items()
    ]


def candidates_for_round(raw, league_ids):
    """Find current research-eligible quotes, never manufacture an outcome.

    Double Chance outcomes overlap. The fair probabilities sum to TWO:
    P(selection) = 2*(1/decimal_odds)/sum(1/all_three_odds).
    Do not normalize to one or silently use 1X2 when DC is unavailable.
    """
    found = []
    seen = set()
    for event in _events(raw):
        competition = event.get("competition") or {}
        league = league_ids.get(str(competition.get("id"))) if isinstance(competition, dict) else None
        if not league:
            continue
        home, away = _teams(event)
        if not home or not away or home.casefold() == away.casefold():
            continue
        odds = _valid_prices(event)
        if odds is None:
            continue
        total_inverse = sum(1.0 / value for value in odds.values())
        if not math.isfinite(total_inverse) or total_inverse <= 0:
            continue
        probabilities = {name: 2.0 / (odd * total_inverse) for name, odd in odds.items()}
        if any(not 0 <= value <= 1 for value in probabilities.values()):
            continue
        for choice in CHOICES:
            p = probabilities[choice]
            if not (LOWER <= p < UPPER):
                continue
            key = (str(event.get("id") or ""), league, home, away, choice)
            if key in seen:
                continue
            seen.add(key)
            historical = HISTORICAL[choice]
            found.append({
                "event_id": str(event.get("id") or ""),
                "league": league, "home": home, "away": away,
                "selection": choice, "label": historical["name"],
                "decimal_odds": odds[choice],
                "bookmaker_probability_pct": round(p * 100, 2),
                "historical_tests": historical["tests"],
                "historical_win_rate_pct": historical["win_rate_pct"],
                "historical_roi_pct": historical["roi_pct"],
                "research_status": "experimental",
            })
    return sorted(found, key=lambda r: (r["league"], r["home"], r["away"], CHOICES.index(r["selection"])))
