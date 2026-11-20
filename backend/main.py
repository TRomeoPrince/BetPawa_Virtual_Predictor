from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse, Response as FileResponseBytes
from pydantic import BaseModel

from . import picks, access_links, purchase_requests, growth, free_access, referral_wallet, admin_analytics, pattern_partners, contributor_rewards, premium_picks, win_proofs, recommendation_quality, current_seasons
from .providers.betpawa import BetPawaFeed
from .predictor import build_prediction
from .time_windows import time_priority, TIME_WINDOW_HISTORY, EAT, estimate_target_datetime_eat
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
    set_subscription_expiry,
    create_session,
    delete_session,
    ensure_bootstrap_admin,
    recover_admin_password_from_env,
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
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
feed = BetPawaFeed()

_bootstrap_password = ensure_bootstrap_admin()
recover_admin_password_from_env()
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


def _is_vip(account):
    return account.get("role") == "admin" or bool(account.get("subscription", {}).get("is_active"))


def _free_round_allowed(context, now=None):
    """Only administrator-enabled, scheduled rounds may be publicly previewed."""
    return free_access.allowed_round(context, now)


def _free_market_result(public_result):
    """Only EPL and Dutch picks, never VIP history, other fixtures or rule metadata."""
    allowed = {"ENGLISH", "EPL", "DUTCH", "NETHERLANDS"}
    fixtures = public_result.get("next_target") or {}
    return {
        "ok": True, "free": True,
        "season": public_result.get("season"),
        "next_matchday": public_result.get("next_matchday"),
        "latest_completed_matchday": public_result.get("latest_completed_matchday"),
        "next_round_id": public_result.get("next_round_id"),
        "next_round_open_utc": public_result.get("next_round_open_utc"),
        "next_round_close_utc": public_result.get("next_round_close_utc"),
        "next_target": {k: v for k, v in fixtures.items() if k.upper() in allowed},
        "predictions": [p for p in public_result.get("predictions", [])
                        if str(p.get("league", "")).upper() in allowed],
        "trackers": [], "personal": {},
        "free_release": True,
    }


def _verify_write_origin(request: Request):
    """Reject browser cross-origin mutation attempts using session cookies."""
    from urllib.parse import urlparse
    origin = request.headers.get("origin")
    if origin:
        parsed=urlparse(origin)
        if parsed.netloc.lower()!=request.url.netloc.lower() or parsed.scheme not in ("http","https"):
            raise HTTPException(403,"Cross-origin change rejected.")


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
        "research_status",
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



class WinProofSubmission(BaseModel):
    image_base64: str
    consent: bool = False


class WinProofReview(BaseModel):
    decision: str


class CuratedWinProofImport(BaseModel):
    archive_base64: str
    redaction_confirmed: bool = False


class SelectionUpdate(BaseModel):
    season: str
    matchday: str
    league: str
    target_home: str
    target_away: str
    expected: str
    selected: bool


class SignupRequest(BaseModel):
    username: str
    display_name: str = ""
    email: str
    password: str
    age_confirmed: bool = False
    referral_code: str = ""


class PatternPartnerSubmission(BaseModel):
    name: str
    email: str
    username: str = ""
    league: str
    market: str
    details: str
    evidence_url: str = ""
    age_confirmed: bool = False
    website: str = ""


class PatternPartnerReview(BaseModel):
    decision: str
    verified_and_adopted: bool = False
    note: str


class PatternPartnerReward(BaseModel):
    username: str
    contributor_verified: bool = False
    strategy_family: str
    rule_id: str


class WalletVipPurchase(BaseModel):
    plan_code: str
    promo_code: str = ""
    idempotency_key: str
    expected_price_ugx: int


class ReferralWithdrawalBody(BaseModel):
    amount_ugx: int
    destination_method: str
    destination_details: str


class ReferralWithdrawalReview(BaseModel):
    paid: bool = False
    verified: bool = False
    payout_reference: str = ""
    reason: str = ""


class ReferralCommissionReversal(BaseModel):
    confirmed_refund: bool = False
    reason: str


class PromotionBody(BaseModel):
    plan_code: str
    price_ugx: int
    code: str = ""
    starts_at: str | None = None
    ends_at: str | None = None
    enabled: bool = True


class PromotionToggle(BaseModel):
    enabled: bool


class PremiumPickAdminBody(BaseModel):
    date_eat: str
    season: str
    matchday: int
    fixture: str
    selection: str
    alarm_eat: str
    window_open_eat: str
    window_close_eat: str
    enabled: bool = True


class PremiumPickToggleBody(BaseModel):
    enabled: bool


class FreeReleaseBody(BaseModel):
    starts_at: str | None = None
    ends_at: str | None = None
    markets: list[str] | None = None
    enabled: bool = True


class FreeReleaseEditBody(BaseModel):
    starts_at: str | None = None
    ends_at: str | None = None
    markets: list[str] | None = None
    enabled: bool | None = None


class FreeReleaseToggle(BaseModel):
    enabled: bool


class LoginRequest(BaseModel):
    username: str
    password: str
    age_confirmed: bool = False


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


class PurchaseRequestBody(BaseModel):
    email: str
    username: str
    display_name: str = ""
    plan_code: str
    payment_method: str
    transaction_ref: str = ""
    proof_base64: str = ""
    age_confirmed: bool = False
    promo_code: str = ""


class PurchaseDecision(BaseModel):
    approve: bool
    verified: bool = False
    reason: str = ""
    public_base_url: str | None = None


class PurchaseResend(BaseModel):
    public_base_url: str | None = None


class ClientCreate(BaseModel):
    username: str
    display_name: str = ""
    plan_code: str | None = None
    chosen_password: str | None = None
    expires_at: str | None = None


class SubscriptionGrant(BaseModel):
    plan_code: str
    custom_days: int | None = None


class SubscriptionExpiry(BaseModel):
    expires_at: str


class SubscriptionRequestBody(BaseModel):
    plan_code: str


class RequestReview(BaseModel):
    approve: bool
    verified: bool = False


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


@app.get("/bpv-themes.css")
def bpv_theme_styles():
    return FileResponse(
        ROOT / "frontend" / "bpv-themes.css",
        media_type="text/css; charset=utf-8",
        headers={"Cache-Control": "no-cache, max-age=0, must-revalidate", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/bpv-round-times.js")
def bpv_round_times_script():
    """Format source-scheduled round windows; never expose private selections."""
    return FileResponse(
        ROOT / "frontend" / "bpv-round-times.js",
        media_type="text/javascript; charset=utf-8",
        headers={"Cache-Control": "no-cache, max-age=0, must-revalidate", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/bpv-stadium-dashboard.js")
def bpv_stadium_dashboard_script():
    """Read-only presentation code; all account data stays behind existing APIs."""
    return FileResponse(
        ROOT / "frontend" / "bpv-stadium-dashboard.js",
        media_type="text/javascript; charset=utf-8",
        headers={"Cache-Control": "no-cache, max-age=0, must-revalidate", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/bpv-themes.js")
def bpv_theme_script():
    return FileResponse(
        ROOT / "frontend" / "bpv-themes.js",
        media_type="text/javascript; charset=utf-8",
        headers={"Cache-Control": "no-cache, max-age=0, must-revalidate", "X-Content-Type-Options": "nosniff"},
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


@app.get("/partners")
def pattern_partners_page():
    return _frontend_response(ROOT / "frontend" / "partners.html")


@app.post("/api/pattern-partners")
def api_pattern_partner_submit(payload: PatternPartnerSubmission, request: Request, response: Response):
    _verify_write_origin(request)
    response.headers["Cache-Control"] = "no-store"
    # Honeypot for unsophisticated automated form submission.
    if payload.website:
        return {"ok":True,"status":"received"}
    try:
        ref=pattern_partners.submit(
            payload.name,payload.email,payload.username,payload.league,payload.market,
            payload.details,payload.evidence_url,payload.age_confirmed
        )
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    return {"ok":True,"status":"submitted","reference":ref}


@app.get("/api/admin/pattern-partners")
def api_admin_pattern_partner_submissions(request: Request, response: Response):
    _require_admin(request)
    response.headers["Cache-Control"] = "no-store, private"
    return {"submissions":pattern_partners.list_submissions()}


@app.post("/api/admin/pattern-partners/{submission_id}/review")
def api_admin_pattern_partner_review(submission_id:int, payload:PatternPartnerReview,
                                     request:Request,response:Response):
    admin=_require_admin(request)
    _verify_write_origin(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        status=pattern_partners.review(
            submission_id,payload.decision,int(admin["id"]),
            payload.verified_and_adopted,payload.note
        )
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    return {"ok":True,"status":status}


@app.post("/api/admin/pattern-partners/{submission_id}/reward")
def api_admin_pattern_partner_reward(submission_id:int,payload:PatternPartnerReward,
                                     request:Request,response:Response):
    admin=_require_admin(request)
    _verify_write_origin(request)
    response.headers["Cache-Control"] = "no-store"
    try:
        return pattern_partners.activate_contributor(
            submission_id,int(admin["id"]),payload.username,payload.contributor_verified,
            payload.strategy_family,payload.rule_id,
            {(row["strategy_family"],row["rule_id"]) for row in _admin_strategy_catalog()},
        )
    except ValueError as exc:
        raise HTTPException(400,str(exc))


@app.get("/purchase")
def purchase_page():
    return _frontend_response(ROOT / "frontend" / "purchase.html")


@app.get("/signup")
def signup_page(request: Request):
    if _session_account(request):
        return RedirectResponse("/client", status_code=302)
    return _frontend_response(ROOT / "frontend" / "signup.html")


@app.get("/r/{code}")
def referral_redirect(code: str):
    if not growth.track_visit(code):
        raise HTTPException(404, "Referral link not found.")
    return RedirectResponse("/signup?ref=" + code.strip().upper(), status_code=302)


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
    # The market page itself is presentation-only. Let every signed-in member
    # inspect a market and see a clear Free/VIP access message instead of
    # silently bouncing back to /client. Prediction APIs still enforce email,
    # active Free releases, market permissions and VIP checks independently.
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


@app.post("/api/auth/signup")
def api_signup(payload: SignupRequest, request: Request, response: Response):
    if os.getenv("PREDICTOR_SIGNUP_ENABLED", "false" if os.getenv("RAILWAY_PROJECT_ID") else "true").lower() not in ("1", "true", "yes", "on"):
        raise HTTPException(503, "Registration is temporarily closed.")
    try:
        account = growth.signup(payload.username, payload.display_name, payload.email,
                                payload.password, payload.age_confirmed, payload.referral_code)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    token = create_session(int(account["id"]))
    response.set_cookie(SESSION_COOKIE, token, max_age=60*60*24*30,
                        httponly=True, samesite="lax", secure=request.url.scheme == "https")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True, "account": public_account(account), "membership": "free"}


@app.get("/api/account/contact")
def api_account_contact(request: Request):
    account = _require_account(request)
    return {"username": account["username"], "display_name": account["display_name"],
            "email": account.get("email")}


@app.get("/api/referrals/me")
def api_my_referrals(request: Request):
    account = _require_account(request)
    if account["role"] == "admin":
        raise HTTPException(403, "Referrals are for members.")
    origin = (os.getenv("PREDICTOR_PUBLIC_BASE_URL") or str(request.base_url)).rstrip("/")
    return growth.referral_stats(int(account["id"]), origin)


@app.get("/api/referrals/people")
def api_referral_people(request: Request, response: Response, limit: int = 25, offset: int = 0):
    """Only show the current member's attributed signups and earned commissions."""
    account = _require_account(request)
    response.headers["Cache-Control"] = "private, no-store"
    if account["role"] != "client":
        raise HTTPException(403, "Referrals are for registered members only.")
    return referral_wallet.referral_dashboard(int(account["id"]), limit=limit, offset=offset)


@app.get("/api/referrals/wallet")
def api_referral_wallet(request: Request, response: Response):
    account = _require_account(request)
    response.headers["Cache-Control"] = "no-store"
    if account["role"] != "client":
        raise HTTPException(403, "Wallets are available to registered members only.")
    try:
        return referral_wallet.wallet(int(account["id"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/referrals/wallet/purchase-vip")
def api_wallet_vip_purchase(payload: WalletVipPurchase, request: Request, response: Response):
    account=_require_account(request)
    _verify_write_origin(request)
    response.headers["Cache-Control"]="no-store"
    if account["role"]!="client" or account["status"]!="active":
        raise HTTPException(403,"Member account required.")
    try:
        return referral_wallet.purchase_vip_with_wallet(
            int(account["id"]),payload.plan_code,payload.promo_code,payload.idempotency_key,payload.expected_price_ugx
        )
    except ValueError as exc:
        raise HTTPException(400,str(exc))


@app.post("/api/referrals/withdrawals")
def api_referral_withdrawal(payload: ReferralWithdrawalBody, request: Request, response: Response):
    account = _require_account(request)
    response.headers["Cache-Control"] = "no-store"
    if account["role"] != "client":
        raise HTTPException(403, "Member account required.")
    _verify_write_origin(request)
    try:
        withdrawal_id = referral_wallet.request_withdrawal(
            int(account["id"]),payload.amount_ugx,payload.destination_method,payload.destination_details
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok":True,"id":withdrawal_id,"status":"pending"}


@app.get("/api/admin/referral-wallets")
def api_admin_referral_wallets(request: Request, response: Response):
    _require_admin(request)
    response.headers["Cache-Control"]="no-store"
    return {"wallets":referral_wallet.admin_wallets()}


@app.get("/api/admin/referral-withdrawals")
def api_admin_referral_withdrawals(request: Request, response: Response):
    _require_admin(request)
    response.headers["Cache-Control"]="no-store"
    return {"withdrawals":referral_wallet.admin_withdrawals()}


@app.post("/api/admin/referral-withdrawals/{withdrawal_id}/review")
def api_admin_referral_withdrawal_review(
    withdrawal_id:int,payload:ReferralWithdrawalReview,request:Request,response:Response
):
    admin=_require_admin(request)
    _verify_write_origin(request)
    response.headers["Cache-Control"]="no-store"
    try:
        referral_wallet.review_withdrawal(
            withdrawal_id,int(admin["id"]),payload.paid,payload.payout_reference,
            payload.reason,payload.verified
        )
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    return {"ok":True,"status":"paid" if payload.paid else "rejected"}


@app.get("/api/admin/contributor-rewards/status")
def api_admin_contributor_reward_status(request:Request,response:Response):
    _require_admin(request)
    response.headers["Cache-Control"]="no-store, private"
    return contributor_rewards.admin_status()


@app.post("/api/admin/contributor-rewards/settle")
def api_admin_contributor_reward_settle(request:Request,response:Response):
    _require_admin(request)
    _verify_write_origin(request)
    response.headers["Cache-Control"]="no-store"
    try:
        return contributor_rewards.settle_due(limit=100)
    except ValueError as exc:
        raise HTTPException(400,str(exc))


@app.post("/api/admin/contributor-rewards/{purchase_id}/reverse")
def api_admin_contributor_reward_reverse(
    purchase_id:int,payload:ReferralCommissionReversal,request:Request,response:Response
):
    admin=_require_admin(request)
    _verify_write_origin(request)
    response.headers["Cache-Control"]="no-store"
    if not payload.confirmed_refund or not 5<=len(payload.reason.strip())<=500:
        raise HTTPException(400,"Verify the refund and enter a reason (5–500 characters).")
    con=referral_wallet.connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        # A refund must reverse every payout liability, even if there was no referrer.
        original=con.execute("""
            SELECT * FROM referral_wallet_ledger
            WHERE event_key=? AND entry_type='commission'
        """,(f"commission:{purchase_id}",)).fetchone()
        if original:
            reversal=con.execute("SELECT 1 FROM referral_wallet_ledger WHERE event_key=?",
                                 (f"reversal:{purchase_id}",)).fetchone()
            if not reversal:
                con.execute("""
                    INSERT INTO referral_wallet_ledger(
                      event_key,referrer_account_id,referred_account_id,purchase_request_id,
                      entry_type,amount_ugx,purchase_amount_ugx,commission_rate_bps,created_at,note
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,(f"reversal:{purchase_id}",original["referrer_account_id"],
                     original["referred_account_id"],purchase_id,"reversal",
                     -int(original["amount_ugx"]),original["purchase_amount_ugx"],
                     original["commission_rate_bps"],contributor_rewards._now(),payload.reason.strip()))
        count=contributor_rewards.reverse_purchase(con,purchase_id,int(admin["id"]),payload.reason.strip())
        con.commit()
        return {"ok":True,"status":"reversed","contributor_entries_reversed":count}
    except ValueError as exc:
        con.rollback()
        raise HTTPException(400,str(exc))
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


@app.post("/api/admin/referral-commissions/{purchase_id}/reverse")
def api_admin_reverse_commission(
    purchase_id:int,payload:ReferralCommissionReversal,request:Request,response:Response
):
    admin=_require_admin(request)
    _verify_write_origin(request)
    response.headers["Cache-Control"]="no-store"
    try:
        referral_wallet.reverse_commission(
            purchase_id,int(admin["id"]),payload.reason,payload.confirmed_refund
        )
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    return {"ok":True,"status":"reversed"}


@app.post("/api/auth/login")
def api_login(payload: LoginRequest, request: Request, response: Response):
    account = authenticate(payload.username, payload.password)
    if not account:
        raise HTTPException(401, "Invalid username or password.")
    if account.get("username") == "PUBLIC TRIAL" and not payload.age_confirmed:
        raise HTTPException(403, "Confirm you are at least 25 years old to enter the public trial.")
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


@app.post("/api/activity/ping")
def api_activity_ping(request: Request, response: Response):
    """A visible logged-in tab can refresh its last-seen timestamp each minute."""
    account=_require_account(request,allow_password_setup=True)
    _verify_write_origin(request)
    response.headers["Cache-Control"]="no-store"
    return {"ok":True,"member":account.get("role")=="client"}


@app.get("/api/auth/me")
def api_me(request: Request):
    account = _require_account(request, allow_password_setup=True)
    return {"account": public_account(account)}


@app.post("/api/auth/change-password")
def api_change_password(payload: PasswordChange, request: Request):
    account = _require_account(request, allow_password_setup=True)
    if account.get("username") == "PUBLIC TRIAL":
        raise HTTPException(403, "Public trial password is managed by the administrator.")
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


@app.get("/api/purchase/quote")
def api_purchase_quote(plan_code: str, response: Response, promo_code: str = ""):
    response.headers["Cache-Control"] = "no-store"
    try:
        return growth.quote(plan_code, promo_code)
    except ValueError as exc:
        raise HTTPException(400, str(exc))



@app.get("/api/admin/premium-picks")
def api_admin_list_premium_picks(request: Request, response: Response):
    _require_admin(request)
    response.headers["Cache-Control"]="private, no-store"
    return {"items":premium_picks.list_entries(include_disabled=True),"timezone":"Africa/Kampala"}


@app.post("/api/admin/premium-picks")
def api_admin_create_premium_pick(payload: PremiumPickAdminBody, request: Request, response: Response):
    admin=_require_admin(request)
    _verify_write_origin(request)
    response.headers["Cache-Control"]="no-store"
    try:
        item=premium_picks.save_entry(payload.model_dump(),int(admin["id"]))
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    return {"ok":True,"item":item}


@app.put("/api/admin/premium-picks/{entry_id}")
def api_admin_edit_premium_pick(entry_id: int, payload: PremiumPickAdminBody, request: Request, response: Response):
    admin=_require_admin(request)
    _verify_write_origin(request)
    response.headers["Cache-Control"]="no-store"
    try:
        item=premium_picks.save_entry(payload.model_dump(),int(admin["id"]),entry_id)
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    return {"ok":True,"item":item}


@app.post("/api/admin/premium-picks/{entry_id}/visibility")
def api_admin_toggle_premium_pick(entry_id: int, payload: PremiumPickToggleBody, request: Request, response: Response):
    admin=_require_admin(request)
    _verify_write_origin(request)
    response.headers["Cache-Control"]="no-store"
    try:
        item=premium_picks.toggle_entry(entry_id,int(admin["id"]),payload.enabled)
    except ValueError as exc:
        raise HTTPException(404,str(exc))
    return {"ok":True,"item":item}


@app.get("/api/premium-picks")
def api_premium_picks(request: Request, response: Response):
    """Curated picks are visible to VIP and to members during active Free Access."""
    account = _require_account(request)
    response.headers["Cache-Control"] = "private, no-store"
    if not _is_vip(account):
        # Preserve existing email-based Free Access eligibility and release timing.
        if not account.get("email") or not free_access.active_release():
            raise HTTPException(403, "VIP or an active Free Access release is required.")
    schedule = premium_picks.snapshot()
    return {"ok": True, **premium_picks.attach_results(schedule, feed)}


@app.get("/api/free-access/status")
def api_free_access_status(request: Request):
    """Only availability is exposed; upcoming release details stay admin-private."""
    account = _require_account(request)
    response = {"vip": _is_vip(account)}
    if response["vip"]:
        response["open"] = True
        response["markets"] = ["overs","unders","btts","wins"]
    else:
        release = free_access.active_release()
        response["open"] = bool(account.get("email")) and bool(release and release["markets"])
        # Market choices are public only DURING an active release, not its timetable.
        response["markets"] = release["markets"] if response["open"] else []
    return response


@app.get("/api/admin/free-releases")
def api_admin_free_releases(request: Request):
    _require_admin(request)
    return {"releases": free_access.list_releases()}


@app.post("/api/admin/free-releases")
def api_admin_create_free_release(payload: FreeReleaseBody, request: Request):
    admin = _require_admin(request)
    _verify_write_origin(request)
    try:
        release_id = free_access.create_release(
            payload.starts_at, int(admin["id"]), payload.enabled, payload.ends_at, payload.markets
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "id": release_id}


@app.patch("/api/admin/free-releases/{release_id}")
def api_admin_edit_free_release(release_id: int, payload: FreeReleaseEditBody, request: Request):
    admin = _require_admin(request)
    _verify_write_origin(request)
    try:
        free_access.update_release(
            release_id, payload.starts_at, payload.ends_at,
            payload.markets, payload.enabled, int(admin["id"])
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.post("/api/admin/free-releases/{release_id}/enabled")
def api_admin_toggle_free_release(release_id: int, payload: FreeReleaseToggle, request: Request):
    _require_admin(request)
    _verify_write_origin(request)
    try:
        free_access.set_enabled(release_id, payload.enabled)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.delete("/api/admin/free-releases/{release_id}")
def api_admin_delete_free_release(release_id: int, request: Request):
    _require_admin(request)
    _verify_write_origin(request)
    try:
        free_access.delete_release(release_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}


@app.get("/api/admin/promotions")
def api_admin_promotions(request: Request):
    _require_admin(request)
    return {"promotions": growth.list_promotions()}


@app.post("/api/admin/promotions")
def api_create_promotion(payload: PromotionBody, request: Request):
    _require_admin(request)
    try:
        promo_id = growth.create_promotion(payload.plan_code, payload.price_ugx, payload.code,
                                          payload.starts_at, payload.ends_at, payload.enabled)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "id": promo_id}


@app.post("/api/admin/promotions/{promotion_id}/enabled")
def api_toggle_promotion(promotion_id: int, payload: PromotionToggle, request: Request):
    _require_admin(request)
    try:
        growth.set_promotion_enabled(promotion_id, payload.enabled)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}


@app.get("/api/purchase/catalog")
def api_purchase_catalog(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return purchase_requests.catalog()


@app.post("/api/purchase/requests")
def api_submit_purchase(payload: PurchaseRequestBody, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if not purchase_requests.purchase_enabled():
        raise HTTPException(503, "Purchases are not accepting requests yet.")
    actor = _session_account(request)
    buyer_id = int(actor["id"]) if actor and actor.get("role") == "client" else None
    try:
        reference = purchase_requests.submit(
            payload.email, payload.username, payload.display_name,
            payload.plan_code, payload.payment_method, payload.transaction_ref,
            payload.proof_base64, payload.age_confirmed,
            account_id=buyer_id, promo_code=payload.promo_code,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "reference": reference, "status": "pending",
            "message": "Payment request received. Access is NOT active until manually verified and approved."}


@app.get("/api/admin/payment-requests")
def api_admin_payment_requests(request: Request, response: Response):
    _require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    return {"requests": purchase_requests.pending()}


@app.get("/api/admin/payment-requests/{request_id}/proof")
def api_admin_payment_proof(request_id: int, request: Request):
    _require_admin(request)
    found = purchase_requests.proof(request_id)
    if not found:
        raise HTTPException(404, "Proof not found.")
    data, mime = found
    ext = {"image/png":"png", "image/jpeg":"jpg", "image/webp":"webp", "application/pdf":"pdf"}[mime]
    return FileResponseBytes(
        data, media_type="application/octet-stream",
        headers={"Cache-Control":"no-store", "X-Content-Type-Options":"nosniff",
                 "Content-Disposition":f'attachment; filename="payment-proof-{request_id}.{ext}"'},
    )


def _purchase_public_origin(admin_supplied: str | None) -> str:
    from urllib.parse import urlparse
    origin = (admin_supplied or os.getenv("PREDICTOR_PUBLIC_BASE_URL","")).strip().rstrip("/")
    try:
        parsed = urlparse(origin)
        valid_port = parsed.port in (None,443)
    except ValueError:
        valid_port = False
        parsed = None
    if (not parsed or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or not valid_port):
        raise HTTPException(400,"Configure a valid HTTPS public website origin before approving.")
    return origin


@app.post("/api/admin/payment-requests/{request_id}/review")
def api_admin_review_payment(request_id: int, payload: PurchaseDecision, request: Request, response: Response):
    admin = _require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    base = None
    if payload.approve:
        try:
            needs_origin = purchase_requests.needs_activation_origin(request_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        if needs_origin:
            # Validate before reserving; avoid leaving bad requests in "processing".
            base = _purchase_public_origin(payload.public_base_url)
    try:
        purchase = purchase_requests.approve_or_reject(
            request_id, int(admin["id"]), payload.approve, payload.verified, payload.reason
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not payload.approve:
        return {"ok": True, "status": "rejected"}
    # A pending reservation prevents duplicate account creation on repeated approvals.
    if purchase.get("buyer_account_id") is not None:
        try:
            account_id = int(purchase["buyer_account_id"])
            current = get_account(account_id)
            if not current or current["role"] != "client" or current["status"] != "active" or current["username"].lower() != purchase["requested_username"].lower():
                raise ValueError("The original buyer account is no longer available.")
            purchase_requests.activate_existing_verified(request_id, account_id, purchase["plan_code"], int(admin["id"]))
        except Exception:
            purchase_requests.reset_processing(request_id)
            raise
        return {"ok": True, "status": "approved", "existing_account": True,
                "email_sent": False, "activation_link": None, "client_account_id": account_id}
    try:
        account, _temp = create_client(
            purchase["requested_username"],purchase["display_name"],
            plan_code=purchase["plan_code"],created_by=int(admin["id"]),
        )
        purchase_requests.mark_approved(request_id, int(account["id"]))
        growth.mark_vip_conversion(int(account["id"]))
    except Exception:
        purchase_requests.reset_processing(request_id)
        raise
    invitation = access_links.issue(int(account["id"]), "activation", int(admin["id"]))
    link = base + "/activate#" + invitation["token"]
    sent = False
    error = None
    try:
        purchase_requests.email_activation(
            purchase["email"], account["username"], invitation["token"], base
        )
        sent = True
    except (Exception) as exc:
        # SMTP failure must not undo a verified payment or pretend mail was sent.
        error = str(exc)[:200]
    purchase_requests.set_email_status(request_id, "sent" if sent else "pending")
    return {"ok":True,"status":"approved", "email_sent":sent,
            "email_notice":error, "activation_link":None if sent else link,
            "client_account_id":account["id"]}


@app.post("/api/admin/payment-requests/{request_id}/resend")
def api_admin_resend_purchase(request_id: int, payload: PurchaseResend, request: Request, response: Response):
    admin = _require_admin(request)
    response.headers["Cache-Control"] = "no-store"
    row = purchase_requests.approved_account(request_id)
    if not row:
        raise HTTPException(404,"Approved request not found.")
    account = get_account(int(row["client_account_id"]))
    if not account or not account["must_change_password"]:
        raise HTTPException(400,"Account already activated or removed.")
    base = _purchase_public_origin(payload.public_base_url)
    invitation = access_links.issue(int(account["id"]),"activation",int(admin["id"]))
    link = base + "/activate#" + invitation["token"]
    try:
        purchase_requests.email_activation(row["email"],account["username"],invitation["token"],base)
        purchase_requests.set_email_status(request_id,"sent")
        return {"ok":True,"email_sent":True}
    except Exception as exc:
        purchase_requests.set_email_status(request_id,"pending")
        return {"ok":True,"email_sent":False,"notice":str(exc)[:200],"activation_link":link}


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
    account = _require_active_access(request)
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


@app.get("/api/admin/analytics")
def api_admin_analytics(request: Request, response: Response):
    _require_admin(request)
    response.headers["Cache-Control"]="no-store, private"
    return admin_analytics.snapshot()


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
            chosen_password=payload.chosen_password,
            expires_at=payload.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # A shared PUBLIC TRIAL account has a preset password and is already activated.
    # No activation link is issued for such an account.
    invitation = (access_links.issue(int(account["id"]), "activation", int(admin["id"]))
                  if account["must_change_password"] else None)
    return {
        "ok": True, "account": public_account(account),
        "temporary_password": temporary_password,
        "activation_token": invitation["token"] if invitation else None,
        "activation_expires_at": invitation["expires_at"] if invitation else None,
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


@app.post("/api/admin/clients/{account_id}/subscription/expiry")
def api_admin_set_subscription_expiry(
    account_id: int, payload: SubscriptionExpiry, request: Request,
):
    admin = _require_admin(request)
    try:
        set_subscription_expiry(
            account_id, payload.expires_at,
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
    if payload.approve and not payload.verified:
        raise HTTPException(400, "Verify the received payment independently before approval.")
    try:
        review_subscription_request(request_id, payload.approve, int(admin["id"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.get("/api/admin/strategies")
def api_admin_strategies(request: Request):
    _require_admin(request)
    return {"strategies": _admin_strategy_catalog()}



@app.get("/api/win-proofs")
def api_win_proofs():
    """Public, approved-only user-submitted win screenshot gallery."""
    return {"items": win_proofs.public_gallery()}


@app.get("/api/win-proofs/{proof_id}/image")
def api_win_proof_image(proof_id: int, request: Request):
    viewer = _session_account(request)
    path = win_proofs.image_path(
        proof_id, viewer_id=int(viewer["id"]) if viewer else None,
        is_admin=bool(viewer and viewer.get("role") == "admin"),
    )
    if not path:
        raise HTTPException(404, "Screenshot not found.")
    return FileResponse(
        path, media_type="image/webp",
        headers={"Cache-Control": "private, max-age=60", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/api/win-proofs/mine")
def api_my_win_proofs(request: Request):
    account = _require_account(request)
    return {"items": win_proofs.mine(int(account["id"]))}


@app.post("/api/win-proofs")
def api_submit_win_proof(payload: WinProofSubmission, request: Request):
    account = _require_account(request)
    _verify_write_origin(request)
    try:
        ident = win_proofs.submit(int(account["id"]), payload.image_base64, payload.consent)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "id": ident, "status": "pending"}


@app.delete("/api/win-proofs/{proof_id}")
def api_delete_my_win_proof(proof_id: int, request: Request):
    account = _require_account(request)
    _verify_write_origin(request)
    try:
        win_proofs.delete_own(proof_id, int(account["id"]))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}


@app.get("/api/admin/win-proofs")
def api_admin_win_proofs(request: Request, response: Response, status: str = "all"):
    _require_admin(request)
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return {"items": win_proofs.admin_list(status)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/admin/win-proofs/{proof_id}/review")
def api_admin_review_win_proof(proof_id: int, payload: WinProofReview, request: Request):
    account = _require_admin(request)
    _verify_write_origin(request)
    try:
        win_proofs.review(proof_id, payload.decision, int(account["id"]))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.post("/api/admin/win-proofs/import")
def api_import_curated_win_proofs(payload: CuratedWinProofImport, request: Request):
    account = _require_admin(request)
    _verify_write_origin(request)
    try:
        count = win_proofs.import_curated_archive(
            int(account["id"]), payload.archive_base64, payload.redaction_confirmed,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "imported": count}


@app.get("/api/status")
def status():
    return {
        "app": "BetPawa Predictor",
        "rules_public": False,
        "mode": "client subscriptions + private admin strategy console",
    }


@app.get("/api/virtual/season-status")
def virtual_season_status(request: Request):
    """Actual season/round windows for signed-in members; no predicted games."""
    _require_account(request)
    try:
        actual, _, _ = feed._catalog()
        return current_seasons.current_season_status(actual)
    except Exception as exc:
        print("Live virtual season status unavailable:", repr(exc))
        raise HTTPException(503, "Current betPawa season feed unavailable.")


@app.get("/api/recommended-picks")
def recommended_picks(request: Request):
    """Read-only next-round cross-market summary; never saves user selections."""
    account = _require_account(request)
    is_free = not _is_vip(account)
    if is_free:
        if not account.get("email") or free_access.active_release() is None:
            raise HTTPException(403, "An active subscription or Free release is required.")
    try:
        context = feed.prediction_context()
        if is_free and not _free_round_allowed(context):
            raise HTTPException(403, "This matchday is not part of an active public release.")
        predictions = build_prediction(context).get("predictions", [])
        if is_free:
            predictions = [
                p for p in predictions
                if str(p.get("league", "")).upper() in {"ENGLISH", "EPL", "DUTCH", "NETHERLANDS"}
                and free_access.allowed_market(_market_category(p.get("expected")))
            ]
        public_predictions = [_public_prediction(p) for p in predictions]
        featured, research_watches = recommendation_quality.rank_recommendations(public_predictions)
        return {
            "ok": True,
            "season": str(context["season"]),
            "next_matchday": context["next_matchday"],
            "next_round_id": context.get("next_round_id"),
            "next_round_open_utc": context.get("next_round_open_utc"),
            "next_round_close_utc": context.get("next_round_close_utc"),
            # Keep the original authorized predictions for other screens.
            # The homepage/client Featured section reads only these stricter
            # reviewed results. Each result is a real current-round pick.
            "predictions": public_predictions,
            "featured_predictions": featured,
            "research_watchlist": research_watches,
            "reviewed_h2h_patterns": recommendation_quality.reviewed_h2h_catalog(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        print("Recommendation service error:", repr(exc))
        raise HTTPException(502, "Recommendations temporarily unavailable.")


@app.post("/api/predict/{category}")
def predict_category(category: str, request: Request, response: Response):
    if category not in {"overs", "unders", "btts", "wins"}:
        raise HTTPException(404, "Unknown market page.")
    account = _require_account(request)
    is_free = not _is_vip(account)
    user_id = account["user_key"]
    started = time.perf_counter()
    if is_free and not account.get("email"):
        raise HTTPException(403, "An active subscription is required.")
    if is_free and free_access.active_release() is None:
        raise HTTPException(403, "No public predictions have been released at the moment.")
    if is_free and not free_access.allowed_market(category):
        raise HTTPException(403, "This prediction market is not enabled for the current Free release.")
    try:
        context = feed.prediction_context()
        if is_free and not _free_round_allowed(context):
            raise HTTPException(403, "This matchday is not part of an active public release.")
        graded_now = grade_user_predictions(user_id, context["completed_rounds_for_grading"]) if not is_free else 0
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
        # A free response is filtered before returning; VIP history is never included.
        if is_free:
            return _free_market_result(_public_result(category_result))
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
