from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .private_rules import (
    RULES,
    MIN_RECENT_TESTS_FOR_PAUSE,
    MIN_RECENT_RATE,
    HISTORICAL_PRIOR_WEIGHT,
)
from .rules_engine import evaluate_league, grade_pick


@dataclass
class Alignment:
    wins: int = 0
    tests: int = 0

    @property
    def rate(self) -> float | None:
        return self.wins / self.tests if self.tests else None


def _grade_pairs(rule: dict[str, Any], pairs: list[tuple[list[dict], list[dict]]]) -> Alignment:
    a = Alignment()
    for source, target in pairs:
        for pick in evaluate_league(rule, source, target):
            outcome = grade_pick(pick, target)
            if outcome is None:
                continue
            a.tests += 1
            a.wins += int(outcome)
    return a


def _combine(a: Alignment, b: Alignment) -> Alignment:
    return Alignment(a.wins + b.wins, a.tests + b.tests)


def confidence(rule: dict[str, Any], recent: Alignment) -> float:
    """Shrink noisy recent results toward the frozen multi-season rate."""
    w = HISTORICAL_PRIOR_WEIGHT
    return (rule["win_rate"] * w + recent.wins) / (w + recent.tests)


def alignment_status(rule: dict[str, Any], recent: Alignment) -> str:
    if recent.tests < MIN_RECENT_TESTS_FOR_PAUSE:
        return "WARMUP"
    floor = max(MIN_RECENT_RATE, rule["baseline"])
    return "ALIGNED" if (recent.rate or 0.0) >= floor else "PAUSED"


def build_prediction(context: dict[str, Any]) -> dict[str, Any]:
    """Evaluate current alignment, then apply latest completed round to next round."""
    current_pairs_by_league = context["current_pairs_by_league"]
    previous_pairs_by_league = context.get("previous_pairs_by_league", {})
    latest_source = context["latest_source"]
    next_target = context["next_target"]

    leagues = []
    predictions = []

    for league, rule in RULES.items():
        current_alignment = _grade_pairs(rule, current_pairs_by_league.get(league, []))
        recent = current_alignment
        used_previous = False
        if context.get("use_previous_for_alignment"):
            prev = _grade_pairs(rule, previous_pairs_by_league.get(league, []))
            recent = _combine(current_alignment, prev)
            used_previous = prev.tests > 0

        status = alignment_status(rule, recent)
        conf = confidence(rule, recent)
        recent_rate = recent.rate

        league_info = {
            "league": league,
            "confidence": round(conf, 6),
            "recent_wins": recent.wins,
            "recent_tests": recent.tests,
            "recent_rate": round(recent_rate, 6) if recent_rate is not None else None,
            "alignment": status,
            "used_previous_season": used_previous,
        }

        source_rows = latest_source.get(league, [])
        target_rows = next_target.get(league, [])
        picks = [] if status == "PAUSED" else evaluate_league(rule, source_rows, target_rows)

        for p in picks:
            predictions.append({
                "league": league,
                "confidence": round(conf, 6),
                "recent_wins": recent.wins,
                "recent_tests": recent.tests,
                "alignment": status,
                "selected_team": p.get("selected_team"),
                "target_position": p.get("target_position"),
                "target_home": p.get("target_home"),
                "target_away": p.get("target_away"),
                "expected": "Over 2.5 FT",
            })

        league_info["triggered"] = bool(picks)
        league_info["prediction_count"] = len(picks)
        leagues.append(league_info)

    return {
        "ok": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "season": context["season"],
        "latest_completed_matchday": context["latest_completed_matchday"],
        "next_matchday": context["next_matchday"],
        "alignment_scope": context["alignment_scope"],
        "leagues": leagues,
        "predictions": predictions,
    }
