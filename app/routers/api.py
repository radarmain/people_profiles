from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import require_api_key, require_user
from app.models.domain import UserProfile
from app.services.redact import redact_user_payload
from app.storage.factory import get_store

router = APIRouter(prefix="/api", tags=["api"])
external_router = APIRouter(
    prefix="/api/v1",
    tags=["external-api"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/me")
def me(user: UserProfile = Depends(require_user)):
    store = get_store()
    agency = store.get_agency(user.agency_id) if user.agency_id else None
    return {
        "user": redact_user_payload(user.model_dump(mode="json")),
        "agency": agency.model_dump(mode="json") if agency else None,
    }


@external_router.get("/users")
def list_external_users(q: str = Query(default="")):
    store = get_store()
    users = store.list_users()
    needle = q.strip().lower()
    if needle:
        users = [
            user for user in users
            if needle in f"{user.email} {user.display_name or ''} {user.email_domain}".lower()
        ]
    return {"users": [redact_user_payload(user.model_dump(mode="json")) for user in users]}


@external_router.get("/users/{user_id}")
def get_external_user(user_id: str):
    user = get_store().get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user": redact_user_payload(user.model_dump(mode="json")),
        "agency": (
            get_store().get_agency(user.agency_id).model_dump(mode="json")
            if user.agency_id and get_store().get_agency(user.agency_id)
            else None
        ),
    }


@external_router.get("/core-profiles")
def list_external_core_profiles(q: str = Query(default="")):
    profiles = get_store().list_core_profiles(q)
    return {"core_profiles": [profile.model_dump(mode="json") for profile in profiles]}
