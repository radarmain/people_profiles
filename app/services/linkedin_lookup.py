import asyncio
import json
import re
from typing import Any

from app.config import Settings
from app.models.domain import UserProfile, utc_now
from app.services.bedrock_session import bedrock_runtime_client
from app.services.enrichment_snapshot import build_llm_context
from app.services.identity_names import ensure_display_name, known_identity, names_compatible
from app.services.web_search import LinkedInCandidate, extract_linkedin_candidates, web_search


def _company_label_from_domain(domain: str) -> str:
    label = domain.split(".", 1)[0]
    return label.replace("-", " ").title()


def build_linkedin_search_queries_for_user(user: UserProfile, settings: Settings) -> list[tuple[str, bool]]:
    """Return (query, linkedin_only) pairs."""
    ensure_display_name(user)
    identity = known_identity(user)
    queries = []
    name = identity.get("display_name") or user.display_name or ""
    given = identity.get("given")
    family = identity.get("family")
    domain = user.email_domain
    company = _company_label_from_domain(domain) if domain else ""
    local_part = user.email.split("@", 1)[0] if user.email else ""

    slack_title = None
    if user.slack_connected and isinstance(user.slack, dict):
        enriched = user.slack.get("enriched") or {}
        slack_user = enriched.get("user") or {}
        slack_title = slack_user.get("title")

    # Prefer full legal/display name when known (Google / calendar).
    if given and family and company:
        queries.append((f'site:linkedin.com/in "{given} {family}" "{company}"', True))
    if name and company:
        queries.append((f'site:linkedin.com/in "{name}" "{company}"', True))
    if name and domain:
        queries.append((f'site:linkedin.com/in "{name}" {domain}', True))
    if name and slack_title:
        queries.append((f'site:linkedin.com/in "{name}" "{slack_title}"', True))
    if name:
        queries.append((f'"{name}" {company} linkedin profile', False))
    # Last-name + company when we only have initial+last from email (avoid fuzzy local-part matches).
    if family and company and not given:
        queries.append((f'site:linkedin.com/in "{family}" "{company}"', True))
        queries.append((f'site:linkedin.com/in "{family}" {domain}', True))
    elif local_part and domain and given:
        queries.append((f'"{local_part}" {domain} site:linkedin.com/in', True))

    seen: set[str] = set()
    unique: list[tuple[str, bool]] = []
    for q, li in queries:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append((q, li))
    return unique[: settings.linkedin_lookup_max_search_queries]


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    return json.loads(text)


def _bedrock_text(settings: Settings, prompt: str, *, max_tokens: int = 700) -> str:
    model_id = settings.linkedin_lookup_model_id or settings.bedrock_model_id
    client = bedrock_runtime_client(settings)
    resp = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
    )
    parts = resp.get("output", {}).get("message", {}).get("content") or []
    return "".join(p.get("text", "") for p in parts if "text" in p).strip()


def _heuristic_disambiguation(
    user: UserProfile, candidates: list[LinkedInCandidate]
) -> dict[str, Any]:
    identity = known_identity(user)
    name = (identity.get("display_name") or user.display_name or "").lower()
    domain = (user.email_domain or "").lower()
    company_token = domain.split(".", 1)[0] if domain else ""

    best: LinkedInCandidate | None = None
    best_score = 0.0
    for candidate in candidates:
        ok, _reason = names_compatible(identity, candidate.title or candidate.merged_text())
        if not ok:
            continue
        text = candidate.merged_text().lower()
        score = 0.0
        if name and name in text:
            score += 0.45
        for part in name.split():
            if len(part) > 2 and part in text:
                score += 0.15
        if company_token and company_token in text:
            score += 0.25
        if domain and domain in text:
            score += 0.2
        if score > best_score:
            best_score = score
            best = candidate

    confidence = min(best_score, 0.85)
    if identity.get("given_is_full") is False and identity.get("given_initial"):
        confidence = min(confidence, 0.5)
    return {
        "selected_profile_url": best.profile_url if best else None,
        "confidence": confidence,
        "reasoning": "Heuristic name/company match on search snippets (Bedrock unavailable).",
        "method": "heuristic",
        "known_identity": {
            "display_name": identity.get("display_name"),
            "given": identity.get("given"),
            "family": identity.get("family"),
        },
    }


def _llm_disambiguation(
    settings: Settings, user: UserProfile, candidates: list[LinkedInCandidate], agency
) -> dict[str, Any]:
    context = build_llm_context(user, agency)
    candidate_payload = [
        {
            "profile_url": c.profile_url,
            "title": c.title,
            "snippets": c.snippets[:4],
        }
        for c in candidates
    ]
    identity = known_identity(user)
    prompt = (
        "You match a professional to the correct LinkedIn profile using ONLY the evidence below.\n"
        "The person's known identity (Google/display name) is authoritative for first/last name.\n"
        "LinkedIn search snippets are trusted for employer when names already match.\n"
        "Return ONLY valid JSON with keys:\n"
        '  "selected_profile_url": string or null,\n'
        '  "confidence": number between 0 and 1,\n'
        '  "reasoning": short string\n'
        "Rules:\n"
        "- NEVER pick a profile whose first name conflicts with KNOWN_IDENTITY.given "
        "(e.g. known Jeff → reject John Lewis).\n"
        "- If KNOWN_IDENTITY.given is null and only a given_initial is known, pick null "
        "(name is ambiguous — Jeff vs John).\n"
        "- Pick null with low confidence if multiple people share the name or employer evidence is weak.\n"
        "- Do not invent URLs.\n"
        "- Prefer profiles whose snippets mention the employer/domain or Slack title.\n\n"
        f"KNOWN_IDENTITY:\n{json.dumps(identity, indent=2, default=str)}\n\n"
        f"KNOWN_USER:\n{json.dumps(context, indent=2, default=str)}\n\n"
        f"CANDIDATES:\n{json.dumps(candidate_payload, indent=2, default=str)}"
    )
    try:
        raw = _bedrock_text(settings, prompt, max_tokens=500)
        parsed = _parse_json_object(raw)
        parsed["method"] = "bedrock"
        return parsed
    except Exception as exc:  # noqa: BLE001
        fallback = _heuristic_disambiguation(user, candidates)
        fallback["bedrock_error"] = str(exc)
        return fallback


def _llm_profile_summary(
    settings: Settings,
    user: UserProfile,
    selected: LinkedInCandidate,
    disambiguation: dict[str, Any],
    agency,
) -> str:
    context = build_llm_context(user, agency)
    prompt = (
        "Write a short markdown summary (80-140 words) of this person's likely professional background "
        "for an internal CRM profile. Use ONLY the JSON context and LinkedIn search snippets below. "
        "Do not invent employers, degrees, or roles not supported by snippets. "
        "If something is uncertain, say so briefly.\n\n"
        f"USER_CONTEXT:\n{json.dumps(context, indent=2, default=str)}\n\n"
        f"SELECTED_LINKEDIN:\n{json.dumps({'url': selected.profile_url, 'title': selected.title, 'snippets': selected.snippets}, indent=2)}\n\n"
        f"MATCH_REASONING:\n{disambiguation.get('reasoning', '')}"
    )
    return _bedrock_text(settings, prompt, max_tokens=350)


async def _collect_candidates(settings: Settings, user: UserProfile) -> tuple[list[LinkedInCandidate], list[str]]:
    queries = build_linkedin_search_queries_for_user(user, settings)
    all_results = []
    errors: list[str] = []
    for query, linkedin_only in queries:
        try:
            hits = await web_search(settings, query, linkedin_only=linkedin_only)
            all_results.extend(hits)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{query}: {exc}")

    candidates = extract_linkedin_candidates(all_results)
    if len(candidates) > settings.linkedin_lookup_max_candidates:
        candidates = candidates[: settings.linkedin_lookup_max_candidates]
    return candidates, errors


async def enrich_linkedin(settings: Settings, user: UserProfile, agency) -> dict[str, Any]:
    if not settings.linkedin_lookup_enabled:
        return {"status": "disabled"}

    if not settings.web_search_available:
        return {
            "status": "not_configured",
            "message": "Set TAVILY_API_KEY or install duckduckgo-search for web lookup.",
        }

    ensure_display_name(user)
    identity = known_identity(user)

    candidates, search_errors = await _collect_candidates(settings, user)
    if not candidates:
        return {
            "status": "not_found",
            "searched_at": utc_now().isoformat(),
            "search_errors": search_errors,
            "candidates": [],
            "known_identity": identity,
        }

    # Drop candidates whose name clearly conflicts before LLM scoring.
    compatible: list[LinkedInCandidate] = []
    rejected: list[dict[str, str]] = []
    for c in candidates:
        ok, reason = names_compatible(identity, c.title or c.merged_text())
        if ok:
            compatible.append(c)
        else:
            rejected.append({"profile_url": c.profile_url, "title": c.title or "", "reason": reason})

    pool = compatible or []
    if not pool:
        return {
            "status": "name_mismatch",
            "searched_at": utc_now().isoformat(),
            "message": "All LinkedIn candidates conflicted with the known name (or name is only an email initial).",
            "search_errors": search_errors,
            "rejected_candidates": rejected[:10],
            "candidates": [
                {"profile_url": c.profile_url, "title": c.title, "snippets": c.snippets[:2]}
                for c in candidates
            ],
            "known_identity": identity,
        }

    disambiguation = await asyncio.to_thread(_llm_disambiguation, settings, user, pool, agency)
    confidence = float(disambiguation.get("confidence") or 0)
    selected_url = disambiguation.get("selected_profile_url")
    selected = next((c for c in pool if c.profile_url == selected_url), None)

    # Hard gate again on the LLM's choice.
    if selected:
        ok, reason = names_compatible(identity, selected.title or selected.merged_text())
        if not ok:
            selected = None
            confidence = 0.0
            disambiguation = {
                **disambiguation,
                "selected_profile_url": None,
                "confidence": 0.0,
                "name_gate": reason,
                "reasoning": f"Rejected LLM pick: {reason}. {(disambiguation.get('reasoning') or '')}",
            }

    # Email-initial-only identity (jlewis → J Lewis): never auto-accept as ok.
    if not identity.get("given_is_full"):
        confidence = min(confidence, 0.5)

    payload: dict[str, Any] = {
        "status": "ok",
        "searched_at": utc_now().isoformat(),
        "confidence": confidence,
        "min_confidence_threshold": settings.linkedin_lookup_min_confidence,
        "disambiguation": disambiguation,
        "search_errors": search_errors,
        "rejected_candidates": rejected[:10],
        "known_identity": identity,
        "candidates": [
            {
                "profile_url": c.profile_url,
                "title": c.title,
                "snippets": c.snippets[:3],
            }
            for c in pool
        ],
    }

    if not selected or confidence < settings.linkedin_lookup_min_confidence:
        payload["status"] = "low_confidence"
        payload["profile_url"] = selected_url if selected else None
        if not identity.get("given_is_full"):
            payload["message"] = (
                "Full first name unknown (email initial only). "
                "Set display name or wait for Google login before accepting a LinkedIn match."
            )
        return payload

    payload["profile_url"] = selected.profile_url
    payload["title"] = selected.title
    try:
        payload["summary"] = await asyncio.to_thread(
            _llm_profile_summary, settings, user, selected, disambiguation, agency
        )
    except Exception as exc:  # noqa: BLE001
        payload["summary"] = selected.merged_text()[:600]
        payload["summary_error"] = str(exc)

    return payload
