import csv
import io
import json
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.dependencies import require_admin
from app.models.domain import UserProfile, utc_now
from app.routers.template_context import page_context
from app.services.admin_overview import (
    agency_admin_row,
    agency_detail_payload,
    org_stats,
    user_admin_row,
    user_detail_payload,
)
from app.services.core_profiles import sync_core_profiles
from app.services.job_runner import run_work_profile_job
from app.storage.factory import get_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


def _admin_context(
    request: Request,
    *,
    active_tab: str,
    breadcrumbs: list[dict[str, str]],
    **extra,
):
    return page_context(
        request,
        active_admin_tab=active_tab,
        breadcrumbs=breadcrumbs,
        **extra,
    )


@router.get("", response_class=HTMLResponse)
async def admin_home(request: Request, user: UserProfile = Depends(require_admin)):
    store = get_store()
    settings = get_settings()
    users = store.list_users()
    agencies = store.list_agencies()
    core_query = request.query_params.get("core_q", "")
    core_profiles = store.list_core_profiles(core_query)
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        page_context(
            request,
            admin_user=user,
            stats=org_stats(users, agencies),
            user_rows=[user_admin_row(u) for u in users],
            agency_rows=[agency_admin_row(a) for a in agencies],
            storage_backend=settings.storage_backend,
            core_query=core_query,
            core_profiles=core_profiles,
            core_sync_notice=request.query_params.get("core_sync"),
            core_sync_error=request.query_params.get("core_sync_error"),
        ),
    )


@router.get("/users", response_class=HTMLResponse)
async def admin_users(request: Request, user: UserProfile = Depends(require_admin)):
    query = request.query_params.get("q", "")
    users = get_store().list_users()
    needle = query.strip().lower()
    if needle:
        users = [
            item for item in users
            if needle in f"{item.email} {item.display_name or ''} {item.email_domain}".lower()
        ]
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        _admin_context(
            request,
            active_tab="users",
            breadcrumbs=[
                {"label": "Admin", "url": "/admin"},
                {"label": "Users", "url": "/admin/users"},
            ],
            admin_user=user,
            query=query,
            user_rows=[user_admin_row(item) for item in users],
        ),
    )


@router.get("/agencies", response_class=HTMLResponse)
async def admin_agencies(request: Request, user: UserProfile = Depends(require_admin)):
    return templates.TemplateResponse(
        request,
        "admin_agencies.html",
        _admin_context(
            request,
            active_tab="agencies",
            breadcrumbs=[
                {"label": "Admin", "url": "/admin"},
                {"label": "Agencies", "url": "/admin/agencies"},
            ],
            admin_user=user,
            agency_rows=[agency_admin_row(item) for item in get_store().list_agencies()],
        ),
    )


@router.get("/core-profiles", response_class=HTMLResponse)
async def admin_core_profiles(request: Request, user: UserProfile = Depends(require_admin)):
    query = request.query_params.get("q", "")
    return templates.TemplateResponse(
        request,
        "admin_core_profiles.html",
        _admin_context(
            request,
            active_tab="core",
            breadcrumbs=[
                {"label": "Admin", "url": "/admin"},
                {"label": "Core profiles", "url": "/admin/core-profiles"},
            ],
            admin_user=user,
            query=query,
            core_profiles=get_store().list_core_profiles(query),
            core_sync_notice=request.query_params.get("core_sync"),
            core_sync_error=request.query_params.get("core_sync_error"),
        ),
    )


@router.get("/generated-profiles", response_class=HTMLResponse)
async def admin_generated_profiles(request: Request, user: UserProfile = Depends(require_admin)):
    query = request.query_params.get("q", "")
    users = get_store().list_users()
    needle = query.strip().lower()
    if needle:
        users = [
            item for item in users
            if needle in f"{item.email} {item.display_name or ''} {item.email_domain}".lower()
        ]
    return templates.TemplateResponse(
        request,
        "admin_generated_profiles.html",
        _admin_context(
            request,
            active_tab="generated",
            breadcrumbs=[
                {"label": "Admin", "url": "/admin"},
                {"label": "Generated profiles", "url": "/admin/generated-profiles"},
            ],
            admin_user=user,
            query=query,
            user_rows=[user_admin_row(item) for item in users],
        ),
    )


@router.post("/core-profiles/sync")
async def admin_sync_core_profiles(
    request: Request,
    admin: UserProfile = Depends(require_admin),
):
    try:
        count = await sync_core_profiles(get_store(), get_settings())
        return RedirectResponse(url=f"/admin/core-profiles?core_sync={count}", status_code=303)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Core profile sync failed for %s", admin.email)
        return RedirectResponse(
            url=f"/admin/core-profiles?core_sync_error={quote(str(exc)[:500])}",
            status_code=303,
        )


@router.get("/core-profiles/export.csv")
async def admin_export_core_profiles(
    admin: UserProfile = Depends(require_admin),
):
    """Export all HiBob-backed Core profiles as a CSV file."""

    del admin
    fields = [
        "core_id",
        "hibob_id",
        "email",
        "email_domain",
        "display_name",
        "title",
        "department",
        "site",
        "manager_id",
        "manager_name",
        "start_date",
        "synced_at",
        "updated_at",
        "raw",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for profile in get_store().list_core_profiles():
        writer.writerow(
            {
                "core_id": profile.core_id,
                "hibob_id": profile.hibob_id or "",
                "email": profile.email,
                "email_domain": profile.email_domain,
                "display_name": profile.display_name or "",
                "title": profile.title or "",
                "department": profile.department or "",
                "site": profile.site or "",
                "manager_id": profile.manager_id or "",
                "manager_name": profile.manager_name or "",
                "start_date": profile.start_date or "",
                "synced_at": profile.synced_at.isoformat(),
                "updated_at": profile.updated_at.isoformat(),
                "raw": json.dumps(profile.raw, ensure_ascii=False, default=str),
            }
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=core-profiles.csv"},
    )


@router.get("/core-profiles/{core_id}", response_class=HTMLResponse)
async def admin_core_profile_detail(
    core_id: str,
    request: Request,
    admin: UserProfile = Depends(require_admin),
):
    store = get_store()
    profile = next((item for item in store.list_core_profiles() if item.core_id == core_id), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Core profile not found")
    generated = store.get_user_by_email(profile.email)
    return templates.TemplateResponse(
        request,
        "admin_core_profile.html",
        _admin_context(
            request,
            active_tab="core",
            breadcrumbs=[
                {"label": "Admin", "url": "/admin"},
                {"label": "Core profiles", "url": "/admin/core-profiles"},
                {"label": profile.display_name or profile.email, "url": request.url.path},
            ],
            admin_user=admin,
            profile=profile,
            generated_user=generated,
            raw_json=json.dumps(profile.raw, indent=2, default=str),
        ),
    )


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def admin_user_detail(
    user_id: str,
    request: Request,
    admin: UserProfile = Depends(require_admin),
):
    store = get_store()
    subject = store.get_user(user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="User not found")
    agency = store.get_agency(subject.agency_id) if subject.agency_id else None
    payload = user_detail_payload(subject)
    wp = subject.work_profile if isinstance(subject.work_profile, dict) else {}
    return templates.TemplateResponse(
        request,
        "admin_user.html",
        _admin_context(
            request,
            active_tab="generated",
            breadcrumbs=[
                {"label": "Admin", "url": "/admin"},
                {"label": "Generated profiles", "url": "/admin/generated-profiles"},
                {"label": subject.display_name or subject.email, "url": request.url.path},
            ],
            admin_user=admin,
            subject=subject,
            subject_row=user_admin_row(subject),
            agency=agency,
            work_profile_json=json.dumps(wp, indent=2, default=str) if wp else "",
            payload_json=json.dumps(payload, indent=2, default=str),
            job_notice=request.query_params.get("job"),
            job_error=request.query_params.get("job_error"),
        ),
    )


@router.post("/users/{user_id}/display-name")
async def admin_set_display_name(
    user_id: str,
    request: Request,
    admin: UserProfile = Depends(require_admin),
):
    """Set/correct display name (critical for LinkedIn matching on provisionals)."""

    store = get_store()
    subject = store.get_user(user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="User not found")

    form = await request.form()
    name = str(form.get("display_name") or "").strip()
    if not name:
        return RedirectResponse(
            url=f"/admin/users/{quote(user_id, safe='')}?job_error={quote('Display name is required')}",
            status_code=303,
        )

    subject.display_name = name
    # Clear a prior bad LinkedIn match so the next work-profile run re-searches.
    li = subject.linkedin if isinstance(subject.linkedin, dict) else {}
    if li.get("status") in ("ok", "low_confidence", "name_mismatch"):
        subject.linkedin = {
            "status": "stale",
            "message": f"Cleared after display name set to {name!r} by {admin.email}",
            "cleared_at": utc_now().isoformat(),
        }
    store.save_user(subject)
    return RedirectResponse(
        url=f"/admin/users/{quote(user_id, safe='')}?job=display_name",
        status_code=303,
    )


@router.post("/users/{user_id}/work-profile")
async def admin_generate_work_profile(
    user_id: str,
    request: Request,
    admin: UserProfile = Depends(require_admin),
):
    """Generate work profile (+ role brief) for any user, including provisionals."""

    store = get_store()
    subject = store.get_user(user_id)
    if not subject:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        # Always run inline so the admin page shows results after redirect.
        await run_work_profile_job(user_id)
        return RedirectResponse(
            url=f"/admin/users/{quote(user_id, safe='')}?job=work_profile",
            status_code=303,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Admin work profile failed for %s (requested by %s)",
            user_id,
            admin.email,
        )
        return RedirectResponse(
            url=f"/admin/users/{quote(user_id, safe='')}?job_error={quote(str(exc)[:500])}",
            status_code=303,
        )


@router.get("/agencies/{agency_id}", response_class=HTMLResponse)
async def admin_agency_detail(
    agency_id: str,
    request: Request,
    admin: UserProfile = Depends(require_admin),
):
    store = get_store()
    agency = store.get_agency(agency_id)
    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")
    members = []
    for uid in agency.member_user_ids:
        member = store.get_user(uid)
        if member:
            members.append(user_admin_row(member))
    payload = agency_detail_payload(agency)
    return templates.TemplateResponse(
        request,
        "admin_agency.html",
        _admin_context(
            request,
            active_tab="agencies",
            breadcrumbs=[
                {"label": "Admin", "url": "/admin"},
                {"label": "Agencies", "url": "/admin/agencies"},
                {"label": agency.display_name or agency.domain, "url": request.url.path},
            ],
            admin_user=admin,
            agency=agency,
            agency_row=agency_admin_row(agency),
            members=members,
            payload_json=json.dumps(payload, indent=2, default=str),
        ),
    )
