from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from .providers.betpawa import BetPawaFeed
from .predictor import build_prediction
from .time_windows import time_priority, TIME_WINDOW_HISTORY
from .private_rules import (
    RULES, ORIGINAL_RULE_META, NEW_STRATEGIES,
    PATTERN2_STRATEGIES, PATTERN2_LEGACY_KEYS,
)
from .access import (
    SESSION_COOKIE,
    account_from_session,
    authenticate,
    change_password,
    create_client,
    create_session,
    delete_session,
    ensure_bootstrap_admin,
    grant_subscription,
    list_clients,
    list_subscription_requests,
    public_account,
    public_plans,
    request_subscription,
    review_subscription_request,
    revoke_subscription,
)
from .db import (
    get_user_history,
    grade_user_predictions,
    save_user_prediction_batch,
    set_prediction_selected,
)

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend" / "index.html"
MARKET_PAGE = ROOT / "frontend" / "market.html"
LOGIN_PAGE = ROOT / "frontend" / "login.html"
CLIENT_PAGE = ROOT / "frontend" / "client.html"
ADMIN_PAGE = ROOT / "frontend" / "admin.html"
COOKIE_NAME = "bp_predictor_user"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365

app = FastAPI(
    title="BetPawa Predictor",
    version="0.4.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
feed = BetPawaFeed()

_bootstrap_password = ensure_bootstrap_admin()
if _bootstrap_password:
    print("\n" + "=" * 68)
    print("FIRST-RUN ADMIN LOGIN")
    print("Username: admin")
    print("Password:", _bootstrap_password)
    print("Change this password from Admin > Security after signing in.")
    print("=" * 68 + "\n")


def _valid_user_id(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[a-f0-9]{32}", value))


def _session_account(request: Request):
    return account_from_session(request.cookies.get(SESSION_COOKIE))


def _require_account(request: Request):
    account = _session_account(request)
    if not account:
        raise HTTPException(401, "Please sign in.")
    return account


def _require_active_access(request: Request):
    account = _require_account(request)
    if account.get("role") != "admin" and not account.get("subscription", {}).get("is_active"):
        raise HTTPException(403, "An active subscription is required.")
    return account


def _require_admin(request: Request):
    account = _require_account(request)
    if account.get("role") != "admin":
        raise HTTPException(403, "Admin access required.")
    return account


def _user_id(request: Request, response: Response) -> str:
    account = _session_account(request)
    if account and _valid_user_id(account.get("user_key")):
        return account["user_key"]

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
    out.pop("by_family_market", None)

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


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class ClientCreate(BaseModel):
    username: str
    display_name: str = ""
    plan_code: str | None = None


class SubscriptionGrant(BaseModel):
    plan_code: str
    custom_days: int | None = None


class SubscriptionRequestBody(BaseModel):
    plan_code: str


class RequestReview(BaseModel):
    approve: bool



def _admin_strategy_catalog() -> list[dict]:
    rows = []

    for league, rule in RULES.items():
        meta = ORIGINAL_RULE_META.get(league, {})
        rows.append({
            "strategy_family": "Pattern 1",
            "rule_id": rule["rule_id"],
            "strategy_name": meta.get("strategy_name", rule["rule_id"]),
            "league": league,
            "market": "Over 2.5 FT",
            "wins": rule["wins"],
            "tests": rule["tests"],
            "win_rate": rule["win_rate"],
            "baseline": rule["baseline"],
            "edge_pp": round((rule["win_rate"] - rule["baseline"]) * 100, 2),
            "positive_seasons": meta.get("positive_seasons"),
            "trigger": meta.get("strategy_name", rule["rule_id"]),
            "time_windows": TIME_WINDOW_HISTORY.get((league, "Over 2.5 FT", rule["rule_id"])),
        })

    pattern1 = [
        s for s in NEW_STRATEGIES
        if (s["league"], s["market"], s["strategy_id"]) not in PATTERN2_LEGACY_KEYS
    ]
    for strategy in pattern1 + list(PATTERN2_STRATEGIES):
        params = strategy.get("params") or {}
        param_text = ", ".join(f"{k}={v}" for k, v in params.items())
        trigger = strategy.get("strategy_name") or strategy["strategy_id"]
        if strategy.get("kind"):
            trigger += f" [{strategy['kind']}"
            if param_text:
                trigger += f": {param_text}"
            trigger += "]"
        rows.append({
            "strategy_family": strategy.get("strategy_family") or "Pattern 1",
            "rule_id": strategy.get("rule_id") or strategy["strategy_id"],
            "strategy_name": strategy.get("strategy_name") or strategy["strategy_id"],
            "league": strategy["league"],
            "market": strategy["market"],
            "wins": strategy["wins"],
            "tests": strategy["tests"],
            "win_rate": strategy["win_rate"],
            "baseline": strategy["baseline"],
            "edge_pp": strategy.get("edge_pp"),
            "positive_seasons": strategy.get("positive_seasons"),
            "trigger": trigger,
            "time_windows": TIME_WINDOW_HISTORY.get((
                strategy["league"], strategy["market"],
                strategy.get("rule_id") or strategy["strategy_id"],
            )),
        })

    rows.sort(key=lambda x: (x["strategy_family"], x["league"], x["market"], -x["win_rate"]))
    return rows


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


def _frontend_response(path: Path):
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/")
def home(request: Request):
    account = _session_account(request)
    if not account:
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/admin" if account.get("role") == "admin" else "/client", status_code=302)


@app.get("/login")
def login_page(request: Request):
    account = _session_account(request)
    if account:
        return RedirectResponse("/admin" if account.get("role") == "admin" else "/client", status_code=302)
    return _frontend_response(LOGIN_PAGE)


@app.get("/client")
def client_dashboard(request: Request):
    account = _session_account(request)
    if not account:
        return RedirectResponse("/login", status_code=302)
    return _frontend_response(CLIENT_PAGE)


@app.get("/admin")
def admin_dashboard(request: Request):
    account = _session_account(request)
    if not account:
        return RedirectResponse("/login", status_code=302)
    if account.get("role") != "admin":
        return RedirectResponse("/client", status_code=302)
    return _frontend_response(ADMIN_PAGE)


@app.get("/client/{category}")
def client_market_page(category: str, request: Request):
    if category not in MARKET_CATEGORIES:
        raise HTTPException(404, "Unknown market page.")
    account = _session_account(request)
    if not account:
        return RedirectResponse("/login", status_code=302)
    if account.get("role") != "admin" and not account.get("subscription", {}).get("is_active"):
        return RedirectResponse("/client", status_code=302)
    return _frontend_response(MARKET_PAGE)


@app.get("/overs")
@app.get("/unders")
@app.get("/btts")
@app.get("/wins")
def legacy_market_redirect(request: Request):
    category = request.url.path.strip("/")
    return RedirectResponse(f"/client/{category}", status_code=302)


@app.post("/api/auth/login")
def api_login(payload: LoginRequest, request: Request, response: Response):
    account = authenticate(payload.username, payload.password)
    if not account:
        raise HTTPException(401, "Invalid username or password.")
    token = create_session(int(account["id"]))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return {"ok": True, "account": public_account(account)}


@app.post("/api/auth/logout")
def api_logout(request: Request, response: Response):
    delete_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def api_me(request: Request):
    account = _require_account(request)
    return {"account": public_account(account)}


@app.post("/api/auth/change-password")
def api_change_password(payload: PasswordChange, request: Request):
    account = _require_account(request)
    try:
        change_password(int(account["id"]), payload.current_password, payload.new_password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.get("/api/plans")
def api_plans():
    return {"plans": public_plans()}


@app.post("/api/client/subscription-request")
def api_subscription_request(payload: SubscriptionRequestBody, request: Request):
    account = _require_account(request)
    if account.get("role") == "admin":
        raise HTTPException(400, "Admin accounts do not need subscriptions.")
    try:
        req = request_subscription(int(account["id"]), payload.plan_code)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "request": req}


@app.get("/api/admin/clients")
def api_admin_clients(request: Request):
    _require_admin(request)
    return {"clients": [public_account(x) for x in list_clients()]}


@app.post("/api/admin/clients")
def api_admin_create_client(payload: ClientCreate, request: Request):
    admin = _require_admin(request)
    try:
        account, temporary_password = create_client(
            payload.username,
            payload.display_name,
            payload.plan_code,
            created_by=int(admin["id"]),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {
        "ok": True,
        "account": public_account(account),
        "temporary_password": temporary_password,
    }


@app.post("/api/admin/clients/{account_id}/subscription")
def api_admin_grant_subscription(
    account_id: int,
    payload: SubscriptionGrant,
    request: Request,
):
    admin = _require_admin(request)
    try:
        grant_subscription(
            account_id,
            payload.plan_code,
            custom_days=payload.custom_days,
            actor_account_id=int(admin["id"]),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.post("/api/admin/clients/{account_id}/subscription/revoke")
def api_admin_revoke_subscription(account_id: int, request: Request):
    admin = _require_admin(request)
    revoke_subscription(account_id, actor_account_id=int(admin["id"]))
    return {"ok": True}


@app.get("/api/admin/subscription-requests")
def api_admin_subscription_requests(request: Request):
    _require_admin(request)
    return {"requests": list_subscription_requests()}


@app.post("/api/admin/subscription-requests/{request_id}/review")
def api_admin_review_subscription(
    request_id: int,
    payload: RequestReview,
    request: Request,
):
    admin = _require_admin(request)
    try:
        review_subscription_request(request_id, payload.approve, int(admin["id"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.get("/api/admin/strategies")
def api_admin_strategies(request: Request):
    _require_admin(request)
    return {"strategies": _admin_strategy_catalog()}


@app.get("/api/status")
def status():
    return {
        "app": "BetPawa Predictor",
        "version": "0.4.0",
        "rules_public": False,
        "mode": "client subscriptions + private admin strategy console",
    }


@app.post("/api/predict")
def predict(request: Request, response: Response):
    account = _require_active_access(request)
    user_id = account["user_key"]
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
        public_result["trackers"] = []
        public_result["personal"] = _public_history(get_user_history(user_id))
        return public_result
    except Exception as e:
        print("Prediction service error:", repr(e))
        raise HTTPException(502, "Prediction service temporarily unavailable.")


@app.post("/api/predict/{category}")
def predict_category(category: str, request: Request, response: Response):
    if category not in MARKET_CATEGORIES:
        raise HTTPException(404, "Unknown market page.")

    account = _require_active_access(request)
    user_id = account["user_key"]
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
        public_result["trackers"] = []
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
    account = _require_active_access(request)
    user_id = account["user_key"]
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
    account = _require_active_access(request)
    user_id = account["user_key"]
    return _public_history(get_user_history(user_id))


@app.post("/api/history/refresh")
def refresh_history(request: Request, response: Response):
    account = _require_active_access(request)
    user_id = account["user_key"]
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
    account = _require_active_access(request)
    user_id = account["user_key"]
    return _filter_public_history(
        _public_history(get_user_history(user_id)),
        category,
    )


@app.post("/api/history/{category}/refresh")
def refresh_history_category(category: str, request: Request, response: Response):
    if category not in MARKET_CATEGORIES:
        raise HTTPException(404, "Unknown market page.")

    account = _require_active_access(request)
    user_id = account["user_key"]
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
    account = _require_active_access(request)
    user_id = account["user_key"]
    return _public_history(get_user_history(user_id))


@app.get("/api/diagnose")
def diagnose(request: Request):
    _require_admin(request)
    return feed.diagnose()
