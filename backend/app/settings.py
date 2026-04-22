"""Env-driven config. Loaded once at startup."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    api_bearer_token: str = "change-me-in-prod"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_founders: str = ""
    stripe_price_pro: str = ""
    stripe_price_scale: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    vapi_api_key: str = ""
    vapi_webhook_secret: str = ""
    vapi_assistant_id_vance: str = ""
    vapi_phone_number_id: str = ""

    elevenlabs_api_key: str = ""

    postmark_server_token: str = ""
    postmark_from_email: str = "ops@3lakeslogistics.com"
    resend_api_key: str = ""
    ses_region: str = "us-east-1"

    fmcsa_webkey: str = ""

    google_maps_api_key: str = ""
    google_vision_credentials_json: str = ""

    motive_api_key: str = ""
    motive_webhook_secret: str = ""
    samsara_api_key: str = ""
    geotab_username: str = ""
    geotab_password: str = ""
    geotab_database: str = ""
    omnitracs_api_key: str = ""

    airtable_api_key: str = ""
    airtable_base_id: str = ""

    slack_webhook_ops: str = ""
    slack_webhook_alerts: str = ""

    pii_encryption_key: str = ""
    retention_days_leads: int = 730
    retention_days_webhooks: int = 180

    sentry_dsn: str = ""

    queue_poll_interval_sec: int = 5
    queue_max_concurrency: int = 4

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
