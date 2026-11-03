from typing import Any

from app.config import Settings
from app.models.domain import CoreProfile, UserProfile
from app.services.hibob import HiBobClient
from app.services.agency import domain_from_email
from app.storage.base import ProfileStore


def core_profile_from_hibob(normalized: dict[str, Any]) -> CoreProfile | None:
    email = str(normalized.get("email") or "").strip().lower()
    if not email:
        return None
    hibob_id = normalized.get("hibob_id")
    return CoreProfile(
        core_id=str(hibob_id or email),
        hibob_id=str(hibob_id) if hibob_id else None,
        email=email,
        email_domain=domain_from_email(email),
        display_name=normalized.get("display_name"),
        title=normalized.get("title"),
        department=normalized.get("department"),
        site=normalized.get("site"),
        manager_id=normalized.get("manager_id"),
        manager_name=normalized.get("manager_name"),
        start_date=normalized.get("start_date"),
        raw=normalized.get("raw") or {},
    )


async def sync_core_profiles(store: ProfileStore, settings: Settings) -> int:
    client = HiBobClient(settings)
    if not client.enabled:
        raise RuntimeError("HiBob is not configured")
    count = 0
    for normalized in await client.list_people():
        profile = core_profile_from_hibob(normalized)
        if profile:
            store.save_core_profile(profile)
            count += 1
    return count


def seed_user_from_core_profile(store: ProfileStore, user: UserProfile) -> UserProfile:
    """Apply the cached HiBob source record before generated enrichment runs."""
    profile = store.get_core_profile_by_email(user.email)
    if not profile:
        return user
    if not user.display_name and profile.display_name:
        user.display_name = profile.display_name
    user.hibob = {
        "status": "ok",
        "source": "core_profile",
        "normalized": {
            "hibob_id": profile.hibob_id,
            "email": profile.email,
            "display_name": profile.display_name,
            "first_name": (profile.display_name or "").split(" ", 1)[0] or None,
            "last_name": (profile.display_name or "").split(" ", 1)[-1] or None,
            "title": profile.title,
            "department": profile.department,
            "site": profile.site,
            "manager_id": profile.manager_id,
            "manager_name": profile.manager_name,
            "start_date": profile.start_date,
            "raw": profile.raw,
        },
    }
    return user
