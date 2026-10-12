from fastapi import APIRouter, Depends

from app.dependencies import require_user
from app.models.domain import UserProfile
from app.services.redact import redact_user_payload
from app.storage.factory import get_store

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/me")
def me(user: UserProfile = Depends(require_user)):
    store = get_store()
    agency = store.get_agency(user.agency_id) if user.agency_id else None
    return {
        "user": redact_user_payload(user.model_dump(mode="json")),
        "agency": agency.model_dump(mode="json") if agency else None,
    }
