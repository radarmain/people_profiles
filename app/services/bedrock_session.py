import os
from typing import Any

import boto3

from app.config import Settings


def boto3_session(settings: Settings, *, region_name: str) -> boto3.Session:
    kwargs: dict[str, Any] = {"region_name": region_name}
    if settings.aws_profile and not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        kwargs["profile_name"] = settings.aws_profile
    return boto3.Session(**kwargs)


def bedrock_runtime_client(settings: Settings):
    return boto3_session(settings, region_name=settings.aws_region).client("bedrock-runtime")


def bedrock_agent_runtime_client(settings: Settings):
    return boto3_session(settings, region_name=settings.bedrock_kb_region).client(
        "bedrock-agent-runtime"
    )
