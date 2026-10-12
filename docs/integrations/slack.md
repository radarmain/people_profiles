# Slack integration

## Purpose

Collect workspace context and user profile fields using a **Slack user token** (not a bot token).

## OAuth

- Authorize URL: `https://slack.com/oauth/v2/authorize`
- Parameters: `user_scope` only (see `SLACK_USER_SCOPES`)
- Callback: `app/routers/auth.py` → stores `slack._oauth.user_access_token`

### Required user scopes

```
users:read
users:read.email
users.profile:read
team:read
channels:read
```

After changing scopes, users must connect Slack again.

## Enrichment

Code: `app/services/slack_enrichment.py`

| API method | Data |
|------------|------|
| `users.info` | Name, title, timezone, admin flags |
| `users.profile.get` | Extended profile fields |
| `team.info` | Workspace name, domain |
| `conversations.list` | Public channels (up to 40), topics, purposes |

Only **public** channels the token can see are included. No DMs, private channels, or message history.

## Stored shape

```json
{
  "_oauth": { "user_access_token", "user_id", "team_id" },
  "oauth_meta": { "team_name", "team_id" },
  "enriched": {
    "user": { ... },
    "team": { ... },
    "public_channels": [ ... ],
    "errors": [ ... ]
  }
}
```

## PoC security note

User tokens are stored on the profile record. Encrypt at rest in production.

## Related

- [Authentication](../authentication.md)
- [Enrichment pipeline](../enrichment-pipeline.md)
