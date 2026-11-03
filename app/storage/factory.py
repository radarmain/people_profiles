import os
from functools import lru_cache

from app.config import get_settings
from app.storage.base import ProfileStore
from app.storage.dynamodb import DynamoDBStore
from app.storage.local_json import LocalJsonStore


@lru_cache
def get_store() -> ProfileStore:
    settings = get_settings()
    if settings.storage_backend == "dynamodb":
        in_managed_runtime = bool(
            os.getenv("AWS_LAMBDA_FUNCTION_NAME")
            or os.getenv("AWS_EXECUTION_ENV")
            or settings.environment.lower() in {"production", "prod"}
        )
        # Lambda/ECS use their runtime role and must not load a local named profile.
        profile = None if in_managed_runtime else (settings.aws_profile or None)
        if profile is None and not os.getenv("AWS_PROFILE"):
            os.environ.pop("AWS_PROFILE", None)
        endpoint = None if in_managed_runtime else (settings.dynamodb_endpoint or None)
        return DynamoDBStore(
            users_table=settings.dynamodb_users_table,
            agencies_table=settings.dynamodb_agencies_table,
            core_profiles_table=settings.dynamodb_core_profiles_table,
            region=settings.aws_region,
            endpoint_url=endpoint,
            profile_name=profile,
        )
    return LocalJsonStore(settings.local_data_dir)
