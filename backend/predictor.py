from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .private_rules import (
    RULES,
    MIN_RECENT_TESTS_FOR_PAUSE,
    MIN_RECENT_RATE,
    HISTORICAL_PRIOR_WEIGHT,
    NEW_STRATEGIES,
    ORIGINAL_RULE_META,
)
from .rules_engine import evaluate_league, grade_pick, evaluate_multimarket_strategy


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
    """Build original frozen-rule picks plus the approved multi-market set.

    Exact market duplicates on the same fixture are merged. Supporting strategy
    rates remain separate; no combined probability is manufactured.
    """
    current_pairs_by_league = context["current_pairs_by_league"]
    previous_pairs_by_league = context.get("previous_pairs_by_league", {})
    latest_source = context["latest_source"]
    next_target = context["next_target"]

    leagues = []
    grouped: dict[tuple, dict[str, Any]] = {}

    def add_support(
        league: str,
        target_position,
        target_home,
        target_away,
        market: str,
        support: dict[str, Any],
        selected_team=None,
        selected_teams=None,
    ):
        if not target_home or not target_away:
            return
        key = (league, target_position, target_home, target_away, market)
        item = grouped.get(key)
        if item is None:
            item = {
                "league": league,
                "target_position": target_position,
                "target_home": target_home,
                "target_away": target_away,
                "expected": market,
                "target_market": market,
                "selected_team": selected_team,
                "selected_teams": list(selected_teams or ([selected_team] if selected_team else [])),
                "supports": [],
            }
            grouped[key] = item
        else:
            item["selected_teams"] = list(dict.fromkeys(
                item.get("selected_teams", []) +
                list(selected_teams or ([selected_team] if selected_team else []))
            ))
            if len(item["selected_teams"]) == 1:
                item["selected_team"] = item["selected_teams"][0]
            elif len(item["selected_teams"]) > 1:
                item["selected_team"] = None

        support_key = (support.get("strategy_id"), support.get("target_market"))
        existing_index = next(
            (
                i for i, s in enumerate(item["supports"])
                if (s.get("strategy_id"), s.get("target_market")) == support_key
            ),
            None,
        )
        if existing_index is None:
            item["supports"].append(support)
        else:
            # Prefer the richer support record without adding a duplicate.
            old = item["supports"][existing_index]
            if len(support) > len(old):
                item["supports"][existing_index] = support

    # Original seven frozen O2.5 rules: preserve the existing live-alignment gate.
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

        meta = ORIGINAL_RULE_META.get(league, {})
        for p in picks:
            support = {
                "strategy_id": rule["rule_id"],
                "strategy_name": meta.get("strategy_name", rule["rule_id"]),
                "league": league,
                "target_market": "Over 2.5 FT",
                "historical_win_rate": rule["win_rate"],
                "wins": rule["wins"],
                "tests": rule["tests"],
                "baseline": rule["baseline"],
                "edge_pp": round((rule["win_rate"] - rule["baseline"]) * 100, 2),
                "positive_seasons": meta.get("positive_seasons"),
                "source_matchday": context["latest_completed_matchday"],
                "target_matchday": context["next_matchday"],
                "source_fixtures": [p.get("source_fixture")] if p.get("source_fixture") else [],
                "selected_teams": [p["selected_team"]] if p.get("selected_team") else [],
                "target_fixture": f"{p.get('target_home')} - {p.get('target_away')}",
                "trigger_explanation": meta.get("strategy_name", rule["rule_id"]),
                "live_alignment": status,
                "recent_wins": recent.wins,
                "recent_tests": recent.tests,
            }
            add_support(
                league,
                p.get("target_position"),
                p.get("target_home"),
                p.get("target_away"),
                "Over 2.5 FT",
                support,
                selected_team=p.get("selected_team"),
            )

        league_info["triggered"] = bool(picks)
        league_info["prediction_count"] = len(picks)
        leagues.append(league_info)

    # Approved research rules. These fire only when every exact trigger condition
    # is satisfied. The target round is used only to locate the next fixture.
    strategy_rounds = context.get("strategy_rounds") or []
    target_index = context.get("strategy_target_index")
    if isinstance(target_index, int) and strategy_rounds:
        for strategy in NEW_STRATEGIES:
            league_rounds = [
                round_map.get(strategy["league"], [])
                for round_map in strategy_rounds
            ]
            for p in evaluate_multimarket_strategy(strategy, league_rounds, target_index):
                add_support(
                    p["league"],
                    p.get("target_position"),
                    p.get("target_home"),
                    p.get("target_away"),
                    p["target_market"],
                    p["support"],
                    selected_team=p.get("selected_team"),
                    selected_teams=p.get("selected_teams"),
                )

    predictions = []
    for item in grouped.values():
        supports = sorted(
            item["supports"],
            key=lambda s: s.get("historical_win_rate") or 0.0,
            reverse=True,
        )
        item["supports"] = supports
        item["support_count"] = len(supports)
        item["multiple_support"] = len(supports) > 1
        item["top_historical_win_rate"] = (
            supports[0].get("historical_win_rate") if supports else None
        )
        # Legacy DB/UI field: this is explicitly the top individual rule rate,
        # never an average or combined probability.
        item["confidence"] = item["top_historical_win_rate"]
        item["recent_wins"] = None
        item["recent_tests"] = None
        item["alignment"] = None
        predictions.append(item)

    predictions.sort(
        key=lambda p: (
            p.get("top_historical_win_rate") or 0.0,
            p.get("support_count") or 0,
        ),
        reverse=True,
    )

    return {
        "ok": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "season": context["season"],
        "latest_completed_matchday": context["latest_completed_matchday"],
        "next_matchday": context["next_matchday"],
        "next_round_id": context.get("next_round_id"),
        "alignment_scope": context["alignment_scope"],
        "leagues": leagues,
        "predictions": predictions,
        "multi_market_strategy_count": len(NEW_STRATEGIES),
    }
