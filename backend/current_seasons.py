"""Actual current virtual season status from betPawa's live season catalog.

Do not infer "current" from largest IDs, cached saved picks, or past seasons.
Source times are UTC; individual fixtures share a scheduled round window.
"""
from datetime import datetime, timezone
import time

from .providers.betpawa import BetPawaFeed, _parse_ts


def current_season_status(actual_catalog, now_ts=None):
    now = time.time() if now_ts is None else float(now_ts)
    observed = datetime.fromtimestamp(now, timezone.utc).isoformat()
    seasons = [
        season for season in BetPawaFeed._items(actual_catalog)
        if isinstance(season, dict) and BetPawaFeed._season_rounds(season)
    ]
    active = [
        season for season in seasons
        if (BetPawaFeed._season_start(season) or float("inf")) <= now
        < (BetPawaFeed._season_end(season) or 0)
    ]

    def window(round_obj):
        if not round_obj:
            return None
        trading = round_obj.get("tradingTime") or {}
        start, end = _parse_ts(trading.get("start")), _parse_ts(trading.get("end"))
        if start is None or end is None or end <= start:
            return None
        return {
            "round_id": str(round_obj["id"]),
            "round_open_utc": datetime.fromtimestamp(start, timezone.utc).isoformat(),
            "round_close_utc": datetime.fromtimestamp(end, timezone.utc).isoformat(),
        }

    result = {
        "verified_at_utc": observed,
        "status": "live" if active else "unavailable",
        "current_season": None,
        "current_matchday": None,
        "active_round": None,
        "next_matchday": None,
        "next_round": None,
        "upcoming_season": None,
    }
    # Missing current feed must not silently pass the last historical season
    # as "live". An unavailable status is clearer and safer than a guess.
    if not active:
        future = [s for s in seasons if (BetPawaFeed._season_start(s) or 0) > now]
        if future:
            result["upcoming_season"] = str(min(
                future, key=lambda s: BetPawaFeed._season_start(s) or float("inf")
            ).get("id"))
        return result

    season = max(active, key=lambda s: BetPawaFeed._season_start(s) or 0)
    rounds = BetPawaFeed._season_rounds(season)
    idx = next((
        i for i, r in enumerate(rounds)
        if (_parse_ts((r.get("tradingTime") or {}).get("start")) or float("inf")) <= now
        < (_parse_ts((r.get("tradingTime") or {}).get("end")) or 0)
    ), None)
    if idx is None:
        result["status"] = "unavailable"
        return result

    result.update({
        "current_season": str(season.get("id")),
        "current_matchday": idx + 1,
        "active_round": window(rounds[idx]),
    })
    if idx + 1 < len(rounds):
        result["next_matchday"] = idx + 2
        result["next_round"] = window(rounds[idx + 1])
    else:
        future = [s for s in seasons if (BetPawaFeed._season_start(s) or 0) > now]
        if future:
            nxt = min(future, key=lambda s: BetPawaFeed._season_start(s) or float("inf"))
            result["upcoming_season"] = str(nxt.get("id"))
            nxt_rounds = BetPawaFeed._season_rounds(nxt)
            if nxt_rounds:
                result["next_matchday"] = 1
                result["next_round"] = window(nxt_rounds[0])
    return result
