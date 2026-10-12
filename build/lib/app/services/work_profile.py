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
        signals.append({"source": "linkedin", "title": str(linkedin["title"])})

    return signals


def collect_work_context(user: UserProfile, agency: AgencyProfile | None) -> dict[str, Any]:
    """Slack channels, KB themes, and agency hints that suggest day-to-day work."""

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

    return {
        "title_signals": collect_title_signals(user),
        "slack_public_channels_sample": channel_names,
        "slack_channel_topics_sample": topics,
        "linkedin_summary_excerpt": (as_dict(user.linkedin).get("summary") or "")[:400],
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
    blob = f"{titles} {channels}"

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
    elif titles.strip():
        seniority = "individual_contributor"

    primary = _pick_title(*(s.get("title") for s in work_ctx.get("title_signals") or []))

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
        "confidence": 0.45 if primary else 0.2,
        "reasoning": "Keyword match on titles and Slack channel names (Bedrock unavailable or parse failed).",
        "evidence_gaps": ["Confirm role with richer Slack/HiBob/LinkedIn signals"],
    }


def infer_work_profile(
    settings: Settings, user: UserProfile, agency: AgencyProfile | None
) -> dict[str, Any]:
    """
    Structured inference: what this person does, for routing workflows in MTP platforms.
    """

    work_ctx = collect_work_context(user, agency)
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
        "- Use calendar_meeting_patterns (who they meet often, external vs same-domain) for network and segment hints.\n"
        "- Distinguish creative leadership vs data/analytics vs engineering vs account management.\n"
        "- Do not invent employers, clients, or tools not in the context.\n"
        "- Low confidence if titles are missing or contradictory.\n\n"
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
    user.work_profile = infer_work_profile(settings, user, agency)
    user.work_profile_generated_at = utc_now()
    user.touch()
    store.save_user(user)
    return user
