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


# Descriptive metadata for the original seven frozen rules. This does not
# change their triggers; it is used only when presenting/storing support.
ORIGINAL_RULE_META = {
    "English": {"strategy_name": "HT 0-0 Row 7 → Same Row", "positive_seasons": "6/11"},
    "Spanish": {"strategy_name": "HT 0-0 → O2.5 → Loser", "positive_seasons": "9/11"},
    "Italian": {"strategy_name": "HT 0-0 Row 6 → Same Row", "positive_seasons": "8/11"},
    "German": {"strategy_name": "Third-Highest Distinct Total → Loser", "positive_seasons": "8/11"},
    "French": {"strategy_name": "HT 0-0 → O2.5 → Winner", "positive_seasons": "8/11"},
    "Dutch": {"strategy_name": "FT 0-0 → Same Row", "positive_seasons": "9/11"},
    "Portuguese": {"strategy_name": "6+ Goals → Loser", "positive_seasons": "7/11"},
}


def _s(
    strategy_id,
    strategy_name,
    league,
    market,
    wins,
    tests,
    baseline,
    edge_pp,
    positive_seasons,
    kind,
    strategy_family="Pattern 1",
    **params,
):
    return {
        "strategy_id": strategy_id,
        "rule_id": strategy_id,
        "strategy_family": strategy_family,
        "strategy_name": strategy_name,
        "league": league,
        "market": market,
        "wins": wins,
        "tests": tests,
        "win_rate": wins / tests,
        "baseline": baseline,
        "edge_pp": edge_pp,
        "positive_seasons": positive_seasons,
        "kind": kind,
        "params": params,
    }


# Qualified multi-market rules from the saved research pass.
# Validation seasons: 139216-139226. Discovery season: 139214.
NEW_STRATEGIES = [
    # OVER 1.5 FT
    _s("P7.ht00over.loser", "HT 0-0 → O2.5 → Loser", "Spanish", "Over 1.5 FT", 184, 212, 0.8008, 6.71, "10/11", "ht00_over_follow", role="loser"),
    _s("P6.ge6.home", "6+ Goals → Home", "Portuguese", "Over 1.5 FT", 252, 300, 0.8096, 3.04, "8/11", "total_threshold_follow", min_total=6, role="home"),
    _s("P3.sh3.loser", "3+ Second-Half Goals → Loser", "Spanish", "Over 1.5 FT", 586, 703, 0.8008, 3.27, "9/11", "second_half_follow", min_second_half=3, role="loser"),


    # UNDER 3.5 FT
    _s("P1.rank1.winner", "Highest Goal-Total Rank → Winner", "Italian", "Under 3.5 FT", 307, 444, 0.6562, 3.52, "8/11", "rank_total_follow", rank=1, role="winner"),
    _s("P6.eq5.loser", "Exactly 5 Goals → Loser", "Spanish", "Under 3.5 FT", 249, 363, 0.6529, 3.31, "8/11", "total_exact_follow", total=5, role="loser"),
    _s("P12.avgge3.5", "Source Round Avg ≥3.5 → All Next Fixtures", "English", "Under 3.5 FT", 556, 820, 0.6383, 3.98, "8/11", "matchday_avg_all", min_avg=3.5),
    _s("P7.htdrawdecisive.loser", "HT Draw → FT Decisive → Loser", "Dutch", "Under 3.5 FT", 458, 753, 0.5779, 3.03, "8/11", "ht_draw_decisive_follow", role="loser"),

    # OVER 2.5 FT
    _s("P7.htdrawdecisive.winner", "HT Draw → FT Decisive → Winner", "Dutch", "Over 2.5 FT", 516, 751, 0.6504, 3.66, "9/11", "ht_draw_decisive_follow", role="winner"),
    _s("P6.ge6.both", "6+ Goals → Both Teams", "Dutch", "Over 2.5 FT", 511, 745, 0.6504, 3.55, "10/11", "total_threshold_follow", min_total=6, role="both"),
    _s("P7.ht00over.loser", "HT 0-0 → O2.5 → Loser", "Spanish", "Over 2.5 FT", 145, 212, 0.5722, 11.18, "9/11", "ht00_over_follow", role="loser"),
    _s("P6.ge6.winner", "6+ Goals → Winner", "German", "Over 2.5 FT", 186, 280, 0.6250, 3.92, "8/11", "total_threshold_follow", min_total=6, role="winner"),
    _s("P6.eq5.away", "Exactly 5 Goals → Away", "English", "Over 2.5 FT", 217, 342, 0.5868, 4.77, "9/11", "total_exact_follow", total=5, role="away"),
    _s("P6.ge5.home", "5+ Goals → Home", "French", "Over 2.5 FT", 404, 637, 0.5960, 3.83, "8/11", "total_threshold_follow", min_total=5, role="home"),
    _s("P9.last3over", "Last 3 Team Matches O2.5", "French", "Over 2.5 FT", 745, 1180, 0.5960, 3.54, "11/11", "last3_over_team"),
    _s("P7.ht00over.away", "HT 0-0 → O2.5 → Away", "English", "Over 2.5 FT", 143, 229, 0.5868, 3.77, "9/11", "ht00_over_follow", role="away"),
    _s("P6.eq5.home", "Exactly 5 Goals → Home", "Spanish", "Over 2.5 FT", 223, 358, 0.5722, 5.07, "9/11", "total_exact_follow", total=5, role="home"),
    _s("P3.sh3.loser", "3+ Second-Half Goals → Loser", "Spanish", "Over 2.5 FT", 436, 703, 0.5722, 4.80, "9/11", "second_half_follow", min_second_half=3, role="loser"),
    _s("P1.rank1.away", "Highest Goal-Total Rank → Away", "Spanish", "Over 2.5 FT", 321, 518, 0.5722, 4.75, "8/11", "rank_total_follow", rank=1, role="away"),
    _s("P13.rank3.home", "Third-Highest Distinct Total → Home", "Spanish", "Over 2.5 FT", 483, 784, 0.5722, 4.39, "8/11", "rank_total_follow", rank=3, role="home"),
    _s("P11.bothover", "Both Teams Previous Match O2.5", "Spanish", "Over 2.5 FT", 713, 1161, 0.5722, 4.19, "8/11", "both_previous_over"),
    _s("P8.conceded4", "Conceded 4+ → Follow Team", "Spanish", "Over 2.5 FT", 309, 505, 0.5722, 3.97, "9/11", "conceded_threshold_follow", min_conceded=4),
    _s("P7.ht00over.home", "HT 0-0 → O2.5 → Home", "Italian", "Over 2.5 FT", 174, 287, 0.5656, 4.07, "8/11", "ht00_over_follow", role="home"),
    _s("P9.last3over", "Last 3 Team Matches O2.5", "Spanish", "Over 2.5 FT", 752, 1242, 0.5722, 3.33, "10/11", "last3_over_team"),

    # BTTS YES
    _s("P6.ge6.winner", "6+ Goals → Winner", "Dutch", "BTTS YES", 218, 325, 0.6315, 3.93, "8/11", "total_threshold_follow", min_total=6, role="winner"),
    _s("P1.rank1.home", "Highest Goal-Total Rank → Home", "Dutch", "BTTS YES", 318, 478, 0.6315, 3.38, "8/11", "rank_total_follow", rank=1, role="home"),
    _s("P3.sh3.winner", "3+ Second-Half Goals → Winner", "Dutch", "BTTS YES", 502, 756, 0.6315, 3.26, "9/11", "second_half_follow", min_second_half=3, role="winner"),
    _s("P7.ht00over.both", "HT 0-0 → O2.5 → Both Teams", "Spanish", "BTTS YES", 288, 446, 0.5829, 6.28, "9/11", "ht00_over_follow", role="both"),
    _s("P2.margin.winner", "Largest Winning Margin → Winner", "French", "BTTS YES", 351, 548, 0.5972, 4.33, "8/11", "largest_margin_follow", role="winner"),
    _s("P6.ge6.away", "6+ Goals → Away", "Spanish", "BTTS YES", 186, 291, 0.5829, 5.63, "8/11", "total_threshold_follow", min_total=6, role="away"),
    _s("P7.ht00over.away", "HT 0-0 → O2.5 → Away", "English", "BTTS YES", 146, 229, 0.5956, 4.20, "8/11", "ht00_over_follow", role="away"),
    _s("P3.sh3.loser", "3+ Second-Half Goals → Loser", "Spanish", "BTTS YES", 444, 703, 0.5829, 4.87, "10/11", "second_half_follow", min_second_half=3, role="loser"),
    _s("P11.bothover", "Both Teams Previous Match O2.5", "Spanish", "BTTS YES", 732, 1161, 0.5829, 4.76, "10/11", "both_previous_over"),
    _s("P6.ge6.winner", "6+ Goals → Winner", "Italian", "BTTS YES", 140, 224, 0.5774, 4.76, "9/11", "total_threshold_follow", min_total=6, role="winner"),
    _s("P8.conceded4", "Conceded 4+ → Follow Team", "Spanish", "BTTS YES", 315, 505, 0.5829, 4.08, "9/11", "conceded_threshold_follow", min_conceded=4),
    _s("P6.eq4.home", "Exactly 4 Goals → Home", "Spanish", "BTTS YES", 352, 570, 0.5829, 3.46, "9/11", "total_exact_follow", total=4, role="home"),
    _s("P13.rank3.home", "Third-Highest Distinct Total → Home", "Spanish", "BTTS YES", 484, 784, 0.5829, 3.44, "8/11", "rank_total_follow", rank=3, role="home"),
    _s("P9.last3over", "Last 3 Team Matches O2.5", "Spanish", "BTTS YES", 764, 1242, 0.5829, 3.22, "9/11", "last3_over_team"),
]


# Pattern 2: approved transition / sequence strategies.
# These use only completed source history and never target-match results to qualify.
# Over 1.5 and Under 3.5 are intentionally NOT added to Pattern 2.
PATTERN2_STRATEGIES = [
    _s(
        "P2-O25-01", "Dutch Extreme-Goals Transition", "Dutch", "Over 2.5 FT",
        511, 745, 0.6504, 3.55, "10/11", "total_threshold_follow",
        strategy_family="Pattern 2", min_total=6, role="both",
    ),
    _s(
        "P2-O25-02", "French 3-Match Over Streak", "French", "Over 2.5 FT",
        745, 1180, 0.5960, 3.54, "11/11", "last3_over_team",
        strategy_family="Pattern 2",
    ),
    _s(
        "P2-O25-03", "French 5+ Goal Source Home", "French", "Over 2.5 FT",
        404, 637, 0.5960, 3.83, "8/11", "total_threshold_follow",
        strategy_family="Pattern 2", min_total=5, role="home",
    ),
    _s(
        "P2-O25-04", "Spanish Highest-Total Away Follow", "Spanish", "Over 2.5 FT",
        321, 518, 0.5722, 4.75, "8/11", "rank_total_follow",
        strategy_family="Pattern 2", rank=1, role="away",
    ),
    _s(
        "P2-O25-05", "Italian HT 0-0 to FT Over Transition", "Italian", "Over 2.5 FT",
        174, 287, 0.5656, 4.07, "8/11", "ht00_over_follow",
        strategy_family="Pattern 2", role="home",
    ),
    _s(
        "P2-BTTS-01", "Dutch 6+ Goal Winner", "Dutch", "BTTS YES",
        218, 325, 0.6315, 3.93, "8/11", "total_threshold_follow",
        strategy_family="Pattern 2", min_total=6, role="winner",
    ),
    _s(
        "P2-BTTS-02", "French Biggest-Margin Winner", "French", "BTTS YES",
        351, 548, 0.5972, 4.33, "8/11", "largest_margin_follow",
        strategy_family="Pattern 2", role="winner",
    ),
    _s(
        "P2-BTTS-03", "Spanish Both-Previous-Over State", "Spanish", "BTTS YES",
        732, 1161, 0.5829, 4.76, "10/11", "both_previous_over",
        strategy_family="Pattern 2",
    ),
]

# These exact mechanics were already present in the earlier broad research list.
# Keep the old definitions in NEW_STRATEGIES for provenance, but evaluate them as
# Pattern 2 only so we do not double-count identical logic as independent support.
PATTERN2_LEGACY_KEYS = {
    ("Dutch", "Over 2.5 FT", "P6.ge6.both"),
    ("French", "Over 2.5 FT", "P9.last3over"),
    ("French", "Over 2.5 FT", "P6.ge5.home"),
    ("Spanish", "Over 2.5 FT", "P1.rank1.away"),
    ("Italian", "Over 2.5 FT", "P7.ht00over.home"),
    ("Dutch", "BTTS YES", "P6.ge6.winner"),
    ("French", "BTTS YES", "P2.margin.winner"),
    ("Spanish", "BTTS YES", "P11.bothover"),
}

# P2-HW-01 (Italian P11.scored3conceded3) remains ON HOLD because the exact
# original classifier is not present in this repository and must not be guessed.
