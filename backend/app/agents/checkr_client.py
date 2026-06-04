"""Checkr API client — MVR and background check integration.

Checkr is the standard for gig-economy driver screening (used by Uber, Lyft,
DoorDash, Spark, Amazon Flex). Pay-per-check, no monthly fee.

Signup: https://checkr.com  (free account, pay ~$15–40 per report)
Docs:   https://docs.checkr.com

Environment variables:
  CHECKR_API_KEY   — your Checkr API key (Basic Auth username, password blank)

Reports we use:
  mvr_standard     Motor Vehicle Record — driving history, violations, suspensions
                   Turnaround: minutes to 24h depending on state DMV.
  basic            Criminal background check (optional, recommended for NEMT)

Flow:
  1. create_candidate(name, dob, license_number, license_state, ...)
  2. create_report(candidate_id, package='mvr_standard')
  3. Checkr calls POST /api/webhooks/checkr when report is complete
  4. If report.status == 'clear' → approve driver
  5. If report.status == 'consider' or 'suspended' → deny driver
"""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings

_NAME = "checkr_client"
_BASE = "https://api.checkr.com/v1"

# Checkr uses HTTP Basic Auth: API key as username, blank password
def _auth() -> tuple[str, str]:
    key = get_settings().checkr_api_key
    if not key:
        raise RuntimeError("CHECKR_API_KEY not configured — sign up at checkr.com")
    return (key, "")


def _get(path: str, params: dict | None = None) -> Any:
    r = httpx.get(f"{_BASE}{path}", auth=_auth(), params=params or {}, timeout=20)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict | None = None) -> Any:
    r = httpx.post(f"{_BASE}{path}", auth=_auth(), json=body or {}, timeout=20)
    r.raise_for_status()
    return r.json()


# ── Candidate management ──────────────────────────────────────────────────────

def create_candidate(
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    dob: str,                   # YYYY-MM-DD
    license_number: str,
    license_state: str,         # 2-letter state code, e.g. "IL"
    zipcode: str | None = None,
) -> dict[str, Any]:
    """
    Create a Checkr candidate record.
    Returns the candidate object including candidate_id needed for report creation.
    """
    body: dict = {
        "first_name":      first_name,
        "last_name":       last_name,
        "email":           email,
        "phone":           phone,
        "dob":             dob,
        "driver_license_number": license_number,
        "driver_license_state":  license_state.upper(),
    }
    if zipcode:
        body["zipcode"] = zipcode
    try:
        result = _post("/candidates", body)
        candidate_id = result.get("id")
        log_agent(_NAME, "create_candidate", payload={"email": email}, result=str(candidate_id))
        return {"created": True, "candidate_id": candidate_id, "candidate": result}
    except httpx.HTTPStatusError as e:
        return {"created": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"created": False, "error": str(e)[:300]}


def get_candidate(candidate_id: str) -> dict[str, Any]:
    """Fetch a candidate record."""
    try:
        return _get(f"/candidates/{candidate_id}")
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


# ── Reports ───────────────────────────────────────────────────────────────────

def create_report(
    candidate_id: str,
    package: str = "mvr_standard",
    node: str | None = None,
) -> dict[str, Any]:
    """
    Order a background/MVR report for a candidate.

    Packages (configure in your Checkr dashboard):
      mvr_standard    Motor Vehicle Record only (~$15)  ← default for Light Fleet
      basic           MVR + criminal background         (~$30)  ← recommended for NEMT
      pro             Full package                      (~$40)

    node: optional Checkr node/program slug if you use them for segmentation.
    """
    body: dict = {"candidate_id": candidate_id, "package": package}
    if node:
        body["node"] = node
    try:
        result = _post("/reports", body)
        report_id = result.get("id")
        try:
            from ..cost_tracking import track_checkr as _tc
            _tc(check_type=package)
        except Exception:
            pass
        log_agent(_NAME, "create_report",
                  payload={"candidate_id": candidate_id, "package": package},
                  result=str(report_id))
        return {
            "created": True,
            "report_id": report_id,
            "status": result.get("status"),
            "package": package,
            "report": result,
        }
    except httpx.HTTPStatusError as e:
        return {"created": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"created": False, "error": str(e)[:300]}


def get_report(report_id: str) -> dict[str, Any]:
    """Fetch a report by ID. status: 'pending' | 'complete' | 'suspended'."""
    try:
        return _get(f"/reports/{report_id}")
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def adjudication(
    report_id: str,
    decision: str,  # 'engaged' (hire) or 'adverse_action' (reject)
) -> dict[str, Any]:
    """Record your hiring decision on a completed report."""
    try:
        result = _post(f"/reports/{report_id}/adjudication", {"adjudication": decision})
        log_agent(_NAME, "adjudication", payload={"report_id": report_id, "decision": decision})
        return {"recorded": True, "result": result}
    except Exception as e:  # noqa: BLE001
        return {"recorded": False, "error": str(e)[:200]}


# ── Invitations (send candidate a link to consent + enter their own info) ─────

def create_invitation(
    email: str,
    package: str = "mvr_standard",
    name: str | None = None,
) -> dict[str, Any]:
    """
    Send the candidate a Checkr-hosted consent + data-entry link.
    Useful if you don't want to collect SSN/DOB yourself.
    Checkr handles all PII collection and consent compliance.
    """
    body: dict = {"email": email, "package": package}
    if name:
        body["name"] = name
    try:
        result = _post("/invitations", body)
        log_agent(_NAME, "create_invitation", payload={"email": email, "package": package})
        return {"created": True, "invitation_url": result.get("invitation_url"), "invitation": result}
    except httpx.HTTPStatusError as e:
        return {"created": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"created": False, "error": str(e)[:300]}


# ── Webhook signature verification ───────────────────────────────────────────

def verify_webhook(payload: bytes, x_checkr_signature: str | None, secret: str) -> bool:
    """Verify Checkr webhook HMAC-SHA256 signature."""
    import hashlib
    import hmac as _hmac
    if not secret or not x_checkr_signature:
        return True  # skip if not configured
    expected = _hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return _hmac.compare_digest(expected, x_checkr_signature)


# ── Health check ──────────────────────────────────────────────────────────────

def ping() -> dict[str, Any]:
    """Verify API key works."""
    try:
        _get("/candidates", {"per_page": 1})
        return {"connected": True, "platform": "checkr"}
    except RuntimeError as e:
        return {"connected": False, "platform": "checkr", "error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"connected": False, "platform": "checkr", "error": f"HTTP {e.response.status_code}"}
    except Exception as e:  # noqa: BLE001
        return {"connected": False, "platform": "checkr", "error": str(e)[:200]}
