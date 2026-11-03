import secrets

from fastapi import Header, HTTPException, Request

from app.config import Settings, get_settings
from app.models.domain import UserProfile
from app.storage.factory import get_store


def get_current_user(request: Request) -> UserProfile | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = get_store().get_user(user_id)
    if user and not get_settings().is_email_allowed(user.email):
        request.session.clear()
        return None
    return user


def require_user(request: Request) -> UserProfile:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def is_admin(user: UserProfile | None, settings: Settings | None = None) -> bool:
    if not user or not user.email:
        return False
    settings = settings or get_settings()
    allowed = settings.admin_email_set
    if not allowed:
        return False
    return user.email.strip().lower() in allowed


def require_admin(request: Request) -> UserProfile:
    user = require_user(request)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_api_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    """Authenticate machine clients with an API key from X-API-Key or Bearer."""

    supplied = x_api_key
    if not supplied and authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    configured = get_settings().external_api_key_set
    if not configured or not supplied:
        raise HTTPException(status_code=401, detail="Valid API key required")
    if not any(secrets.compare_digest(supplied, expected) for expected in configured):
        raise HTTPException(status_code=401, detail="Valid API key required")
    return supplied
