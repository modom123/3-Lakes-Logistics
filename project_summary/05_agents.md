# 05 — AI Agents

Modules in `backend/app/agents/`. Dispatch through `router.py`; shared
system prompts in `prompts.py`. Each agent is a stub in Phase 2 (Stage 3 of
the 60-day plan) ready to be deepened in Stage 5.

| Agent | File | Role |
|-------|------|------|
| Vance | `vance.py` | Head of AI Ops — top-level orchestration |
| Sonny | `sonny.py` | Dispatch + load matching |
| Shield | `shield.py` | Compliance & insurance monitoring |
| Scout | `scout.py` | Prospecting intake & qualification |
| Penny | `penny.py` | Finance / billing |
| Settler | `settler.py` | Driver settlements & payouts |
| Audit | `audit.py` | Document audits, COI / W-9 parsing |
| Nova | `nova.py` | Driver experience / support |
| Signal | `signal.py` | Outbound comms (email/SMS/voice) |
| Echo | `echo.py` | Inbound comms triage |
| Atlas | `atlas.py` | Routing & geography |
| Beacon | `beacon.py` | Safety alerts / Shield companion |
| Orbit | `orbit.py` | Lifecycle / reactivation |
| Pulse | `pulse.py` | KPI + health monitoring |

## Supporting
- `router.py` — maps task intent → agent → tool call
- `prompts.py` — system prompts + persona sheets
- `motive_webhook.py` — Motive ELD inbound webhook handler
