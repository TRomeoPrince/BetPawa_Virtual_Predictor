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
