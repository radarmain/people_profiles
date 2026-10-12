from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


AccountKind = Literal["member", "provisional"]

_USER_BLOB_FIELDS = (
    "google",
    "slack",
    "hibob",
    "internal",
    "knowledge_base",
    "linkedin",
    "work_profile",
    "network_associations",
    "processing_status",
)


class UserProfile(BaseModel):
    """Canonical user record keyed by Google subject (or provisional id)."""

    user_id: str
    email: str
    email_domain: str
    display_name: str | None = None
    picture_url: str | None = None

    account_kind: AccountKind = "member"

    google: dict[str, Any] = Field(default_factory=dict)
    slack: dict[str, Any] = Field(default_factory=dict)
    hibob: dict[str, Any] = Field(default_factory=dict)
    internal: dict[str, Any] = Field(default_factory=dict)
    knowledge_base: dict[str, Any] = Field(default_factory=dict)
    linkedin: dict[str, Any] = Field(default_factory=dict)
    work_profile: dict[str, Any] = Field(default_factory=dict)
    network_associations: dict[str, Any] = Field(default_factory=dict)

    slack_connected: bool = False
    slack_connect_bypassed: bool = False
    agency_id: str | None = None

    llm_summary: str | None = None
    llm_summary_generated_at: datetime | None = None
    work_profile_generated_at: datetime | None = None
    processing_status: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()

    @property
    def is_provisional(self) -> bool:
        return self.account_kind == "provisional"

    @model_validator(mode="before")
    @classmethod
    def _coerce_null_blobs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key in _USER_BLOB_FIELDS:
                if data.get(key) is None:
                    data[key] = {}
            if not data.get("account_kind"):
                data["account_kind"] = "member"
        return data


class AgencyProfile(BaseModel):
    """Agency keyed by email domain (e.g. acme.com)."""

    agency_id: str
    domain: str
    display_name: str | None = None

    member_user_ids: list[str] = Field(default_factory=list)
    member_count: int = 0

    inferred: dict[str, Any] = Field(default_factory=dict)
    knowledge_base: dict[str, Any] = Field(default_factory=dict)
    llm_summary: str | None = None
    llm_summary_generated_at: datetime | None = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()

    @model_validator(mode="before")
    @classmethod
    def _coerce_null_blobs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key in ("inferred", "knowledge_base"):
                if data.get(key) is None:
                    data[key] = {}
        return data
