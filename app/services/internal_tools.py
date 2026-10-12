"""Placeholder for internal enrichment sources.

Wire each integration as a function that returns a JSON-serializable dict.
The profile builder merges these under user.internal[source_name].
"""

from typing import Any


async def enrich_from_internal_tools(*, email: str, domain: str) -> dict[str, Any]:
    # PoC stub — replace with calls to your internal APIs.
    return {
        "status": "not_configured",
        "email": email,
        "domain": domain,
        "notes": "Add internal API clients here (CRM, licensing, support desk, etc.).",
    }
