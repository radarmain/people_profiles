import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import Settings

LINKEDIN_IN_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)?linkedin\.com/in/[a-zA-Z0-9_-]+/?",
    re.IGNORECASE,
)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source_query: str


@dataclass
class LinkedInCandidate:
    profile_url: str
    title: str = ""
    snippets: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)

    def merged_text(self) -> str:
        return " ".join([self.title, *self.snippets]).strip()


def normalize_linkedin_profile_url(url: str) -> str | None:
    match = LINKEDIN_IN_PATTERN.search(url)
    if not match:
        return None
    raw = match.group(0).rstrip("/")
    slug = raw.rsplit("/", 1)[-1]
    return f"https://www.linkedin.com/in/{slug}"


def extract_linkedin_candidates(results: list[SearchResult]) -> list[LinkedInCandidate]:
    by_url: dict[str, LinkedInCandidate] = {}
    for result in results:
        normalized = normalize_linkedin_profile_url(result.url)
        if not normalized:
            for found in LINKEDIN_IN_PATTERN.findall(result.snippet):
                normalized = normalize_linkedin_profile_url(found)
                if normalized:
                    break
        if not normalized:
            continue

        candidate = by_url.get(normalized)
        if not candidate:
            candidate = LinkedInCandidate(profile_url=normalized, title=result.title)
            by_url[normalized] = candidate
        if result.snippet and result.snippet not in candidate.snippets:
            candidate.snippets.append(result.snippet)
        if result.title and not candidate.title:
            candidate.title = result.title
        if result.url not in candidate.source_urls:
            candidate.source_urls.append(result.url)
    return list(by_url.values())


async def _search_tavily(
    settings: Settings, query: str, *, max_results: int, linkedin_only: bool
) -> list[SearchResult]:
    payload: dict[str, Any] = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
    }
    if linkedin_only:
        payload["include_domains"] = ["linkedin.com"]

    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post("https://api.tavily.com/search", json=payload)
        resp.raise_for_status()
        data = resp.json()

    out: list[SearchResult] = []
    for item in data.get("results") or []:
        out.append(
            SearchResult(
                title=item.get("title") or "",
                url=item.get("url") or "",
                snippet=item.get("content") or "",
                source_query=query,
            )
        )
    return out


def _search_duckduckgo_sync(query: str, *, max_results: int) -> list[SearchResult]:
    try:
        from duckduckgo_search import DDGS
    except ImportError as exc:
        raise RuntimeError("Install duckduckgo-search or configure TAVILY_API_KEY") from exc

    out: list[SearchResult] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            out.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=item.get("href") or "",
                    snippet=item.get("body") or "",
                    source_query=query,
                )
            )
    return out


async def web_search(
    settings: Settings,
    query: str,
    *,
    max_results: int | None = None,
    linkedin_only: bool = False,
) -> list[SearchResult]:
    limit = max_results or settings.web_search_max_results
    provider = settings.web_search_provider.lower().strip()

    if provider in ("auto", "tavily") and settings.tavily_api_key:
        return await _search_tavily(settings, query, max_results=limit, linkedin_only=linkedin_only)

    if provider == "tavily" and not settings.tavily_api_key:
        raise RuntimeError("WEB_SEARCH_PROVIDER=tavily but TAVILY_API_KEY is not set")

    import asyncio

    return await asyncio.to_thread(_search_duckduckgo_sync, query, max_results=limit)
