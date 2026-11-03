from copy import deepcopy
from typing import Any


def redact_user_payload(data: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(data)
    google = out.get("google")
    if isinstance(google, dict):
        for key in ("_oauth", "oauth"):
            if key in google:
                google[key] = {"present": True}
    slack = out.get("slack")
    if isinstance(slack, dict):
        for key in ("_oauth", "oauth"):
            if key in slack:
                slack[key] = {"present": True}
    return out
