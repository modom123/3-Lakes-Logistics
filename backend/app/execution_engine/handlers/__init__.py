"""Step handler dispatch table.

Each domain registers its handlers here. The executor imports
HANDLER_MAP and routes step numbers to their concrete functions.
"""
from __future__ import annotations

from .onboarding import ONBOARDING_HANDLERS
from .dispatch import DISPATCH_HANDLERS_PART1 as DISPATCH_HANDLERS
from .transit import TRANSIT_HANDLERS
from .settlement import SETTLEMENT_HANDLERS
from .lf_onboarding  import LF_ONBOARDING_HANDLERS
from .lf_dispatch    import LF_DISPATCH_HANDLERS
from .lf_transit     import LF_TRANSIT_HANDLERS
from .lf_settlement  import LF_SETTLEMENT_HANDLERS
from .lf_load_hunt   import LF_LOAD_HUNT_HANDLERS

HANDLER_MAP: dict = {
    **ONBOARDING_HANDLERS,
    **DISPATCH_HANDLERS,
    **TRANSIT_HANDLERS,
    **SETTLEMENT_HANDLERS,
    **LF_ONBOARDING_HANDLERS,
    **LF_DISPATCH_HANDLERS,
    **LF_TRANSIT_HANDLERS,
    **LF_SETTLEMENT_HANDLERS,
    **LF_LOAD_HUNT_HANDLERS,
}
