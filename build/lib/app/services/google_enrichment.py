from typing import Any

import httpx

from app.config import Settings
from app.services.google_calendar_enrichment import enrich_google_calendar
from app.services.google_oauth import refresh_google_access_token, resolve_google_access_token

PEOPLE_FIELDS = (
    "names,emailAddresses,photos,organizations,phoneNumbers,locales,biographies,urls,metadata"
)

def _pick_primary(items: list[dict] | None, key: str = "value") -> str | None:
    if not items:
        return None
    for item in items:
        if item.get("metadata", {}).get("primary"):
            return item.get(key) or item.get("formattedValue")
    first = items[0]
    return first.get(key) or first.get("formattedValue")


def normalize_people_payload(data: dict[str, Any]) -> dict[str, Any]:
    orgs = []
    for org in data.get("organizations") or []:
        orgs.append(
            {
                "name": org.get("name"),
                "title": org.get("title"),
                "department": org.get("department"),
                "type": org.get("type"),
                "current": org.get("current"),
            }
        )

    phones = [
        p.get("value") or p.get("canonicalForm")
        for p in (data.get("phoneNumbers") or [])
        if p.get("value") or p.get("canonicalForm")
    ]

    urls = [u.get("url") for u in (data.get("urls") or []) if u.get("url")]

    return {
        "display_name": _pick_primary(data.get("names"), "displayName"),
        "given_name": _pick_primary(data.get("names"), "givenName"),
        "family_name": _pick_primary(data.get("names"), "familyName"),
        "email": _pick_primary(data.get("emailAddresses"), "value"),
        "locale": _pick_primary(data.get("locales")),
        "bio": _pick_primary(data.get("biographies")),
        "organizations": orgs,
        "phone_numbers": phones[:3],
        "urls": urls[:5],
        "photo_url": _pick_primary(data.get("photos"), "url"),
    }


async def fetch_google_people_profile(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            "https://people.googleapis.com/v1/people/me",
            params={"personFields": PEOPLE_FIELDS},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 401:
            return {"status": "unauthorized", "message": "Google access token expired; re-link Google account."}
        if resp.status_code == 403:
            return {
                "status": "forbidden",
                "message": "Enable Google People API in Cloud Console and re-login with expanded scopes.",
            }
        resp.raise_for_status()
        raw = resp.json()
    return {"status": "ok", "normalized": normalize_people_payload(raw), "raw": raw}


async def enrich_google(
    user_google: dict[str, Any] | None,
    settings: Settings,
    *,
    email_domain: str | None = None,
) -> dict[str, Any]:
    """Merge OpenID profile with People API when an access or refresh token is available."""

    user_google = user_google if isinstance(user_google, dict) else {}
    oauth = dict(user_google.get("_oauth") or {})
    openid = user_google.get("openid") or user_google

    result: dict[str, Any] = {
        "openid": {
            k: openid.get(k)
            for k in (
                "sub",
                "email",
                "email_verified",
                "name",
                "given_name",
                "family_name",
                "picture",
                "locale",
                "hd",
            )
            if k in openid
        },
        "_oauth": oauth,
        "people": {
            "status": "reauth_required",
            "message": "Sign in again via “Re-link Google” to enable People API enrichment.",
        },
        "calendar": {
            "status": "reauth_required",
            "message": "Sign in again via “Re-link Google” to enable Calendar enrichment.",
        },
    }

    if not oauth.get("access_token") and not oauth.get("refresh_token"):
        return result

    access_token, oauth = await resolve_google_access_token(settings, oauth)
    result["_oauth"] = oauth

    if not access_token:
        result["people"] = {
            "status": "reauth_required",
            "message": "Missing Google refresh token. Use Re-link Google (consent) once.",
        }
        return result

    try:
        people = await fetch_google_people_profile(access_token)
        if people.get("status") == "unauthorized" and oauth.get("refresh_token"):
            refreshed = await refresh_google_access_token(settings, oauth["refresh_token"])
            if refreshed.get("ok"):
                oauth["access_token"] = refreshed["access_token"]
                if refreshed.get("expires_at"):
                    oauth["expires_at"] = refreshed["expires_at"]
                result["_oauth"] = oauth
                people = await fetch_google_people_profile(oauth["access_token"])
        result["people"] = people
    except Exception as exc:  # noqa: BLE001
        result["people"] = {"status": "error", "message": str(exc)}

    openid_email = (result.get("openid") or {}).get("email") or ""
    user_email = openid_email
    domain = (email_domain or "").strip().lower()
    if not domain and "@" in openid_email:
        domain = openid_email.split("@", 1)[1].lower()

    try:
        cal_token, oauth = await resolve_google_access_token(settings, result.get("_oauth") or oauth)
        result["_oauth"] = oauth
        result["calendar"] = await enrich_google_calendar(
            access_token=cal_token,
            oauth=oauth,
            user_email=user_email,
            user_domain=domain,
            settings=settings,
        )
    except Exception as exc:  # noqa: BLE001
        result["calendar"] = {"status": "error", "message": str(exc)}

    return result
