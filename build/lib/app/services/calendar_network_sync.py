"""Resolve calendar attendees → MTP users, score closeness, create same-domain provisionals."""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.models.domain import UserProfile, utc_now
from app.services.provisional_user import create_provisional_from_calendar
from app.services.safe_dict import as_dict
from app.storage.base import ProfileStore

logger = logging.getLogger(__name__)


def _closeness_score(meeting_count: int, max_count: int) -> int:
    if max_count <= 0 or meeting_count <= 0:
        return 1
    return max(1, min(100, round(100 * meeting_count / max_count)))


def _upsert_edge(user: UserProfile, edge: dict[str, Any], *, window_days: int) -> None:
    assoc = as_dict(user.network_associations)
    edges = list(assoc.get("edges") or [])
    other_id = edge["other_user_id"]
    merged: list[dict[str, Any]] = []
    found = False
    for existing in edges:
        if not isinstance(existing, dict):
            continue
        if existing.get("other_user_id") == other_id and existing.get("source", "calendar") == "calendar":
            merged.append({**existing, **edge})
            found = True
        else:
            merged.append(existing)
    if not found:
        merged.append(edge)
    merged.sort(key=lambda e: int(e.get("closeness_score") or 0), reverse=True)
    user.network_associations = {
        "updated_at": utc_now().isoformat(),
        "window_days": window_days,
        "edges": merged,
    }


def _attendee_list(user: UserProfile) -> list[dict[str, Any]]:
    google = as_dict(user.google)
    calendar = as_dict(google.get("calendar"))
    if calendar.get("status") != "ok":
        return []
    normalized = as_dict(calendar.get("normalized"))
    attendees = normalized.get("all_attendees") or normalized.get("top_attendees") or []
    if not isinstance(attendees, list):
        return []
    return [a for a in attendees if isinstance(a, dict)]


def _window_days(user: UserProfile, settings: Settings) -> int:
    google = as_dict(user.google)
    calendar = as_dict(google.get("calendar"))
    window = as_dict(calendar.get("window"))
    try:
        return int(window.get("lookback_days") or settings.google_calendar_lookback_days)
    except (TypeError, ValueError):
        return settings.google_calendar_lookback_days


async def sync_calendar_network(
    store: ProfileStore,
    settings: Settings,
    user: UserProfile,
) -> UserProfile:
    """
    For each calendar attendee: link if known; create provisional if same-domain unknown.
    Writes bidirectional closeness edges (1–100).
    """

    if not settings.calendar_network_enabled:
        return user
    if user.account_kind != "member":
        return user

    attendees = _attendee_list(user)
    if not attendees:
        return user

    cap = max(1, settings.calendar_network_max_attendees_for_network)
    attendees = attendees[:cap]
    user_domain = (user.email_domain or "").strip().lower()
    window_days = _window_days(user, settings)

    link_targets: list[tuple[UserProfile, dict[str, Any]]] = []
    new_provisionals: list[UserProfile] = []
    created_count = 0
    max_new = max(0, settings.calendar_network_max_new_provisionals_per_sync)

    for att in attendees:
        email = (att.get("email") or "").strip().lower()
        if not email or "@" not in email or email == user.email.strip().lower():
            continue

        other = store.get_user_by_email(email)
        if other:
            if other.user_id == user.user_id:
                continue
            link_targets.append((other, att))
            continue

        att_domain = (att.get("domain") or "").strip().lower()
        if not att_domain and "@" in email:
            att_domain = email.split("@", 1)[1].strip().lower()

        if (
            settings.calendar_network_create_provisional
            and user_domain
            and att_domain == user_domain
            and created_count < max_new
        ):
            provisional, created = create_provisional_from_calendar(
                store,
                email=email,
                display_name=att.get("display_name"),
                discovered_by_user_id=user.user_id,
            )
            if provisional.user_id == user.user_id:
                continue
            link_targets.append((provisional, att))
            if created:
                created_count += 1
                new_provisionals.append(provisional)

    if not link_targets:
        return user

    max_count = max(int(att.get("meeting_count") or 0) for _other, att in link_targets) or 1

    # Reload source user (agency/ensure may have mutated)
    source = store.get_user(user.user_id) or user

    for other, att in link_targets:
        meeting_count = int(att.get("meeting_count") or 0)
        score = _closeness_score(meeting_count, max_count)
        minutes = att.get("estimated_minutes")
        try:
            minutes_f = float(minutes) if minutes is not None else 0.0
        except (TypeError, ValueError):
            minutes_f = 0.0

        # Fresh load of other in case multiple writers
        peer = store.get_user(other.user_id) or other

        edge_to_peer = {
            "other_user_id": peer.user_id,
            "email": peer.email,
            "display_name": peer.display_name or att.get("display_name"),
            "closeness_score": score,
            "meeting_count": meeting_count,
            "estimated_minutes": minutes_f,
            "other_account_kind": peer.account_kind,
            "source": "calendar",
        }
        edge_to_source = {
            "other_user_id": source.user_id,
            "email": source.email,
            "display_name": source.display_name,
            "closeness_score": score,
            "meeting_count": meeting_count,
            "estimated_minutes": minutes_f,
            "other_account_kind": source.account_kind,
            "source": "calendar",
        }

        _upsert_edge(source, edge_to_peer, window_days=window_days)
        _upsert_edge(peer, edge_to_source, window_days=window_days)
        store.save_user(peer)

        # Also annotate calendar top_attendees / all_attendees for UI
        _tag_calendar_attendee(source, email=peer.email, mtp_user_id=peer.user_id, display_name=peer.display_name)

    store.save_user(source)

    # Queue baseline enrich for newly created provisionals
    if new_provisionals:
        try:
            from app.services._user_profiles_jobs import JOB_ENRICH, dispatch_user_profiles_job

            for provisional in new_provisionals:
                try:
                    await dispatch_user_profiles_job(JOB_ENRICH, provisional)
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to enqueue enrich for provisional %s", provisional.user_id)
        except Exception:  # noqa: BLE001
            logger.exception("Could not dispatch provisional enrich jobs")

    return store.get_user(source.user_id) or source


def _tag_calendar_attendee(
    user: UserProfile,
    *,
    email: str,
    mtp_user_id: str,
    display_name: str | None,
) -> None:
    google = as_dict(user.google)
    calendar = as_dict(google.get("calendar"))
    if calendar.get("status") != "ok":
        return
    normalized = as_dict(calendar.get("normalized"))
    for key in ("top_attendees", "all_attendees"):
        rows = normalized.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and (row.get("email") or "").strip().lower() == email:
                row["mtp_user_id"] = mtp_user_id
                if display_name:
                    row["mtp_display_name"] = display_name
    edges = [
        {
            "mtp_user_id": e.get("other_user_id"),
            "email": e.get("email"),
            "meeting_count": e.get("meeting_count"),
            "estimated_minutes": e.get("estimated_minutes"),
            "closeness_score": e.get("closeness_score"),
        }
        for e in (as_dict(user.network_associations).get("edges") or [])
        if isinstance(e, dict)
    ]
    normalized["mtp_connection_edges"] = edges
    calendar["normalized"] = normalized
    google["calendar"] = calendar
    user.google = google
