import asyncio

from app.config import Settings
from app.models.domain import AgencyProfile
from app.services.agency import infer_agency_signals
from app.services.bedrock_knowledge_base import retrieve_for_agency
from app.storage.base import ProfileStore


def refresh_agency_rollups(store: ProfileStore, agency: AgencyProfile) -> AgencyProfile:
    agency.inferred = infer_agency_signals(store, agency)
    agency.member_count = len(agency.member_user_ids)
    agency.touch()
    store.save_agency(agency)
    return agency


async def enrich_agency_for_summary(
    store: ProfileStore, settings: Settings, agency: AgencyProfile
) -> AgencyProfile:
    agency = refresh_agency_rollups(store, agency)

    if settings.bedrock_kb_configured:
        try:
            agency.knowledge_base = await asyncio.to_thread(retrieve_for_agency, settings, agency)
        except Exception as exc:  # noqa: BLE001
            agency.knowledge_base = {"status": "error", "message": str(exc)}
        store.save_agency(agency)

    return agency
