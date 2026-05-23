"""agent_router — dispatches POST /api/agents/{agent}/run calls."""
from __future__ import annotations

from typing import Any, Callable

from . import (
    alexander, atlas, audit, beacon, bond_courier, echo, isabella, james_bond,
    katerina, naomi, nova, orbit, penny, pulse, scout, settler, shield,
    signal, sofia, sonny, technical_team, vance, victoria, winston,
)

_DISPATCH: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "vance":        vance.run,
    "sonny":        sonny.run,
    "shield":       shield.run,
    "scout":        scout.run,
    "penny":        penny.run,
    "settler":      settler.run,
    "audit":        audit.run,
    "nova":         nova.run,
    "signal":       signal.run,
    "echo":         echo.run,
    "atlas":        atlas.run,
    "beacon":       beacon.run,
    "orbit":        orbit.run,
    "pulse":        pulse.run,
    "victoria":     victoria.run,
    "alexander":    alexander.run,
    "sofia":        sofia.run,
    "isabella":     isabella.run,
    "katerina":     katerina.run,
    "winston":      winston.run,
    "naomi":        naomi.run,
    "james_bond":     james_bond.run,
    "bond_courier":   bond_courier.run,
    "technical_team": technical_team.run,
}


def available_agents() -> list[str]:
    return sorted(_DISPATCH.keys())


def has(agent: str) -> bool:
    return agent in _DISPATCH


def dispatch(agent: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _DISPATCH[agent](payload)
