"""Private frozen strategy definitions.

These rules were selected from the user's saved multi-season validation results.
They stay server-side and are intentionally not returned by public API endpoints.
"""

RULES = {
    "English": {
        "rule_id": "P4.ht00.pos7",
        "wins": 68, "tests": 107, "win_rate": 68 / 107,
        "baseline": 0.586777,
    },
    "Spanish": {
        "rule_id": "P7.ht00over.loser",
        "wins": 145, "tests": 212, "win_rate": 145 / 212,
        "baseline": 0.572176,
    },
    "Italian": {
        "rule_id": "P4.ht00.pos6",
        "wins": 68, "tests": 105, "win_rate": 68 / 105,
        "baseline": 0.565565,
    },
    "German": {
        "rule_id": "P13.rank3.loser",
        "wins": 374, "tests": 558, "win_rate": 374 / 558,
        "baseline": 0.625038,
    },
    "French": {
        "rule_id": "P7.ht00over.winner",
        "wins": 104, "tests": 157, "win_rate": 104 / 157,
        "baseline": 0.595960,
    },
    "Dutch": {
        "rule_id": "P4.ft00",
        "wins": 89, "tests": 126, "win_rate": 89 / 126,
        "baseline": 0.650444,
    },
    "Portuguese": {
        "rule_id": "P6.ge6.loser",
        "wins": 159, "tests": 245, "win_rate": 159 / 245,
        "baseline": 0.587389,
    },
}

# Current-season sanity check. A validated rule is paused only after it has
# accumulated enough recent trigger outcomes and falls below this floor or the
# league's ordinary O2.5 baseline (whichever is higher).
MIN_RECENT_TESTS_FOR_PAUSE = 5
MIN_RECENT_RATE = 0.60

# Recent form should matter, but a tiny live sample must not overwrite hundreds
# of historical tests. This is the effective historical weight used to shrink
# the recent rate toward the validated historical rate.
HISTORICAL_PRIOR_WEIGHT = 20.0

# At the very start of a new season there is almost no current evidence. In that
# case the verifier may inspect only the tail of recent completed prior seasons.
EARLY_SEASON_COMPLETED_ROUNDS = 4
PREVIOUS_SEASON_ROUNDS_TO_CHECK = 11  # 11 rounds give up to 10 graded transitions.
MAX_PREVIOUS_SEASONS = 2
