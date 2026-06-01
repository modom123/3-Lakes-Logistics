"""Onboarding status endpoints — public carrier view + staff Eagle Eye view."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..logging_service import get_logger

log = get_logger("3ll.api.onboarding_status")
router = APIRouter()
_bearer = HTTPBearer(auto_error=False)


def _require_auth(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    """Simple bearer token check — any non-empty token is accepted (internal API)."""
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Bearer token required")
    return creds.credentials


# ── GET /api/onboarding/status/{carrier_id} — PUBLIC ─────────────────────────

@router.get("/onboarding/status/{carrier_id}", tags=["onboarding-status"])
async def get_onboarding_status(carrier_id: str):
    """Public endpoint — returns a carrier's current onboarding phase.

    Used by the carrier-facing status page (no auth required).
    """
    try:
        from ..onboarding.phase_tracker import get_carrier_phase
        data = get_carrier_phase(carrier_id)
        return {
            "carrier_id": carrier_id,
            **data,
        }
    except Exception as exc:
        log.error("get_onboarding_status error for %s: %s", carrier_id, exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve onboarding status")


# ── GET /api/onboarding/all-progress — REQUIRES AUTH ─────────────────────────

@router.get("/onboarding/all-progress", tags=["onboarding-status"])
async def get_all_onboarding_progress(_token: str = Depends(_require_auth)):
    """Staff endpoint — returns phase status for all active carriers.

    Used by Eagle Eye dashboard's Onboarding Progress panel.
    """
    try:
        from ..onboarding.phase_tracker import get_all_carriers_phases
        carriers = get_all_carriers_phases()
        return {"carriers": carriers, "total": len(carriers)}
    except Exception as exc:
        log.error("get_all_onboarding_progress error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve carrier phases")


# ── POST /api/onboarding/resend-email/{carrier_id} — REQUIRES AUTH ───────────

@router.post("/onboarding/resend-email/{carrier_id}", tags=["onboarding-status"])
async def resend_onboarding_email(carrier_id: str, _token: str = Depends(_require_auth)):
    """Staff endpoint — resends the current phase email to a carrier.

    Forces a resend by clearing the idempotency record first.
    """
    try:
        from ..onboarding.phase_tracker import get_carrier_phase, advance_phase_notification
        from ..supabase_client import get_supabase

        # Get current phase
        phase_data = get_carrier_phase(carrier_id)
        current_phase = phase_data.get("phase", 1)

        # Clear idempotency so the email actually sends
        sb = None
        try:
            sb = get_supabase()
        except Exception:
            pass

        if sb:
            try:
                sb.table("onboarding_phase_log").delete().eq("carrier_id", carrier_id).eq("phase", current_phase).execute()
            except Exception:
                pass

        # Clear agent memory key
        try:
            from ..agents.memory import forget
            forget(f"phase_email_sent:{carrier_id}:{current_phase}")
        except Exception:
            pass

        # Resend
        advance_phase_notification(carrier_id, current_phase)

        return {
            "resent": True,
            "carrier_id": carrier_id,
            "phase": current_phase,
            "phase_name": phase_data.get("phase_name"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.error("resend_onboarding_email error for %s: %s", carrier_id, exc)
        raise HTTPException(status_code=500, detail="Failed to resend phase email")
