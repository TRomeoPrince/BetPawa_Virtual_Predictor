from __future__ import annotations
from typing import Any


def _complete(m: dict[str, Any]) -> bool:
    return all(isinstance(m.get(k), int) for k in ("ht_home", "ht_away", "ft_home", "ft_away"))


def _dedupe(picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for p in picks:
        key = (p.get("target_position"), p.get("target_home"), p.get("target_away"))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _target_by_position(target: list[dict[str, Any]], position: int):
    return next((m for m in target if m.get("position") == position), None)


def _target_by_team(target: list[dict[str, Any]], team: str):
    return next((m for m in target if m.get("home") == team or m.get("away") == team), None)


def _make_pick(rule: dict[str, Any], source: dict[str, Any], target: dict[str, Any] | None, selected_team: str | None):
    return {
        "rule_id": rule["rule_id"],
        "historical_win_rate": rule["win_rate"],
        "selected_team": selected_team,
        "source_position": source.get("position"),
        "target_position": target.get("position") if target else None,
        "target_home": target.get("home") if target else None,
        "target_away": target.get("away") if target else None,
        "expected": "Over 2.5 FT",
    }


def evaluate_league(rule: dict[str, Any], source: list[dict[str, Any]], target: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply exactly one frozen league rule. Strategy details never leave backend."""
    rid = rule["rule_id"]
    picks: list[dict[str, Any]] = []

    if rid.startswith("P4.ht00.pos"):
        pos = int(rid.rsplit("pos", 1)[1])
        s = next((m for m in source if m.get("position") == pos and _complete(m)), None)
        if s and s["ht_home"] == 0 and s["ht_away"] == 0:
            picks.append(_make_pick(rule, s, _target_by_position(target, pos), None))

    elif rid == "P4.ft00":
        for s in source:
            if _complete(s) and s["ft_home"] == 0 and s["ft_away"] == 0:
                picks.append(_make_pick(rule, s, _target_by_position(target, int(s["position"])), None))

    elif rid in {"P7.ht00over.loser", "P7.ht00over.winner"}:
        want_winner = rid.endswith("winner")
        for s in source:
            if not _complete(s):
                continue
            if s["ht_home"] != 0 or s["ht_away"] != 0:
                continue
            if s["ft_home"] + s["ft_away"] < 3 or s["ft_home"] == s["ft_away"]:
                continue
            if want_winner:
                team = s["home"] if s["ft_home"] > s["ft_away"] else s["away"]
            else:
                team = s["home"] if s["ft_home"] < s["ft_away"] else s["away"]
            picks.append(_make_pick(rule, s, _target_by_team(target, team), team))

    elif rid == "P13.rank3.loser":
        completed = [m for m in source if _complete(m)]
        levels = sorted({m["ft_home"] + m["ft_away"] for m in completed}, reverse=True)
        if len(levels) >= 3:
            level = levels[2]
            for s in completed:
                if s["ft_home"] + s["ft_away"] != level or s["ft_home"] == s["ft_away"]:
                    continue
                team = s["home"] if s["ft_home"] < s["ft_away"] else s["away"]
                picks.append(_make_pick(rule, s, _target_by_team(target, team), team))

    elif rid == "P6.ge6.loser":
        for s in source:
            if not _complete(s) or s["ft_home"] + s["ft_away"] < 6 or s["ft_home"] == s["ft_away"]:
                continue
            team = s["home"] if s["ft_home"] < s["ft_away"] else s["away"]
            picks.append(_make_pick(rule, s, _target_by_team(target, team), team))

    return _dedupe([p for p in picks if p.get("target_home") and p.get("target_away")])


def grade_pick(pick: dict[str, Any], target_rows: list[dict[str, Any]]) -> bool | None:
    """Return True/False for O2.5 if the target fixture has a final score."""
    row = None
    if pick.get("target_position") is not None:
        row = _target_by_position(target_rows, int(pick["target_position"]))
    if row is None and pick.get("selected_team"):
        row = _target_by_team(target_rows, str(pick["selected_team"]))
    if not row or not _complete(row):
        return None
    return (row["ft_home"] + row["ft_away"]) >= 3



# ---------- Multi-market strategy engine ----------

def _fixture_text(m: dict[str, Any]) -> str:
    return f"{m.get('home', '?')} - {m.get('away', '?')}"


def _teams_for_role(m: dict[str, Any], role: str) -> list[str]:
    role = role.lower()
    if role == "home":
        return [m["home"]]
    if role == "away":
        return [m["away"]]
    if role == "both":
        return [m["home"], m["away"]]
    if role in {"winner", "loser"}:
        if not _complete(m) or m["ft_home"] == m["ft_away"]:
            return []
        home_won = m["ft_home"] > m["ft_away"]
        if role == "winner":
            return [m["home"] if home_won else m["away"]]
        return [m["away"] if home_won else m["home"]]
    return []


def _previous_team_matches(
    rounds: list[list[dict[str, Any]]],
    before_index: int,
    team: str,
    limit: int,
):
    out = []
    for idx in range(before_index - 1, -1, -1):
        row = next(
            (m for m in rounds[idx] if m.get("home") == team or m.get("away") == team),
            None,
        )
        if row is not None and _complete(row):
            out.append((idx, row))
            if len(out) >= limit:
                break
    return out


def _multi_support(strategy, target_index, source_fixtures, selected_teams, target):
    return {
        "strategy_id": strategy["strategy_id"],
        "rule_id": strategy.get("rule_id") or strategy["strategy_id"],
        "strategy_family": strategy.get("strategy_family") or "Pattern 1",
        "strategy_name": strategy["strategy_name"],
        "league": strategy["league"],
        "target_market": strategy["market"],
        "historical_win_rate": strategy["win_rate"],
        "wins": strategy["wins"],
        "tests": strategy["tests"],
        "baseline": strategy["baseline"],
        "edge_pp": strategy["edge_pp"],
        "positive_seasons": strategy["positive_seasons"],
        "source_matchday": target_index,
        "target_matchday": target_index + 1,
        "source_fixtures": list(dict.fromkeys(source_fixtures)),
        "selected_teams": list(dict.fromkeys(selected_teams)),
        "target_fixture": _fixture_text(target),
        "trigger_explanation": strategy["strategy_name"],
    }


def evaluate_multimarket_strategy(
    strategy: dict[str, Any],
    rounds: list[list[dict[str, Any]]],
    target_index: int,
) -> list[dict[str, Any]]:
    """Apply one approved strategy with strict no-look-ahead.

    rounds contains one league only, ordered by matchday. Qualification reads
    only indexes strictly before target_index. The target round is used only to
    locate the already-selected team's/row's next fixture.
    """
    if target_index <= 0 or target_index >= len(rounds):
        return []

    source = rounds[target_index - 1]
    target = rounds[target_index]
    kind = strategy["kind"]
    params = strategy.get("params") or {}
    raw: list[dict[str, Any]] = []

    def emit(target_row, source_rows, teams):
        if not target_row:
            return
        support = _multi_support(
            strategy,
            target_index,
            [_fixture_text(x) for x in source_rows],
            teams,
            target_row,
        )
        raw.append({
            "league": strategy["league"],
            "target_market": strategy["market"],
            "target_position": target_row.get("position"),
            "target_home": target_row.get("home"),
            "target_away": target_row.get("away"),
            "selected_team": teams[0] if len(teams) == 1 else None,
            "selected_teams": teams,
            "support": support,
        })

    def follow_source_matches(source_matches, role):
        for s in source_matches:
            for team in _teams_for_role(s, role):
                emit(_target_by_team(target, team), [s], [team])

    completed = [m for m in source if _complete(m)]

    if kind == "ht00_over_follow":
        qualified = [
            m for m in completed
            if m["ht_home"] == 0 and m["ht_away"] == 0
            and m["ft_home"] + m["ft_away"] >= 3
        ]
        follow_source_matches(qualified, params["role"])

    elif kind == "total_threshold_follow":
        qualified = [
            m for m in completed
            if m["ft_home"] + m["ft_away"] >= int(params["min_total"])
        ]
        follow_source_matches(qualified, params["role"])

    elif kind == "total_exact_follow":
        qualified = [
            m for m in completed
            if m["ft_home"] + m["ft_away"] == int(params["total"])
        ]
        follow_source_matches(qualified, params["role"])

    elif kind == "second_half_follow":
        qualified = [
            m for m in completed
            if (m["ft_home"] + m["ft_away"]) - (m["ht_home"] + m["ht_away"])
            >= int(params["min_second_half"])
        ]
        follow_source_matches(qualified, params["role"])

    elif kind == "ht_draw_decisive_follow":
        qualified = [
            m for m in completed
            if m["ht_home"] == m["ht_away"] and m["ft_home"] != m["ft_away"]
        ]
        follow_source_matches(qualified, params["role"])

    elif kind == "matchday_avg_all":
        if completed and len(completed) == len(source):
            avg = sum(m["ft_home"] + m["ft_away"] for m in completed) / len(completed)
            if avg >= float(params["min_avg"]):
                for t in target:
                    emit(t, completed, [])

    elif kind == "rank_total_follow":
        levels = sorted(
            {m["ft_home"] + m["ft_away"] for m in completed},
            reverse=True,
        )
        rank = int(params["rank"])
        if len(levels) >= rank:
            wanted = levels[rank - 1]
            qualified = [
                m for m in completed
                if m["ft_home"] + m["ft_away"] == wanted
            ]
            follow_source_matches(qualified, params["role"])

    elif kind == "last3_over_team":
        for t in target:
            for team in (t.get("home"), t.get("away")):
                if not team:
                    continue
                prev = _previous_team_matches(rounds, target_index, team, 3)
                if len(prev) != 3:
                    continue
                if all(m["ft_home"] + m["ft_away"] >= 3 for _, m in prev):
                    emit(t, [m for _, m in prev], [team])

    elif kind == "both_previous_over":
        for t in target:
            home = t.get("home")
            away = t.get("away")
            if not home or not away:
                continue
            hp = _previous_team_matches(rounds, target_index, home, 1)
            ap = _previous_team_matches(rounds, target_index, away, 1)
            if len(hp) != 1 or len(ap) != 1:
                continue
            hm = hp[0][1]
            am = ap[0][1]
            if hm["ft_home"] + hm["ft_away"] >= 3 and am["ft_home"] + am["ft_away"] >= 3:
                emit(t, [hm, am], [home, away])

    elif kind == "conceded_threshold_follow":
        threshold = int(params["min_conceded"])
        for s in completed:
            if s["ft_away"] >= threshold:
                emit(_target_by_team(target, s["home"]), [s], [s["home"]])
            if s["ft_home"] >= threshold:
                emit(_target_by_team(target, s["away"]), [s], [s["away"]])

    elif kind == "largest_margin_follow":
        decisive = [m for m in completed if m["ft_home"] != m["ft_away"]]
        if decisive:
            max_margin = max(abs(m["ft_home"] - m["ft_away"]) for m in decisive)
            qualified = [
                m for m in decisive
                if abs(m["ft_home"] - m["ft_away"]) == max_margin
            ]
            follow_source_matches(qualified, params.get("role", "winner"))

    # One strategy may select both source teams which can lead to the same target
    # fixture. Merge those into one support record.
    merged: dict[tuple, dict[str, Any]] = {}
    for p in raw:
        key = (
            p.get("target_position"),
            p.get("target_home"),
            p.get("target_away"),
        )
        if key not in merged:
            merged[key] = p
            continue
        dst = merged[key]
        dst["selected_teams"] = list(dict.fromkeys(
            (dst.get("selected_teams") or []) + (p.get("selected_teams") or [])
        ))
        dst["selected_team"] = (
            dst["selected_teams"][0] if len(dst["selected_teams"]) == 1 else None
        )
        sup = dst["support"]
        psup = p["support"]
        sup["selected_teams"] = list(dict.fromkeys(
            sup.get("selected_teams", []) + psup.get("selected_teams", [])
        ))
        sup["source_fixtures"] = list(dict.fromkeys(
            sup.get("source_fixtures", []) + psup.get("source_fixtures", [])
        ))

    return list(merged.values())
