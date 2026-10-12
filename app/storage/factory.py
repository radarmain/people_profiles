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
        in_lambda = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
        profile = None if in_lambda else settings.aws_profile
        endpoint = None if in_lambda else (settings.dynamodb_endpoint or None)
        return DynamoDBStore(
            users_table=settings.dynamodb_users_table,
            agencies_table=settings.dynamodb_agencies_table,
            region=settings.aws_region,
            endpoint_url=endpoint,
            profile_name=profile,
        )
    return LocalJsonStore(settings.local_data_dir)
