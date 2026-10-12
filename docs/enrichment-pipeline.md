# Enrichment pipeline

Orchestrator: `app/services/profile_builder.py` → `refresh_user_profile()`.

## Order of operations (member refresh)

1. **Google** — `enrich_google()`: OpenID + People API + **Calendar** co-attendance aggregates (user OAuth)
2. **Calendar network** — `sync_calendar_network()`: link attendees, score closeness, create same-domain provisionals
3. **Slack** — if `slack_connected`: `enrich_slack()` (team, user, public channels)
4. **Internal tools** — stub in `internal_tools.py`
5. **HiBob** — People search by email (if configured)
6. **Bedrock KB** — `retrieve_for_user()` (if `BEDROCK_KNOWLEDGE_BASE_ID` set)
7. **LinkedIn** — `enrich_linkedin()` (if enabled and web search available)
8. **Agency** — `ensure_user_agency()` updates membership and rollups

**Provisional users** skip Google/Slack (no tokens) and run steps 4–8 only, then are queued via the same enrich job type after creation.

Each step writes JSON blobs onto `UserProfile` (and agency for membership).

## Generate summaries flow

`POST /profile/summary` in `routers/pages.py`:

1. `refresh_user_profile()` (full pipeline above)
2. `persist_work_profile()` — structured role/function JSON → `user.work_profile`
3. `persist_user_summary()` — Bedrock Converse (or fallback) → `user.llm_summary` (role-focused brief)
4. `enrich_agency_for_summary()` — refresh rollups + `retrieve_for_agency()`
5. `persist_agency_summary()` — Bedrock → `agency.llm_summary`

User summary is generated **before** agency summary so member excerpts can include the latest user summary text.

## Status fields

Integrations use consistent status patterns:

| Status | Meaning |
|--------|---------|
| `not_configured` | Credentials/env missing |
| `ok` | Data retrieved |
| `not_found` | API OK, no match |
| `low_confidence` | LinkedIn: candidates but below threshold |
| `reauth_required` | Google: need Re-link Google |
| `error` / `partial` | Failure or mixed KB results |

## Related

- [LLM summaries](./llm-summaries.md)
- Integration docs under [docs/integrations/](./integrations/google.md)
