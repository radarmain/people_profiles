"""Shared Google OAuth token helpers for People, Calendar, etc."""

import time
from typing import Any

import httpx

from app.config import Settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
EXPIRY_BUFFER_SECONDS = 120


def token_expired(oauth: dict[str, Any]) -> bool:
    expires_at = oauth.get("expires_at")
    if expires_at is None:
        return False
    try:
        return float(expires_at) <= time.time() + EXPIRY_BUFFER_SECONDS
    except (TypeError, ValueError):
        return False


async def refresh_google_access_token(settings: Settings, refresh_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code >= 400:
            return {"ok": False, "error": resp.text}
        data = resp.json()
    expires_in = data.get("expires_in")
    expires_at = time.time() + float(expires_in) if expires_in else None
    return {
        "ok": True,
        "access_token": data.get("access_token"),
        "expires_at": expires_at,
        "scope": data.get("scope"),
    }


async def resolve_google_access_token(
    settings: Settings, oauth: dict[str, Any]
) -> tuple[str | None, dict[str, Any]]:
    updated = dict(oauth)
    access_token = updated.get("access_token")
    refresh_token = updated.get("refresh_token")

    if access_token and not token_expired(updated):
        return access_token, updated

    if refresh_token:
        refreshed = await refresh_google_access_token(settings, refresh_token)
        if refreshed.get("ok"):
            updated["access_token"] = refreshed["access_token"]
            if refreshed.get("expires_at"):
                updated["expires_at"] = refreshed["expires_at"]
            return updated["access_token"], updated

    return access_token, updated
