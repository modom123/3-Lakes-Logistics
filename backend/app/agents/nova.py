"""Nova — Step 33. Broker check-call email responder."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent


CHECK_CALL_TEMPLATE = """Hi {broker_name},

Quick update on load {load_number} ({origin} → {dest}):

  Status:   {status}
  Location: {current_location}
  ETA:      {eta}
  Driver:   {driver_name} ({driver_phone})

Reach out anytime.
— 3 Lakes Logistics Dispatch
"""


def compose_check_call(load: dict[str, Any]) -> str:
    return CHECK_CALL_TEMPLATE.format(
        broker_name=load.get("broker_name", "there"),
        load_number=load.get("load_number", "n/a"),
        origin=f"{load.get('origin_city')}, {load.get('origin_state')}",
        dest=f"{load.get('dest_city')}, {load.get('dest_state')}",
        status=load.get("status", "in_transit"),
        current_location=load.get("current_location", "en route"),
        eta=load.get("eta", "on schedule"),
        driver_name=load.get("driver_name", "on-file"),
        driver_phone=load.get("driver_phone", ""),
    )


def run(payload: dict[str, Any]) -> dict[str, Any]:
    body = compose_check_call(payload)
    log_agent("nova", "check_call_email", payload={"load": payload.get("load_number")}, result="composed")
    # TODO: send via Postmark client
    return {"agent": "nova", "subject": f"Load {payload.get('load_number')} update", "body": body}
