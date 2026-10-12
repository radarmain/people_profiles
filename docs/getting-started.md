# Getting started

## Prerequisites

- Python 3.11+
- Google Cloud OAuth client (Web application)
- Slack app with user token scopes
- Optional: AWS CLI profile `concrete` for Bedrock and KB
- Optional: HiBob service user, Tavily API key

## Install

```bash
cd /path/to/mtpi_userprofiles
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Edit `.env` — minimum: `APP_SECRET_KEY`, `GOOGLE_*`, `SLACK_*`, `APP_BASE_URL`.

## Run

```bash
uvicorn app.main:app --reload --port 8080
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080).

## OAuth redirect URIs

Must match `APP_BASE_URL` exactly (including `127.0.0.1` vs `localhost`):

| Provider | Redirect URI |
|----------|----------------|
| Google | `{APP_BASE_URL}/auth/google/callback` |
| Slack | `{APP_BASE_URL}/auth/slack/callback` |

## First login checklist

1. **Continue with Google** on home.
2. **Connect Slack** when prompted.
3. On profile: **Refresh enrichment** (loads KB, LinkedIn, etc. if configured).
4. **Re-link Google** if People API shows `reauth_required` (see [Google integration](./integrations/google.md)).
5. **Generate user & agency summaries** when Bedrock is available.

## DynamoDB Local (optional)

```bash
docker compose up -d dynamodb-local
AWS_PROFILE=concrete python scripts/init_dynamodb_tables.py
```

Set in `.env`:

```env
STORAGE_BACKEND=dynamodb
DYNAMODB_ENDPOINT=http://127.0.0.1:8000
```

## Health check

```bash
curl http://127.0.0.1:8080/health
```

## Related

- [Configuration reference](./configuration.md)
- [Authentication](./authentication.md)
