# HTTP routes & API

## Public / health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness JSON |

## Pages

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Optional | Home, integration status pills |
| GET | `/connect/slack` | Yes | Slack connect instructions |
| GET | `/profile` | Yes + Slack | Main profile UI |
| POST | `/profile/refresh` | Yes | Run enrichment pipeline |
| POST | `/profile/summary` | Yes | Refresh + user & agency LLM summaries |
| GET | `/admin` | Admin | Generated profiles overview plus Core profiles |
| GET | `/admin/users/{user_id}` | Admin | User detail (redacted JSON) |
| POST | `/admin/users/{user_id}/work-profile` | Admin | Generate work profile + role brief (incl. provisionals) |
| GET | `/admin/agencies/{agency_id}` | Admin | Agency detail + members |

Static assets: `/static/*`

## Authentication

| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/login` | Start Google OAuth |
| GET | `/auth/google/callback` | Google OAuth callback |
| GET | `/auth/google/relink` | Force Google consent (session required) |
| GET | `/auth/slack/connect` | Start Slack user OAuth |
| GET | `/auth/slack/callback` | Slack OAuth callback |
| POST | `/auth/logout` | Clear session |

## JSON API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/me` | Yes | Full user + agency JSON (`_oauth` redacted) |

## External API

Machine clients use `X-API-Key: <key>` or `Authorization: Bearer <key>`.
Keys are configured with `EXTERNAL_API_KEYS` and should be stored in Secrets Manager
in production.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/users` | List generated profiles; optional `q` search |
| GET | `/api/v1/users/{user_id}` | Get one generated profile and agency |
| GET | `/api/v1/core-profiles` | List HiBob-backed Core profiles; optional `q` search |

Example:

```bash
curl -b cookies.txt http://127.0.0.1:8080/api/me
```

(Session cookie required after browser login.)

## Related

- [Authentication](./authentication.md)
- [Getting started](./getting-started.md)
