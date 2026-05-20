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
    if not s.supabase_url:
        raise RuntimeError("SUPABASE_URL must be set in Render environment variables")
    # Prefer service-role key (bypasses RLS); fall back to anon key so the
    # app stays functional even if only the anon key is configured.
    key = s.supabase_service_role_key or s.supabase_anon_key
    if not key:
        raise RuntimeError(
            "Set SUPABASE_SERVICE_ROLE_KEY (preferred) or SUPABASE_ANON_KEY in Render"
        )
    return create_client(s.supabase_url, key)
