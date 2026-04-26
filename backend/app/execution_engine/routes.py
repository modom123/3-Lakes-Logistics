"""Execution Engine REST endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..api.deps import require_bearer
from ..supabase_client import get_supabase
from ..logging_service import get_logger
from .registry import STEP_REGISTRY
from .executor import run_domain, run_step

router = APIRouter()
log = get_logger("3ll.execution.routes")

_VALID_DOMAINS = {
    "onboarding", "dispatch", "transit", "settlement",
    "clm", "compliance", "analytics",
}


class RunStepRequest(BaseModel):
    carrier_id: UUID | None = None
    contract_id: UUID | None = None
    input_payload: dict = {}


class RunDomainRequest(BaseModel):
    domain: str
    carrier_id: UUID | None = None
    contract_id: UUID | None = None


@router.get("/steps")
def list_steps(domain: str | None = None):
    steps = list(STEP_REGISTRY.values())
    if domain:
        steps = [s for s in steps if s.domain == domain]
    return [
        {
            "number": s.number,
            "name": s.name,
            "domain": s.domain,
            "description": s.description,
            "auto_trigger": s.auto_trigger,
            "requires_steps": s.requires_steps,
        }
        for s in sorted(steps, key=lambda s: s.number)
    ]


@router.get("/domains")
def list_domains():
    domains: dict[str, list[int]] = {}
    for s in STEP_REGISTRY.values():
        domains.setdefault(s.domain, []).append(s.number)
    return [
        {
            "domain": d,
            "step_count": len(nums),
            "step_range": f"{min(nums)}–{max(nums)}",
        }
        for d, nums in sorted(domains.items(), key=lambda x: min(x[1]))
    ]


@router.post("/steps/{step_number}/run")
def run_single_step(
    step_number: int,
    req: RunStepRequest,
    _: str = Depends(require_bearer),
):
    if step_number not in STEP_REGISTRY:
        raise HTTPException(404, f"Step {step_number} not in registry")
    return run_step(step_number, req.carrier_id, req.contract_id, req.input_payload)


@router.post("/domain/run")
def run_domain_steps(req: RunDomainRequest, _: str = Depends(require_bearer)):
    if req.domain not in _VALID_DOMAINS:
        raise HTTPException(400, f"domain must be one of {sorted(_VALID_DOMAINS)}")
    return run_domain(req.domain, req.carrier_id, req.contract_id)


@router.get("/executions")
def list_executions(
    domain: str | None = None,
    status: str | None = None,
    carrier_id: str | None = None,
    limit: int = 100,
    _: str = Depends(require_bearer),
):
    sb = get_supabase()
    q = sb.table("execution_steps").select("*")
    if domain:
        q = q.eq("domain", domain)
    if status:
        q = q.eq("status", status)
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    return q.order("created_at", desc=True).limit(min(limit, 500)).execute().data
