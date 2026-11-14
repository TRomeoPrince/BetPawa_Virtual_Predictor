"""Exact-direction English virtual-football paired-fixture research picks.

11-season 139216-139226 validation counts from NEW_PATTERNS. The small
sample is exploratory, not a profitable betting edge. The three below-floor
user-requested choices remain visibly labelled WATCH, never silently promoted.
Scores for the target fixture are never consulted to generate a pick.
"""
from __future__ import annotations

_ALIASES = {
    "ast": "AST", "avl": "AST", "astonvilla": "AST", "astonvillafc": "AST",
    "cry": "CRY", "crystalpalace": "CRY", "crystalpalacefc": "CRY",
    "tot": "TOT", "tottenham": "TOT", "tottenhamhotspur": "TOT", "spurs": "TOT",
    "che": "CHE", "chelsea": "CHE", "chelseafc": "CHE",
    "bre": "BRE", "brentford": "BRE", "brentfordfc": "BRE",
    "sun": "SUN", "sunderland": "SUN", "sunderlandafc": "SUN",
}

# Each market is independent. Numbers are (wins, tests) in the documented
# 11-season validation subset, not a sum of overlapping historical archives.
_SCREENED = {
    ("AST", "CRY"): (("HOME WIN", 7, 8), ("Over 2.5 FT", 7, 8), ("BTTS YES", 5, 8)),
    ("CRY", "AST"): (("BTTS NO", 7, 10),),
    ("TOT", "CRY"): (("HOME WIN", 7, 10), ("Over 2.5 FT", 7, 10), ("BTTS YES", 7, 10)),
    ("CRY", "TOT"): (("BTTS YES", 7, 11),),
    ("CHE", "TOT"): (("Over 2.5 FT", 8, 9), ("BTTS YES", 7, 9)),
    ("TOT", "CHE"): (("Over 2.5 FT", 8, 9), ("BTTS YES", 9, 9)),
    ("BRE", "SUN"): (("HOME WIN", 7, 11), ("BTTS YES", 7, 11)),
}

# Explicitly requested market watches below the 60% historical screening floor.
_WATCH = {
    ("CRY", "AST"): (("AWAY WIN", 5, 10),),  # Aston Villa away
    ("CRY", "TOT"): (("Over 2.5 FT", 6, 11),),
    ("SUN", "BRE"): (("AWAY WIN", 2, 9),),   # Brentford away
}


def _code(value):
    compact = "".join(c for c in str(value or "").lower() if c.isalnum())
    return _ALIASES.get(compact)


def evaluate_pair_picks(english_fixtures):
    """Return independent exact-market picks for fixtures in the upcoming round.

    No cross-venue substitution, score inspection or implicit multi-market bet.
    """
    picks = []
    for row in english_fixtures or []:
        home, away = _code(row.get("home")), _code(row.get("away"))
        if not home or not away:
            continue
        pair = (home, away)
        for status, rules in (
            ("screened", _SCREENED.get(pair, ())),
            ("watch", _WATCH.get(pair, ())),
        ):
            for market, wins, tests in rules:
                if status == "screened" and wins / tests < 0.60:
                    continue
                suffix = market.replace(" ", "").replace(".", "")
                rule_id = f"H2H-{home}-{away}-{suffix}"
                team = row.get("home") if market == "HOME WIN" else (
                    row.get("away") if market == "AWAY WIN" else None
                )
                support = {
                    "strategy_id": rule_id,
                    "rule_id": rule_id,
                    "strategy_family": "Paired-fixture research",
                    "strategy_name": f"{home} - {away}: {market}",
                    "league": "English",
                    "target_market": market,
                    "historical_win_rate": wins / tests,
                    "wins": wins,
                    "tests": tests,
                    "positive_seasons": None,
                    "baseline": None,
                    "edge_pp": None,
                    "research_status": status,
                    "source_fixtures": [],
                    "selected_teams": [team] if team else [],
                    "target_fixture": f"{row.get('home')} - {row.get('away')}",
                    "trigger_explanation": (
                        "Exact fixture orientation, 11-season historical sample; "
                        "exploratory, no independently verified betting edge."
                    ),
                }
                picks.append({
                    "league": "English",
                    "target_position": row.get("position"),
                    "target_home": row.get("home"),
                    "target_away": row.get("away"),
                    "target_market": market,
                    "selected_team": team,
                    "selected_teams": [team] if team else [],
                    "support": support,
                })
    return picks
