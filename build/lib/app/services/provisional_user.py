"""Create and merge provisional (pre-login) user profiles discovered via calendar."""

from __future__ import annotations

import hashlib
from typing import Any

from app.models.domain import UserProfile, utc_now
from app.services.agency import domain_from_email, ensure_user_agency
from app.services.safe_dict import as_dict
from app.storage.base import ProfileStore


def provisional_user_id_for_email(email: str) -> str:
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:24]
    return f"prov_{digest}"


def create_provisional_from_calendar(
    store: ProfileStore,
    *,
    email: str,
    display_name: str | None,
    discovered_by_user_id: str,
) -> tuple[UserProfile, bool]:
    """
    Ensure a provisional user exists for email.

    Returns (user, created) where created is True only when a new record was written.
    """

    normalized = email.strip().lower()
    existing = store.get_user_by_email(normalized)
    if existing:
        return existing, False

    user_id = provisional_user_id_for_email(normalized)
    by_id = store.get_user(user_id)
    if by_id:
        return by_id, False

    user = UserProfile(
        user_id=user_id,
        email=normalized,
        email_domain=domain_from_email(normalized),
        display_name=display_name or None,
        account_kind="provisional",
        google={
            "discovered_via": "calendar",
            "discovered_by_user_id": discovered_by_user_id,
            "discovered_at": utc_now().isoformat(),
        },
    )
    store.save_user(user)
    ensure_user_agency(store, user)
    return store.get_user(user_id) or user, True


def _rewrite_edge_user_ids(edges: list[Any], *, old_id: str, new_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        row = dict(edge)
        if row.get("other_user_id") == old_id:
            row["other_user_id"] = new_id
            row["other_account_kind"] = "member"
        out.append(row)
    return out


def rewrite_association_refs(
    store: ProfileStore,
    *,
    old_user_id: str,
    new_user_id: str,
    edge_peer_ids: list[str],
) -> None:
    """Update other users' network edges that pointed at the provisional id."""

    for peer_id in edge_peer_ids:
        if peer_id in (old_user_id, new_user_id):
            continue
        peer = store.get_user(peer_id)
        if not peer:
            continue
        assoc = as_dict(peer.network_associations)
        edges = assoc.get("edges") or []
        if not isinstance(edges, list):
            continue
        rewritten = _rewrite_edge_user_ids(edges, old_id=old_user_id, new_id=new_user_id)
        if rewritten != edges:
            assoc["edges"] = rewritten
            assoc["updated_at"] = utc_now().isoformat()
            peer.network_associations = assoc
            store.save_user(peer)


def merge_provisional_into_member(
    store: ProfileStore,
    *,
    provisional: UserProfile,
    google_sub: str,
    email: str,
    display_name: str | None,
    picture_url: str | None,
    google_bundle: dict[str, Any],
) -> UserProfile:
    """Promote a provisional profile to a Google-authenticated member keyed by sub."""

    old_id = provisional.user_id
    peer_ids = [
        str(e.get("other_user_id"))
        for e in (as_dict(provisional.network_associations).get("edges") or [])
        if isinstance(e, dict) and e.get("other_user_id")
    ]

    member = UserProfile(
        user_id=google_sub,
        email=email.strip().lower(),
        email_domain=domain_from_email(email),
        display_name=display_name or provisional.display_name,
        picture_url=picture_url or provisional.picture_url,
        account_kind="member",
        google=google_bundle,
        slack=as_dict(provisional.slack),
        hibob=as_dict(provisional.hibob),
        internal=as_dict(provisional.internal),
        knowledge_base=as_dict(provisional.knowledge_base),
        linkedin=as_dict(provisional.linkedin),
        work_profile=as_dict(provisional.work_profile),
        network_associations=as_dict(provisional.network_associations),
        slack_connected=provisional.slack_connected,
        slack_connect_bypassed=provisional.slack_connect_bypassed,
        agency_id=provisional.agency_id,
        llm_summary=provisional.llm_summary,
        llm_summary_generated_at=provisional.llm_summary_generated_at,
        work_profile_generated_at=provisional.work_profile_generated_at,
        processing_status=as_dict(provisional.processing_status),
        created_at=provisional.created_at,
    )

    # Preserve discovery metadata under google without clobbering oauth.
    discovered = {
        k: v
        for k, v in as_dict(provisional.google).items()
        if k.startswith("discovered_")
    }
    if discovered:
        member.google = {**discovered, **google_bundle}

    store.save_user(member)
    ensure_user_agency(store, member)

    # Agency membership: replace provisional id with Google sub.
    if member.agency_id:
        agency = store.get_agency(member.agency_id)
        if agency and old_id in agency.member_user_ids:
            agency.member_user_ids = [
                google_sub if uid == old_id else uid for uid in agency.member_user_ids
            ]
            if google_sub not in agency.member_user_ids:
                agency.member_user_ids.append(google_sub)
            agency.member_count = len(set(agency.member_user_ids))
            # Deduplicate while preserving order
            seen: set[str] = set()
            deduped: list[str] = []
            for uid in agency.member_user_ids:
                if uid not in seen:
                    seen.add(uid)
                    deduped.append(uid)
            agency.member_user_ids = deduped
            agency.member_count = len(deduped)
            store.save_agency(agency)

    rewrite_association_refs(
        store,
        old_user_id=old_id,
        new_user_id=google_sub,
        edge_peer_ids=peer_ids,
    )

    if old_id != google_sub:
        store.delete_user(old_id)

    return store.get_user(google_sub) or member
