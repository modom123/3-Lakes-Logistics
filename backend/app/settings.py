"""Env-driven config. Loaded once at startup."""
from functools import lru_cache

from pydantic import Field
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

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_founders: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    vapi_api_key: str = ""
    vapi_assistant_id_vance: str = ""
    vapi_phone_number_id: str = ""

    elevenlabs_api_key: str = ""

    postmark_server_token: str = ""
    postmark_from_email: str = "ops@3lakeslogistics.com"

    fmcsa_webkey: str = ""

    google_maps_api_key: str = ""
    google_vision_credentials_json: str = ""

    motive_api_key: str = ""
    samsara_api_key: str = ""
    geotab_username: str = ""
    geotab_password: str = ""
    omnitracs_api_key: str = ""

    airtable_api_key: str = ""
    airtable_base_id: str = ""

    sentry_dsn: str = ""

    # Claude AI — CLM contract scanner + autonomous agents
    anthropic_api_key: str = ""

    # Supabase JWT secret — from Supabase project Settings → API → JWT Secret
    supabase_jwt_secret: str = ""

    # SendGrid — inbound email parsing for contract documents
    sendgrid_api_key: str = ""
    sendgrid_inbound_secret: str = ""

    # External load board APIs (DAT Freight, Truckstop, 123Loadboard)
    dat_api_key: str = ""
    dat_api_secret: str = ""
    truckstop_api_key: str = ""
    loadboard_123_api_key: str = ""

    # Cron — secret to protect scheduled endpoint triggers
    cron_secret: str = ""

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
