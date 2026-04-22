"""19 AI agent personas. Each module is self-contained and callable
through agent_router.dispatch(). See prompts.py for system prompts.
"""
from . import (
    atlas,     # master orchestrator
    audit,     # credit checks, fuel advances
    beacon,    # executive summaries
    echo,      # SMS driver support
    motive_webhook,  # ELD webhook fan-in
    nova,      # broker check-call emails
    orbit,     # geofence arrivals
    penny,     # Stripe billing
    prompts,   # all 19 system prompts
    pulse,     # weekly fleet wellness
    router,    # agent_router
    scout,     # OCR for BOL/Rate Con
    settler,   # weekly driver payouts
    shield,    # FMCSA safety
    signal,    # emergency 800-number
    sonny,     # load board scraper
    vance,     # outbound prospecting voice
)

__all__ = [
    "atlas", "audit", "beacon", "echo", "motive_webhook", "nova",
    "orbit", "penny", "prompts", "pulse", "router", "scout", "settler",
    "shield", "signal", "sonny", "vance",
]
