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
    version="0.4.1",
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


def _public_support(support: dict) -> dict:
    allowed = {
        "historical_win_rate", "wins", "tests", "baseline", "edge_pp",
        "positive_seasons", "source_matchday", "target_matchday",
        "selected_teams", "target_fixture", "live_alignment", "recent_wins",
        "recent_tests", "time_status", "time_alignment", "time_alignment_window",
        "time_alignment_note", "time_historical_wins", "time_historical_tests",
        "time_historical_rate", "time_historical_windows",
    }
    return {k: support[k] for k in allowed if k in support}


def _public_prediction(item: dict) -> dict:
    supports = [_public_support(s) for s in (item.get("supports") or [])]
    out = dict(item)
    out["supports"] = supports
    for key in (
        "strategy_families", "strategy_family_label", "strategy_family",
        "rule_id", "strategy_id", "strategy_name", "trigger_explanation",
    ):
        out.pop(key, None)
    out["time_supports"] = [
        {
            "time_status": s.get("time_status"),
            "time_alignment": s.get("time_alignment"),
            "time_alignment_window": s.get("time_alignment_window"),
            "time_alignment_note": s.get("time_alignment_note"),
            "time_historical_wins": s.get("time_historical_wins"),
            "time_historical_tests": s.get("time_historical_tests"),
            "time_historical_rate": s.get("time_historical_rate"),
            "time_historical_windows": s.get("time_historical_windows") or [],
        }
        for s in supports
    ]
    return out


def _public_result(result: dict) -> dict:
    out = dict(result)
    out["predictions"] = [_public_prediction(p) for p in (result.get("predictions") or [])]
    out["trackers"] = []
    out.pop("by_rule_internal", None)
    out.pop("by_rule_time_internal", None)
    out.pop("by_family_market", None)
    return out


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
    value = str(expected or "").upper()
    if "OVER" in value:
        return "overs"
    if "UNDER" in value:
        return "unders"
    if "BTTS" in value:
        return "btts"
    if "HOME WIN" in value or "AWAY WIN" in value or value in {"HOME", "AWAY"}:
        return "wins"
    return None


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
    if category not in {"overs", "unders", "btts", "wins"}:
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
        "version": "0.4.1",
        "rules_public": False,
        "mode": "client subscriptions + private admin strategy console",
    }


@app.post("/api/predict/{category}")
def predict_category(category: str, request: Request, response: Response):
    if category not in {"overs", "unders", "btts", "wins"}:
        raise HTTPException(404, "Unknown market page.")
    account = _require_active_access(request)
    user_id = account["user_key"]
    started = time.perf_counter()
    try:
        context = feed.prediction_context()
        graded_now = grade_user_predictions(user_id, context["completed_rounds_for_grading"])
        result = build_prediction(context)
        category_result = {
            **result,
            "predictions": [
                p for p in result.get("predictions", [])
                if _market_category(p.get("expected")) == category
            ],
            "trackers": [],
        }
        public_result = _public_result(category_result)
        save_user_prediction_batch(user_id, public_result)
        history = get_user_history(user_id)
        public_result["personal"] = history
        public_result["performance"] = {
            "seconds": round(time.perf_counter() - started, 3),
            "round_cache_hits": context.get("round_cache_hits", 0),
            "round_cache_misses": context.get("round_cache_misses", 0),
            "context_cache_hit": context.get("context_cache_hit", False),
            "graded_previous_now": graded_now,
        }
        return public_result
    except HTTPException:
        raise
    except Exception as e:
        print("Prediction service error:", repr(e))
        raise HTTPException(502, "Prediction service temporarily unavailable.")


@app.post("/api/selection")
def update_selection(payload: SelectionUpdate, request: Request, response: Response):
    account = _require_active_access(request)
    user_id = account["user_key"]
    set_prediction_selected(
        user_id,
        payload.season,
        payload.matchday,
        payload.league,
        payload.target_home,
        payload.target_away,
        payload.expected,
        payload.selected,
    )
    return {"ok": True}


@app.get("/api/history/{category}")
def history_category(category: str, request: Request, response: Response):
    if category not in {"overs", "unders", "btts", "wins"}:
        raise HTTPException(404, "Unknown market page.")
    account = _require_active_access(request)
    user_id = account["user_key"]
    return get_user_history(user_id, category=category)


@app.post("/api/history/{category}/refresh")
def refresh_history(category: str, request: Request, response: Response):
    if category not in {"overs", "unders", "btts", "wins"}:
        raise HTTPException(404, "Unknown market page.")
    account = _require_active_access(request)
    user_id = account["user_key"]
    started = time.perf_counter()
    try:
        context = feed.prediction_context()
        graded = grade_user_predictions(user_id, context["completed_rounds_for_grading"])
        history = get_user_history(user_id, category=category)
        history["refresh"] = {
            "graded_now": graded,
            "seconds": round(time.perf_counter() - started, 3),
        }
        return history
    except HTTPException:
        raise
    except Exception as e:
        print("Prediction service error:", repr(e))
        raise HTTPException(502, "Prediction service temporarily unavailable.")


@app.get("/api/predictions")
def predictions(request: Request, response: Response):
    account = _require_active_access(request)
    user_id = account["user_key"]
    return get_user_history(user_id)


@app.get("/api/diagnose")
def diagnose(request: Request):
    _require_admin(request)
    return feed.diagnose()
