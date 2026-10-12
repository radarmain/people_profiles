"""Summaries for org-wide admin views (no OAuth secrets)."""

from typing import Any

from app.models.domain import AgencyProfile, UserProfile
from app.services.redact import redact_user_payload
from app.services.safe_dict import as_dict


def _job_state(user: UserProfile) -> str | None:
    ps = as_dict(user.processing_status)
    return ps.get("state")


def _work_profile_line(user: UserProfile) -> str | None:
    wp = as_dict(user.work_profile)
    if not wp.get("status") and not wp.get("primary_role_label"):
        return None
    parts = [wp.get("primary_role_label"), wp.get("function"), wp.get("seniority")]
    text = " · ".join(p for p in parts if p and p != "unknown")
    return text or wp.get("status")


def _network_edge_count(user: UserProfile) -> int:
    edges = as_dict(user.network_associations).get("edges") or []
    return len(edges) if isinstance(edges, list) else 0


def user_admin_row(user: UserProfile) -> dict[str, Any]:
    google = as_dict(user.google)
    cal = as_dict(google.get("calendar"))
    cal_norm = as_dict(cal.get("normalized"))
    wp = as_dict(user.work_profile)
    network_edges = _network_edge_count(user)

    return {
        "user_id": user.user_id,
        "email": user.email,
        "display_name": user.display_name,
        "agency_id": user.agency_id,
        "account_kind": user.account_kind,
        "slack_connected": user.slack_connected,
        "slack_bypassed": user.slack_connect_bypassed,
        "work_profile_line": _work_profile_line(user),
        "work_function": wp.get("function"),
        "calendar_status": cal.get("status"),
        "calendar_attendees": cal_norm.get("unique_other_attendees"),
        "network_edges": network_edges,
        "mtp_calendar_edges": network_edges,
        "linkedin_status": as_dict(user.linkedin).get("status"),
        "hibob_status": as_dict(user.hibob).get("status"),
        "kb_status": as_dict(user.knowledge_base).get("status"),
        "has_user_summary": bool(user.llm_summary),
        "has_work_profile": bool(wp.get("status") == "ok" or wp.get("primary_role_label")),
        "job_state": _job_state(user),
        "updated_at": user.updated_at,
    }


def agency_admin_row(agency: AgencyProfile) -> dict[str, Any]:
    inferred = as_dict(agency.inferred)
    return {
        "agency_id": agency.agency_id,
        "domain": agency.domain,
        "display_name": agency.display_name,
        "member_count": agency.member_count,
        "member_user_ids": list(agency.member_user_ids),
        "has_agency_summary": bool(agency.llm_summary),
        "kb_status": as_dict(agency.knowledge_base).get("status"),
        "top_departments": inferred.get("top_departments") or [],
        "updated_at": agency.updated_at,
    }


def org_stats(users: list[UserProfile], agencies: list[AgencyProfile]) -> dict[str, int]:
    failed = sum(1 for u in users if _job_state(u) == "failed")
    with_wp = sum(
        1
        for u in users
        if as_dict(u.work_profile).get("status") == "ok"
        or as_dict(u.work_profile).get("primary_role_label")
    )
    cal_ok = sum(
        1 for u in users if as_dict(as_dict(u.google).get("calendar")).get("status") == "ok"
    )
    provisional = sum(1 for u in users if u.account_kind == "provisional")
    return {
        "user_count": len(users),
        "agency_count": len(agencies),
        "work_profiles": with_wp,
        "calendar_enriched": cal_ok,
        "provisional_users": provisional,
        "jobs_failed": failed,
    }


def user_detail_payload(user: UserProfile) -> dict[str, Any]:
    return redact_user_payload(user.model_dump(mode="json"))


def agency_detail_payload(agency: AgencyProfile) -> dict[str, Any]:
    return agency.model_dump(mode="json")
