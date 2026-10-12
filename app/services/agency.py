from collections import Counter

from app.models.domain import AgencyProfile, UserProfile
from app.storage.base import ProfileStore


def domain_from_email(email: str) -> str:
    return email.split("@", 1)[1].strip().lower()


def agency_display_name(domain: str) -> str:
    label = domain.split(".", 1)[0]
    return label.replace("-", " ").title()


def ensure_user_agency(store: ProfileStore, user: UserProfile) -> AgencyProfile:
    domain = user.email_domain or domain_from_email(user.email)
    agency = store.get_agency(domain)
    if not agency:
        agency = AgencyProfile(agency_id=domain, domain=domain, display_name=agency_display_name(domain))

    if user.user_id not in agency.member_user_ids:
        agency.member_user_ids.append(user.user_id)
    agency.member_count = len(agency.member_user_ids)
    agency.inferred = infer_agency_signals(store, agency)
    store.save_agency(agency)

    user.agency_id = agency.agency_id
    store.save_user(user)
    return agency


def infer_agency_signals(store: ProfileStore, agency: AgencyProfile) -> dict:
    departments: Counter[str] = Counter()
    titles: Counter[str] = Counter()
    slack_teams: Counter[str] = Counter()

    for uid in agency.member_user_ids:
        member = store.get_user(uid)
        if not member:
            continue
        hibob = (member.hibob.get("normalized") if isinstance(member.hibob, dict) else None) or {}
        if dept := hibob.get("department"):
            departments[str(dept)] += 1
        if title := hibob.get("title"):
            titles[str(title)] += 1
        slack_raw = member.slack if isinstance(member.slack, dict) else {}
        slack_enriched = slack_raw.get("enriched")
        slack_enriched = slack_enriched if isinstance(slack_enriched, dict) else {}
        team_obj = slack_enriched.get("team")
        team = team_obj.get("name") if isinstance(team_obj, dict) else None
        if team:
            slack_teams[str(team)] += 1

    return {
        "top_departments": departments.most_common(5),
        "top_titles": titles.most_common(5),
        "slack_workspaces": slack_teams.most_common(3),
        "sample_domains": [agency.domain],
    }
