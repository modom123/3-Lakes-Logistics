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

    # Email ingest pipeline
    sendgrid_inbound_email: str = "loads@3lakes.logistics"

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

    # Reliability — Redis cache + backup API failover
    redis_url: str = ""
    backup_api_url: str = ""

    # Claude AI — CLM contract scanner + autonomous agents
    anthropic_api_key: str = ""

    # SendGrid — inbound email parsing for contract documents
    sendgrid_api_key: str = ""
    sendgrid_inbound_secret: str = ""

    # Hostinger IMAP — internal team communications & carrier emails
    hostinger_imap_host: str = "imap.hostinger.com"
    hostinger_imap_port: int = 993
    hostinger_imap_username: str = ""
    hostinger_imap_password: str = ""
    hostinger_imap_enabled: bool = False
    hostinger_imap_poll_interval_seconds: int = 300  # 5 minutes default

    # --- Load Board API Keys (Sonny) ---
    dat_client_id: str = ""
    dat_client_secret: str = ""
    truckstop_username: str = ""
    truckstop_password: str = ""
    truckstop_partner_id: str = ""
    loadboard_123_api_key: str = ""
    truckerpath_api_key: str = ""
    direct_freight_username: str = ""
    direct_freight_password: str = ""
    uber_freight_client_id: str = ""
    uber_freight_client_secret: str = ""
    loadsmart_api_key: str = ""
    newtrul_api_key: str = ""
    flock_freight_api_key: str = ""
    jbhunt_client_id: str = ""
    jbhunt_client_secret: str = ""
    coyote_client_id: str = ""
    coyote_client_secret: str = ""
    arrive_client_id: str = ""
    arrive_client_secret: str = ""
    echo_global_api_key: str = ""
    cargo_chief_api_key: str = ""

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
