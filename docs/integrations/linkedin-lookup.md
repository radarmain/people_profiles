# LinkedIn lookup

## Purpose

Discover a likely LinkedIn `/in/...` profile **without** a known username, using web search and Bedrock disambiguation.

Code:

- `app/services/web_search.py`
- `app/services/linkedin_lookup.py`

## Important constraints

- Does **not** scrape LinkedIn pages
- Uses **search engine snippets** only (Tavily or DuckDuckGo)
- Accepts a match only when LLM confidence ≥ `LINKEDIN_LOOKUP_MIN_CONFIDENCE` (default `0.72`)

## Flow

1. Build search queries (name, domain, Slack title, `site:linkedin.com/in` variants)
2. Collect LinkedIn URLs from results
3. Bedrock chooses best candidate + confidence (heuristic fallback if Bedrock fails)
4. If confident enough, Bedrock writes a short summary from snippets

## Configuration

```env
LINKEDIN_LOOKUP_ENABLED=true
LINKEDIN_LOOKUP_MIN_CONFIDENCE=0.72
WEB_SEARCH_PROVIDER=auto
TAVILY_API_KEY=...   # recommended
```

## Status values

| Status | Meaning |
|--------|---------|
| `ok` | Match + summary |
| `low_confidence` | Candidates found, not promoted |
| `not_found` | No LinkedIn URLs in search results |
| `not_configured` | Web search unavailable |
| `disabled` | Feature off |

## LLM & summaries

High-confidence LinkedIn data is included in `build_llm_context()` and user summary prompts.

## Name gate

LinkedIn candidates are rejected when they conflict with **known identity** (Google OpenID / People / display name / resolved name):

- Known **Jeff** Lewis → reject **John** Lewis
- Email-only identities like `jlewis@…` (initial + last name only) are treated as **ambiguous** — never auto-accepted as `ok` until a full first name is known

Before LinkedIn, `resolve_identity_name` (`app/services/identity_resolve.py`) web-searches the email/company to recover a full name when Google Calendar did not supply `displayName` and the person has not signed in yet. Admin **Save name** still works as an override.

See `app/services/identity_names.py`.

## Related

- [Configuration](../configuration.md)
- [LLM summaries](../llm-summaries.md)
