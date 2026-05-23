"""Studio REST API — browse marketing assets and retrieve brand copy.

Endpoints:
  GET /api/studio/assets              — full asset catalog + brand stats
  GET /api/studio/assets/{name}       — serve the actual file (HTML/PNG/etc.)
  GET /api/studio/copy                — all channel copy
  GET /api/studio/copy?channel=sms    — copy for one channel
  GET /api/studio/email-template      — email-safe HTML for campaigns
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..api.deps import require_bearer
from .registry import ASSETS, BRAND_STATS, BRAND_TAGLINE, BRAND_VALUE_PROP, CHANNEL_COPY, BOOKING_URL, WEBSITE_URL

router = APIRouter()

_MARKETING_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "marketing")
)


@router.get("/studio/assets")
def list_assets(_: str = Depends(require_bearer)) -> dict:
    """List all marketing assets with metadata and brand stats."""
    base = os.environ.get("API_BASE_URL", "").rstrip("/")
    assets_with_urls = []
    for a in ASSETS:
        a2 = dict(a)
        if base:
            a2["url"] = f"{base}/marketing/{a['file']}"
        assets_with_urls.append(a2)
    return {
        "ok":       True,
        "assets":   assets_with_urls,
        "stats":    BRAND_STATS,
        "tagline":  BRAND_TAGLINE,
        "value_prop": BRAND_VALUE_PROP,
    }


@router.get("/studio/assets/{name}")
def get_asset(name: str, _: str = Depends(require_bearer)):
    """Serve a marketing asset file directly."""
    asset = next((a for a in ASSETS if a["name"] == name), None)
    if not asset:
        raise HTTPException(404, f"Asset '{name}' not found. Valid: {[a['name'] for a in ASSETS]}")
    path = os.path.join(_MARKETING_DIR, asset["file"])
    if not os.path.exists(path):
        raise HTTPException(404, "Asset file not found on disk")
    return FileResponse(path)


@router.get("/studio/copy")
def get_copy(channel: str | None = None, _: str = Depends(require_bearer)) -> dict:
    """Get brand copy. Pass ?channel=sms|email|voice|social for a specific channel."""
    if channel:
        if channel not in CHANNEL_COPY:
            raise HTTPException(400, f"Unknown channel '{channel}'. Valid: {list(CHANNEL_COPY)}")
        return {"ok": True, "channel": channel, "copy": CHANNEL_COPY[channel], "stats": BRAND_STATS}
    return {
        "ok":        True,
        "copy":      CHANNEL_COPY,
        "stats":     BRAND_STATS,
        "tagline":   BRAND_TAGLINE,
        "value_prop": BRAND_VALUE_PROP,
        "booking_url": BOOKING_URL,
    }


@router.get("/studio/email-template")
def get_email_template(
    state: str = "",
    lead_name: str = "there",
    _: str = Depends(require_bearer),
) -> dict:
    """Return the email-safe HTML template populated with optional lead data."""
    from .email_template import build_html
    html = build_html(state=state, lead_name=lead_name)
    subject = (
        CHANNEL_COPY["email"]["subject_open_loads"].format(state=state)
        if state else CHANNEL_COPY["email"]["subject_pitch"]
    )
    return {"ok": True, "subject": subject, "html": html}
