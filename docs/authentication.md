# Authentication & sessions

## Google (required)

- Entry: `GET /auth/login` → Google OAuth → `GET /auth/google/callback`
- Scopes: OpenID + profile + email + People API-related scopes (see [Google integration](./integrations/google.md))
- **`access_type=offline`** is requested so refresh tokens can be stored for People API calls
- User record key: Google `sub` → `UserProfile.user_id`

### Re-link Google

`GET /auth/google/relink` (requires session) forces `prompt=consent` to obtain or refresh a **refresh token**. Use when People API status is `reauth_required`.

On callback, refresh tokens are **merged**: a new login without a refresh token in the response keeps the previous refresh token if present.

## Slack (required for profile)

- Entry: `GET /auth/slack/connect` → Slack OAuth v2 → `GET /auth/slack/callback`
- Only **`user_scope`** is sent (no bot install)
- Stores `slack._oauth.user_access_token` and runs initial Slack enrichment

Users must **re-authorize Slack** after scope changes in the Slack app or `.env`.

## Session

- Cookie-based session via `SessionMiddleware`
- Key field: `session["user_id"]`
- Logout: `POST /auth/logout` clears session

## Security notes (PoC)

- OAuth tokens are stored in profile JSON / DynamoDB **in plaintext**
- `/api/me` redacts `_oauth` blocks (reports `"present": true` only)
- Production should use encrypted storage (e.g. Secrets Manager) and short-lived tokens

## Related

- [HTTP routes](./api-routes.md)
- [Google integration](./integrations/google.md)
- [Slack integration](./integrations/slack.md)
