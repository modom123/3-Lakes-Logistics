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

    # Bland AI — outbound prospecting calls (Vance agent)
    # Much cheaper than Vapi (~$0.06/min base + Claude LLM)
    # Better for high-volume calling (1000+ calls/month)
    bland_ai_api_key: str = ""
    bland_ai_webhook_secret: str = ""
    bland_ai_org_id: str = ""

    elevenlabs_api_key: str = ""

    postmark_server_token: str = ""
    postmark_from_email: str = "ops@3lakeslogistics.com"

    # Email ingest pipeline
    sendgrid_inbound_email: str = "loads@3lakeslogistics.com"

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

    # Adobe Sign — e-signature integration
    # Use Integration Key (simpler than OAuth for backend services):
    #   Adobe Sign admin → Account → Adobe Sign API → API Information → REST API → Integration Key
    adobe_integration_key: str = ""          # Integration Key (preferred for backend)
    adobe_client_id: str = ""               # OAuth client_id (alternative)
    adobe_client_secret: str = ""           # OAuth client_secret (alternative)
    adobe_account_id: str = ""
    adobe_api_endpoint: str = "https://api.na1.adobesign.com"
    adobe_webhook_secret: str = ""          # Sent as Authorization header on callbacks
    # Template/library doc IDs — create these in Adobe Sign admin as reusable templates
    adobe_template_carrier_agreement: str = ""   # Library doc ID for Dispatch Agreement
    adobe_template_w9: str = ""                  # Library doc ID for W9 (if hosting it for carriers)

    sentry_dsn: str = ""

    # Reliability — Redis cache + backup API failover
    redis_url: str = ""
    backup_api_url: str = ""

    # Claude AI — CLM contract scanner + autonomous agents
    anthropic_api_key: str = ""

    # SendGrid — inbound email parsing for contract documents
    sendgrid_api_key: str = ""
    sendgrid_inbound_secret: str = ""

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
