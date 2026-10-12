"""Infer what someone does at their agency — structured profile for workflow routing."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import Settings
from app.models.domain import AgencyProfile, UserProfile, utc_now
from app.services.bedrock_session import bedrock_runtime_client
from app.services.enrichment_snapshot import build_llm_context
from app.services.safe_dict import as_dict
from app.services.work_profile_taxonomy import (
    AGENCY_ORIENTATIONS,
    SENIORITY_BANDS,
    SUGGESTED_WORKFLOWS,
    WORK_FUNCTIONS,
)


def _pick_title(*candidates: str | None) -> str | None:
    for c in candidates:
        if c and str(c).strip():
            return str(c).strip()
    return None


def collect_title_signals(user: UserProfile) -> list[dict[str, str]]:
    """Normalized title strings from each enrichment source."""

    signals: list[dict[str, str]] = []

    google = as_dict(user.google)
    people = as_dict(google.get("people"))
    people_norm = as_dict(people.get("normalized"))
    for org in people_norm.get("organizations") or []:
        if not isinstance(org, dict):
            continue
        title = org.get("title")
        if title:
            signals.append(
                {
                    "source": "google_people",
                    "title": str(title),
                    "org": str(org.get("name") or ""),
                    "current": str(org.get("current")),
                }
            )

    slack = as_dict(user.slack)
    enriched = as_dict(slack.get("enriched"))
    slack_user = as_dict(enriched.get("user"))
    slack_title = _pick_title(
        slack_user.get("title"),
        as_dict(enriched.get("profile_extended")).get("title"),
    )
    if slack_title:
        signals.append({"source": "slack", "title": slack_title})

    hibob = as_dict(user.hibob)
    hibob_norm = as_dict(hibob.get("normalized"))
    if hibob_norm.get("title"):
        signals.append(
            {
                "source": "hibob",
                "title": str(hibob_norm["title"]),
                "department": str(hibob_norm.get("department") or ""),
            }
        )

    linkedin = as_dict(user.linkedin)
    if linkedin.get("status") == "ok" and linkedin.get("title"):
        # Defense: never treat a name-mismatched LinkedIn title as a role signal.
        from app.services.identity_names import known_identity, names_compatible

        identity = known_identity(user)
        ok, _reason = names_compatible(identity, str(linkedin.get("title")))
        if ok and identity.get("given_is_full"):
            signals.append({"source": "linkedin", "title": str(linkedin["title"])})

    return signals


def collect_network_peer_signals(user: UserProfile, store=None) -> list[dict[str, Any]]:
    """Closest meeting partners — useful when the subject has little direct title data."""

    assoc = as_dict(user.network_associations)
    edges = assoc.get("edges") or []
    if not isinstance(edges, list):
        return []

    ranked = sorted(
        [e for e in edges if isinstance(e, dict)],
        key=lambda e: int(e.get("closeness_score") or 0),
        reverse=True,
    )[:12]

    peers: list[dict[str, Any]] = []
    for edge in ranked:
        peer_row: dict[str, Any] = {
            "email": edge.get("email"),
            "display_name": edge.get("display_name"),
            "closeness_score": edge.get("closeness_score"),
            "meeting_count": edge.get("meeting_count"),
            "other_account_kind": edge.get("other_account_kind"),
        }
        peer_id = edge.get("other_user_id")
        if store and peer_id:
            peer = store.get_user(str(peer_id))
            if peer:
                wp = as_dict(peer.work_profile)
                peer_row["peer_role_label"] = wp.get("primary_role_label")
                peer_row["peer_function"] = wp.get("function")
                peer_row["peer_seniority"] = wp.get("seniority")
        peers.append(peer_row)
    return peers


def collect_work_context(
    user: UserProfile, agency: AgencyProfile | None, store=None
) -> dict[str, Any]:
    """Slack channels, KB themes, network, and agency hints that suggest day-to-day work."""

    slack = as_dict(user.slack)
    enriched = as_dict(slack.get("enriched"))
    channels = enriched.get("public_channels") or []
    channel_names = [
        str(c.get("name"))
        for c in channels
        if isinstance(c, dict) and c.get("name")
    ][:25]

    topics = [
        {"channel": c.get("name"), "topic": c.get("topic")}
        for c in channels
        if isinstance(c, dict) and c.get("topic")
    ][:12]

    ctx = build_llm_context(user, agency)
    kb = ctx.get("knowledge_base") or {}
    kb_snippets = (kb.get("snippets") or [])[:5]

    google = as_dict(user.google)
    cal = as_dict(google.get("calendar"))
    cal_norm = as_dict(cal.get("normalized")) if cal.get("status") == "ok" else {}
    linkedin = as_dict(user.linkedin)
    network_peers = collect_network_peer_signals(user, store)
    from app.services.identity_names import known_identity, names_compatible

    identity = known_identity(user)
    linkedin_usable = False
    if linkedin.get("status") == "ok" and linkedin.get("title") and identity.get("given_is_full"):
        linkedin_usable, _ = names_compatible(identity, str(linkedin.get("title")))

    return {
        "account_kind": user.account_kind,
        "known_identity": {
            "display_name": identity.get("display_name"),
            "given": identity.get("given"),
            "family": identity.get("family"),
        },
        "title_signals": collect_title_signals(user),
        "slack_public_channels_sample": channel_names,
        "slack_channel_topics_sample": topics,
        "linkedin_status": linkedin.get("status"),
        "linkedin_title": linkedin.get("title") if linkedin_usable else None,
        "linkedin_summary_excerpt": (linkedin.get("summary") or "")[:400] if linkedin_usable else None,
        "knowledge_base_snippets": kb_snippets,
        "calendar_meeting_patterns": {
            "top_attendees": (cal_norm.get("top_attendees") or [])[:15],
            "top_attendee_domains": cal_norm.get("top_attendee_domains"),
            "meetings_with_external_domains": cal_norm.get("meetings_with_external_domains"),
            "meetings_with_same_domain": cal_norm.get("meetings_with_same_domain"),
            "unique_other_attendees": cal_norm.get("unique_other_attendees"),
        }
        if cal_norm
        else None,
        "network_associations": {
            "window_days": as_dict(user.network_associations).get("window_days"),
            "closest_peers": network_peers,
        }
        if network_peers
        else None,
        "agency_domain": agency.domain if agency else user.email_domain,
        "agency_display_name": agency.display_name if agency else None,
    }


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    return json.loads(text)


def _heuristic_work_profile(user: UserProfile, work_ctx: dict[str, Any]) -> dict[str, Any]:
    titles = " ".join(
        s.get("title", "") for s in work_ctx.get("title_signals") or []
    ).lower()
    channels = " ".join(work_ctx.get("slack_public_channels_sample") or []).lower()
    linkedin_blob = f"{work_ctx.get('linkedin_title') or ''} {work_ctx.get('linkedin_summary_excerpt') or ''}".lower()
    peers = work_ctx.get("network_associations") or {}
    peer_funcs = [
        str(p.get("peer_function") or "")
        for p in (peers.get("closest_peers") or [])
        if isinstance(p, dict)
    ]
    peer_blob = " ".join(peer_funcs).lower()
    blob = f"{titles} {channels} {linkedin_blob} {peer_blob}"

    function = "unknown"
    if any(k in blob for k in ("creative director", "art director", "copywriter", "designer", "creative")):
        function = "creative"
    elif any(k in blob for k in ("data", "analyst", "analytics", "insights", "bi ")):
        function = "data_analytics"
    elif any(k in blob for k in ("engineer", "developer", "engineering", "architect", "cto")):
        function = "technology_engineering"
    elif any(k in blob for k in ("account", "client partner", "client success")):
        function = "account_client"
    elif any(k in blob for k in ("media", "performance", "paid social", "sem", "ppc")):
        function = "media_performance"
    elif any(k in blob for k in ("strateg", "planning", "brand strategy")):
        function = "strategy"
    elif any(k in blob for k in ("ceo", "cfo", "coo", "president", "founder", "head of", "director", "vp")):
        function = "leadership_general"
    elif peer_funcs:
        # Sparse provisional: lean on closest peers' known functions
        from collections import Counter

        counts = Counter(f for f in peer_funcs if f and f != "unknown")
        if counts:
            function = counts.most_common(1)[0][0]

    seniority = "unknown"
    if "intern" in blob:
        seniority = "intern"
    elif any(k in blob for k in ("chief ", "ceo", "cfo", "cto", "coo")):
        seniority = "c_suite"
    elif "vp" in blob or "vice president" in blob:
        seniority = "vp"
    elif "director" in blob or "head of" in blob:
        seniority = "director"
    elif "manager" in blob or "lead" in blob:
        seniority = "manager"
    elif "senior" in blob:
        seniority = "senior_ic"
    elif titles.strip() or linkedin_blob.strip():
        seniority = "individual_contributor"

    primary = _pick_title(
        *(s.get("title") for s in work_ctx.get("title_signals") or []),
        work_ctx.get("linkedin_title"),
    )

    workflows: list[str] = []
    if function == "creative":
        workflows = ["creative_brief_review", "concept_development", "client_presentation"]
    elif function == "data_analytics":
        workflows = ["data_analysis", "performance_reporting", "stakeholder_updates"]
    elif function == "media_performance":
        workflows = ["media_planning", "performance_reporting", "campaign_trafficking"]
    elif function == "technology_engineering":
        workflows = ["technical_delivery", "resource_planning"]
    elif seniority in ("director", "vp", "c_suite", "manager"):
        workflows = ["team_management", "stakeholder_updates", "resource_planning"]

    has_direct = bool(primary or titles.strip() or linkedin_blob.strip())
    has_network = bool(peers.get("closest_peers"))
    confidence = 0.45 if has_direct else (0.28 if has_network else 0.15)
    if work_ctx.get("account_kind") == "provisional" and confidence > 0.4:
        confidence = 0.4

    gaps = []
    if not has_direct:
        gaps.append("No direct title from Slack/HiBob/Google/LinkedIn")
    if work_ctx.get("account_kind") == "provisional":
        gaps.append("Provisional user — no Google/Slack login yet")
    if not has_network:
        gaps.append("No calendar network associations")
    gaps.append("Confirm role with richer signals when available")

    return {
        "status": "ok",
        "method": "heuristic",
        "primary_role_label": primary,
        "function": function,
        "seniority": seniority,
        "agency_orientation": "unknown",
        "discipline_tags": [],
        "is_people_leader": seniority in ("manager", "director", "vp", "c_suite"),
        "work_focus_phrases": [],
        "suggested_workflows": workflows or ["unknown"],
        "confidence": confidence,
        "reasoning": (
            "Keyword match on titles, LinkedIn, Slack channels, and closest meeting peers "
            "(Bedrock unavailable or parse failed)."
        ),
        "evidence_gaps": gaps,
    }


def infer_work_profile(
    settings: Settings, user: UserProfile, agency: AgencyProfile | None, store=None
) -> dict[str, Any]:
    """
    Structured inference: what this person does, for routing workflows in MTP platforms.
    Works for sparse/provisional users using LinkedIn + meeting-network peers.
    """

    work_ctx = collect_work_context(user, agency, store=store)
    identity_ctx = build_llm_context(user, agency)

    prompt = (
        "You profile people who work at agencies in the Meet The People network. "
        "Goal: understand WHAT THEY DO day-to-day so other platforms can offer the right workflows "
        "(e.g. creative brief review vs data reporting vs team management).\n\n"
        "Using ONLY the JSON below, return ONLY valid JSON with these keys:\n"
        '  "primary_role_label": string (best human title, e.g. "Creative Director"),\n'
        f'  "function": one of {json.dumps(list(WORK_FUNCTIONS))},\n'
        f'  "seniority": one of {json.dumps(list(SENIORITY_BANDS))},\n'
        f'  "agency_orientation": one of {json.dumps(list(AGENCY_ORIENTATIONS))},\n'
        '  "discipline_tags": string[] (e.g. brand, performance, UX, B2B),\n'
        '  "is_people_leader": boolean,\n'
        '  "work_focus_phrases": string[] (3-8 short phrases: what they actually work on),\n'
        f'  "suggested_workflows": string[] (pick from {json.dumps(list(SUGGESTED_WORKFLOWS))}, 2-6 items),\n'
        '  "confidence": number 0-1,\n'
        '  "reasoning": string (2-4 sentences citing sources),\n'
        '  "evidence_gaps": string[] (what would improve certainty)\n'
        "Rules:\n"
        "- Prefer Slack title, then HiBob, then Google org, then LinkedIn when they conflict.\n"
        "- For provisional / sparse profiles: lean on LinkedIn + network_associations.closest_peers "
        "(closeness_score and peer_function/peer_role_label) — still use low confidence.\n"
        "- Use calendar_meeting_patterns (who they meet often, external vs same-domain) for network and segment hints.\n"
        "- Distinguish creative leadership vs data/analytics vs engineering vs account management.\n"
        "- Do not invent employers, clients, or tools not in the context.\n"
        "- Low confidence if titles are missing or contradictory; never invent high confidence.\n\n"
        f"WORK_CONTEXT:\n{json.dumps(work_ctx, indent=2, default=str)}\n\n"
        f"FULL_ENRICHMENT:\n{json.dumps(identity_ctx, indent=2, default=str)}"
    )

    try:
        client = bedrock_runtime_client(settings)
        resp = client.converse(
            modelId=settings.bedrock_model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 900, "temperature": 0.25},
        )
        parts = resp.get("output", {}).get("message", {}).get("content") or []
        raw = "".join(p.get("text", "") for p in parts if "text" in p).strip()
        parsed = _parse_json_object(raw)
        parsed["status"] = "ok"
        parsed["method"] = "bedrock"
        parsed["title_signals"] = work_ctx.get("title_signals")
        parsed["generated_at"] = utc_now().isoformat()
        if user.account_kind == "provisional" and float(parsed.get("confidence") or 0) > 0.55:
            parsed["confidence"] = 0.55
        return parsed
    except Exception as exc:  # noqa: BLE001
        fallback = _heuristic_work_profile(user, work_ctx)
        fallback["bedrock_error"] = str(exc)
        fallback["title_signals"] = work_ctx.get("title_signals")
        fallback["generated_at"] = utc_now().isoformat()
        return fallback


def persist_work_profile(
    settings: Settings, user: UserProfile, agency: AgencyProfile | None, store
) -> UserProfile:
    user.work_profile = infer_work_profile(settings, user, agency, store=store)
    user.work_profile_generated_at = utc_now()
    user.touch()
    store.save_user(user)
    return user
