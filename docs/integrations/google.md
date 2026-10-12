# Google (OAuth + People API)

## OAuth

- Registered in `app/routers/auth.py` via Authlib + Google OpenID discovery
- Default scopes include OpenID, profile, email, and People API-related scopes (`app/config.py`)

### Redirect URI

`{APP_BASE_URL}/auth/google/callback`

### Stored shape

```json
{
  "openid": { "sub", "email", "name", "picture", "hd", ... },
  "_oauth": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_at": ...
  },
  "people": { "status": "ok", "normalized": { ... } },
  "calendar": { "status": "ok", "normalized": { "top_attendees": [ ... ] } }
}
```

## People API

- Code: `app/services/google_enrichment.py`
- Endpoint: `GET https://people.googleapis.com/v1/people/me`
- Requires **Google People API enabled** in the same GCP project as the OAuth client

### Token lifecycle

1. Login with `access_type=offline`
2. Refresh token stored in `_oauth.refresh_token`
3. On enrichment, access token is refreshed if expired (`oauth2.googleapis.com/token`)
4. If no tokens: status `reauth_required` → user clicks **Re-link Google** (`/auth/google/relink`)

## LLM exposure

`enrichment_snapshot` includes org/bio/phones from People API when `status: ok`. It does **not** expose raw `no_token` / `reauth_required` as noisy API status strings to the LLM.

## Calendar

See [Google Calendar](./google-calendar.md) for meeting-network enrichment (user OAuth, no admin).

## Related

- [Authentication](../authentication.md)
- [Configuration](../configuration.md)
