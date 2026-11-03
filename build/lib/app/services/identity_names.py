"""Resolve a person's known name and reject identity mismatches (e.g. Jeff vs John)."""

from __future__ import annotations

import re
from typing import Any

from app.models.domain import UserProfile
from app.services.safe_dict import as_dict

_NAME_SPLIT = re.compile(r"[\s,|/\-_]+")


def _clean_token(token: str) -> str:
    return re.sub(r"[^a-zA-Z]", "", token or "").strip()


def parse_email_local_name(email: str) -> dict[str, str | None]:
    """
    Best-effort parse of email local part into given/family hints.

    Examples:
      jeff.lewis -> given=Jeff, family=Lewis
      jlewis     -> given_initial=J, family=Lewis
      jefflewis  -> ambiguous (returned as family-only when trailing capital pattern fails)
    """

    local = email.split("@", 1)[0].strip().lower() if email and "@" in email else ""
    local = re.sub(r"\+.*$", "", local)
    if not local:
        return {"given": None, "given_initial": None, "family": None, "display_hint": None}

    if "." in local or "_" in local or "-" in local:
        parts = [p for p in re.split(r"[._-]+", local) if p]
        if len(parts) >= 2:
            given = parts[0].title()
            family = parts[-1].title()
            return {
                "given": given,
                "given_initial": given[0].upper() if given else None,
                "family": family,
                "display_hint": f"{given} {family}",
            }

    # Pattern: jlewis / jlewis2 -> initial + family
    m = re.match(r"^([a-z])([a-z]{2,})(\d*)$", local)
    if m:
        initial = m.group(1).upper()
        family = m.group(2).title()
        return {
            "given": None,
            "given_initial": initial,
            "family": family,
            "display_hint": f"{initial} {family}",
        }

    return {
        "given": None,
        "given_initial": local[0].upper() if local else None,
        "family": None,
        "display_hint": local.title() if local else None,
    }


def known_identity(user: UserProfile) -> dict[str, Any]:
    """Assemble the best known identity for matching Google / LinkedIn / search."""

    google = as_dict(user.google)
    openid = as_dict(google.get("openid"))
    people = as_dict(as_dict(google.get("people")).get("normalized"))
    hibob = as_dict(as_dict(user.hibob).get("normalized"))

    display = (
        (user.display_name or "").strip()
        or (openid.get("name") or "").strip()
        or (people.get("display_name") or "").strip()
        or (hibob.get("display_name") or "").strip()
        or None
    )
    given = (
        (openid.get("given_name") or "").strip()
        or (people.get("given_name") or "").strip()
        or (hibob.get("first_name") or "").strip()
        or None
    )
    family = (
        (openid.get("family_name") or "").strip()
        or (people.get("family_name") or "").strip()
        or (hibob.get("last_name") or "").strip()
        or None
    )

    email_parsed = parse_email_local_name(user.email or "")

    if display and (not given or not family):
        tokens = [_clean_token(t) for t in _NAME_SPLIT.split(display) if _clean_token(t)]
        if len(tokens) >= 2:
            given = given or tokens[0]
            family = family or tokens[-1]
        elif len(tokens) == 1 and len(tokens[0]) == 1:
            given = given or tokens[0]

    if not family and email_parsed.get("family"):
        family = str(email_parsed["family"])
    if not given and email_parsed.get("given"):
        given = str(email_parsed["given"])

    given_initial = None
    if given and len(given) == 1:
        given_initial = given.upper()
        given = None
    elif given:
        given_initial = given[0].upper()
    elif email_parsed.get("given_initial"):
        given_initial = str(email_parsed["given_initial"])

    if not display:
        if given and family:
            display = f"{given} {family}"
        elif email_parsed.get("display_hint"):
            display = str(email_parsed["display_hint"])

    return {
        "display_name": display,
        "given": given.title() if given else None,
        "family": family.title() if family else None,
        "given_initial": given_initial,
        "given_is_full": bool(given and len(given) >= 2),
        "email": (user.email or "").strip().lower(),
        "email_local": (user.email or "").split("@", 1)[0].lower() if user.email else "",
    }


_NAME_SUFFIXES = frozenset(
    {
        "mba",
        "phd",
        "md",
        "jd",
        "cpa",
        "cfa",
        "pmp",
        "jr",
        "sr",
        "ii",
        "iii",
        "iv",
        "esq",
    }
)


def extract_person_name_from_text(text: str | None) -> dict[str, str | None]:
    """Pull a likely 'First Last' from a LinkedIn title/snippet line."""

    if not text:
        return {"given": None, "family": None, "display_name": None}
    # "John Lewis - Winston-Salem..." or "Jeff Lewis | RADaR"
    head = re.split(r"\s[-–|•]\s", text.strip(), maxsplit=1)[0]
    # "Jeff Lewis, MBA" → drop credential/generational suffixes
    head = re.sub(r",\s*[^,]+$", "", head).strip()
    tokens = [_clean_token(t) for t in _NAME_SPLIT.split(head) if _clean_token(t)]
    while tokens and tokens[-1].lower() in _NAME_SUFFIXES:
        tokens.pop()
    if len(tokens) >= 2:
        return {
            "given": tokens[0].title(),
            "family": tokens[-1].title(),
            "display_name": f"{tokens[0].title()} {tokens[-1].title()}",
        }
    if len(tokens) == 1:
        return {"given": None, "family": tokens[0].title(), "display_name": tokens[0].title()}
    return {"given": None, "family": None, "display_name": None}


def names_compatible(identity: dict[str, Any], candidate_text: str | None) -> tuple[bool, str]:
    """
    Return (ok, reason).

    Hard-fail when a full known given name conflicts with the candidate's given name
    (Jeff Lewis vs John Lewis). When we only know an initial (jlewis → J), refuse to
    auto-accept full first-name candidates as high-confidence identity matches.
    """

    cand = extract_person_name_from_text(candidate_text)
    known_given = identity.get("given")
    known_family = identity.get("family")
    known_initial = identity.get("given_initial")
    cand_given = cand.get("given")
    cand_family = cand.get("family")

    if known_family and cand_family:
        if known_family.lower() != cand_family.lower():
            return False, f"family_mismatch:{known_family}!={cand_family}"

    if known_given and cand_given:
        if known_given.lower() != cand_given.lower():
            # Allow nicknames only if same first letter AND one is prefix? Keep strict for now.
            return False, f"given_mismatch:{known_given}!={cand_given}"

    if not known_given and known_initial and cand_given:
        # Email-only identity like jlewis: cannot distinguish Jeff vs John.
        return False, f"given_ambiguous:known_initial={known_initial},candidate={cand_given}"

    if known_family and not cand_family and candidate_text:
        if known_family.lower() not in candidate_text.lower():
            return False, f"family_not_in_text:{known_family}"

    return True, "ok"


def ensure_display_name(user: UserProfile) -> str | None:
    """Set a weak display_name from email/Google when missing; returns display_name."""

    identity = known_identity(user)
    display = identity.get("display_name")
    if display and not user.display_name:
        user.display_name = display
    elif display:
        return user.display_name or display
    return user.display_name or display
