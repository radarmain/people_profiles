from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _strip_inline_env_comment(value: object) -> object:
    if isinstance(value, str):
        return value.split("#", 1)[0].strip()
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_secret_key: str = "dev-only-change-me"
    app_base_url: str = "http://127.0.0.1:8080"
    environment: str = "local"
    # Comma-separated emails allowed to access /admin (empty = no admins)
    admin_emails: str = ""

    storage_backend: str = "local"
    local_data_dir: str = ".data"

    aws_profile: str | None = "concrete"
    aws_region: str = "us-east-1"
    aws_kb_region: str = ""
    dynamodb_endpoint: str | None = None
    dynamodb_users_table: str = "_user_profiles_users"
    dynamodb_agencies_table: str = "_user_profiles_agencies"

    user_profiles_offload: bool = Field(default=False, validation_alias="_USER_PROFILES_OFFLOAD")
    # When false (default), role/summary runs in the web process so the button waits for results.
    user_profiles_offload_summarize: bool = Field(
        default=False,
        validation_alias="_USER_PROFILES_OFFLOAD_SUMMARIZE",
    )
    user_profiles_jobs_queue_url: str = Field(default="", validation_alias="_USER_PROFILES_JOBS_QUEUE_URL")
    user_profiles_worker_function_name: str = Field(
        default="_user_profiles_worker",
        validation_alias="_USER_PROFILES_WORKER_FUNCTION_NAME",
    )

    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_scopes: str = (
        "openid email profile "
        "https://www.googleapis.com/auth/user.organization.read "
        "https://www.googleapis.com/auth/user.phonenumbers.read "
        "https://www.googleapis.com/auth/userinfo.profile "
        "https://www.googleapis.com/auth/calendar.readonly"
    )
    google_oauth_prompt_consent: bool = False

    google_calendar_enabled: bool = True
    google_calendar_lookback_days: int = 90
    google_calendar_max_events: int = 400
    google_calendar_max_calendars: int = 5
    google_calendar_top_attendees: int = 20

    calendar_network_enabled: bool = True
    calendar_network_create_provisional: bool = True
    calendar_network_max_attendees_for_network: int = 500
    calendar_network_max_new_provisionals_per_sync: int = 25

    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_user_scopes: str = (
        "users:read,users:read.email,users.profile:read,team:read,channels:read"
    )

    hibob_service_user_id: str = ""
    hibob_service_user_token: str = ""
    hibob_api_base: str = "https://api.hibob.com/v1"

    bedrock_model_id: str = "amazon.nova-lite-v1:0"
    llm_fallback_without_bedrock: bool = True

    bedrock_knowledge_base_id: str = ""
    # managed = Bedrock Managed KB (default); vector = self-hosted vector store KB; auto = try both
    bedrock_kb_search_mode: str = "managed"
    bedrock_kb_number_of_results: int = 8
    bedrock_kb_max_queries: int = 4
    bedrock_kb_max_merged_results: int = 12
    bedrock_kb_max_chunk_chars: int = 1500

    linkedin_lookup_enabled: bool = True
    linkedin_lookup_min_confidence: float = 0.72
    linkedin_lookup_max_candidates: int = 10
    linkedin_lookup_max_search_queries: int = 4
    linkedin_lookup_model_id: str = ""

    web_search_provider: str = "auto"
    web_search_max_results: int = 8
    tavily_api_key: str = ""

    @field_validator("aws_region", "aws_kb_region", mode="before")
    @classmethod
    def clean_aws_region(cls, value: object) -> object:
        return _strip_inline_env_comment(value)

    @field_validator("dynamodb_endpoint", mode="before")
    @classmethod
    def empty_dynamodb_endpoint_is_aws(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = _strip_inline_env_comment(value)
            if not cleaned:
                return None
            return cleaned
        return value

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def slack_configured(self) -> bool:
        return bool(self.slack_client_id and self.slack_client_secret)

    @property
    def hibob_configured(self) -> bool:
        return bool(self.hibob_service_user_id and self.hibob_service_user_token)

    @property
    def bedrock_kb_region(self) -> str:
        """Region for Bedrock Knowledge Base Retrieve (can differ from AWS_REGION)."""
        raw = (self.aws_kb_region or self.aws_region).strip()
        return raw.split("#", 1)[0].strip()

    @property
    def bedrock_kb_configured(self) -> bool:
        return bool(self.bedrock_knowledge_base_id.strip())

    @property
    def web_search_available(self) -> bool:
        if self.tavily_api_key.strip():
            return True
        return self.web_search_provider in ("auto", "duckduckgo")


@lru_cache
def get_settings() -> Settings:
    return Settings()
