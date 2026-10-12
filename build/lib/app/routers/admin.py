import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.dependencies import require_admin
from app.models.domain import UserProfile
from app.routers.template_context import page_context
from app.services.admin_overview import (
    agency_admin_row,
    agency_detail_payload,
    org_stats,
    user_admin_row,
    user_detail_payload,
)
from app.storage.factory import get_store

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def admin_home(request: Request, user: UserProfile = Depends(require_admin)):
    store = get_store()
    settings = get_settings()
    users = store.list_users()
    agencies = store.list_agencies()
    return templates.TemplateResponse(
        request,
        "admin.html",
        page_context(
            request,
            admin_user=user,
            stats=org_stats(users, agencies),
            user_rows=[user_admin_row(u) for u in users],
            agency_rows=[agency_admin_row(a) for a in agencies],
            storage_backend=settings.storage_backend,
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
        page_context(
            request,
            admin_user=admin,
            subject=subject,
            subject_row=user_admin_row(subject),
            agency=agency,
            work_profile_json=json.dumps(wp, indent=2, default=str) if wp else "",
            payload_json=json.dumps(payload, indent=2, default=str),
        ),
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
        page_context(
            request,
            admin_user=admin,
            agency=agency,
            agency_row=agency_admin_row(agency),
            members=members,
            payload_json=json.dumps(payload, indent=2, default=str),
        ),
    )
