"""Seed demo data for local dev + EAGLE EYE screenshots."""
from __future__ import annotations

from datetime import datetime, timezone

from app.supabase_client import get_supabase


DEMO_CARRIERS = [
    {"company_name": "Great Lakes Hauling", "dot_number": "3219847", "mc_number": "1254321",
     "phone": "+12165551001", "email": "ops@greatlakes.example", "plan": "founders", "status": "active"},
    {"company_name": "Fox Run Transport",   "dot_number": "3341122", "mc_number": "1299001",
     "phone": "+12165551002", "email": "dispatch@foxrun.example", "plan": "founders", "status": "onboarding"},
]


def main() -> None:
    sb = get_supabase()
    for c in DEMO_CARRIERS:
        sb.table("active_carriers").upsert(c, on_conflict="dot_number").execute()
    print(f"Seeded {len(DEMO_CARRIERS)} carriers.")


if __name__ == "__main__":
    main()
