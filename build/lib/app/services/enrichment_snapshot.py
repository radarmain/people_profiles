"""Compact, LLM-safe view of enriched profile data (no OAuth secrets)."""

from typing import Any

from app.models.domain import AgencyProfile, UserProfile
from app.services.safe_dict import as_dict


def _google_snapshot(google: dict[str, Any] | None) -> dict[str, Any]:
    google = as_dict(google)
    openid = google.get("openid") or google
    people_block = google.get("people") or {}
    people_norm = people_block.get("normalized") if isinstance(people_block, dict) else None

    snap: dict[str, Any] = {
        "email": openid.get("email"),
        "name": openid.get("name"),
        "locale": openid.get("locale"),
        "workspace_domain_hint": openid.get("hd"),
    }
    if people_norm:
        snap["organizations"] = people_norm.get("organizations")
        snap["bio"] = people_norm.get("bio")
        snap["phone_numbers"] = people_norm.get("phone_numbers")
        snap["urls"] = people_norm.get("urls")
    elif isinstance(people_block, dict):
        status = people_block.get("status")
        if status not in (None, "ok", "no_token", "reauth_required"):
            snap["people_api_note"] = people_block.get("message") or status

    calendar_block = google.get("calendar") or {}
    if isinstance(calendar_block, dict) and calendar_block.get("status") == "ok":
        cal_norm = calendar_block.get("normalized") or {}
        snap["calendar"] = {
            "lookback_days": (calendar_block.get("window") or {}).get("lookback_days"),
            "events_with_other_attendees": cal_norm.get("events_with_other_attendees"),
            "unique_other_attendees": cal_norm.get("unique_other_attendees"),
            "meetings_with_external_domains": cal_norm.get("meetings_with_external_domains"),
            "meetings_with_same_domain": cal_norm.get("meetings_with_same_domain"),
            "top_attendees": (cal_norm.get("top_attendees") or [])[:12],
            "mtp_connection_edges": (cal_norm.get("mtp_connection_edges") or [])[:12],
            "top_attendee_domains": cal_norm.get("top_attendee_domains"),
        }
    elif isinstance(calendar_block, dict) and calendar_block.get("status") not in (
        None,
        "not_configured",
        "reauth_required",
    ):
        snap["calendar_note"] = calendar_block.get("message") or calendar_block.get("status")
    return snap


def _slack_snapshot(slack: dict[str, Any] | None) -> dict[str, Any]:
    slack = as_dict(slack)
    enriched = as_dict(slack.get("enriched"))
    user = enriched.get("user") or {}
    team = enriched.get("team") or {}
    channels = enriched.get("public_channels") or []

    channel_names = [c.get("name") for c in channels if c.get("name")]
    topics = [
        {"channel": c.get("name"), "topic": c.get("topic")}
        for c in channels
        if c.get("topic")
    ][:8]

    return {
        "workspace": team.get("name"),
        "workspace_domain": team.get("domain") or team.get("email_domain"),
        "display_name": user.get("display_name") or user.get("real_name"),
        "title": user.get("title") or (enriched.get("profile_extended") or {}).get("title"),
        "status": user.get("status_text"),
        "timezone": user.get("timezone") or user.get("timezone_label"),
        "is_admin": user.get("is_admin"),
        "public_channels_member_sample": channel_names[:20],
        "channel_topics_sample": topics,
        "channel_stats": enriched.get("public_channel_stats"),
        "enrichment_errors": enriched.get("errors"),
    }


def _knowledge_base_snapshot(kb: dict[str, Any] | None) -> dict[str, Any] | None:
    kb = as_dict(kb)
    if not kb or kb.get("status") == "not_configured":
        return None
    normalized = kb.get("normalized") or {}
    chunks = normalized.get("top_chunks") or []
    return {
        "status": kb.get("status"),
        "queries": kb.get("queries"),
        "errors": kb.get("errors"),
        "snippets": [
            {
                "score": c.get("score"),
                "text": c.get("text"),
                "source_uri": c.get("source_uri"),
                "metadata": c.get("metadata"),
                "matched_queries": c.get("matched_queries"),
            }
            for c in chunks
        ],
    }


def _linkedin_snapshot(linkedin: dict[str, Any] | None) -> dict[str, Any] | None:
    linkedin = as_dict(linkedin)
    if not linkedin or linkedin.get("status") in ("disabled", "not_configured"):
        return None
    return {
        "status": linkedin.get("status"),
        "confidence": linkedin.get("confidence"),
        "profile_url": linkedin.get("profile_url"),
        "title": linkedin.get("title"),
        "summary": linkedin.get("summary"),
        "disambiguation_reasoning": (linkedin.get("disambiguation") or {}).get("reasoning"),
    }


def build_llm_context(user: UserProfile, agency: AgencyProfile | None) -> dict[str, Any]:
    hibob = as_dict(user.hibob)
    payload: dict[str, Any] = {
        "identity": {
            "email": user.email,
            "display_name": user.display_name,
            "email_domain": user.email_domain,
        },
        "google": _google_snapshot(user.google),
        "slack": _slack_snapshot(user.slack) if user.slack_connected else None,
        "hibob": hibob.get("normalized"),
        "hibob_status": hibob.get("status"),
        "internal": as_dict(user.internal),
        "knowledge_base": _knowledge_base_snapshot(user.knowledge_base),
        "linkedin": _linkedin_snapshot(user.linkedin),
        "agency": None,
    }
    if agency:
        payload["agency"] = {
            "domain": agency.domain,
            "display_name": agency.display_name,
            "member_count": agency.member_count,
            "inferred": agency.inferred,
        }
    return payload
