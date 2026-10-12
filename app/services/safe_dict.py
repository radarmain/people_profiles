from typing import Any


def as_dict(value: Any) -> dict:
    """Coerce DynamoDB/null profile blobs to empty dicts."""
    return value if isinstance(value, dict) else {}


def normalize_user_blobs(user) -> None:
    """Ensure JSON blob fields are dicts before enrichment (in-place)."""
    user.google = as_dict(user.google)
    user.slack = as_dict(user.slack)
    user.hibob = as_dict(user.hibob)
    user.internal = as_dict(user.internal)
    user.knowledge_base = as_dict(user.knowledge_base)
    user.linkedin = as_dict(user.linkedin)
    user.work_profile = as_dict(user.work_profile)
    user.network_associations = as_dict(user.network_associations)
    user.processing_status = as_dict(user.processing_status)
