import base64
from typing import Any

import httpx

from app.config import Settings


def _auth_header(settings: Settings) -> str:
    raw = f"{settings.hibob_service_user_id}:{settings.hibob_service_user_token}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _flatten_employee(employee: dict[str, Any]) -> dict[str, Any]:
    """Map HiBob slash notation fields to a small normalized dict."""

    def get(path: str) -> Any:
        return employee.get(path)

    return {
        "hibob_id": get("/root/id"),
        "first_name": get("/root/firstName"),
        "last_name": get("/root/surname") or get("/root/lastName"),
        "email": get("/root/email"),
        "title": get("/work/title"),
        "department": get("/work/department"),
        "site": get("/work/site"),
        "manager_id": get("/work/reportsTo/id") if isinstance(get("/work/reportsTo"), dict) else None,
        "start_date": get("/work/startDate"),
        "raw": employee,
    }


class HiBobClient:
    """Server-side HiBob People search by email.

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

        payload = {
            "fields": [
                "root.id",
                "root.firstName",
                "root.surname",
                "root.email",
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
        return {"normalized": normalized, "search_response": data}
