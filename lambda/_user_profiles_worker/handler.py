"""AWS Lambda entrypoint for _user_profiles background jobs."""

import asyncio
import json
import logging
import os
from typing import Any

# Ensure project root is on path when deployed as zip with app/ at root
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _parse_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    if "Records" in event:
        jobs = []
        for record in event["Records"]:
            body = record.get("body") or "{}"
            jobs.append(json.loads(body))
        return jobs
    if "job_type" in event and "user_id" in event:
        return [event]
    raise ValueError("Unsupported event shape for _user_profiles_worker")


async def _process_job(job: dict[str, Any]) -> None:
    from app.services.job_runner import run_enrich_job, run_summarize_job

    job_type = job["job_type"]
    user_id = job["user_id"]
    if job_type == "enrich":
        await run_enrich_job(user_id)
    elif job_type == "summarize":
        await run_summarize_job(user_id)
    else:
        raise ValueError(f"Unknown job_type: {job_type}")


def handler(event, context):  # noqa: ARG001
    os.environ.setdefault("STORAGE_BACKEND", "dynamodb")
    jobs = _parse_event(event)
    for job in jobs:
        logger.info("Processing _user_profiles job: %s", job)
        asyncio.run(_process_job(job))
    return {"statusCode": 200, "processed": len(jobs)}
