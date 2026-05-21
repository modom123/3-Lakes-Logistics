"""Env-driven config. Loaded once at startup."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:8080,https://3-lakes-logistics.vercel.app,https://3-lakes-logistic.vercel.app,https://3lakeslogistics.com,https://www.3lakeslogistics.com"
    api_bearer_token: str = "taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE"

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

    # Hostinger mailboxes — IMAP (imap.hostinger.com:993) + SMTP (smtp.hostinger.com:587)
    # Set one password per mailbox. Login = full email address.
    email_loads_password: str = ""   # loads@3lakeslogistics.com
    email_sales_password: str = ""   # sales@3lakeslogistics.com
    email_info_password:  str = ""   # info@3lakeslogistics.com
    email_mark_password:  str = ""   # mark@3lakeslogistics.com
    email_cece_password:  str = ""   # cece@3lakeslogistics.com

    fmcsa_webkey: str = ""

    # US DOT open data (data.transportation.gov) — Socrata app token
    # Used by Alexander Wright agent for market intelligence
    # Free token at https://data.transportation.gov/login
    dot_api_key: str = ""

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
    adobe_client_id: str = ""
    adobe_client_secret: str = ""
    adobe_account_id: str = ""
    adobe_api_endpoint: str = "https://api.na1.adobesign.com"

    # Social media — Facebook, Instagram, LinkedIn, TikTok, YouTube
    facebook_page_id: str = ""
    facebook_access_token: str = ""
    instagram_account_id: str = ""
    linkedin_access_token: str = ""
    linkedin_organization_id: str = ""
    tiktok_access_token: str = ""
    tiktok_open_id: str = ""
    tiktok_image_url: str = ""   # public URL of a branded image to post (e.g. https://3lakeslogistics.com/social-card.png)
    youtube_access_token: str = ""  # OAuth2 token with youtube scope

    render_api_key: str = ""

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
