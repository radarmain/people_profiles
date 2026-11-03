from urllib.parse import urlencode

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.dependencies import require_user
from app.models.domain import UserProfile
from app.services.agency import domain_from_email, ensure_user_agency
from app.services.provisional_user import merge_provisional_into_member
from app.services._user_profiles_jobs import JOB_ENRICH, dispatch_user_profiles_job
from app.storage.factory import get_store

router = APIRouter(prefix="/auth", tags=["auth"])

oauth = OAuth()


def _register_oauth() -> None:
    settings = get_settings()
    if settings.google_configured:
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": settings.google_oauth_scopes},
        )


_register_oauth()


def _google_authorize_extra(request: Request) -> dict[str, str]:
    settings = get_settings()
    extra: dict[str, str] = {"access_type": "offline"}
    if settings.google_oauth_prompt_consent or request.query_params.get("consent") == "1":
        extra["prompt"] = "consent"
    elif request.session.pop("google_force_consent", False):
        extra["prompt"] = "consent"
    return extra


@router.get("/login")
async def login_page(request: Request):
    settings = get_settings()
    if not settings.google_configured:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )
    redirect_uri = f"{settings.app_base_url}/auth/google/callback"
    return await oauth.google.authorize_redirect(
        request, redirect_uri, **_google_authorize_extra(request)
    )


@router.get("/google/relink")
async def google_relink(request: Request, user: UserProfile = Depends(require_user)):
    """Force Google consent screen to obtain refresh token for People API."""
    settings = get_settings()
    if not settings.google_configured:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured.")
    request.session["google_force_consent"] = True
    request.session["user_id"] = user.user_id
    redirect_uri = f"{settings.app_base_url}/auth/google/callback"
    return await oauth.google.authorize_redirect(
        request, redirect_uri, access_type="offline", prompt="consent"
    )


@router.get("/google/callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        raise HTTPException(status_code=400, detail="Google did not return userinfo")

    user_id = userinfo["sub"]
    email = userinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Google account must have an email")

    store = get_store()
    existing = store.get_user(user_id)
    by_email = store.get_user_by_email(email)

    # Prefer OAuth tokens from the Google-sub record; fall back to provisional.
    prev_oauth = (existing.google.get("_oauth") if existing else None) or {}
    if not prev_oauth and by_email and by_email.is_provisional:
        prev_oauth = (by_email.google.get("_oauth") if by_email.google else None) or {}
    refresh_token = token.get("refresh_token") or prev_oauth.get("refresh_token")
    google_bundle = {
        "openid": dict(userinfo),
        "_oauth": {
            "access_token": token.get("access_token"),
            "refresh_token": refresh_token,
            "expires_at": token.get("expires_at"),
        },
    }

    if existing:
        user = existing
        user.account_kind = "member"
        user.google = google_bundle
        user.display_name = userinfo.get("name") or user.display_name
        user.picture_url = userinfo.get("picture") or user.picture_url
        user.email = email
        user.email_domain = domain_from_email(email)
        store.save_user(user)
        ensure_user_agency(store, user)
    elif by_email and by_email.is_provisional:
        user = merge_provisional_into_member(
            store,
            provisional=by_email,
            google_sub=user_id,
            email=email,
            display_name=userinfo.get("name"),
            picture_url=userinfo.get("picture"),
            google_bundle=google_bundle,
        )
    else:
        user = UserProfile(
            user_id=user_id,
            email=email,
            email_domain=domain_from_email(email),
            display_name=userinfo.get("name"),
            picture_url=userinfo.get("picture"),
            account_kind="member",
            google=google_bundle,
        )
        store.save_user(user)
        ensure_user_agency(store, user)

    request.session["user_id"] = user.user_id

    # Full profile scrub runs asynchronously (SQS/Lambda when offload enabled).
    await dispatch_user_profiles_job(JOB_ENRICH, user)

    if user.slack_connected or user.slack_connect_bypassed:
        return RedirectResponse(url="/profile", status_code=303)
    return RedirectResponse(url="/connect/slack", status_code=303)


@router.post("/slack/bypass")
async def slack_bypass(user: UserProfile = Depends(require_user)):
    store = get_store()
    user.slack_connect_bypassed = True
    store.save_user(user)
    return RedirectResponse(url="/profile", status_code=303)


@router.get("/slack/connect")
async def slack_connect(request: Request, user: UserProfile = Depends(require_user)):
    settings = get_settings()
    if not settings.slack_configured:
        raise HTTPException(status_code=503, detail="Slack OAuth is not configured.")

    state = user.user_id
    request.session["slack_oauth_state"] = state

    params = {
        "client_id": settings.slack_client_id,
        "user_scope": settings.slack_user_scopes,
        "redirect_uri": f"{settings.app_base_url.rstrip('/')}/auth/slack/callback",
        "state": state,
    }
    url = "https://slack.com/oauth/v2/authorize?" + urlencode(params)
    return RedirectResponse(url=url, status_code=303)


@router.get("/slack/callback")
async def slack_callback(request: Request, code: str | None = None, state: str | None = None):
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing Slack OAuth parameters")

    expected = request.session.get("slack_oauth_state")
    if not expected or expected != state:
        raise HTTPException(status_code=400, detail="Invalid Slack OAuth state")

    settings = get_settings()
    store = get_store()
    user = store.get_user(state)
    if not user:
        raise HTTPException(status_code=400, detail="User session expired")

    async with httpx.AsyncClient(timeout=30.0) as client:
        token_resp = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
                "redirect_uri": f"{settings.app_base_url.rstrip('/')}/auth/slack/callback",
            },
        )
        token_data = token_resp.json()

    if not token_data.get("ok"):
        raise HTTPException(status_code=400, detail=f"Slack OAuth failed: {token_data.get('error')}")

    authed_user = token_data.get("authed_user") or {}
    access_token = authed_user.get("access_token")
    slack_user_id = authed_user.get("id")
    if not access_token or not slack_user_id:
        raise HTTPException(status_code=400, detail="Slack did not return a user token")

    user.slack = {
        "_oauth": {
            "user_access_token": access_token,
            "user_id": slack_user_id,
            "team_id": (token_data.get("team") or {}).get("id"),
        },
        "oauth_meta": {
            "team_name": (token_data.get("team") or {}).get("name"),
            "team_id": (token_data.get("team") or {}).get("id"),
        },
    }
    user.slack_connected = True
    user.slack_connect_bypassed = False
    store.save_user(user)
    await dispatch_user_profiles_job(JOB_ENRICH, user)

    return RedirectResponse(url="/profile", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
