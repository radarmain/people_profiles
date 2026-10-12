# Internal tools (stub)

## Purpose

Hook point for **your** internal systems (CRM, licensing, support, data warehouse exports, etc.) to contribute structured facts to a user profile.

## Current implementation

File: `app/services/internal_tools.py`

`enrich_from_internal_tools(email, domain)` returns:

```json
{
  "status": "not_configured",
  "email": "...",
  "domain": "...",
  "notes": "Add internal API clients here..."
}
```

Stored at `user.internal.tools`.

## How to extend

1. Add async HTTP clients or boto3 calls per internal service
2. Return JSON-serializable dicts keyed by source name
3. Merge in `profile_builder.py`:

```python
user.internal = {
  "tools": await enrich_from_internal_tools(...),
  "crm": await enrich_from_crm(...),
}
```

4. Extend `enrichment_snapshot.build_llm_context()` if new fields should reach Bedrock
5. Document new env vars in [configuration.md](../configuration.md)

## Design tips

- Prefer **server-to-server** auth (IAM, API keys in Secrets Manager)
- Never expose internal API keys to the browser
- Include `source`, `fetched_at`, and `status` on each sub-object for debugging

## Related

- [Enrichment pipeline](../enrichment-pipeline.md)
- [Architecture](../architecture.md)
