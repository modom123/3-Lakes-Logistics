"""Driver Welcome Packet route — serves a personalised HTML welcome packet.

GET /api/light-fleet/drivers/{driver_id}/welcome-packet

Returns the full HTML document for the named driver, looked up from the
``light_vehicle_drivers`` Supabase table.  Protected by bearer token.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from ..supabase_client import get_supabase
from ..email.welcome_packet import generate_welcome_packet_html
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.get(
    "/drivers/{driver_id}/welcome-packet",
    response_class=HTMLResponse,
    summary="Driver welcome packet",
    tags=["light-fleet"],
)
def get_driver_welcome_packet(driver_id: str) -> HTMLResponse:
    """Return the HTML welcome packet for a single Light Fleet driver.

    The document is generated on-the-fly from the driver's current profile
    data (name, approved_services, vehicle_type).  Pass the bearer token in
    the ``Authorization`` header.
    """
    sb = get_supabase()
    res = (
        sb.table("light_vehicle_drivers")
        .select("id,name,approved_services,vehicle_type,vehicle_make,vehicle_model,vehicle_year")
        .eq("id", driver_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Driver not found")

    dr = res.data[0]
    name: str = dr.get("name") or "Driver"
    approved_services: list[str] = dr.get("approved_services") or []
    vehicle_type: str = (
        dr.get("vehicle_type")
        or " ".join(
            filter(
                None,
                [dr.get("vehicle_year"), dr.get("vehicle_make"), dr.get("vehicle_model")],
            )
        )
        or "vehicle"
    )

    html = generate_welcome_packet_html(
        name=name,
        approved_services=approved_services,
        vehicle_type=vehicle_type,
        driver_id=str(dr.get("id") or driver_id),
    )
    return HTMLResponse(content=html, status_code=200)
