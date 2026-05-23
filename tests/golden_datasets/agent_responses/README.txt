Golden Dataset — Agent Responses
=================================

This directory stores the BASELINE expected responses from AI agents
when processing the rate confirmation golden datasets.

Usage:
  1. Run the agent against all golden datasets in rate_confirmations/
  2. Save the agent's JSON response as GD-XXX-response.json
  3. Future runs compare against these baselines to detect regressions

Accuracy Target: >= 80% of fields extracted correctly across all datasets.

Escalation Threshold: Any golden dataset entry where base_rate is "null"
or the document is adversarial MUST have escalate=true in the response.

Files:
  GD-001-response.json  — Expected extraction for chicago-dallas lane
  GD-002-response.json  — Expected extraction for detroit-nashville lane
  GD-003-response.json  — Expected extraction for houston-phoenix lane
  GD-004-response.json  — Expected ESCALATION for TBD rate document
  GD-005-response.json  — Expected extraction for minimal document

Adversarial Test Inputs (in test_agent_golden_datasets.py):
  ADV-001  — Prompt injection attack → MUST escalate
  ADV-002  — Conflicting rates → MUST escalate
  ADV-003  — Nonsense text → MUST escalate
  ADV-004  — Empty input → MUST escalate
  ADV-005  — Unicode attack → may or may not escalate
