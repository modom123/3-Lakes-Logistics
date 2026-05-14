"""Step 22: agent_router. EAGLE EYE buttons call
POST /api/agents/{agent}/run which dispatches here.
"""
from __future__ import annotations

from typing import Any, Callable

from . import (
    atlas, audit, beacon, echo, nova, orbit, penny, pulse,
    scout, settler, shield, signal, sonny, vance,
)

_DISPATCH: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "vance":   vance.run,
    "sonny":   sonny.run,
    "shield":  shield.run,
    "scout":   scout.run,
    "penny":   penny.run,
    "settler": settler.run,
    "audit":   audit.run,
    "nova":    nova.run,
    "signal":  signal.run,
    "echo":    echo.run,
    "atlas":   atlas.run,
    "beacon":  beacon.run,
    "orbit":   orbit.run,
    "pulse":   pulse.run,
}


def available_agents() -> list[str]:
    return sorted(_DISPATCH.keys())


def has(agent: str) -> bool:
    return agent in _DISPATCH


def dispatch(agent: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _DISPATCH[agent](payload)
