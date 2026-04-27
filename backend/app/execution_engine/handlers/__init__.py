"""Step handler dispatch table.

Each domain registers its handlers here. The executor imports
HANDLER_MAP and routes step numbers to their concrete functions.
"""
from __future__ import annotations

from typing import Callable
from uuid import UUID

from .onboarding import ONBOARDING_HANDLERS

HandlerFn = Callable[[UUID | None, UUID | None, dict], dict]

HANDLER_MAP: dict[int, HandlerFn] = {
    **ONBOARDING_HANDLERS,
}
