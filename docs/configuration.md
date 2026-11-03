# Configuration reference

Settings load from `.env` via `pydantic-settings` (`app/config.py`). Restart the server after changes (`get_settings()` is cached).

## Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_SECRET_KEY` | (dev placeholder) | Session cookie signing secret |
| `APP_BASE_URL` | `http://127.0.0.1:8080` | Base URL for OAuth redirects |
| `ENVIRONMENT` | `local` | Shown in `/health` |
| `ALLOWED_EMAILS` | empty | Comma-separated Google emails allowed to sign in |
| `ADMIN_EMAILS` | empty | Comma-separated emails allowed to access `/admin` |
| `EXTERNAL_API_KEYS` | empty | Comma-separated API keys for `/api/v1` clients |

## Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_BACKEND` | `local` | `local` or `dynamodb` |
| `LOCAL_DATA_DIR` | `.data` | JSON files when local |
| `AWS_PROFILE` | `concrete` | Boto3 profile |
| `AWS_REGION` | `us-east-1` | DynamoDB, Bedrock Converse |
| `AWS_KB_REGION` | (falls back to `AWS_REGION`) | Bedrock KB Retrieve region |
| `DYNAMODB_ENDPOINT` | `http://127.0.0.1:8000` | Set for DynamoDB Local |
| `DYNAMODB_USERS_TABLE` | `_user_profiles_users` | Users table name |
| `DYNAMODB_AGENCIES_TABLE` | `_user_profiles_agencies` | Agencies table name |
| `DYNAMODB_CORE_PROFILES_TABLE` | `_user_profiles_core_profiles` | HiBob Core profiles table name |

## Lambda offload (`_user_profiles`)

| Variable | Description |
|----------|-------------|
| `_USER_PROFILES_OFFLOAD` | `true` → enqueue jobs to AWS instead of in-process |
| `_USER_PROFILES_JOBS_QUEUE_URL` | SQS queue URL (from deploy output) |
| `_USER_PROFILES_WORKER_FUNCTION_NAME` | Lambda name (default `_user_profiles_worker`) |
| `_USER_PROFILES_ARTIFACT_BUCKET` | S3 bucket for deploy script |
| `_USER_PROFILES_STACK_NAME` | CloudFormation stack (default `_user_profiles_stack`) |
| `_USER_PROFILES_PREFIX` | Resource prefix (default `_user_profiles`) |

## Google

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_OAUTH_SCOPES` | Optional override (space-separated) |
| `GOOGLE_OAUTH_PROMPT_CONSENT` | If `true`, always show consent on login |

Default scopes include `calendar.readonly` (see [Google Calendar](./integrations/google-calendar.md)).

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CALENDAR_ENABLED` | `true` | Fetch meeting aggregates on enrichment |
| `GOOGLE_CALENDAR_LOOKBACK_DAYS` | `90` | How far back to scan events |
| `GOOGLE_CALENDAR_MAX_EVENTS` | `400` | Max events per refresh |
| `GOOGLE_CALENDAR_MAX_CALENDARS` | `5` | Calendars to scan |
| `GOOGLE_CALENDAR_TOP_ATTENDEES` | `20` | Top meeting partners to keep |
| `CALENDAR_NETWORK_ENABLED` | `true` | Build meeting associations after calendar fetch |
| `CALENDAR_NETWORK_CREATE_PROVISIONAL` | `true` | Create same-domain unknown attendees |
| `CALENDAR_NETWORK_MAX_ATTENDEES_FOR_NETWORK` | `500` | Cap attendees for network sync |
| `CALENDAR_NETWORK_MAX_NEW_PROVISIONALS_PER_SYNC` | `25` | Max new provisional users per refresh |

## Slack

| Variable | Description |
|----------|-------------|
| `SLACK_CLIENT_ID` | Slack app client ID |
| `SLACK_CLIENT_SECRET` | Slack app secret |
| `SLACK_USER_SCOPES` | Comma-separated user token scopes |

Default scopes: `users:read`, `users:read.email`, `users.profile:read`, `team:read`, `channels:read`.

## HiBob

| Variable | Description |
|----------|-------------|
| `HIBOB_SERVICE_USER_ID` | Service user ID |
| `HIBOB_SERVICE_USER_TOKEN` | Service user token |
| `HIBOB_API_BASE` | API base (default `https://api.hibob.com/v1`) |

If ID/token empty, HiBob enrichment is skipped (`status: not_configured`).

## Bedrock (LLM)

| Variable | Default | Description |
|----------|---------|-------------|
| `BEDROCK_MODEL_ID` | `amazon.nova-lite-v1:0` | Converse model for summaries + LinkedIn disambiguation |
| `LLM_FALLBACK_WITHOUT_BEDROCK` | `true` | Template summaries if Converse fails |

## Bedrock Knowledge Base

| Variable | Default | Description |
|----------|---------|-------------|
| `BEDROCK_KNOWLEDGE_BASE_ID` | | KB ID; empty = skip |
| `BEDROCK_KB_SEARCH_MODE` | `managed` | `managed`, `vector`, or `auto` |
| `BEDROCK_KB_NUMBER_OF_RESULTS` | `8` | Results per query |
| `BEDROCK_KB_MAX_QUERIES` | `4` | Max queries per user/agency run |
| `BEDROCK_KB_MAX_MERGED_RESULTS` | `12` | Deduped chunks kept |
| `BEDROCK_KB_MAX_CHUNK_CHARS` | `1500` | Truncate stored chunk text |

## LinkedIn lookup

| Variable | Default | Description |
|----------|---------|-------------|
| `LINKEDIN_LOOKUP_ENABLED` | `true` | Master switch |
| `LINKEDIN_LOOKUP_MIN_CONFIDENCE` | `0.72` | Min score to accept match + summary |
| `WEB_SEARCH_PROVIDER` | `auto` | `auto`, `tavily`, or `duckduckgo` |
| `TAVILY_API_KEY` | | Recommended for reliable search |
| `WEB_SEARCH_MAX_RESULTS` | `8` | Hits per query |

## Related

- [Integrations](./integrations/google.md) (per-service setup)
- [AWS & production notes](./aws-and-production-notes.md)
