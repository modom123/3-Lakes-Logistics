"""Step 44: Lead Scoring (1-10).

ICP heuristics:
  + owner-op or small fleet (1-10 trucks)   → +3
  + DOT <180 days old (new authority)        → +2
  + MC active (interstate)                   → +2
  + phone present                            → +1
  + email present                            → +1
  + equipment match our Founders categories  → +1
Max 10.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

FOUNDERS_EQUIPMENT = {"dry_van", "reefer", "flatbed", "step_deck",
                      "box26", "cargo_van", "tanker_hazmat", "hotshot", "auto"}


def score_lead(lead: dict[str, Any]) -> int:
    score = 0
    fleet = lead.get("fleet_size")
    if isinstance(fleet, int) and 1 <= fleet <= 10:
        score += 3
    if lead.get("dot_age_days") and lead["dot_age_days"] < 180:
        score += 2
    if lead.get("mc_number"):
        score += 2
    if lead.get("phone"):
        score += 1
    if lead.get("email"):
        score += 1
    equipment = lead.get("equipment_types") or []
    if any(e in FOUNDERS_EQUIPMENT for e in equipment):
        score += 1
    return min(score, 10)
