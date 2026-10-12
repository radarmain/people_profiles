import asyncio
import json
import os
from typing import Any

import boto3

from app.config import Settings, get_settings
from app.models.domain import UserProfile, utc_now
from app.services.job_runner import run_enrich_job, run_summarize_job
from app.storage.factory import get_store

JOB_ENRICH = "enrich"
JOB_SUMMARIZE = "summarize"


def _boto3_client(service: str, settings: Settings):
    kwargs: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.aws_profile and not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        session = boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region)
        return session.client(service)
    return boto3.client(service, **kwargs)


def _mark_queued(user: UserProfile, job_type: str) -> None:
    store = get_store()
    user.processing_status = {
        "job_type": job_type,
        "state": "queued",
        "updated_at": utc_now().isoformat(),
    }
    store.save_user(user)


async def _run_local(job_type: str, user_id: str) -> None:
    if job_type == JOB_ENRICH:
        await run_enrich_job(user_id)
    elif job_type == JOB_SUMMARIZE:
        await run_summarize_job(user_id)
    else:
        raise ValueError(f"Unknown job type: {job_type}")


def _enqueue_sqs(settings: Settings, payload: dict[str, Any]) -> None:
    if not settings.user_profiles_jobs_queue_url:
        raise RuntimeError("_USER_PROFILES_JOBS_QUEUE_URL is not set")
    client = _boto3_client("sqs", settings)
    client.send_message(QueueUrl=settings.user_profiles_jobs_queue_url, MessageBody=json.dumps(payload))


def _invoke_lambda_async(settings: Settings, payload: dict[str, Any]) -> None:
    if not settings.user_profiles_worker_function_name:
        raise RuntimeError("_USER_PROFILES_WORKER_FUNCTION_NAME is not set")
    client = _boto3_client("lambda", settings)
    client.invoke(
        FunctionName=settings.user_profiles_worker_function_name,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )


def _should_run_inline(settings: Settings, job_type: str) -> bool:
    if not settings.user_profiles_offload:
        return True
    if job_type == JOB_SUMMARIZE and not settings.user_profiles_offload_summarize:
        return True
    return False


async def dispatch_user_profiles_job(job_type: str, user: UserProfile) -> str:
    """Returns mode: local, sqs, or lambda."""

    settings = get_settings()
    payload = {"job_type": job_type, "user_id": user.user_id}

    if _should_run_inline(settings, job_type):
        await _run_local(job_type, user.user_id)
        return "local"

    store = get_store()
    fresh = store.get_user(user.user_id) or user
    _mark_queued(fresh, job_type)

    if settings.user_profiles_jobs_queue_url:
        await asyncio.to_thread(_enqueue_sqs, settings, payload)
        return "sqs"

    if settings.user_profiles_worker_function_name:
        await asyncio.to_thread(_invoke_lambda_async, settings, payload)
        return "lambda"

    await _run_local(job_type, user.user_id)
    return "local"
