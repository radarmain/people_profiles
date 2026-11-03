import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.dependencies import require_user
from app.routers.template_context import page_context

logger = logging.getLogger(__name__)
from app.models.domain import UserProfile
from app.services.enrichment_snapshot import build_llm_context
from app.services._user_profiles_jobs import JOB_ENRICH, JOB_SUMMARIZE, dispatch_user_profiles_job
from app.storage.factory import get_store

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "home.html",
        page_context(
            request,
            google_ready=settings.google_configured,
            slack_ready=settings.slack_configured,
            hibob_ready=settings.hibob_configured,
            bedrock_kb_ready=settings.bedrock_kb_configured,
            linkedin_lookup_ready=settings.linkedin_lookup_enabled and settings.web_search_available,
        ),
    )


@router.get("/connect/slack", response_class=HTMLResponse)
async def connect_slack_page(request: Request, user: UserProfile = Depends(require_user)):
    # Always allow reconnect/connect when Slack is not linked (bypass only skips the gate).
    if user.slack_connected:
        return RedirectResponse(url="/profile", status_code=303)
    settings = get_settings()
    slack_redirect_uri = f"{settings.app_base_url.rstrip('/')}/auth/slack/callback"
    return templates.TemplateResponse(
        request,
        "connect_slack.html",
        page_context(request, slack_redirect_uri=slack_redirect_uri),
    )


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user: UserProfile = Depends(require_user)):
    job_notice = request.query_params.get("job")
    job_error = request.query_params.get("job_error")
    if not user.slack_connected and not user.slack_connect_bypassed:
        return RedirectResponse(url="/connect/slack", status_code=303)

    settings = get_settings()
    store = get_store()
    agency = store.get_agency(user.agency_id) if user.agency_id else None
    snapshot = build_llm_context(user, agency)
    network = user.network_associations if isinstance(user.network_associations, dict) else {}
    network_edges = network.get("edges") or []
    if not isinstance(network_edges, list):
        network_edges = []
    network_edges = sorted(
        [e for e in network_edges if isinstance(e, dict)],
        key=lambda e: int(e.get("closeness_score") or 0),
        reverse=True,
    )[:15]
    return templates.TemplateResponse(
        request,
        "profile.html",
        page_context(
            request,
            user=user,
            agency=agency,
            snapshot=snapshot,
            network_edges=network_edges,
            network_window_days=network.get("window_days"),
            storage_backend=settings.storage_backend,
            dynamodb_target="aws"
            if settings.storage_backend == "dynamodb" and not settings.dynamodb_endpoint
            else ("local" if settings.storage_backend == "dynamodb" else settings.storage_backend),
            dynamodb_users_table=settings.dynamodb_users_table
            if settings.storage_backend == "dynamodb"
            else None,
            job_notice=job_notice,
            job_error=job_error,
        ),
    )


@router.post("/profile/refresh")
async def refresh_profile(request: Request, user: UserProfile = Depends(require_user)):
    await dispatch_user_profiles_job(JOB_ENRICH, user)
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/summary")
async def generate_summary(request: Request, user: UserProfile = Depends(require_user)):
    try:
        mode = await dispatch_user_profiles_job(JOB_SUMMARIZE, user)
        return RedirectResponse(url=f"/profile?job=summarize&mode={mode}", status_code=303)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Summarize job failed for user %s", user.user_id)
        return RedirectResponse(
            url=f"/profile?job_error={quote(str(exc)[:500])}",
            status_code=303,
        )
