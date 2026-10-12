"""Shared enrichment and summary jobs (local process or Lambda worker)."""

from app.config import Settings, get_settings
from app.models.domain import UserProfile, utc_now
from app.services.agency import ensure_user_agency
from app.services.agency_enrichment import enrich_agency_for_summary
from app.services.llm import SummaryService
from app.services.profile_builder import refresh_user_profile
from app.services.safe_dict import normalize_user_blobs
from app.services.work_profile import persist_work_profile
from app.storage.base import ProfileStore
from app.storage.factory import get_store


def _set_job_status(user: UserProfile, *, job_type: str, state: str, detail: str | None = None) -> None:
    user.processing_status = {
        "job_type": job_type,
        "state": state,
        "detail": detail,
        "updated_at": utc_now().isoformat(),
    }


async def run_enrich_job(user_id: str, store: ProfileStore | None = None, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    store = store or get_store()
    user = store.get_user(user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")
    normalize_user_blobs(user)

    _set_job_status(user, job_type="enrich", state="running")
    store.save_user(user)

    try:
        await refresh_user_profile(store, settings, user)
        user = store.get_user(user_id) or user
        _set_job_status(user, job_type="enrich", state="completed")
        store.save_user(user)
    except Exception as exc:  # noqa: BLE001
        user = store.get_user(user_id) or user
        _set_job_status(user, job_type="enrich", state="failed", detail=str(exc))
        store.save_user(user)
        raise


async def run_summarize_job(user_id: str, store: ProfileStore | None = None, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    store = store or get_store()
    user = store.get_user(user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")
    normalize_user_blobs(user)

    _set_job_status(user, job_type="summarize", state="running")
    store.save_user(user)

    try:
        await refresh_user_profile(store, settings, user)
        user = store.get_user(user_id) or user

        agency = store.get_agency(user.agency_id) if user.agency_id else None
        if not agency:
            agency = ensure_user_agency(store, user)

        persist_work_profile(settings, user, agency, store)
        user = store.get_user(user_id) or user

        summary_service = SummaryService(settings)
        summary_service.persist_user_summary(user, agency, store)

        agency = await enrich_agency_for_summary(store, settings, agency)
        user = store.get_user(user_id) or user
        summary_service.persist_agency_summary(store, agency)

        user = store.get_user(user_id) or user
        _set_job_status(user, job_type="summarize", state="completed")
        store.save_user(user)
    except Exception as exc:  # noqa: BLE001
        user = store.get_user(user_id) or user
        _set_job_status(user, job_type="summarize", state="failed", detail=str(exc))
        store.save_user(user)
        raise
