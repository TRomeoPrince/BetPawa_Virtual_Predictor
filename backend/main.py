from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .providers.betpawa import BetPawaFeed
from .predictor import build_prediction
from .time_windows import time_priority
from .db import (
    get_user_history,
    grade_user_predictions,
    save_user_prediction_batch,
    set_prediction_selected,
)

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend" / "index.html"
MARKET_PAGE = ROOT / "frontend" / "market.html"
COOKIE_NAME = "bp_predictor_user"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365

app = FastAPI(title="BetPawa Predictor", version="0.3.10")
feed = BetPawaFeed()


def _valid_user_id(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[a-f0-9]{32}", value))


def _user_id(request: Request, response: Response) -> str:
    value = request.cookies.get(COOKIE_NAME)
    if not _valid_user_id(value):
        value = uuid.uuid4().hex
        response.set_cookie(
            COOKIE_NAME,
            value,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
    return value


def _public_prediction(p: dict) -> dict:
    """Return only non-sensitive prediction data to the browser.

    Strategy IDs, names, triggers, source fixtures, selected teams and internal
    rule metadata never cross the API boundary.
    """
    supports = p.get("supports") or []
    top = supports[0] if supports else {}

    return {
        "league": p.get("league"),
        "target_position": p.get("target_position"),
        "target_home": p.get("target_home"),
        "target_away": p.get("target_away"),
        "expected": p.get("expected"),
        "target_market": p.get("target_market") or p.get("expected"),
        "support_count": int(p.get("support_count") or len(supports) or 1),
        "multiple_support": bool(p.get("multiple_support") or len(supports) > 1),
        "top_historical_win_rate": p.get("top_historical_win_rate") or p.get("confidence"),
        "top_wins": top.get("wins"),
        "top_tests": top.get("tests"),
        "top_edge_pp": top.get("edge_pp"),
        "top_positive_seasons": top.get("positive_seasons"),
        "strategy_families": p.get("strategy_families") or sorted({
            s.get("strategy_family") or "Pattern 1" for s in supports
        }),
        "strategy_family_label": p.get("strategy_family_label") or " + ".join(sorted({
            s.get("strategy_family") or "Pattern 1" for s in supports
        })),
        "estimated_target_time_eat": p.get("estimated_target_time_eat"),
        "time_window": p.get("time_window"),
        "time_source": p.get("time_source"),
        "timezone": p.get("timezone"),
        "utc_offset": p.get("utc_offset"),
        "time_status": p.get("time_status") or "UNCONFIRMED",
        "time_historical_wins": p.get("time_historical_wins"),
        "time_historical_tests": p.get("time_historical_tests"),
        "time_historical_rate": p.get("time_historical_rate"),
        "time_supports": [
            {
                "strategy_family": x.get("strategy_family") or "Pattern 1",
                "time_status": x.get("time_status") or "UNCONFIRMED",
                "time_historical_wins": x.get("time_historical_wins"),
                "time_historical_tests": x.get("time_historical_tests"),
                "time_historical_rate": x.get("time_historical_rate"),
                "time_window": x.get("time_window"),
            }
            for x in (p.get("time_supports") or [])
        ],
    }


def _public_tracker(t: dict) -> dict:
    """Expose tracker state/results without exposing private trigger internals."""
    return {
        "tracker_key": t.get("tracker_key"),
        "league": t.get("league"),
        "market": t.get("market"),
        "state": t.get("state"),
        "season_wins": t.get("season_wins"),
        "season_losses": t.get("season_losses"),
        "season_triggers": t.get("season_triggers"),
        "season_rate": t.get("season_rate"),
        "last_outcome": t.get("last_outcome"),
        "last_matchday": t.get("last_matchday"),
        "candidate_count": t.get("candidate_count"),
        "current_candidates": [
            {
                "league": p.get("league"),
                "target_home": p.get("target_home"),
                "target_away": p.get("target_away"),
                "expected": p.get("expected"),
            }
            for p in (t.get("current_candidates") or [])
        ],
    }


def _public_history(h: dict) -> dict:
    """Strip sensitive strategy metadata from personal history responses."""
    out = dict(h or {})
    # Exact rule IDs remain backend-only.
    out.pop("by_rule_internal", None)
    out.pop("by_rule_time_internal", None)

    def clean_batch(batch):
        if not batch:
            return batch
        b = dict(batch)
        cleaned = []
        for p in b.get("predictions") or []:
            supports = p.get("supports") or []
            top = supports[0] if supports else {}
            cleaned.append({
                "league": p.get("league"),
                "target_home": p.get("target_home"),
                "target_away": p.get("target_away"),
                "expected": p.get("expected"),
                "outcome": p.get("outcome"),
                "ht_home": p.get("ht_home"),
                "ht_away": p.get("ht_away"),
                "ft_home": p.get("ft_home"),
                "ft_away": p.get("ft_away"),
                "support_count": len(supports) or 1,
                "multiple_support": len(supports) > 1,
                "top_historical_win_rate": p.get("confidence"),
                "top_wins": top.get("wins"),
                "top_tests": top.get("tests"),
                "top_edge_pp": top.get("edge_pp"),
                "top_positive_seasons": top.get("positive_seasons"),
                "strategy_families": sorted({
                    s.get("strategy_family") or "Pattern 1" for s in supports
                }),
                "strategy_family_label": " + ".join(sorted({
                    s.get("strategy_family") or "Pattern 1" for s in supports
                })),
                "estimated_target_time_eat": p.get("estimated_target_time_eat"),
                "time_window": p.get("time_window"),
                "time_source": p.get("time_source"),
                "timezone": p.get("timezone"),
                "utc_offset": p.get("utc_offset"),
                "time_status": p.get("time_status") or "UNCONFIRMED",
                "time_historical_wins": p.get("time_historical_wins"),
                "time_historical_tests": p.get("time_historical_tests"),
                "time_historical_rate": p.get("time_historical_rate"),
                "time_supports": [
                    {
                        "strategy_family": s.get("strategy_family") or "Pattern 1",
                        "time_status": s.get("time_status") or "UNCONFIRMED",
                        "time_historical_wins": s.get("time_historical_wins"),
                        "time_historical_tests": s.get("time_historical_tests"),
                        "time_historical_rate": s.get("time_historical_rate"),
                        "time_window": s.get("time_window"),
                    }
                    for s in supports
                ],
                "created_at": p.get("created_at"),
                "graded_at": p.get("graded_at"),
                "selected": bool(p.get("selected")),
            })
        b["predictions"] = cleaned
        return b

    out["last_batch"] = clean_batch(out.get("last_batch"))
    out["last_completed_batch"] = clean_batch(out.get("last_completed_batch"))
    out["recent_batches"] = [
        clean_batch(b) for b in (out.get("recent_batches") or [])
    ]
    return out


MARKET_CATEGORIES = {"overs", "unders", "btts", "wins"}


class SelectionUpdate(BaseModel):
    season: str
    matchday: str
    league: str
    target_home: str
    target_away: str
    expected: str
    selected: bool



def _market_category(expected: str | None) -> str | None:
    label = " ".join(str(expected or "").upper().split())
    if label.startswith("OVER "):
        return "overs"
    if label.startswith("UNDER "):
        return "unders"
    if "BTTS" in label:
        return "btts"
    if label in {
        "HOME WIN", "AWAY WIN", "HOME FT", "AWAY FT",
        "FT HOME", "FT AWAY", "1", "2",
    }:
        return "wins"
    return None


def _filter_public_predictions(predictions: list[dict], category: str) -> list[dict]:
    filtered = [
        dict(p) for p in (predictions or [])
        if _market_category(p.get("expected")) == category
    ]
    filtered.sort(
        key=lambda p: (
            time_priority(p.get("time_status")),
            float(p.get("top_historical_win_rate") or 0.0),
            int(p.get("top_wins") or 0),
            int(p.get("support_count") or 0),
            int(p.get("top_tests") or 0),
        ),
        reverse=True,
    )
    for index, p in enumerate(filtered, start=1):
        p["market_rank"] = index
    return filtered


def _filter_public_history(history: dict, category: str) -> dict:
    """Return one market family's personal history without mixing other markets."""
    source = dict(history or {})
    out = dict(source)

    market_rows = [
        dict(m) for m in (source.get("by_market") or [])
        if _market_category(m.get("market")) == category
    ]
    wins = sum(int(m.get("wins") or 0) for m in market_rows)
    losses = sum(int(m.get("losses") or 0) for m in market_rows)
    pending = sum(int(m.get("pending") or 0) for m in market_rows)
    graded = wins + losses
    out["overall"] = {
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "graded": graded,
        "win_rate": (wins / graded) if graded else None,
    }
    out["by_market"] = market_rows

    family_rows = [
        dict(m) for m in (source.get("by_family_market") or [])
        if _market_category(m.get("market")) == category
    ]
    family_map = {}
    for row in family_rows:
        family = row.get("strategy_family") or "Pattern 1"
        item = family_map.setdefault(
            family,
            {"strategy_family": family, "wins": 0, "losses": 0, "pending": 0},
        )
        item["wins"] += int(row.get("wins") or 0)
        item["losses"] += int(row.get("losses") or 0)
        item["pending"] += int(row.get("pending") or 0)

    by_family = []
    for family in sorted(family_map):
        item = family_map[family]
        item["graded"] = item["wins"] + item["losses"]
        item["win_rate"] = (
            item["wins"] / item["graded"] if item["graded"] else None
        )
        by_family.append(item)
    out["by_family"] = by_family

    filtered_batches = []
    for batch in source.get("recent_batches") or []:
        b = dict(batch)
        preds = [
            dict(p) for p in (batch.get("predictions") or [])
            if _market_category(p.get("expected")) == category
        ]
        bw = sum(p.get("outcome") == "WON" for p in preds)
        bl = sum(p.get("outcome") == "LOST" for p in preds)
        bp = sum(p.get("outcome") == "PENDING" for p in preds)
        bg = bw + bl
        b.update({
            "predictions": preds,
            "candidate_count": len(preds),
            "wins": bw,
            "losses": bl,
            "pending": bp,
            "graded": bg,
            "win_rate": (bw / bg) if bg else None,
        })
        filtered_batches.append(b)

    out["recent_batches"] = filtered_batches
    out["last_batch"] = filtered_batches[0] if filtered_batches else None
    out["last_completed_batch"] = next(
        (
            b for b in filtered_batches
            if b.get("predictions")
            and b.get("graded", 0) > 0
            and b.get("pending", 0) == 0
        ),
        None,
    )

    selected_batches = []
    sw = sl = sp = 0
    for batch in filtered_batches:
        chosen = [p for p in (batch.get("predictions") or []) if p.get("selected")]
        if not chosen:
            continue
        b = dict(batch)
        bw = sum(p.get("outcome") == "WON" for p in chosen)
        bl = sum(p.get("outcome") == "LOST" for p in chosen)
        bp = sum(p.get("outcome") == "PENDING" for p in chosen)
        bg = bw + bl
        sw += bw
        sl += bl
        sp += bp
        b.update({
            "predictions": chosen,
            "candidate_count": len(chosen),
            "wins": bw,
            "losses": bl,
            "pending": bp,
            "graded": bg,
            "win_rate": (bw / bg) if bg else None,
        })
        selected_batches.append(b)

    selected_graded = sw + sl
    out["selected_overall"] = {
        "wins": sw,
        "losses": sl,
        "pending": sp,
        "graded": selected_graded,
        "win_rate": (sw / selected_graded) if selected_graded else None,
    }
    out["selected_batches"] = selected_batches
    out["last_selected_batch"] = selected_batches[0] if selected_batches else None
    out["last_completed_selected_batch"] = next(
        (
            b for b in selected_batches
            if b.get("graded", 0) > 0 and b.get("pending", 0) == 0
        ),
        None,
    )
    return out


def _frontend_response(path: Path, request: Request):
    response = FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
    _user_id(request, response)
    return response


@app.get("/")
def home(request: Request):
    return _frontend_response(FRONTEND, request)


@app.get("/overs")
@app.get("/unders")
@app.get("/btts")
@app.get("/wins")
def market_page(request: Request):
    return _frontend_response(MARKET_PAGE, request)


@app.get("/api/status")
def status():
    return {
        "app": "BetPawa Predictor",
        "version": "0.3.10",
        "rules_public": False,
        "mode": "Pattern 1 + Pattern 2 + time confirmation + cache-safe frontend",
    }


@app.post("/api/predict")
def predict(request: Request, response: Response):
    user_id = _user_id(request, response)
    started = time.perf_counter()
    try:
        context = feed.prediction_context()

        # Grade this browser user's old predictions using rounds we already had to
        # load for the current prediction. No extra round fetch is required.
        graded_now = grade_user_predictions(
            user_id,
            context.get("completed_rounds_for_grading", []),
        )

        result = build_prediction(context)
        result["feed_mode"] = context.get("feed_mode")
        result["next_round_id"] = context.get("next_round_id")
        result["performance"] = {
            "seconds": round(time.perf_counter() - started, 3),
            "round_cache_hits": context.get("round_cache_hits", 0),
            "round_cache_misses": context.get("round_cache_misses", 0),
            "context_cache_hit": bool(context.get("context_cache_hit")),
            "graded_previous_now": graded_now,
        }

        save_user_prediction_batch(user_id, result)

        public_result = dict(result)
        public_result["predictions"] = [
            _public_prediction(p) for p in result.get("predictions", [])
        ]
        public_result["trackers"] = [
            _public_tracker(t) for t in result.get("trackers", [])
        ]
        public_result["personal"] = _public_history(get_user_history(user_id))
        return public_result
    except Exception as e:
        raise HTTPException(502, str(e))


@app.post("/api/predict/{category}")
def predict_category(category: str, request: Request, response: Response):
    if category not in MARKET_CATEGORIES:
        raise HTTPException(404, "Unknown market page.")

    user_id = _user_id(request, response)
    started = time.perf_counter()
    try:
        context = feed.prediction_context()
        graded_now = grade_user_predictions(
            user_id,
            context.get("completed_rounds_for_grading", []),
        )

        result = build_prediction(context)
        result["feed_mode"] = context.get("feed_mode")
        result["next_round_id"] = context.get("next_round_id")
        result["performance"] = {
            "seconds": round(time.perf_counter() - started, 3),
            "round_cache_hits": context.get("round_cache_hits", 0),
            "round_cache_misses": context.get("round_cache_misses", 0),
            "context_cache_hit": bool(context.get("context_cache_hit")),
            "graded_previous_now": graded_now,
        }

        # Save the complete prediction snapshot once. The browser only receives
        # the market family it explicitly opened.
        save_user_prediction_batch(user_id, result)

        public_result = dict(result)
        public_result["predictions"] = _filter_public_predictions(
            [_public_prediction(p) for p in result.get("predictions", [])],
            category,
        )
        public_result["trackers"] = [
            _public_tracker(t)
            for t in result.get("trackers", [])
            if _market_category(t.get("market")) == category
        ]
        public_result["personal"] = _filter_public_history(
            _public_history(get_user_history(user_id)),
            category,
        )
        public_result["market_page"] = category
        return public_result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, str(e))


@app.post("/api/selection")
def update_selection(payload: SelectionUpdate, request: Request, response: Response):
    user_id = _user_id(request, response)
    changed = set_prediction_selected(
        user_id=user_id,
        season=payload.season,
        matchday=payload.matchday,
        league=payload.league,
        target_home=payload.target_home,
        target_away=payload.target_away,
        expected=payload.expected,
        selected=payload.selected,
    )
    if not changed:
        raise HTTPException(404, "Prediction was not found for this browser.")
    return {"ok": True, "selected": payload.selected}


@app.get("/api/history")
def history(request: Request, response: Response):
    user_id = _user_id(request, response)
    return _public_history(get_user_history(user_id))


@app.post("/api/history/refresh")
def refresh_history(request: Request, response: Response):
    user_id = _user_id(request, response)
    started = time.perf_counter()
    try:
        context = feed.prediction_context()
        graded = grade_user_predictions(
            user_id,
            context.get("completed_rounds_for_grading", []),
        )
        history = _public_history(get_user_history(user_id))
        history["refresh"] = {
            "graded_now": graded,
            "seconds": round(time.perf_counter() - started, 3),
            "context_cache_hit": bool(context.get("context_cache_hit")),
        }
        return history
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/api/history/{category}")
def history_category(category: str, request: Request, response: Response):
    if category not in MARKET_CATEGORIES:
        raise HTTPException(404, "Unknown market page.")
    user_id = _user_id(request, response)
    return _filter_public_history(
        _public_history(get_user_history(user_id)),
        category,
    )


@app.post("/api/history/{category}/refresh")
def refresh_history_category(category: str, request: Request, response: Response):
    if category not in MARKET_CATEGORIES:
        raise HTTPException(404, "Unknown market page.")

    user_id = _user_id(request, response)
    started = time.perf_counter()
    try:
        context = feed.prediction_context()
        graded = grade_user_predictions(
            user_id,
            context.get("completed_rounds_for_grading", []),
        )
        history = _filter_public_history(
            _public_history(get_user_history(user_id)),
            category,
        )
        history["refresh"] = {
            "graded_now": graded,
            "seconds": round(time.perf_counter() - started, 3),
            "context_cache_hit": bool(context.get("context_cache_hit")),
        }
        return history
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/api/predictions")
def predictions(request: Request, response: Response):
    # Backward-compatible endpoint, now correctly scoped to the requesting user.
    user_id = _user_id(request, response)
    return _public_history(get_user_history(user_id))


@app.get("/api/diagnose")
def diagnose():
    return feed.diagnose()
