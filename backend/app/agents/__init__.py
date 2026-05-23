"""29 AI agent personas. Each module is self-contained and callable
through agent_router.dispatch(). See prompts.py for system prompts.
"""
from . import (
    alexander,       # DOT market intelligence (VP Market Intelligence)
    atlas,           # master orchestrator
    audit,           # credit checks, fuel advances
    beacon,          # executive summaries
    cc_gulley,       # Chief Strategy Officer — 30/60/90-day strategic roadmap
    echo,            # SMS driver support
    isabella,        # omnichannel outreach campaign builder
    james_bond,      # IEBC Consultant — tech audits, gap analysis, directives
    katerina,        # SLA / process automation auditor
    mark_odom,       # CEO Commander — daily brief, tier-3 decisions
    motive_webhook,  # ELD webhook fan-in
    naomi,           # predictive lead scoring & targeting
    nova,            # broker check-call emails
    orbit,           # geofence arrivals
    penny,           # Stripe billing
    prompts,         # all 29 system prompts
    pulse,           # weekly fleet wellness
    router,          # agent_router
    scout,           # OCR for BOL/Rate Con
    settler,         # weekly driver payouts
    shield,          # FMCSA safety
    signal,          # emergency 800-number
    sofia,           # invoice reconciliation & AR
    sonny,           # load board scraper
    vance,           # outbound prospecting voice
    victoria,        # CGO growth snapshot
    winston,         # carrier retention & at-risk monitoring
)

__all__ = [
    "alexander", "atlas", "audit", "beacon", "cc_gulley", "echo", "isabella",
    "james_bond", "katerina", "mark_odom", "motive_webhook", "naomi", "nova",
    "orbit", "penny", "prompts", "pulse", "router", "scout", "settler",
    "shield", "signal", "sofia", "sonny", "vance", "victoria", "winston",
]
