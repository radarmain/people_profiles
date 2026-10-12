import base64
from typing import Any

import httpx

from app.config import Settings


def _auth_header(settings: Settings) -> str:
    raw = f"{settings.hibob_service_user_id}:{settings.hibob_service_user_token}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _unwrap(value: Any) -> Any:
    """HiBob often wraps scalars as {'value': ...}."""
    if isinstance(value, dict) and "value" in value and len(value) == 1:
        return value["value"]
    return value


def _flatten_employee(employee: dict[str, Any]) -> dict[str, Any]:
    """Map HiBob people/search employee payload to a small normalized dict.

    Prefer humanReadable strings (titles/departments are named-list IDs otherwise).
    """

    hr = employee.get("humanReadable") if isinstance(employee.get("humanReadable"), dict) else {}
    hr_work = hr.get("work") if isinstance(hr.get("work"), dict) else {}
    work = employee.get("work") if isinstance(employee.get("work"), dict) else {}

    def slash(path: str) -> Any:
        return _unwrap(employee.get(path))

    reports = slash("/work/reportsTo")
    manager_id = None
    manager_name = None
    if isinstance(reports, dict):
        manager_id = reports.get("id")
        manager_name = reports.get("displayName") or (
            f"{reports.get('firstName') or ''} {reports.get('surname') or ''}".strip() or None
        )
    elif isinstance(hr_work.get("reportsTo"), str):
        manager_name = hr_work.get("reportsTo")

    title = hr_work.get("title") or work.get("title") or slash("/work/title")
    department = hr_work.get("department") or work.get("department") or slash("/work/department")
    # Drop opaque named-list IDs if humanReadable was missing
    if isinstance(title, str) and title.isdigit():
        title = None
    if isinstance(department, str) and department.isdigit():
        department = None

    return {
        "hibob_id": employee.get("id") or slash("/root/id"),
        "first_name": employee.get("firstName") or hr.get("firstName") or slash("/root/firstName"),
        "last_name": employee.get("surname")
        or hr.get("surname")
        or slash("/root/surname")
        or slash("/root/lastName"),
        "display_name": employee.get("displayName")
        or hr.get("displayName")
        or slash("/root/displayName"),
        "email": employee.get("email") or hr.get("email") or slash("/root/email"),
        "title": title,
        "department": department,
        "site": hr_work.get("site") or work.get("site") or slash("/work/site"),
        "manager_id": manager_id,
        "manager_name": manager_name,
        "start_date": work.get("startDate") or slash("/work/startDate"),
        "raw": employee,
    }


class HiBobClient:
    """Server-side HiBob People search by email (read-only).

    Only calls POST /people/search — HiBob's read API for employee fields.
    Does not create, update, or delete employees or any other HiBob resources.

    See: https://apidocs.hibob.com/docs/how-to-read-employee-data.md
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base = settings.hibob_api_base.rstrip("/")

    @property
    def enabled(self) -> bool:
        return self.settings.hibob_configured

    async def find_by_email(self, email: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        # humanReadable APPEND resolves named-list IDs (title/department) to labels.
        payload = {
            "fields": [
                "root.id",
                "root.firstName",
                "root.surname",
                "root.email",
                "root.displayName",
                "work.title",
                "work.department",
                "work.site",
                "work.startDate",
                "work.reportsTo",
            ],
            "filters": [
                {
                    "fieldPath": "root.email",
                    "operator": "equals",
                    "values": [email],
                }
            ],
            "humanReadable": "APPEND",
        }

        headers = {
            "Authorization": _auth_header(self.settings),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self.base}/people/search", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        employees = data.get("employees") or data.get("results") or data
        if isinstance(employees, dict):
            employees = employees.get("employees") or []

        if not employees:
            return None

        normalized = _flatten_employee(employees[0])
        return {"status": "ok", "normalized": normalized, "search_response": data}
