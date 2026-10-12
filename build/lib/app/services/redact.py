from copy import deepcopy
from typing import Any


def redact_user_payload(data: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(data)
    google = out.get("google")
    if isinstance(google, dict) and "_oauth" in google:
        google["_oauth"] = {"present": True}
    slack = out.get("slack")
    if isinstance(slack, dict) and "_oauth" in slack:
        slack["_oauth"] = {"present": True}
    return out
