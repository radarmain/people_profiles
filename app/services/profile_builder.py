import asyncio

from app.config import Settings
from app.services.bedrock_knowledge_base import retrieve_for_user
from app.models.domain import UserProfile
from app.services.agency import ensure_user_agency
from app.services.calendar_network_sync import sync_calendar_network
from app.services.google_enrichment import enrich_google
from app.services.hibob import HiBobClient
from app.services.core_profiles import seed_user_from_core_profile
from app.services.identity_resolve import resolve_identity_name
from app.services.linkedin_lookup import enrich_linkedin
from app.services.internal_tools import enrich_from_internal_tools
from app.services.safe_dict import as_dict, normalize_user_blobs
from app.services.slack_enrichment import enrich_slack
from app.storage.base import ProfileStore


def _slack_credentials(slack: dict | None) -> tuple[str | None, str | None]:
    slack = as_dict(slack)
    oauth = slack.get("_oauth") or {}
    token = oauth.get("user_access_token")
    user_id = oauth.get("user_id")
    if token and user_id:
        return token, user_id

    legacy = slack.get("oauth") or {}
    authed = legacy.get("authed_user") or {}
    return authed.get("access_token"), authed.get("id")


async def refresh_slack_enrichment(user: UserProfile) -> None:
    user.slack = as_dict(user.slack)
    token, slack_user_id = _slack_credentials(user.slack)
    if not token or not slack_user_id:
        if not isinstance(user.slack.get("enriched"), dict):
            user.slack["enriched"] = {}
        user.slack["enriched"]["status"] = "missing_token_reconnect_slack"
        return
    user.slack["enriched"] = await enrich_slack(access_token=token, slack_user_id=slack_user_id)


async def _enrich_shared_sources(store: ProfileStore, settings: Settings, user: UserProfile) -> None:
    """HiBob, internal tools, KB, LinkedIn — available with or without Google OAuth."""

    internal = await enrich_from_internal_tools(email=user.email, domain=user.email_domain)
    user.internal = {"tools": internal}

    if store.get_core_profile_by_email(user.email):
        seed_user_from_core_profile(store, user)
    else:
        hibob_client = HiBobClient(settings)
        if hibob_client.enabled:
            try:
                hibob_data = await hibob_client.find_by_email(user.email)
                user.hibob = hibob_data or {"status": "not_found"}
            except Exception as exc:  # noqa: BLE001 — PoC: capture vendor errors on profile
                user.hibob = {"status": "error", "message": str(exc)}
        else:
            user.hibob = {"status": "not_configured"}

    if settings.bedrock_kb_configured:
        try:
            user.knowledge_base = await asyncio.to_thread(retrieve_for_user, settings, user)
        except Exception as exc:  # noqa: BLE001
            user.knowledge_base = {"status": "error", "message": str(exc)}
    else:
        user.knowledge_base = {"status": "not_configured"}

    agency = store.get_agency(user.agency_id) if user.agency_id else None
    # Resolve full name before LinkedIn so Jeff≠John style mismatches are gated.
    try:
        await resolve_identity_name(settings, user)
    except Exception:  # noqa: BLE001
        pass
    try:
        user.linkedin = await enrich_linkedin(settings, user, agency)
    except Exception as exc:  # noqa: BLE001
        user.linkedin = {"status": "error", "message": str(exc)}


async def refresh_user_profile(store: ProfileStore, settings: Settings, user: UserProfile) -> UserProfile:
    normalize_user_blobs(user)

    if user.account_kind == "provisional":
        # No Google/Slack tokens — baseline enrich only.
        await _enrich_shared_sources(store, settings, user)
        user.touch()
        store.save_user(user)
        ensure_user_agency(store, user)
        return user

    user.google = await enrich_google(user.google, settings, email_domain=user.email_domain)
    store.save_user(user)

    user = await sync_calendar_network(store, settings, user)
    user = store.get_user(user.user_id) or user

    if user.slack_connected:
        await refresh_slack_enrichment(user)

    await _enrich_shared_sources(store, settings, user)

    user.touch()
    store.save_user(user)
    ensure_user_agency(store, user)
    return user
