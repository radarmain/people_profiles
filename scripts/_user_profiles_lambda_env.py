#!/usr/bin/env python3
"""Build Lambda Environment Variables JSON from .env for aws cli."""

import json
import os
from pathlib import Path


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        out[key.strip()] = value
    return out


# Keys copied to Lambda (secrets + integration config). Extend as needed.
PASS_THROUGH = [
    "STORAGE_BACKEND",
    "DYNAMODB_USERS_TABLE",
    "DYNAMODB_AGENCIES_TABLE",
    "DYNAMODB_CORE_PROFILES_TABLE",
    "AWS_REGION",
    "AWS_KB_REGION",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_OAUTH_SCOPES",
    "SLACK_CLIENT_ID",
    "SLACK_CLIENT_SECRET",
    "SLACK_USER_SCOPES",
    "HIBOB_SERVICE_USER_ID",
    "HIBOB_SERVICE_USER_TOKEN",
    "HIBOB_API_BASE",
    "BEDROCK_MODEL_ID",
    "LLM_FALLBACK_WITHOUT_BEDROCK",
    "BEDROCK_KNOWLEDGE_BASE_ID",
    "BEDROCK_KB_SEARCH_MODE",
    "BEDROCK_KB_NUMBER_OF_RESULTS",
    "BEDROCK_KB_MAX_QUERIES",
    "BEDROCK_KB_MAX_MERGED_RESULTS",
    "BEDROCK_KB_MAX_CHUNK_CHARS",
    "LINKEDIN_LOOKUP_ENABLED",
    "LINKEDIN_LOOKUP_MIN_CONFIDENCE",
    "LINKEDIN_LOOKUP_MAX_CANDIDATES",
    "LINKEDIN_LOOKUP_MAX_SEARCH_QUERIES",
    "LINKEDIN_LOOKUP_MODEL_ID",
    "WEB_SEARCH_PROVIDER",
    "WEB_SEARCH_MAX_RESULTS",
    "TAVILY_API_KEY",
]


def main() -> None:
    env_file = Path(os.environ.get("ROOT", ".")) / ".env"
    if not env_file.exists():
        env_file = Path(__file__).resolve().parent.parent / ".env"
    values = load_dotenv(env_file)
    values.setdefault("STORAGE_BACKEND", "dynamodb")
    prefix = values.get("_USER_PROFILES_PREFIX", "_user_profiles")
    values.setdefault("DYNAMODB_USERS_TABLE", f"{prefix}_users")
    values.setdefault("DYNAMODB_AGENCIES_TABLE", f"{prefix}_agencies")
    values.setdefault("DYNAMODB_CORE_PROFILES_TABLE", f"{prefix}_core_profiles")
    variables = {
        k: values[k]
        for k in PASS_THROUGH
        if k in values and values[k] and k not in ("DYNAMODB_ENDPOINT", "AWS_PROFILE", "AWS_REGION")
    }
    print(json.dumps({"Variables": variables}))


if __name__ == "__main__":
    main()
