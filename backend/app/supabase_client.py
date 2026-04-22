"""Global Supabase client (step 14).

Uses the service-role key so backend code can bypass RLS. Never expose
this client to a browser.
"""
from functools import lru_cache

from supabase import Client, create_client

from .settings import get_settings


@lru_cache
def get_supabase() -> Client:
    s = get_settings()
    if not s.supabase_url or not s.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
        )
    return create_client(s.supabase_url, s.supabase_service_role_key)
