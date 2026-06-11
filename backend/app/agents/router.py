"""agent_router — dispatches POST /api/agents/{agent}/run calls."""
from __future__ import annotations

from typing import Any, Callable

from . import (
    alexander, atlas, audit, beacon, bond_courier, bond_devops, casey, cash, chloe_sinclair, diana_cole,
    drew, dr_james_nemt, echo, elena_ross, felix_grant, isabella, jamie_park, james_bond,
    jordan, kai, katerina, load_hunter, lucas_sterling, marcus_reid, maya, morgan_hayes,
    naomi, nova, orbit, outside_bond, penny, pulse, quinn, rex, rio, scout, settler, shield,
    signal, sofia, sonny, technical_team, vance, victor_nash, victoria, winston,
)

_DISPATCH: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "vance":          vance.run,
    "sonny":          sonny.run,
    "shield":         shield.run,
    "scout":          scout.run,
    "penny":          penny.run,
    "settler":        settler.run,
    "audit":          audit.run,
    "nova":           nova.run,
    "signal":         signal.run,
    "echo":           echo.run,
    "atlas":          atlas.run,
    "beacon":         beacon.run,
    "orbit":          orbit.run,
    "pulse":          pulse.run,
    "victoria":       victoria.run,
    "alexander":      alexander.run,
    "sofia":          sofia.run,
    "isabella":       isabella.run,
    "katerina":       katerina.run,
    "winston":        winston.run,
    "naomi":          naomi.run,
    "james_bond":       james_bond.run,
    "outside_bond":     outside_bond.run,
    "bond_courier":     bond_courier.run,
    "bond_devops":      bond_devops.run,
    "technical_team":   technical_team.run,
    "lucas_sterling":   lucas_sterling.run,
    "chloe_sinclair":   chloe_sinclair.run,
    "marcus_reid":      marcus_reid.run,
    "jamie_park":       jamie_park.run,
    # ── Load Hunter ──
    "load_hunter":    load_hunter.run,
    # ── Light Fleet workers ──
    "maya":           maya.run,
    "kai":            kai.run,
    "rio":            rio.run,
    "cash":           cash.run,
    # ── Light Fleet IEBC Executives ──
    "diana_cole":     diana_cole.run,
    "dr_james_nemt":  dr_james_nemt.run,
    "elena_ross":     elena_ross.run,
    "victor_nash":    victor_nash.run,
    "felix_grant":    felix_grant.run,
    "morgan_hayes":   morgan_hayes.run,
    # ── Broker Division ──
    "rex":            rex.run,
    "jordan":         jordan.run,
    "casey":          casey.run,
    "drew":           drew.run,
    "quinn":          quinn.run,
}


def available_agents() -> list[str]:
    return sorted(_DISPATCH.keys())


def has(agent: str) -> bool:
    return agent in _DISPATCH


def dispatch(agent: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _DISPATCH[agent](payload)
