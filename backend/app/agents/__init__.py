"""30 AI agent personas + 1 bridge courier. Each module is self-contained
and callable through agent_router.dispatch(). See prompts.py for system prompts.
"""
from . import (
    alexander,       # DOT market intelligence (VP Market Intelligence)
    atlas,           # master orchestrator
    audit,           # credit checks, fuel advances
    beacon,          # executive summaries
    bond_courier,    # IEBC <-> Daytona message bridge
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
    outside_bond,    # IEBC external remediation agent
    penny,           # Stripe billing
    prompts,         # all 30 system prompts
    pulse,           # weekly fleet wellness
    router,          # agent_router
    scout,           # OCR for BOL/Rate Con
    settler,         # weekly driver payouts
    shield,          # FMCSA safety
    signal,          # emergency 800-number
    sofia,           # invoice reconciliation & AR
    sonny,           # load board scraper
    technical_team,  # IEBC remediation — Winston, Isabella, Alexander + Bond escalation
    vance,           # outbound prospecting voice
    vance_follow_up, # post-call follow-up SMS/email
    victoria,        # CGO growth snapshot
    winston,         # carrier retention & at-risk monitoring
)

__all__ = [
    "alexander", "atlas", "audit", "beacon", "bond_courier", "cc_gulley",
    "echo", "isabella", "james_bond", "katerina", "mark_odom", "motive_webhook",
    "naomi", "nova", "orbit", "outside_bond", "penny", "prompts", "pulse", "router",
    "scout", "settler", "shield", "signal", "sofia", "sonny", "technical_team",
    "vance", "vance_follow_up", "victoria", "winston",
]
