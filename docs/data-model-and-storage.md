# Data model & storage

## UserProfile

| Field | Description |
|-------|-------------|
| `user_id` | Primary key (Google `sub`, or `prov_…` for provisional) |
| `account_kind` | `member` (signed in) or `provisional` (calendar-discovered) |
| `email`, `email_domain` | Identity and agency linkage |
| `display_name`, `picture_url` | From Google or calendar display name |
| `google` | OpenID claims, `_oauth` tokens, `people` / `calendar` enrichment |
| `slack` | `_oauth`, `enriched` (team, user, channels) |
| `hibob` | Search result or status |
| `internal` | Stub / future internal APIs |
| `knowledge_base` | Bedrock Retrieve results |
| `linkedin` | Lookup status, URL, confidence, summary |
| `network_associations` | Bidirectional meeting edges + closeness scores |
| `agency_id` | Same as email domain |
| `work_profile` | Structured role/function JSON for workflow routing |
| `work_profile_generated_at` | When work profile was last inferred |
| `llm_summary` | Human-readable role & work brief (markdown) |
| `slack_connected` | Gate for profile page |

## AgencyProfile

| Field | Description |
|-------|-------------|
| `agency_id` | Email domain (e.g. `radar-analytics.com`) |
| `domain`, `display_name` | Domain and friendly label |
| `member_user_ids` | Google user IDs in this app |
| `member_count` | Length of member list |
| `inferred` | Rollups: top departments, titles, Slack workspaces |
| `knowledge_base` | Domain-focused Retrieve results |
| `llm_summary` | Generated agency markdown |

## Agency membership

`ensure_user_agency()` runs after login and enrichment:

1. Load or create agency for `user.email_domain`
2. Append `user_id` to `member_user_ids` if new
3. Recompute `inferred` from all members

## Local storage

```
.data/
  users/{user_id}.json
  agencies/{domain}.json
```

Filenames sanitize `/` in IDs.

## DynamoDB

Init script: `scripts/init_dynamodb_tables.py`

- **Users**: PK `user_id`, GSI `email-index` on `email`
- **Agencies**: PK `agency_id`

Uses `AWS_PROFILE` and optional `DYNAMODB_ENDPOINT` for local.

## Related

- [Architecture](./architecture.md)
- [Configuration](./configuration.md)
