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
| GET | `/admin` | Admin | Org overview: all users & agencies |
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

Example:

```bash
curl -b cookies.txt http://127.0.0.1:8080/api/me
```

(Session cookie required after browser login.)

## Related

- [Authentication](./authentication.md)
- [Getting started](./getting-started.md)
