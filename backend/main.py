from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse

from .providers.betpawa import BetPawaFeed
from .predictor import build_prediction
from .db import (
    get_user_history,
    grade_user_predictions,
    save_user_prediction_batch,
)

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend" / "index.html"
COOKIE_NAME = "bp_predictor_user"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365

app = FastAPI(title="BetPawa Predictor", version="0.3.3")
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
    }


def _public_history(h: dict) -> dict:
    """Strip sensitive strategy metadata from personal history responses."""
    out = dict(h or {})

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
                "created_at": p.get("created_at"),
                "graded_at": p.get("graded_at"),
            })
        b["predictions"] = cleaned
        return b

    out["last_batch"] = clean_batch(out.get("last_batch"))
    out["last_completed_batch"] = clean_batch(out.get("last_completed_batch"))
    out["recent_batches"] = [
        clean_batch(b) for b in (out.get("recent_batches") or [])
    ]
    return out


@app.get("/")
def home(request: Request):
    response = FileResponse(FRONTEND)
    _user_id(request, response)
    return response


@app.get("/api/status")
def status():
    return {
        "app": "BetPawa Predictor",
        "version": "0.3.3",
        "rules_public": False,
        "mode": "41-rule multi-market + frozen rules + personal cached prediction",
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
        public_result["personal"] = _public_history(get_user_history(user_id))
        return public_result
    except Exception as e:
        raise HTTPException(502, str(e))


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


@app.get("/api/predictions")
def predictions(request: Request, response: Response):
    # Backward-compatible endpoint, now correctly scoped to the requesting user.
    user_id = _user_id(request, response)
    return _public_history(get_user_history(user_id))


@app.get("/api/diagnose")
def diagnose():
    return feed.diagnose()
