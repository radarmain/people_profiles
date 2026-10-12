from typing import Any

import httpx

MAX_PUBLIC_CHANNELS = 40


async def _slack_api(
    client: httpx.AsyncClient,
    *,
    token: str,
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resp = await client.get(
        f"https://slack.com/api/{method}",
        params=params or {},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    if not data.get("ok"):
        return {"ok": False, "error": data.get("error"), "raw": data}
    return data


def _normalize_user(user: dict[str, Any]) -> dict[str, Any]:
    profile = user.get("profile") or {}
    return {
        "id": user.get("id"),
        "real_name": user.get("real_name"),
        "display_name": profile.get("display_name") or profile.get("real_name"),
        "title": profile.get("title"),
        "status_text": profile.get("status_text"),
        "status_emoji": profile.get("status_emoji"),
        "phone": profile.get("phone"),
        "email": profile.get("email"),
        "timezone": user.get("tz") or profile.get("tz"),
        "timezone_label": user.get("tz_label"),
        "is_admin": user.get("is_admin"),
        "is_owner": user.get("is_owner"),
        "updated": user.get("updated"),
        "fields": profile.get("fields") or {},
    }


def _normalize_team(team: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": team.get("id"),
        "name": team.get("name"),
        "domain": team.get("domain"),
        "email_domain": team.get("email_domain"),
        "icon": (team.get("icon") or {}).get("image_88"),
    }


def _normalize_channels(channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for ch in channels:
        topic = (ch.get("topic") or {}).get("value") or ""
        purpose = (ch.get("purpose") or {}).get("value") or ""
        out.append(
            {
                "id": ch.get("id"),
                "name": ch.get("name"),
                "num_members": ch.get("num_members"),
                "is_member": ch.get("is_member"),
                "is_general": ch.get("is_general"),
                "topic": topic[:200] if topic else None,
                "purpose": purpose[:200] if purpose else None,
            }
        )
    return out


async def enrich_slack(*, access_token: str, slack_user_id: str) -> dict[str, Any]:
    enriched: dict[str, Any] = {
        "user_id": slack_user_id,
        "user": None,
        "team": None,
        "public_channels": [],
        "errors": [],
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        info = await _slack_api(client, token=access_token, method="users.info", params={"user": slack_user_id})
        if info.get("ok") is False:
            enriched["errors"].append(f"users.info: {info.get('error')}")
        else:
            user = info.get("user") or {}
            enriched["user"] = _normalize_user(user)

        profile = await _slack_api(
            client,
            token=access_token,
            method="users.profile.get",
            params={"user": slack_user_id},
        )
        if profile.get("ok") is False:
            enriched["errors"].append(f"users.profile.get: {profile.get('error')}")
        else:
            prof = profile.get("profile") or {}
            enriched["profile_extended"] = {
                "title": prof.get("title"),
                "phone": prof.get("phone"),
                "fields": prof.get("fields") or {},
                "status_text": prof.get("status_text"),
            }

        team = await _slack_api(client, token=access_token, method="team.info")
        if team.get("ok") is False:
            enriched["errors"].append(f"team.info: {team.get('error')}")
        else:
            enriched["team"] = _normalize_team(team.get("team") or {})

        channels: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(channels) < MAX_PUBLIC_CHANNELS:
            params: dict[str, Any] = {
                "types": "public_channel",
                "exclude_archived": "true",
                "limit": "200",
            }
            if cursor:
                params["cursor"] = cursor
            conv = await _slack_api(client, token=access_token, method="conversations.list", params=params)
            if conv.get("ok") is False:
                enriched["errors"].append(f"conversations.list: {conv.get('error')}")
                break
            batch = conv.get("channels") or []
            channels.extend(batch)
            cursor = (conv.get("response_metadata") or {}).get("next_cursor") or ""
            if not cursor:
                break

    member_channels = [c for c in channels if c.get("is_member")]
    if not member_channels:
        member_channels = channels

    enriched["public_channels"] = _normalize_channels(member_channels[:MAX_PUBLIC_CHANNELS])
    enriched["public_channel_stats"] = {
        "listed": len(channels),
        "included_in_profile": len(enriched["public_channels"]),
        "member_of": sum(1 for c in channels if c.get("is_member")),
    }
    return enriched
