import asyncio
from .routes import router as execution_router
from .executor import run_domain


async def fire_onboarding(carrier_id: str) -> list[dict]:
    """Async wrapper — runs onboarding domain steps in a thread so the event loop stays free."""
    loop = asyncio.get_event_loop()
    from uuid import UUID
    cid = UUID(carrier_id) if carrier_id else None
    return await loop.run_in_executor(None, run_domain, "onboarding", cid, None)


__all__ = ["execution_router", "fire_onboarding"]
