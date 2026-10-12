import hashlib
from typing import Any

from botocore.exceptions import ClientError

from app.config import Settings
from app.models.domain import AgencyProfile, UserProfile
from app.services.bedrock_session import bedrock_agent_runtime_client
from app.services.safe_dict import as_dict


def _dedupe_queries(queries: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        normalized = " ".join(q.split()).strip()
        if len(normalized) < 3:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
        if len(out) >= limit:
            break
    return out


def build_retrieval_queries(user: UserProfile) -> list[str]:
    """Search phrases likely to match internal docs about this person or their agency."""

    queries: list[str] = []
    if user.email:
        queries.append(user.email)
    if user.display_name:
        queries.append(user.display_name)
    if user.display_name and user.email_domain:
        queries.append(f"{user.display_name} {user.email_domain}")

    hibob = as_dict(user.hibob.get("normalized") if isinstance(user.hibob, dict) else None)
    if hibob:
        title = hibob.get("title")
        if title and user.display_name:
            queries.append(f"{user.display_name} {title}")
        if hibob.get("department"):
            queries.append(f"{user.email_domain} {hibob['department']}")

    slack_enriched = as_dict(user.slack.get("enriched") if isinstance(user.slack, dict) else None)
    if slack_enriched:
        slack_user = as_dict(slack_enriched.get("user"))
        slack_title = slack_user.get("title")
        if slack_title and user.display_name:
            queries.append(f"{user.display_name} {slack_title}")
        team = as_dict(slack_enriched.get("team"))
        if team.get("name"):
            queries.append(f"{team['name']} {user.email_domain}")

    if user.email_domain:
        queries.append(f"agency client {user.email_domain}")

    return queries


def _chunk_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _normalize_result_item(item: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"score": None, "text": "", "source_uri": None, "metadata": {}}
    content = item.get("content") or {}
    text = (content.get("text") or "").strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "…"

    location = item.get("location") or {}
    s3_loc = location.get("s3Location") or {}
    source_uri = s3_loc.get("uri")
    if not source_uri:
        source_uri = (location.get("webLocation") or {}).get("url")

    metadata = item.get("metadata") or {}
    return {
        "score": item.get("score"),
        "text": text,
        "source_uri": source_uri,
        "metadata": metadata,
    }


def _retrieval_configuration(settings: Settings, *, mode: str) -> dict[str, Any]:
    n = settings.bedrock_kb_number_of_results
    if mode == "vector":
        return {"vectorSearchConfiguration": {"numberOfResults": n}}
    return {"managedSearchConfiguration": {"numberOfResults": n}}


def _search_modes(settings: Settings) -> list[str]:
    mode = (settings.bedrock_kb_search_mode or "managed").strip().lower()
    if mode == "auto":
        return ["managed", "vector"]
    if mode in ("managed", "vector"):
        return [mode]
    return ["managed"]


def _retrieve_sync(settings: Settings, query: str) -> dict[str, Any]:
    client = bedrock_agent_runtime_client(settings)
    modes = _search_modes(settings)
    last_error: Exception | None = None
    used_mode: str | None = None
    resp: dict[str, Any] | None = None

    for mode in modes:
        try:
            resp = client.retrieve(
                knowledgeBaseId=settings.bedrock_knowledge_base_id,
                retrievalQuery={"text": query},
                retrievalConfiguration=_retrieval_configuration(settings, mode=mode),
            )
            used_mode = mode
            break
        except ClientError as exc:
            last_error = exc
            message = str(exc)
            incompatible = "Incompatible configuration" in message
            if incompatible and mode != modes[-1]:
                continue
            raise

    if resp is None:
        assert last_error is not None
        raise last_error

    raw_results = resp.get("retrievalResults") or []
    chunks = [
        _normalize_result_item(item, max_chars=settings.bedrock_kb_max_chunk_chars)
        for item in raw_results
    ]
    return {
        "query": query,
        "chunks": chunks,
        "result_count": len(chunks),
        "search_mode": used_mode,
    }


def build_agency_retrieval_queries(agency: AgencyProfile) -> list[str]:
    queries: list[str] = [
        agency.domain,
        f"agency client {agency.domain}",
    ]
    if agency.display_name:
        queries.append(f'"{agency.display_name}" company profile')
        queries.append(f"{agency.display_name} {agency.domain}")
    return queries


def _run_retrieval_queries(settings: Settings, queries: list[str]) -> dict[str, Any]:
    query_runs: list[dict[str, Any]] = []
    errors: list[str] = []
    merged: dict[str, dict[str, Any]] = {}

    for query in queries:
        try:
            run = _retrieve_sync(settings, query)
            query_runs.append(run)
            for chunk in run["chunks"]:
                fp = _chunk_fingerprint(chunk.get("text") or "")
                existing = merged.get(fp)
                if not existing or (chunk.get("score") or 0) > (existing.get("score") or 0):
                    merged[fp] = {**chunk, "matched_queries": [query]}
                elif query not in existing.get("matched_queries", []):
                    existing.setdefault("matched_queries", []).append(query)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{query}: {exc}")

    ranked = sorted(
        merged.values(),
        key=lambda c: c.get("score") or 0,
        reverse=True,
    )[: settings.bedrock_kb_max_merged_results]

    status = "ok"
    if errors and not ranked:
        status = "error"
    elif errors:
        status = "partial"

    search_mode = settings.bedrock_kb_search_mode
    if query_runs and query_runs[0].get("search_mode"):
        search_mode = query_runs[0]["search_mode"]

    return {
        "status": status,
        "knowledge_base_id": settings.bedrock_knowledge_base_id,
        "region": settings.bedrock_kb_region,
        "search_mode": search_mode,
        "queries": queries,
        "query_runs": query_runs,
        "errors": errors,
        "normalized": {
            "top_chunks": ranked,
            "unique_chunk_count": len(merged),
        },
    }


def retrieve_for_user(settings: Settings, user: UserProfile) -> dict[str, Any]:
    if not settings.bedrock_kb_configured:
        return {"status": "not_configured"}

    queries = _dedupe_queries(
        build_retrieval_queries(user),
        limit=settings.bedrock_kb_max_queries,
    )
    if not queries:
        return {"status": "skipped", "message": "No search queries could be built for this user."}

    return _run_retrieval_queries(settings, queries)


def retrieve_for_agency(settings: Settings, agency: AgencyProfile) -> dict[str, Any]:
    if not settings.bedrock_kb_configured:
        return {"status": "not_configured"}

    queries = _dedupe_queries(
        build_agency_retrieval_queries(agency),
        limit=settings.bedrock_kb_max_queries,
    )
    if not queries:
        return {"status": "skipped", "message": "No agency search queries could be built."}

    return _run_retrieval_queries(settings, queries)
