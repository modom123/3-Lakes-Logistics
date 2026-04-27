"""Step handler dispatch table.

Each domain registers its handlers here. The executor imports
HANDLER_MAP and routes step numbers to their concrete functions.
"""
from __future__ import annotations

from .onboarding import ONBOARDING_HANDLERS
from .dispatch import DISPATCH_HANDLERS_PART1

HandlerFn = None  # resolved at call time

HANDLER_MAP: dict = {
    **ONBOARDING_HANDLERS,
    **DISPATCH_HANDLERS_PART1,
}
