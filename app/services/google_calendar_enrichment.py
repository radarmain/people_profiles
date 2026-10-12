"""Google Calendar (user OAuth) — co-attendance aggregates for network / role signals."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.google_oauth import refresh_google_access_token

CALENDAR_API = "https://www.googleapis.com/calendar/v3"


def _parse_event_minutes(event: dict[str, Any]) -> float:
    start = event.get("start") or {}
    end = event.get("end") or {}
    start_raw = start.get("dateTime") or start.get("date")
    end_raw = end.get("dateTime") or end.get("date")
    if not start_raw or not end_raw:
        return 0.0
    if "T" not in start_raw:
        return 0.0
    try:
        start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
        return max(0.0, (end_dt - start_dt).total_seconds() / 60.0)
    except ValueError:
        return 0.0


def _email_domain(email: str) -> str:
    if "@" not in email:
        return ""
    return email.split("@", 1)[1].strip().lower()


def _attendee_row(
    email: str,
    *,
    attendee_names: dict[str, str],
    attendee_meetings: Counter[str],
    attendee_minutes: Counter[str],
) -> dict[str, Any]:
    return {
        "email": email,
        "display_name": attendee_names.get(email),
        "domain": _email_domain(email),
        "meeting_count": attendee_meetings[email],
        "estimated_minutes": round(attendee_minutes[email], 1),
    }


def aggregate_calendar_events(
    events: list[dict[str, Any]],
    *,
    user_email: str,
    user_domain: str,
    top_n: int = 20,
    max_attendees_for_network: int = 500,
) -> dict[str, Any]:
    user_email = user_email.strip().lower()
    user_domain = user_domain.strip().lower()

    attendee_meetings: Counter[str] = Counter()
    attendee_minutes: Counter[str] = Counter()
    attendee_names: dict[str, str] = {}
    domain_meetings: Counter[str] = Counter()
    external_meetings = 0
    internal_meetings = 0
    events_with_attendees = 0
    total_minutes = 0.0

    for event in events:
        if event.get("status") == "cancelled":
            continue
        attendees = event.get("attendees") or []
        if len(attendees) < 2:
            continue
        events_with_attendees += 1
        minutes = _parse_event_minutes(event)
        total_minutes += minutes

        others = []
        for att in attendees:
            if not isinstance(att, dict):
                continue
            email = (att.get("email") or "").strip().lower()
            if not email or "@" not in email or email == user_email:
                continue
            if att.get("responseStatus") == "declined":
                continue
            others.append(email)
            if att.get("displayName"):
                attendee_names.setdefault(email, str(att["displayName"]))

        if not others:
            continue

        has_external = False
        has_internal = False
        for email in others:
            attendee_meetings[email] += 1
            attendee_minutes[email] += minutes
            dom = _email_domain(email)
            if dom:
                domain_meetings[dom] += 1
            if user_domain and dom == user_domain:
                has_internal = True
            elif dom:
                has_external = True

        if has_external:
            external_meetings += 1
        if has_internal:
            internal_meetings += 1

    ranked = attendee_meetings.most_common()
    cap = max(1, max_attendees_for_network)
    all_attendees = [
        _attendee_row(
            email,
            attendee_names=attendee_names,
            attendee_meetings=attendee_meetings,
            attendee_minutes=attendee_minutes,
        )
        for email, _count in ranked[:cap]
    ]
    top_attendees = all_attendees[:top_n]

    return {
        "events_scanned": len(events),
        "events_with_other_attendees": events_with_attendees,
        "estimated_meeting_minutes": round(total_minutes, 1),
        "unique_other_attendees": len(attendee_meetings),
        "meetings_with_external_domains": external_meetings,
        "meetings_with_same_domain": internal_meetings,
        "top_attendees": top_attendees,
        "all_attendees": all_attendees,
        "top_attendee_domains": domain_meetings.most_common(12),
    }


async def _list_calendar_ids(client: httpx.AsyncClient, access_token: str, max_calendars: int) -> list[str]:
    resp = await client.get(
        f"{CALENDAR_API}/users/me/calendarList",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"minAccessRole": "reader"},
    )
    if resp.status_code >= 400:
        return ["primary"]
    items = resp.json().get("items") or []
    ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cid = item.get("id")
        if cid:
            ids.append(cid)
        if len(ids) >= max_calendars:
            break
    return ids or ["primary"]


async def _fetch_events_for_calendar(
    client: httpx.AsyncClient,
    access_token: str,
    calendar_id: str,
    *,
    time_min: str,
    time_max: str,
    max_events: int,
    collected: list[dict[str, Any]],
) -> None:
    page_token: str | None = None
    while len(collected) < max_events:
        params: dict[str, Any] = {
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": min(250, max_events - len(collected)),
            "fields": "nextPageToken,items(id,status,start,end,attendees(email,displayName,responseStatus))",
        }
        if page_token:
            params["pageToken"] = page_token

        cal_id = quote(calendar_id, safe="")
        resp = await client.get(
            f"{CALENDAR_API}/calendars/{cal_id}/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        if resp.status_code == 404:
            return
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items") or []:
            if isinstance(item, dict):
                collected.append(item)
            if len(collected) >= max_events:
                break
        page_token = data.get("nextPageToken")
        if not page_token:
            break


async def fetch_calendar_aggregates(
    settings: Settings,
    access_token: str,
    *,
    user_email: str,
    user_domain: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    lookback = max(7, settings.google_calendar_lookback_days)
    time_min = (now - timedelta(days=lookback)).isoformat().replace("+00:00", "Z")
    time_max = now.isoformat().replace("+00:00", "Z")

    events: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        calendar_ids = await _list_calendar_ids(
            client, access_token, settings.google_calendar_max_calendars
        )
        for cid in calendar_ids:
            await _fetch_events_for_calendar(
                client,
                access_token,
                cid,
                time_min=time_min,
                time_max=time_max,
                max_events=settings.google_calendar_max_events - len(events),
                collected=events,
            )
            if len(events) >= settings.google_calendar_max_events:
                break

    normalized = aggregate_calendar_events(
        events,
        user_email=user_email,
        user_domain=user_domain,
        top_n=settings.google_calendar_top_attendees,
        max_attendees_for_network=settings.calendar_network_max_attendees_for_network,
    )
    return {
        "status": "ok",
        "window": {"start": time_min, "end": time_max, "lookback_days": lookback},
        "calendars_scanned": len(calendar_ids),
        "normalized": normalized,
    }


async def enrich_google_calendar(
    *,
    access_token: str | None,
    oauth: dict[str, Any],
    user_email: str,
    user_domain: str,
    settings: Settings,
) -> dict[str, Any]:
    if not settings.google_calendar_enabled:
        return {"status": "not_configured"}

    if not access_token:
        return {
            "status": "reauth_required",
            "message": "Re-link Google to grant Calendar read access.",
        }

    try:
        result = await fetch_calendar_aggregates(
            settings,
            access_token,
            user_email=user_email,
            user_domain=user_domain,
        )
        return result
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            if oauth.get("refresh_token"):
                refreshed = await refresh_google_access_token(settings, oauth["refresh_token"])
                if refreshed.get("ok"):
                    return await fetch_calendar_aggregates(
                        settings,
                        refreshed["access_token"],
                        user_email=user_email,
                        user_domain=user_domain,
                    )
            return {"status": "unauthorized", "message": "Calendar token expired; re-link Google."}
        if exc.response.status_code == 403:
            return {
                "status": "forbidden",
                "message": "Enable Google Calendar API in GCP and re-link Google with Calendar scope.",
            }
        return {"status": "error", "message": exc.response.text[:500]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "message": str(exc)}
