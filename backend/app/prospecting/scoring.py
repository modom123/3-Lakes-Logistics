"""Lead scoring 0-100 (Stage 5 recalibration of step 44).

Signals:
  owner-op or small fleet (1-10 trucks)     +30
  DOT < 180 days old                        +20
  MC active (interstate)                    +20
  phone present                             +10
  email present                             +10
  equipment matches Founders categories     +10
Max 100.
"""
from __future__ import annotations

from typing import Any

FOUNDERS_EQUIPMENT = {"dry_van", "reefer", "flatbed", "step_deck",
                      "box26", "cargo_van", "tanker_hazmat", "hotshot", "auto"}


def score_lead(lead: dict[str, Any]) -> int:
    score = 0
    fleet = lead.get("fleet_size")
    if isinstance(fleet, int) and 1 <= fleet <= 10:
        score += 30
    dot_age = lead.get("dot_age_days")
    if isinstance(dot_age, (int, float)) and dot_age < 180:
        score += 20
    if lead.get("mc_number"):
        score += 20
    if lead.get("phone"):
        score += 10
    if lead.get("email"):
        score += 10
    equipment = lead.get("equipment_types") or []
    if any(e in FOUNDERS_EQUIPMENT for e in equipment):
        score += 10
    return min(score, 100)
