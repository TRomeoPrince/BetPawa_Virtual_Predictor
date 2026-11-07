from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from . import picks, access_links
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
    delete_client,
    create_session,
    delete_session,
    ensure_bootstrap_admin,
    grant_subscription,
    get_account,
    list_account_subscription_requests,
    list_clients,
    list_subscription_requests,
    public_account,
    public_plans,
    request_subscription,
    review_subscription_request,
    revoke_subscription,
    reset_client_password,
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
PICKS_PAGE = ROOT / "frontend" / "picks.html"
ADMIN_PAGE = ROOT / "frontend" / "admin.html"
PASSWORD_SETUP_PAGE = ROOT / "frontend" / "password-setup.html"
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
    if os.environ.get("PREDICTOR_ADMIN_PASSWORD"):
        print("Initial admin account created from PREDICTOR_ADMIN_PASSWORD.")
    else:
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


def _require_account(request: Request, allow_password_setup: bool = False):
    account = _session_account(request)
    if not account:
        raise HTTPException(401, "Please sign in.")
    if account.get("must_change_password") and not allow_password_setup:
        raise HTTPException(403, "Password setup required. Open /password-setup.")
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
        "positive_seasons", "time_status", "time_alignment", "time_alignment_window",
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
        "selected_team", "selected_teams", "target_position", "source_fixtures",
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


def _public_history(history: dict) -> dict:
    """Never expose internal strategy IDs or source triggers in client history."""
    out = dict(history)
    for key in ("by_rule_internal", "by_rule_time_internal", "by_family_market"):
        out.pop(key, None)

    def clean_batch(batch):
        if not isinstance(batch, dict):
            return batch
        return {
            **batch,
            "predictions": [
                _public_prediction(p) for p in (batch.get("predictions") or [])
            ],
        }

    for key in (
        "last_batch", "last_completed_batch", "last_selected_batch",
        "last_completed_selected_batch",
    ):
        out[key] = clean_batch(out.get(key))
    out["recent_batches"] = [
        clean_batch(b) for b in (out.get("recent_batches") or [])
    ]
    out["selected_results"] = [
        _public_prediction(p) for p in (out.get("selected_results") or [])
    ]
    return out


def _public_result(result: dict) -> dict:
    out = dict(result)
    out["predictions"] = [_public_prediction(p) for p in (result.get("predictions") or [])]
    out["trackers"] = []
    for key in (
        "by_rule_internal", "by_rule_time_internal", "by_family_market",
        "leagues", "multi_market_strategy_count", "pattern2_strategy_count",
    ):
        out.pop(key, None)
    if isinstance(out.get("personal"), dict):
        out["personal"] = _public_history(out["personal"])
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
    age_confirmed: bool = False


class LinkToken(BaseModel):
    token: str


class LinkActivation(BaseModel):
    token: str
    new_password: str
    age_confirmed: bool = False


class LinkIssue(BaseModel):
    kind: str


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


class BetJournalBody(BaseModel):
    bet_date: str
    league: str = ""
    fixture: str
    category: str
    selection: str
    stake_ugx: int
    decimal_odds: float
    outcome: str = "PENDING"
    notes: str = ""


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
def home():
    """Public marketing page; private dashboards remain behind authentication."""
    return _frontend_response(FRONTEND)


@app.get("/activate")
def activation_page():
    return _frontend_response(ROOT / "frontend" / "activate.html")


@app.get("/access")
def link_login_page():
    return _frontend_response(ROOT / "frontend" / "access-link.html")


@app.get("/login")
def login_page(request: Request):
    account = _session_account(request)
    if account:
        destination = ("/password-setup" if account.get("must_change_password")
                       else "/admin" if account.get("role") == "admin" else "/client")
        return RedirectResponse(destination, status_code=302)
    return _frontend_response(LOGIN_PAGE)


@app.get("/password-setup")
def password_setup_page(request: Request):
    account = _session_account(request)
    if not account:
        return RedirectResponse("/login", status_code=302)
    if not account.get("must_change_password"):
        return RedirectResponse(
            "/admin" if account.get("role") == "admin" else "/client",
            status_code=302,
        )
    return _frontend_response(PASSWORD_SETUP_PAGE)


@app.get("/client")
def client_dashboard(request: Request):
    account = _session_account(request)
    if not account:
        return RedirectResponse("/login", status_code=302)
    if account.get("must_change_password"):
        return RedirectResponse("/password-setup", status_code=302)
    return _frontend_response(CLIENT_PAGE)


@app.get("/admin")
def admin_dashboard(request: Request):
    account = _session_account(request)
    if not account:
        return RedirectResponse("/login", status_code=302)
    if account.get("must_change_password"):
        return RedirectResponse("/password-setup", status_code=302)
    if account.get("role") != "admin":
        return RedirectResponse("/client", status_code=302)
    return _frontend_response(ADMIN_PAGE)


@app.get("/client/picks")
def client_picks_page(request: Request):
    account = _session_account(request)
    if not account:
        return RedirectResponse("/login", status_code=302)
    if account.get("must_change_password"):
        return RedirectResponse("/password-setup", status_code=302)
    return _frontend_response(PICKS_PAGE)


@app.get("/client/{category}")
def client_market_page(category: str, request: Request):
    if category not in {"overs", "unders", "btts", "wins"}:
        raise HTTPException(404, "Unknown market page.")
    account = _session_account(request)
    if not account:
        return RedirectResponse("/login", status_code=302)
    if account.get("must_change_password"):
        return RedirectResponse("/password-setup", status_code=302)
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


def _link_session(request: Request, response: Response, account):
    delete_session(request.cookies.get(SESSION_COOKIE))
    response.set_cookie(
        SESSION_COOKIE,create_session(int(account["id"])),max_age=60*60*24*30,
        httponly=True,samesite="lax",secure=request.url.scheme=="https",
    )
    response.headers["Cache-Control"]="no-store"
    return {"ok":True,"account":public_account(account)}


@app.post("/api/auth/link-login")
def api_link_login(payload: LinkToken, request: Request, response: Response):
    account=access_links.redeem_login(payload.token)
    if not account:
        raise HTTPException(401,"Link invalid, revoked, expired or subscription inactive.")
    return _link_session(request,response,account)


@app.post("/api/auth/link-activate")
def api_link_activate(payload: LinkActivation,request: Request,response: Response):
    try:
        account=access_links.activate(payload.token,payload.new_password,payload.age_confirmed)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    return _link_session(request,response,account)


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
    account = _require_account(request, allow_password_setup=True)
    return {"account": public_account(account)}


@app.post("/api/auth/change-password")
def api_change_password(payload: PasswordChange, request: Request):
    account = _require_account(request, allow_password_setup=True)
    if (account.get("must_change_password") and account.get("role") == "client"
            and not payload.age_confirmed):
        raise HTTPException(400, "You must confirm you are at least 25 years old.")
    try:
        change_password(int(account["id"]), payload.current_password, payload.new_password)
        if account.get("role")=="client":
            access_links.invalidate(int(account["id"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "requires_login": True}


@app.get("/api/plans")
def api_plans():
    return {"plans": public_plans()}


@app.get("/api/client/subscription-requests")
def api_client_subscription_requests(request: Request):
    account = _require_account(request)
    return {
        "requests": list_account_subscription_requests(int(account["id"]))
        if account.get("role") != "admin" else []
    }


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


@app.get("/api/client/picks")
def api_client_picks(
    request: Request, category: str = "all", scope: str = "latest",
    outcome: str = "all", limit: int = 50, offset: int = 0,
):
    account = _require_account(request)
    try:
        return picks.get_picks(
            account["user_key"], category=category, scope=scope,
            outcome=outcome, limit=limit, offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/client/picks/refresh")
def api_client_picks_refresh(request: Request):
    account = _require_active_access(request)
    try:
        context = feed.prediction_context()
        graded = grade_user_predictions(account["user_key"], context["completed_rounds_for_grading"])
        return {"graded_now": graded}
    except Exception as exc:
        print("Picks refresh error:", repr(exc))
        raise HTTPException(502, "Results refresh temporarily unavailable.")


@app.get("/api/client/bet-journal")
def api_client_bet_journal(
    request: Request, category: str = "all", outcome: str = "all",
    limit: int = 50, offset: int = 0,
):
    account = _require_account(request)
    try:
        return picks.get_journal(
            account["user_key"], category=category, outcome=outcome,
            limit=limit, offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/client/bet-journal")
def api_client_create_bet(payload: BetJournalBody, request: Request):
    account = _require_account(request)
    try:
        return {"bet": picks.create_bet(account["user_key"], payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.put("/api/client/bet-journal/{bet_id}")
def api_client_update_bet(bet_id: int, payload: BetJournalBody, request: Request):
    account = _require_account(request)
    try:
        return {"bet": picks.update_bet(account["user_key"], bet_id, payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/client/bet-journal/{bet_id}")
def api_client_delete_bet(bet_id: int, request: Request):
    account = _require_account(request)
    if not picks.delete_bet(account["user_key"], bet_id):
        raise HTTPException(404, "Bet record not found.")
    return {"ok": True}


@app.get("/api/admin/clients")
def api_admin_clients(request: Request):
    _require_admin(request)
    return {"clients": [public_account(x) for x in list_clients()]}


@app.post("/api/admin/clients")
def api_admin_create_client(payload: ClientCreate, request: Request, response: Response):
    admin = _require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        account, temporary_password = create_client(
            payload.username,
            payload.display_name,
            payload.plan_code,
            created_by=int(admin["id"]),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    invitation=access_links.issue(int(account["id"]),"activation",int(admin["id"]))
    return {
        "ok": True, "account": public_account(account),
        "temporary_password": temporary_password,
        "activation_token": invitation["token"],"activation_expires_at":invitation["expires_at"],
    }


@app.post("/api/admin/clients/{account_id}/reset-password")
def api_admin_reset_client_password(account_id: int, request: Request, response: Response):
    admin = _require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        temp_password = reset_client_password(account_id, int(admin["id"]))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    access_links.invalidate(account_id)
    invitation=access_links.issue(account_id,"activation",int(admin["id"]))
    return {
        "ok": True, "account": public_account(get_account(account_id)),
        "temporary_password": temp_password,
        "activation_token": invitation["token"],"activation_expires_at":invitation["expires_at"],
    }


@app.delete("/api/admin/clients/{account_id}")
def api_admin_delete_client(account_id: int, request: Request, response: Response):
    admin = _require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        delete_client(account_id, int(admin["id"]))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}


@app.post("/api/admin/clients/{account_id}/links")
def admin_issue_link(account_id:int,payload:LinkIssue,request:Request,response:Response):
    admin=_require_admin(request)
    response.headers["Cache-Control"]="no-store"
    try:
        return {"ok":True,"kind":payload.kind,**access_links.issue(account_id,payload.kind,int(admin["id"]))}
    except ValueError as exc:
        raise HTTPException(400,str(exc))


@app.post("/api/admin/clients/{account_id}/links/revoke")
def admin_revoke_link(account_id:int,payload:LinkIssue,request:Request):
    admin=_require_admin(request)
    try:
        access_links.revoke(account_id,payload.kind,int(admin["id"]))
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    return {"ok":True}


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
            "next_target": context.get("next_target") or {},
            "predictions": [
                p for p in result.get("predictions", [])
                if _market_category(p.get("expected")) == category
            ],
            "trackers": [],
        }
        # Persist the full private support metadata server-side, then sanitize
        # every prediction and history object before returning it to clients.
        save_user_prediction_batch(user_id, category_result)
        history = get_user_history(user_id, category=category)
        public_result = _public_result(category_result)
        public_result["personal"] = _public_history(history)
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
    updated = set_prediction_selected(
        user_id,
        payload.season,
        payload.matchday,
        payload.league,
        payload.target_home,
        payload.target_away,
        payload.expected,
        payload.selected,
    )
    if not updated:
        raise HTTPException(
            409, "This pick cannot be changed. Only pending selections "
                 "in your latest checked matchday are editable."
        )
    return {"ok": True}


@app.get("/api/history/{category}")
def history_category(category: str, request: Request, response: Response):
    if category not in {"overs", "unders", "btts", "wins"}:
        raise HTTPException(404, "Unknown market page.")
    account = _require_active_access(request)
    user_id = account["user_key"]
    return _public_history(get_user_history(user_id, category=category))


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
        history = _public_history(get_user_history(user_id, category=category))
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
    return _public_history(get_user_history(user_id))


@app.get("/api/diagnose")
def diagnose(request: Request):
    _require_admin(request)
    return feed.diagnose()
