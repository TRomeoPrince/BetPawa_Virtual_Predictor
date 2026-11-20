"""Conservative, read-only featured H2H research selector.

Evidence: NEW_PATTERNS/{Wins,OVERS,BTTS}/PAIR_MARKETS_2026-11-13.md,
validation seasons 139216-139226, independent recent 139430-139432.
These are small historical samples, not calibrated win probabilities.
Selections must ALSO be in the actual next-round predictor output.
No strategy is activated, no odds/ROI generated, and no bets placed.
"""
from __future__ import annotations

from .h2h_markets import _code

# Exact home/away orientation and independent market are mandatory.
# Tuples = validation wins, validation matches, recent wins, recent matches.
# Include only the most consistently observed, screened candidates.
# The frontend reports denominators, never claims a "sure win".
_EVIDENCE = {
    ("AST", "CRY", "HOME WIN"): (7, 8, 3, 3),
    ("AST", "CRY", "OVER 2.5 FT"): (7, 8, 3, 3),
    ("TOT", "CRY", "HOME WIN"): (7, 10, 2, 3),
    ("TOT", "CRY", "OVER 2.5 FT"): (7, 10, 2, 3),
    ("TOT", "CRY", "BTTS YES"): (7, 10, 2, 3),
    ("CHE", "TOT", "OVER 2.5 FT"): (8, 9, 2, 2),
    ("TOT", "CHE", "OVER 2.5 FT"): (8, 9, 2, 2),
    ("TOT", "CHE", "BTTS YES"): (9, 9, 2, 2),
}
# Recent checks show BRE-SUN to be inconsistent (e.g. HOME WIN 0/2
# recently despite 7/11 older validation) so both directions are removed
# from featured recommendations only, not historical logs or market pages.
_EXCLUDED_PAIRS = {("BRE", "SUN"), ("SUN", "BRE")}

# Research watches, clearly separated and NEVER called featured selections.
# CRY-TOT BTTS YES 7/11 (63.6%), recently 3/3; useful to investigate,
# insufficient to justify promotion to the stricter featured cutoff.
_WATCH_EVIDENCE = {("CRY", "TOT", "BTTS YES"): (7, 11, 3, 3)}


def _key(prediction):
    league = str(prediction.get("league") or "").strip().upper()
    if league not in {"ENGLISH", "EPL"}:
        return None
    home = _code(prediction.get("target_home"))
    away = _code(prediction.get("target_away"))
    market = str(prediction.get("expected") or "").strip().upper()
    if not home or not away or not market:
        return None
    if (home, away) in _EXCLUDED_PAIRS:
        return None
    return (home, away, market)


def _decorate(prediction, evidence, tier):
    wins, tests, recent_wins, recent_tests = evidence
    item = dict(prediction)
    item["research_evidence"] = {
        "status": tier,
        "validation_wins": wins,
        "validation_tests": tests,
        "recent_wins": recent_wins,
        "recent_tests": recent_tests,
        "sample_note": "Small historical samples; not a probability or guaranteed outcome.",
    }
    return item


def rank_recommendations(predictions):
    """Return (featured, watchlist) for real, already-authorized model picks.

    No predicted selections are invented. A reviewed fixture only qualifies
    for feature if validation >=70% over >=8 games and separate recent
    verification >=2/3 over >=2 matches. VENUE DIRECTION MUST MATCH.
    These thresholds screen historical research, not future certainty.
    """
    featured, watchlist = [], []
    seen = set()
    for prediction in predictions or ():
        key = _key(prediction)
        if key is None or key in seen:
            continue
        seen.add(key)
        evidence = _EVIDENCE.get(key)
        if evidence:
            wins, tests, recent_wins, recent_tests = evidence
            if tests >= 8 and wins / tests >= 0.7 and recent_tests >= 2 and recent_wins / recent_tests >= 2/3:
                featured.append(_decorate(prediction, evidence, "historical-screened"))
                continue
        evidence = _WATCH_EVIDENCE.get(key)
        if evidence:
            watchlist.append(_decorate(prediction, evidence, "watch-only"))
    featured.sort(key=lambda p: (
        -(p["research_evidence"]["validation_wins"]/p["research_evidence"]["validation_tests"]),
        -p["research_evidence"]["validation_tests"],
        str(p.get("target_home", "")), str(p.get("expected", "")),
    ))
    return featured, watchlist


# The exact market-specific H2H research the site owner asked to feature.
# This is an archive/watchlist, NOT a stream of scheduled live fixtures.
_REVIEW_ORDER = [
    ("TOT", "CHE", "BTTS YES"),
    ("TOT", "CHE", "OVER 2.5 FT"),
    ("CHE", "TOT", "OVER 2.5 FT"),
    ("TOT", "CRY", "HOME WIN"),
    ("TOT", "CRY", "OVER 2.5 FT"),
    ("TOT", "CRY", "BTTS YES"),
    ("AST", "CRY", "HOME WIN"),
    ("AST", "CRY", "OVER 2.5 FT"),
    ("CRY", "TOT", "BTTS YES"),
]


def reviewed_h2h_catalog():
    """Display reviewed pairs transparently when no qualifying live game exists.

    Historical data must never be mistaken for an actual scheduled match.
    Markets, venue direction, and smaller watch-only sample remain explicit.
    """
    result = []
    for key in _REVIEW_ORDER:
        evidence = _EVIDENCE.get(key) or _WATCH_EVIDENCE.get(key)
        if not evidence or (key[0], key[1]) in _EXCLUDED_PAIRS:
            continue
        wins, tests, recent_wins, recent_tests = evidence
        result.append({
            "home": key[0],
            "away": key[1],
            "market": key[2],
            "validation_wins": wins,
            "validation_tests": tests,
            "recent_wins": recent_wins,
            "recent_tests": recent_tests,
            "tier": "watch-only" if key in _WATCH_EVIDENCE else "historical-reviewed",
            "scheduled": False,
            "note": "Past H2H evidence only; NOT a currently verified fixture or guaranteed outcome.",
        })
    return result
