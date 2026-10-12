import json
from typing import Any

from app.config import Settings
from app.models.domain import AgencyProfile, UserProfile, utc_now
from app.services.bedrock_session import bedrock_runtime_client
from app.services.agency_context import build_agency_llm_context
from app.services.enrichment_snapshot import build_llm_context


def _fallback_summary(user: UserProfile, agency: AgencyProfile | None) -> str:
    ctx = build_llm_context(user, agency)
    google = ctx.get("google") or {}
    slack = ctx.get("slack") or {}

    lines = [
        f"**{user.display_name or user.email}**",
        f"- Email: {user.email}",
    ]
    if google.get("workspace_domain_hint"):
        lines.append(f"- Google Workspace domain: {google['workspace_domain_hint']}")
    orgs = google.get("organizations") or []
    current = next((o for o in orgs if o.get("current")), orgs[0] if orgs else None)
    if current and (current.get("title") or current.get("name")):
        lines.append(
            f"- Google org/title: {current.get('title') or '—'} @ {current.get('name') or '—'}"
        )
    if google.get("bio"):
        bio = google["bio"]
        suffix = "…" if len(bio) > 160 else ""
        lines.append(f"- Google bio: {bio[:160]}{suffix}")

    if slack:
        if slack.get("workspace"):
            lines.append(f"- Slack workspace: {slack['workspace']}")
        if slack.get("title"):
            lines.append(f"- Slack title: {slack['title']}")
        if slack.get("status"):
            lines.append(f"- Slack status: {slack['status']}")
        if slack.get("timezone"):
            lines.append(f"- Timezone: {slack['timezone']}")
        channels = slack.get("public_channels_member_sample") or []
        if channels:
            preview = ", ".join(f"#{c}" for c in channels[:12])
            extra = len(channels) - 12
            if extra > 0:
                preview += f" (+{extra} more)"
            lines.append(f"- Public channels (sample): {preview}")

    hibob = user.hibob.get("normalized") if isinstance(user.hibob, dict) else None
    if hibob:
        if hibob.get("title"):
            lines.append(f"- Role (HiBob): {hibob['title']}")
        if hibob.get("department"):
            lines.append(f"- Department (HiBob): {hibob['department']}")

    linkedin = ctx.get("linkedin") or {}
    if linkedin.get("profile_url") and linkedin.get("status") == "ok":
        lines.append("")
        lines.append("**LinkedIn (automated match)**")
        lines.append(f"- Profile: {linkedin['profile_url']} (confidence {linkedin.get('confidence')})")
        if linkedin.get("title"):
            lines.append(f"- Title signal: {linkedin['title']}")
        if linkedin.get("summary"):
            lines.append(f"- {linkedin['summary'][:300]}…" if len(linkedin.get("summary") or "") > 300 else f"- {linkedin.get('summary')}")

    kb = ctx.get("knowledge_base") or {}
    snippets = kb.get("snippets") or []
    if snippets:
        lines.append("")
        lines.append("**Knowledge base matches**")
        for snip in snippets[:5]:
            src = snip.get("source_uri") or "unknown source"
            text = (snip.get("text") or "").replace("\n", " ")
            if len(text) > 220:
                text = text[:220] + "…"
            lines.append(f"- ({snip.get('score')}) {text} [{src}]")

    if agency:
        lines.append("")
        lines.append(f"**Agency ({agency.domain})**")
        lines.append(f"- Known members in this app: {agency.member_count}")

    lines.append("")
    lines.append(
        "_Generated without Bedrock (local fallback). Connect AWS profile `concrete` for richer LLM summaries._"
    )
    return "\n".join(lines)


class SummaryService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_user_summary(self, user: UserProfile, agency: AgencyProfile | None) -> str:
        context = json.dumps(build_llm_context(user, agency), indent=2, default=str)
        work = user.work_profile if isinstance(user.work_profile, dict) else {}
        work_block = json.dumps(work, indent=2, default=str) if work else "{}"
        prompt = (
            "You are profiling someone in the Meet The People agency network. "
            "The primary goal is to explain WHAT THEY DO at work so other platforms can route the right workflows "
            "(creative leadership vs data/analytics vs account vs engineering vs general leadership).\n"
            "Using ONLY the JSON context below (including WORK_PROFILE if present), write a markdown brief "
            "(250-400 words) with sections:\n"
            "## Role in plain language\n## Function & seniority\n## What their day-to-day likely involves\n"
            "## Evidence (titles, Slack, LinkedIn, knowledge base — cite sources)\n"
            "## Suggested platform workflows\n## Confidence & gaps\n"
            "Be specific about titles and channel/topic signals. Do not invent clients or tools.\n\n"
            f"WORK_PROFILE:\n{work_block}\n\n"
            f"CONTEXT:\n{context}"
        )

        try:
            client = bedrock_runtime_client(self.settings)
            resp = client.converse(
                modelId=self.settings.bedrock_model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 900, "temperature": 0.35},
            )
            parts = resp.get("output", {}).get("message", {}).get("content") or []
            text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
            if text:
                return text
        except Exception:
            if not self.settings.llm_fallback_without_bedrock:
                raise

        return _fallback_summary(user, agency)

    def persist_user_summary(
        self, user: UserProfile, agency: AgencyProfile | None, store
    ) -> UserProfile:
        summary = self.generate_user_summary(user, agency)
        user.llm_summary = summary
        user.llm_summary_generated_at = utc_now()
        user.touch()
        store.save_user(user)
        return user

    def _fallback_agency_summary(self, store, agency: AgencyProfile) -> str:
        ctx = build_agency_llm_context(store, agency)
        lines = [
            f"**{agency.display_name or agency.domain}** (`{agency.domain}`)",
            f"- Members in app: {agency.member_count}",
        ]
        rollups = ctx.get("inferred_rollups") or {}
        for label, key in (("Departments", "top_departments"), ("Titles", "top_titles")):
            items = rollups.get(key) or []
            if items:
                lines.append(f"- {label}: " + ", ".join(f"{n} ({c})" for n, c in items[:4]))
        kb = ctx.get("knowledge_base") or {}
        for snip in (kb.get("snippets") or [])[:4]:
            text = (snip.get("text") or "").replace("\n", " ")[:200]
            lines.append(f"- KB: {text}")
        lines.append("")
        lines.append("_Agency summary fallback (Bedrock unavailable)._")
        return "\n".join(lines)

    def generate_agency_summary(self, store, agency: AgencyProfile) -> str:
        context = json.dumps(build_agency_llm_context(store, agency), indent=2, default=str)
        prompt = (
            "You are writing an internal agency/account profile for a B2B marketing or analytics company. "
            "Using ONLY the JSON context below, produce a markdown brief (250-450 words) with sections:\n"
            "## Company overview\n## Team composition (from known members)\n"
            "## Slack & operating signals\n## Knowledge base intelligence (cite sources)\n"
            "## Relationship summary\n## Gaps & recommended account research\n"
            "Synthesize across all members; do not invent clients, revenue, or headcount beyond the data.\n\n"
            f"CONTEXT:\n{context}"
        )

        try:
            client = bedrock_runtime_client(self.settings)
            resp = client.converse(
                modelId=self.settings.bedrock_model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 900, "temperature": 0.35},
            )
            parts = resp.get("output", {}).get("message", {}).get("content") or []
            text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
            if text:
                return text
        except Exception:
            if not self.settings.llm_fallback_without_bedrock:
                raise

        return self._fallback_agency_summary(store, agency)

    def persist_agency_summary(self, store, agency: AgencyProfile) -> AgencyProfile:
        summary = self.generate_agency_summary(store, agency)
        agency.llm_summary = summary
        agency.llm_summary_generated_at = utc_now()
        agency.touch()
        store.save_agency(agency)
        return agency
