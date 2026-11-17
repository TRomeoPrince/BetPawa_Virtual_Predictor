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
    PATTERN2_STRATEGIES,
    PATTERN2_LEGACY_KEYS,
    ORIGINAL_RULE_META,
)
from .rules_engine import evaluate_league, grade_pick, evaluate_multimarket_strategy
from .time_windows import apply_time_confirmation, time_priority
from .h2h_markets import evaluate_pair_picks


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


def _english_o25_tracker(context: dict[str, Any]) -> dict[str, Any]:
    """Track one English O2.5 pattern through the current season.

    Internal rule: highest FT goal-total level in a completed English round,
    follow the winner(s) into the next fixture, then grade O2.5.

    Lifecycle:
      ACTIVE -> loss -> RISKY
      RISKY -> win -> ACTIVE
      RISKY -> loss -> WATCHING
      WATCHING -> win -> ACTIVE
      WATCHING -> loss -> WATCHING

    WATCHING means the pattern is not trusted yet, but future triggers continue
    to be observed so a later recovery can reactivate it.

    If several source matches tie for the highest total, all decisive winners
    are followed. A trigger round counts as a success only when every resulting
    target pick finishes O2.5; this keeps the tracker conservative.
    """
    all_round_maps = context.get("strategy_rounds") or []
    target_index = context.get("strategy_target_index")
    if not isinstance(target_index, int) or target_index <= 0:
        return {}

    rounds = [round_map.get("English", []) for round_map in all_round_maps]
    tracker_strategy = {
        "strategy_id": "_tracker.english.rank1.winner",
        "strategy_name": "English O2.5 live tracker",
        "league": "English",
        "market": "Over 2.5 FT",
        "wins": 0,
        "tests": 1,
        "win_rate": 0.0,
        "baseline": 0.0,
        "edge_pp": 0.0,
        "positive_seasons": None,
        "kind": "rank_total_follow",
        "params": {"rank": 1, "role": "winner"},
    }

    state = "ACTIVE"
    events: list[dict[str, Any]] = []

    # Index target_index is the upcoming round, so only earlier targets can be
    # graded. Each idx represents one source->target trigger opportunity.
    for idx in range(1, min(target_index, len(rounds))):
        picks = evaluate_multimarket_strategy(tracker_strategy, rounds, idx)
        if not picks:
            continue

        outcomes = []
        fixtures = []
        for p in picks:
            row = next(
                (
                    m for m in rounds[idx]
                    if m.get("home") == p.get("target_home")
                    and m.get("away") == p.get("target_away")
                ),
                None,
            )
            if not row:
                continue
            fh, fa = row.get("ft_home"), row.get("ft_away")
            if not isinstance(fh, int) or not isinstance(fa, int):
                continue
            outcomes.append((fh + fa) >= 3)
            fixtures.append({
                "home": row.get("home"),
                "away": row.get("away"),
                "ft_home": fh,
                "ft_away": fa,
            })

        if not outcomes:
            continue

        worked = all(outcomes)
        before_state = state
        if worked:
            # Any successful observed trigger proves the pattern has started
            # working again, including after a WATCHING period.
            state = "ACTIVE"
        elif state == "ACTIVE":
            state = "RISKY"
        else:
            # A second loss moves RISKY -> WATCHING. Additional losses keep it
            # under observation rather than killing it for the whole season.
            state = "WATCHING"

        events.append({
            "matchday": idx + 1,
            "outcome": "WIN" if worked else "LOSS",
            "state_before": before_state,
            "state_after": state,
            "fixtures": fixtures,
        })

    current_picks = []
    if target_index < len(rounds):
        for p in evaluate_multimarket_strategy(tracker_strategy, rounds, target_index):
            current_picks.append({
                "league": "English",
                "target_home": p.get("target_home"),
                "target_away": p.get("target_away"),
                "expected": "Over 2.5 FT",
            })

    wins = sum(e["outcome"] == "WIN" for e in events)
    losses = sum(e["outcome"] == "LOSS" for e in events)
    last = events[-1] if events else None

    return {
        "tracker_key": "english_o25_live",
        "league": "English",
        "market": "Over 2.5 FT",
        "state": state,
        "season_wins": wins,
        "season_losses": losses,
        "season_triggers": len(events),
        "season_rate": (wins / len(events)) if events else None,
        "last_outcome": last.get("outcome") if last else None,
        "last_matchday": last.get("matchday") if last else None,
        "current_candidates": current_picks,
        "candidate_count": len(current_picks),
    }


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
                "rule_id": rule["rule_id"],
                "strategy_family": "Pattern 1",
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

    # Pattern 1 research rules. Exact mechanics that were promoted to Pattern 2
    # are skipped here to avoid counting the same rule twice under two families.
    strategy_rounds = context.get("strategy_rounds") or []
    target_index = context.get("strategy_target_index")
    if isinstance(target_index, int) and strategy_rounds:
        pattern1_strategies = [
            s for s in NEW_STRATEGIES
            if (s["league"], s["market"], s["strategy_id"]) not in PATTERN2_LEGACY_KEYS
        ]
        for strategy in pattern1_strategies:
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

        # Pattern 2 transition / sequence rules.
        for strategy in PATTERN2_STRATEGIES:
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

    # Exact home/away paired-fixture market research. Each independent Win,
    # Over and BTTS outcome has a distinct card and separate score grading.
    for p in evaluate_pair_picks(next_target.get("English", [])):
        add_support(
            p["league"], p["target_position"], p["target_home"],
            p["target_away"], p["target_market"], p["support"],
            selected_team=p["selected_team"],
            selected_teams=p["selected_teams"],
        )

    predictions = []
    for item in grouped.values():
        supports = sorted(
            item["supports"],
            key=lambda s: s.get("historical_win_rate") or 0.0,
            reverse=True,
        )
        item["supports"] = supports
        families = []
        for support in supports:
            family = support.get("strategy_family") or "Pattern 1"
            if family not in families:
                families.append(family)
        families.sort(key=lambda x: (0 if x == "Pattern 1" else 1, x))
        item["strategy_families"] = families
        item["strategy_family_label"] = " + ".join(families)
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
        item = apply_time_confirmation(
            item,
            context["season"],
            context["next_matchday"],
        )
        predictions.append(item)

    predictions.sort(
        key=lambda p: (
            time_priority(p.get("time_status")),
            p.get("top_historical_win_rate") or 0.0,
            (p.get("supports") or [{}])[0].get("wins") or 0,
            p.get("support_count") or 0,
        ),
        reverse=True,
    )

    trackers = []
    english_tracker = _english_o25_tracker(context)
    if english_tracker:
        trackers.append(english_tracker)

    return {
        "ok": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "season": context["season"],
        "latest_completed_matchday": context["latest_completed_matchday"],
        "next_matchday": context["next_matchday"],
        "next_round_id": context.get("next_round_id"),
        "next_round_open_utc": context.get("next_round_open_utc"),
        "next_round_close_utc": context.get("next_round_close_utc"),
        "alignment_scope": context["alignment_scope"],
        "leagues": leagues,
        "predictions": predictions,
        "trackers": trackers,
        "multi_market_strategy_count": (
            len([
                s for s in NEW_STRATEGIES
                if (s["league"], s["market"], s["strategy_id"]) not in PATTERN2_LEGACY_KEYS
            ])
            + len(PATTERN2_STRATEGIES)
        ),
        "pattern2_strategy_count": len(PATTERN2_STRATEGIES),
    }
