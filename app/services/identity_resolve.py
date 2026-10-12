"""Discover a full display name when Google/calendar only give an email initial."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.config import Settings
from app.models.domain import UserProfile, utc_now
from app.services.bedrock_session import bedrock_runtime_client
from app.services.identity_names import extract_person_name_from_text, known_identity
from app.services.web_search import web_search


def _company_label(domain: str) -> str:
    label = (domain or "").split(".", 1)[0]
    return label.replace("-", " ").title()


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    return json.loads(text)


def _bedrock_extract(settings: Settings, prompt: str) -> dict[str, Any]:
    model_id = settings.linkedin_lookup_model_id or settings.bedrock_model_id
    client = bedrock_runtime_client(settings)
    resp = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 400, "temperature": 0.1},
    )
    parts = resp.get("output", {}).get("message", {}).get("content") or []
    text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
    try:
        return _parse_json_object(text)
    except Exception:  # noqa: BLE001
        return {"display_name": None, "confidence": 0, "reasoning": text[:300]}


async def resolve_identity_name(settings: Settings, user: UserProfile) -> dict[str, Any]:
    """
    When identity is email-initial-only (jlewis → J Lewis), search the web for a
    full name tied to the company/domain before LinkedIn matching.

    Updates user.display_name in-place when confidence is high and the given name
    is unambiguous (matches known initial + family).
    """

    identity = known_identity(user)
    if identity.get("given_is_full"):
        return {
            "status": "already_known",
            "display_name": identity.get("display_name"),
            "known_identity": identity,
        }

    if not settings.web_search_available:
        return {"status": "not_configured", "known_identity": identity}

    family = identity.get("family")
    initial = identity.get("given_initial")
    domain = user.email_domain or ""
    company = _company_label(domain)
    email = user.email or ""
    local = email.split("@", 1)[0] if email else ""

    queries = [
        f'"{email}"',
        f'"{local}" "{company}"',
        f'"{family}" "{company}"' if family and company else "",
        f'"{family}" {domain}' if family and domain else "",
    ]
    hits: list[dict[str, Any]] = []
    errors: list[str] = []
    for q in [x for x in queries if x]:
        try:
            batch = await web_search(settings, q, linkedin_only=False)
            hits.extend(batch[:8])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{q}: {exc}")

    # Dedupe by URL/title
    seen: set[str] = set()
    unique_hits: list[dict[str, Any]] = []
    for h in hits:
        key = (h.get("url") or h.get("title") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_hits.append(h)
    unique_hits = unique_hits[:15]

    if not unique_hits:
        return {
            "status": "not_found",
            "searched_at": utc_now().isoformat(),
            "search_errors": errors,
            "known_identity": identity,
        }

    evidence = "\n".join(
        f"- {h.get('title')}: {(h.get('snippet') or '')[:220]}" for h in unique_hits
    )
    prompt = (
        "Extract the person's FULL name from search results for an email identity.\n"
        f"Email: {email}\n"
        f"Company/domain hints: {company} / {domain}\n"
        f"Known family name: {family or 'unknown'}\n"
        f"Known given-name initial: {initial or 'unknown'}\n"
        "Rules:\n"
        "- Only return a name if evidence clearly ties that person to this company/domain/email.\n"
        "- If multiple different given names fit the initial (e.g. Jeff vs John), return null.\n"
        "- Prefer legal/preferred first name + last name.\n"
        "Return JSON only:\n"
        '{"display_name": string|null, "given": string|null, "family": string|null, '
        '"confidence": 0-1, "reasoning": string}\n\n'
        f"Results:\n{evidence}\n"
    )

    try:
        extracted = await asyncio.to_thread(_bedrock_extract, settings, prompt)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "message": str(exc),
            "search_errors": errors,
            "known_identity": identity,
        }

    display = (extracted.get("display_name") or "").strip() or None
    given = (extracted.get("given") or "").strip() or None
    fam = (extracted.get("family") or "").strip() or None
    conf = float(extracted.get("confidence") or 0)

    if display and (not given or not fam):
        parsed = extract_person_name_from_text(display)
        given = given or parsed.get("given")
        fam = fam or parsed.get("family")

    accepted = False
    reason = "low_confidence_or_incomplete"
    if display and given and fam and conf >= 0.7:
        if family and fam.lower() != str(family).lower():
            reason = f"family_mismatch:{family}!={fam}"
        elif initial and given[:1].upper() != str(initial).upper():
            reason = f"initial_mismatch:{initial}!={given[0]}"
        elif len(given) < 2:
            reason = "given_too_short"
        else:
            accepted = True
            reason = "ok"

    payload: dict[str, Any] = {
        "status": "resolved" if accepted else "unresolved",
        "searched_at": utc_now().isoformat(),
        "confidence": conf,
        "extracted": extracted,
        "accept_reason": reason,
        "search_errors": errors,
        "evidence_count": len(unique_hits),
        "known_identity": identity,
    }

    if accepted and display:
        user.display_name = f"{given.title()} {fam.title()}"
        payload["display_name"] = user.display_name
        # Stash under google for audit without inventing OpenID.
        g = dict(user.google or {}) if isinstance(user.google, dict) else {}
        g["identity_resolve"] = {
            "status": "resolved",
            "display_name": user.display_name,
            "confidence": conf,
            "reasoning": extracted.get("reasoning"),
            "resolved_at": utc_now().isoformat(),
        }
        user.google = g

    return payload
