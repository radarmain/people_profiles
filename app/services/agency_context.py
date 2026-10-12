from typing import Any

from app.models.domain import AgencyProfile, UserProfile
from app.storage.base import ProfileStore


def _member_snapshot(member: UserProfile) -> dict[str, Any]:
    slack_enriched = (member.slack.get("enriched") if isinstance(member.slack, dict) else None) or {}
    slack_user = slack_enriched.get("user") or {}
    hibob_raw = member.hibob if isinstance(member.hibob, dict) else {}
    hibob = hibob_raw.get("normalized")
    linkedin = member.linkedin if isinstance(member.linkedin, dict) else None
    linkedin = linkedin or {}

    kb_snippets = []
    kb_norm = (member.knowledge_base or {}).get("normalized") or {}
    for chunk in (kb_norm.get("top_chunks") or [])[:3]:
        kb_snippets.append(
            {
                "score": chunk.get("score"),
                "text": (chunk.get("text") or "")[:400],
                "source_uri": chunk.get("source_uri"),
            }
        )

    return {
        "user_id": member.user_id,
        "email": member.email,
        "display_name": member.display_name,
        "slack_title": slack_user.get("title"),
        "slack_workspace": (slack_enriched.get("team") or {}).get("name"),
        "hibob_title": hibob.get("title") if hibob else None,
        "hibob_department": hibob.get("department") if hibob else None,
        "linkedin_url": linkedin.get("profile_url") if linkedin.get("status") == "ok" else None,
        "linkedin_summary": linkedin.get("summary") if linkedin.get("status") == "ok" else None,
        "user_summary_excerpt": (member.llm_summary or "")[:500] if member.llm_summary else None,
        "knowledge_base_snippets": kb_snippets,
    }


def build_agency_llm_context(store: ProfileStore, agency: AgencyProfile) -> dict[str, Any]:
    members = []
    for uid in agency.member_user_ids:
        member = store.get_user(uid)
        if member:
            members.append(_member_snapshot(member))

    kb = agency.knowledge_base or {}
    kb_snap = None
    if kb and kb.get("status") not in (None, "not_configured"):
        normalized = kb.get("normalized") or {}
        kb_snap = {
            "status": kb.get("status"),
            "queries": kb.get("queries"),
            "snippets": [
                {
                    "score": c.get("score"),
                    "text": (c.get("text") or "")[:400],
                    "source_uri": c.get("source_uri"),
                }
                for c in (normalized.get("top_chunks") or [])[:8]
            ],
        }

    return {
        "agency_id": agency.agency_id,
        "domain": agency.domain,
        "display_name": agency.display_name,
        "member_count": agency.member_count,
        "inferred_rollups": agency.inferred,
        "members": members,
        "knowledge_base": kb_snap,
    }
