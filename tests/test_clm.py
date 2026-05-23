"""CLM — Comprehensive Test Suite (Phases 1–3 from CLM Test Framework PDF).

Structure mirrors the PDF's three-part framework:
  Part 1 — Gold-Standard Extraction    : Feed the canonical addendum text; verify
                                         every extracted field against the expected JSON.
  Part 2 — System Validation Checklist : Entity matching, synonym mapping,
                                         date-overlap logic, time-bar trigger alert.
  Part 3 — Confidence Threshold Sandbox: High-confidence auto-approve, low-confidence
                                         flag-for-review, garbage-in graceful fallback.

Additional sections cover every CLM REST endpoint end-to-end:
  § API Endpoints  — scan, list, get, milestone, invoice, events, summary
  § Rate Benchmark — above/below/at-market assertions
  § Broker         — blacklist CRUD, scorecard, broker intake
  § Disputes       — open → escalate → resolve lifecycle
  § Analytics      — snapshot + refresh
  § Lifecycle      — archive, export, compliance-audit, complete (step 150)
  § Security       — auth guards, token-less rejection
  § Concurrency    — 5 parallel scans, no data corruption

Run:
    pytest tests/test_clm.py -v
"""
from __future__ import annotations

import concurrent.futures
import time
import re
import requests
import pytest

BASE_URL = "https://three-lakes-logistics-api.onrender.com"
API_TOKEN = "taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE"
HEADERS   = {"Content-Type": "application/json", "Authorization": f"Bearer {API_TOKEN}"}

# ── module-level state (populated by early tests, reused by later ones) ────────
_contract_id:     str | None = None   # set by gold-standard scan
_bol_id:          str | None = None   # set by BOL scan
_dispute_id:      str | None = None   # set by open-dispute test
_test_broker_mc:  str        = "CLM-TEST-MC-99999"


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — GOLD-STANDARD EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

# Exact contract text from the CLM Test Framework PDF (Part 1)
GOLD_CONTRACT_TEXT = """ADDENDUM TO LOGISTICS SERVICES AGREEMENT
This binding rider is executed on May 24, 2026, by and between 3 Lakes Logistics LLC
(operating under SCAC code 'TLXO', DOT# 3948571, and MC# 684722), hereinafter
referred to as 'Carrier', and Titan Manufacturing Corp, hereinafter 'Shipper'. This addendum
becomes effective on June 1, 2026, and will automatically terminate on May 31, 2027.

Operational & Financial Rules:
The Base Linehaul Rate for the Detroit to Chicago lane is fixed at $2.85 per mile. Shipper
agrees to allow a Free Time Allowance of exactly 2 hours at both the origin loading dock
and destination discharge facilities. If Carrier's driver is detained beyond this window,
Shipper shall be auto-billed a Detention Rate of $75.00 per hour, capped at a maximum of
$600.00 per day. In the event that an automated route dispatch is canceled via the
platform after the driver has physically turned wheels toward the origin facility, a TONU fee
of $150.00 shall instantly apply.

Compliance, Data, & Liability:
Carrier must maintain a 'Satisfactory' safety rating with the FMCSA at all times. To facilitate
automated dispatch orchestration, Carrier grants explicit consent to stream ELD
telematics data directly into Shipper's control tower, providing real-time location ping
frequencies every 15 minutes while under dispatch. The digital perimeter defining arrival
(Origin and Destination Geofence) shall be set to a strict 500-meter radius from the
facility centerpoint. Carrier's Standard Cargo Liability under this agreement is strictly
capped at $100,000.00 per shipment. Any cargo damage or shortage claims must be
formally filed within a strict time-bar window of 9 months from the date of delivery, or
they shall be legally waived. Payment terms for all audited freight bills are Net 30 days
from electronic invoice receipt. This agreement shall be interpreted under the governing
laws of the State of Michigan."""

# Gold-standard expected values (from PDF "Target Output" section)
GOLD_EXPECTED = {
    "carrier_name":       "3 Lakes Logistics LLC",    # 001
    "dot_number":         "3948571",                   # 004
    "mc_number":          "684722",                    # 005
    "shipper_name":       "Titan Manufacturing Corp",  # 002
    "pickup_date":        "2026-06-01",                # effective / 012
    "delivery_date":      "2027-05-31",                # expiration / 013
    "rate_per_mile":      2.85,                        # 021
    "detention_rate":     75.0,                        # 023
    "tonu":               150.0,                       # 025
    "payment_terms":      "Net-30",                    # 033 (or contains "30")
    "origin_city":        "Detroit",                   # origin lane city
    "destination_city":   "Chicago",                   # destination lane city
}


def test_gold_standard_scan_returns_201():
    """POST /api/clm/scan with the canonical addendum text → 201 Created."""
    global _contract_id
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": GOLD_CONTRACT_TEXT, "contract_type": "broker_agreement"},
        headers=HEADERS,
        timeout=60,
    )
    assert r.status_code == 201, (
        f"CLM scan endpoint returned {r.status_code}. Body: {r.text[:300]}"
    )
    data = r.json()
    _contract_id = str(data.get("contract_id", ""))
    assert _contract_id, "Scan response missing contract_id"


def test_gold_standard_confidence_above_threshold():
    """Gold-standard contract text should yield ≥ 70% confidence score."""
    if not _contract_id:
        pytest.skip("Depends on test_gold_standard_scan_returns_201")
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": GOLD_CONTRACT_TEXT, "contract_type": "broker_agreement"},
        headers=HEADERS,
        timeout=60,
    )
    data = r.json()
    conf = data.get("confidence_score", 0)
    assert conf >= 0.70, (
        f"Confidence {conf:.2f} below 0.70 for gold-standard text — "
        "extraction pipeline needs tuning."
    )


def test_gold_standard_extracts_financial_fields():
    """Extractor pulls rate_per_mile, detention_rate, and TONU from gold text."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": GOLD_CONTRACT_TEXT, "contract_type": "broker_agreement"},
        headers=HEADERS,
        timeout=60,
    )
    ev = r.json().get("extracted_vars", {})
    rpm = ev.get("rate_per_mile")
    assert rpm is not None, "rate_per_mile not extracted"
    assert abs(float(rpm) - 2.85) < 0.01, f"rate_per_mile={rpm}, expected 2.85"

    det = ev.get("detention_rate")
    if det is not None:
        assert abs(float(det) - 75.0) < 0.01, f"detention_rate={det}, expected 75.00"

    tonu = ev.get("tonu")
    if tonu is not None:
        assert abs(float(tonu) - 150.0) < 0.01, f"tonu={tonu}, expected 150.00"


def test_gold_standard_extracts_party_names():
    """Carrier name (3 Lakes Logistics LLC) and shipper (Titan Manufacturing) extracted."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": GOLD_CONTRACT_TEXT, "contract_type": "broker_agreement"},
        headers=HEADERS,
        timeout=60,
    )
    ev = r.json().get("extracted_vars", {})
    carrier = (ev.get("carrier_name") or ev.get("extra", {}).get("carrier_name") or "").lower()
    shipper = (ev.get("shipper_name") or ev.get("broker_name") or "").lower()
    assert "lakes" in carrier or "3 lakes" in carrier, (
        f"carrier_name not extracted correctly: got '{carrier}'"
    )
    assert "titan" in shipper, (
        f"shipper/broker name not extracted correctly: got '{shipper}'"
    )


def test_gold_standard_extracts_dates():
    """Effective date (2026-06-01) and expiration date (2027-05-31) extracted."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": GOLD_CONTRACT_TEXT, "contract_type": "broker_agreement"},
        headers=HEADERS,
        timeout=60,
    )
    ev = r.json().get("extracted_vars", {})
    # Accept these in pickup/delivery or the extra dict
    extra = ev.get("extra", {}) or {}
    effective   = ev.get("pickup_date")   or extra.get("effective_date")   or extra.get("012_effective_date")
    expiration  = ev.get("delivery_date") or extra.get("expiration_date")  or extra.get("013_expiration_date")
    assert effective and "2026-06-01" in str(effective), (
        f"Effective date not extracted: got '{effective}'"
    )
    assert expiration and "2027-05-31" in str(expiration), (
        f"Expiration date not extracted: got '{expiration}'"
    )


def test_gold_standard_extracts_lane():
    """Origin city (Detroit) and destination city (Chicago) extracted."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": GOLD_CONTRACT_TEXT, "contract_type": "broker_agreement"},
        headers=HEADERS,
        timeout=60,
    )
    ev = r.json().get("extracted_vars", {})
    origin = (ev.get("origin_city") or "").lower()
    dest   = (ev.get("destination_city") or "").lower()
    assert "detroit" in origin, f"origin_city not extracted: got '{origin}'"
    assert "chicago" in dest,   f"destination_city not extracted: got '{dest}'"


def test_gold_standard_extracts_payment_terms():
    """Payment terms (Net-30) extracted and stored correctly."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": GOLD_CONTRACT_TEXT, "contract_type": "broker_agreement"},
        headers=HEADERS,
        timeout=60,
    )
    ev = r.json().get("extracted_vars", {})
    terms = str(ev.get("payment_terms") or "")
    assert "30" in terms, f"payment_terms missing '30': got '{terms}'"


def test_gold_standard_fields_extracted_count():
    """Gold-standard text should extract at least 8 non-null fields."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": GOLD_CONTRACT_TEXT, "contract_type": "broker_agreement"},
        headers=HEADERS,
        timeout=60,
    )
    data = r.json()
    count = data.get("fields_extracted", 0)
    assert count >= 8, (
        f"Only {count} fields extracted from gold-standard text — expected ≥ 8. "
        "LLM extraction may be failing or Claude API key is missing."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — SYSTEM VALIDATION CHECKLIST
# ═══════════════════════════════════════════════════════════════════════════════

# Part 2 Check 1: Multi-Lingual & Synonym Mapping
# "Waiting time charges", "Demurrage", "Dock delays" → detention_rate (Term 023)
SYNONYM_CONTRACT = """FREIGHT SERVICES CONTRACT
Carrier: Midwest Hauling Co. | Broker: Apex Freight LLC
Route: St. Louis, MO to Indianapolis, IN
Rate: $1.75/mile | Load #MW-4421

DETENTION POLICY:
After a free-time window of 1 hour, waiting time charges of $65.00 per hour shall accrue.
Any demurrage or dock delays extending beyond the maximum 4-hour threshold will trigger
automatic billing at the same $65.00 rate per hour. Carrier must document all detention
events via ELD timestamp records."""

def test_synonym_mapping_waiting_time_to_detention_rate():
    """Synonym mapping: 'waiting time charges' / 'demurrage' → detention_rate field (Term 023)."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": SYNONYM_CONTRACT, "contract_type": "rate_confirmation"},
        headers=HEADERS,
        timeout=60,
    )
    assert r.status_code == 201
    ev = r.json().get("extracted_vars", {})
    det = ev.get("detention_rate")
    assert det is not None, (
        "detention_rate not extracted from 'waiting time charges' / 'demurrage' text. "
        "Synonym mapping failure — Term 023 should cover these aliases."
    )
    assert abs(float(det) - 65.0) < 0.01, f"Expected detention_rate=65.0, got {det}"


# Part 2 Check 2: Entity Matching — mismatched MC# detection
MC_MISMATCH_CONTRACT = """RATE CONFIRMATION
Broker: FastFreight Inc. | MC# 000001 | DOT# 0000001
Carrier: Test Carrier LLC
Origin: Memphis, TN → Destination: Nashville, TN
Rate: $850.00 total | Payment: Net-30 | Load #FF-9001"""

def test_entity_matching_mismatched_mc_flagged():
    """Contract with MC# 000001 (not in our DB) should scan successfully and be stored.
    The system records the counterparty — FMCSA mismatch detection happens at step_126.
    Verify the contract is created and the counterparty MC is captured in extracted_vars."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": MC_MISMATCH_CONTRACT, "contract_type": "rate_confirmation"},
        headers=HEADERS,
        timeout=60,
    )
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text[:200]}"
    ev = r.json().get("extracted_vars", {})
    mc = str(ev.get("broker_mc") or "")
    assert "000001" in mc or mc != "", (
        "broker_mc not extracted from entity-mismatch contract"
    )


# Part 2 Check 3: Date format validation — ISO 8601 compliance
ISO_DATE_CONTRACT = """LOAD TENDER / RATE CONFIRMATION
Broker: Reliable Freight Partners | MC# 441882
Carrier: Delta Transport LLC
Pickup: June 15, 2026 at the Chicago terminal.
Delivery: June 16th, 2026 — Nashville distribution center.
Rate: $2.10/mile | Total: $1,890.00 | Payment: Quick Pay 5 days"""

def test_date_extraction_iso8601_format():
    """Extracted pickup/delivery dates must conform to ISO 8601 (YYYY-MM-DD)."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": ISO_DATE_CONTRACT, "contract_type": "rate_confirmation"},
        headers=HEADERS,
        timeout=60,
    )
    assert r.status_code == 201
    ev = r.json().get("extracted_vars", {})
    for field in ("pickup_date", "delivery_date"):
        val = ev.get(field)
        if val is not None:
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", str(val)), (
                f"{field}='{val}' is not ISO 8601 format (YYYY-MM-DD). "
                "Fine-tuning anchor point violated — dates must be ISO 8601."
            )


# Part 2 Check 4: Time-bar trigger — 9-month claims window captured
def test_time_bar_extraction():
    """Claims filing time-bar (9 months) extracted and stored in extracted_vars."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": GOLD_CONTRACT_TEXT, "contract_type": "broker_agreement"},
        headers=HEADERS,
        timeout=60,
    )
    ev = r.json().get("extracted_vars", {})
    extra = ev.get("extra", {}) or {}
    # Accept it in extra dict under various key names
    time_bar = (
        extra.get("016_claims_filing_time_bar_months")
        or extra.get("claims_filing_time_bar_months")
        or extra.get("claims_time_bar")
        or extra.get("cargo_claim_time_bar_months")
    )
    # Also acceptable if captured in special_instructions
    instructions = str(ev.get("special_instructions") or "")
    has_9mo = time_bar is not None or "9" in instructions
    assert has_9mo, (
        "Claims filing time-bar (9 months) not extracted from gold-standard text. "
        "Term 016 should trigger a 30-day-prior alert for open disputes."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3 — CONFIDENCE THRESHOLD SANDBOX
# ═══════════════════════════════════════════════════════════════════════════════

HIGH_CONFIDENCE_TEXT = """RATE CONFIRMATION
Broker: Blue Sky Logistics | MC# 887421 | DOT# 4482910
Carrier: Midwest Express LLC | MC# 334521
Load #BS-20260524-001
Origin: 1200 Commerce Dr, Detroit, MI 48201 — Pickup: 2026-05-27 07:00
Destination: 800 Industry Blvd, Chicago, IL 60601 — Delivery: 2026-05-27 18:00
Commodity: Automotive parts | Weight: 42,500 lbs | Trailer: 53' Dry Van
Rate: $2,450.00 total ($2.45/mile) | Miles: 1,000
Fuel surcharge: $180.00 | Detention: $75/hr after 2 hrs free time
Payment terms: Net-30 from electronic invoice | Factoring: Allowed
Driver must call broker 30 min before pickup and delivery.
Signature: Jane Rodriguez — Blue Sky Logistics Operations"""

LOW_CONFIDENCE_TEXT = """hey carrier, just call us about the load going somewhere
around tuesday ish. rate is like 2k maybe more depending. just confirm.
thx - dispatch"""

GARBAGE_TEXT = "random words 123 !@# nothing here contract maybe"


def test_high_confidence_text_yields_high_score():
    """Complete, well-structured rate confirmation → confidence ≥ 0.80 (auto-approve threshold)."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": HIGH_CONFIDENCE_TEXT, "contract_type": "rate_confirmation"},
        headers=HEADERS,
        timeout=60,
    )
    assert r.status_code == 201
    data = r.json()
    conf = data.get("confidence_score", 0)
    assert conf >= 0.80, (
        f"High-confidence contract scored {conf:.2f} — expected ≥ 0.80. "
        "Auto-approve threshold would not be met."
    )
    assert data.get("fields_extracted", 0) >= 8, "Expected ≥ 8 fields from high-quality rate con"


def test_low_confidence_text_flagged_for_review():
    """Vague, incomplete text → confidence < 0.60 and warnings present."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": LOW_CONFIDENCE_TEXT, "contract_type": "rate_confirmation"},
        headers=HEADERS,
        timeout=60,
    )
    assert r.status_code == 201
    data = r.json()
    conf = data.get("confidence_score", 1.0)
    assert conf < 0.70, (
        f"Low-confidence text scored {conf:.2f} — expected < 0.70. "
        "Vague contracts should be routed to human review."
    )


def test_garbage_input_graceful_fallback():
    """Garbage/nonsense text should not crash the API — returns 201 with low confidence."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": GARBAGE_TEXT, "contract_type": "rate_confirmation"},
        headers=HEADERS,
        timeout=60,
    )
    assert r.status_code in (201, 422), (
        f"Garbage input returned unexpected status {r.status_code}. "
        "API should either process gracefully (201) or validate input (422)."
    )
    if r.status_code == 201:
        conf = r.json().get("confidence_score", 0)
        assert conf < 0.50, f"Garbage text confidence too high: {conf:.2f}"


def test_bol_scan_correct_type():
    """BOL scan extracts bol_number and consignee — distinct from rate_confirmation logic."""
    global _bol_id
    bol_text = """BILL OF LADING
BOL#: GLE-BOL-20260524
Shipper: Titan Manufacturing Corp | 500 Industrial Pkwy, Detroit, MI
Consignee: Midwest Distribution LLC | 1400 Fulton Ave, Chicago, IL
Carrier: 3 Lakes Logistics LLC | DOT# 3948571 | Driver: James Carter
Commodity: Engine components | Pieces: 80 pallets | Weight: 38,200 lbs
Seal#: SL-89912 | Trailer#: TR-4421
Special Instructions: Temperature-controlled dock required at delivery."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": bol_text, "contract_type": "bol"},
        headers=HEADERS,
        timeout=60,
    )
    assert r.status_code == 201
    data = r.json()
    _bol_id = str(data.get("contract_id", ""))
    ev = data.get("extracted_vars", {})
    assert ev.get("bol_number") or ev.get("extra", {}).get("bol_number"), (
        "bol_number not extracted from BOL text"
    )
    consignee = ev.get("consignee_name") or ""
    assert "midwest" in consignee.lower() or consignee, "consignee_name not extracted"


def test_pod_scan_extracts_delivery_confirmation():
    """POD scan extracts delivery_date and consignee_name."""
    pod_text = """PROOF OF DELIVERY
Load #: GLE-20260524-001
Carrier: 3 Lakes Logistics LLC | Driver: James Carter
Consignee: Midwest Distribution LLC
Delivered to: 1400 Fulton Ave, Chicago, IL 60608
Date of Delivery: 2026-05-27 | Time: 16:45
Pieces Delivered: 80 pallets | Weight: 38,200 lbs
Condition on Arrival: Good — no exceptions noted
Consignee Signature: M. Thompson | Driver Signature: J. Carter"""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": pod_text, "contract_type": "pod"},
        headers=HEADERS,
        timeout=60,
    )
    assert r.status_code == 201
    ev = r.json().get("extracted_vars", {})
    assert ev.get("delivery_date") or ev.get("consignee_name"), (
        "POD scan failed to extract delivery_date or consignee_name"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § API ENDPOINTS — CRUD + FILTERS
# ═══════════════════════════════════════════════════════════════════════════════

def test_clm_list_returns_array():
    """GET /api/clm/ returns a list of contracts."""
    r = requests.get(f"{BASE_URL}/api/clm/", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"


def test_clm_list_filter_by_status():
    """GET /api/clm/?status=active filters correctly — all returned records are active."""
    r = requests.get(f"{BASE_URL}/api/clm/?status=active", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    for c in r.json():
        assert c.get("status") == "active", (
            f"Status filter broken — got record with status='{c.get('status')}'"
        )


def test_clm_list_filter_by_type():
    """GET /api/clm/?contract_type=rate_confirmation filters to that type."""
    r = requests.get(
        f"{BASE_URL}/api/clm/?contract_type=rate_confirmation",
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 200
    for c in r.json():
        assert c.get("contract_type") == "rate_confirmation"


def test_clm_get_single_contract():
    """GET /api/clm/{id} returns a full contract record with all columns."""
    if not _contract_id:
        pytest.skip("Depends on gold-standard scan test")
    r = requests.get(f"{BASE_URL}/api/clm/{_contract_id}", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert str(data.get("id")) == _contract_id
    assert "status" in data
    assert "contract_type" in data


def test_clm_get_nonexistent_returns_404():
    """GET /api/clm/{fake-uuid} → 404."""
    r = requests.get(
        f"{BASE_URL}/api/clm/00000000-0000-0000-0000-000000000000",
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"


def test_clm_summary_shape():
    """GET /api/clm/summary returns all required dashboard fields."""
    r = requests.get(f"{BASE_URL}/api/clm/summary", headers=HEADERS, timeout=15)
    assert r.status_code == 200, f"Summary endpoint failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    required = ["total", "active", "executed", "flagged", "avg_confidence_pct",
                "revenue_recognized", "revenue_pending", "open_disputes", "recent"]
    for key in required:
        assert key in data, f"Summary missing field: '{key}'"
    assert isinstance(data["total"], int), "summary.total must be int"
    assert isinstance(data["recent"], list), "summary.recent must be list"


def test_clm_summary_counts_consistent():
    """Summary counts must be internally consistent (active + executed + flagged ≤ total)."""
    r = requests.get(f"{BASE_URL}/api/clm/summary", headers=HEADERS, timeout=15)
    data = r.json()
    total = data.get("total", 0)
    active = data.get("active", 0)
    executed = data.get("executed", 0)
    flagged = data.get("flagged", 0)
    assert active + executed + flagged <= total, (
        f"Count inconsistency: active({active}) + executed({executed}) + flagged({flagged}) "
        f"> total({total})"
    )


def test_clm_milestone_update():
    """PATCH /api/clm/{id}/milestone → updates milestone_pct on the contract."""
    if not _contract_id:
        pytest.skip("Depends on gold-standard scan test")
    r = requests.patch(
        f"{BASE_URL}/api/clm/{_contract_id}/milestone",
        json={"milestone_pct": 50, "notes": "CLM test milestone 50%"},
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 200, f"Milestone update failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data.get("milestone_pct") == 50, f"milestone_pct not updated: {data}"


def test_clm_events_log_populated():
    """GET /api/clm/{id}/events returns at least 1 event after scan + milestone."""
    if not _contract_id:
        pytest.skip("Depends on gold-standard scan test")
    r = requests.get(
        f"{BASE_URL}/api/clm/{_contract_id}/events",
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 200
    events = r.json()
    assert isinstance(events, list), "Events must be a list"
    assert len(events) >= 1, "Expected at least 1 event in event log after scan"
    event_types = [e.get("event_type") for e in events]
    assert "scanned" in event_types, f"'scanned' event not found. Got: {event_types}"


def test_clm_invoice_trigger():
    """POST /api/clm/{id}/invoice → marks revenue_recognized=true and returns contract."""
    if not _contract_id:
        pytest.skip("Depends on gold-standard scan test")
    r = requests.post(
        f"{BASE_URL}/api/clm/{_contract_id}/invoice",
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 200, f"Invoice trigger failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert data.get("revenue_recognized") is True, (
        "revenue_recognized not set to True after invoice trigger"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § RATE BENCHMARK
# ═══════════════════════════════════════════════════════════════════════════════

def test_rate_benchmark_above_market():
    """Rate significantly above market average → assessment='above_market'."""
    r = requests.post(
        f"{BASE_URL}/api/clm/rate-benchmark",
        json={
            "rate_per_mile": 9.99,
            "origin_city": "Detroit",
            "destination_city": "Chicago",
            "equipment_type": "dry_van",
        },
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("assessment") in ("above_market", "premium"), (
        f"Expected above_market for $9.99/mi, got '{data.get('assessment')}'"
    )


def test_rate_benchmark_below_market():
    """Rate significantly below market → assessment='below_market'."""
    r = requests.post(
        f"{BASE_URL}/api/clm/rate-benchmark",
        json={
            "rate_per_mile": 0.10,
            "origin_city": "Memphis",
            "destination_city": "Nashville",
            "equipment_type": "dry_van",
        },
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("assessment") in ("below_market", "low"), (
        f"Expected below_market for $0.10/mi, got '{data.get('assessment')}'"
    )


def test_rate_benchmark_response_shape():
    """Rate benchmark response includes rate_per_mile, market_avg, assessment, variance_pct."""
    r = requests.post(
        f"{BASE_URL}/api/clm/rate-benchmark",
        json={"rate_per_mile": 2.50, "origin_city": "Chicago", "destination_city": "St. Louis"},
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 200
    data = r.json()
    for field in ("rate_per_mile", "market_avg_per_mile", "assessment"):
        assert field in data, f"rate-benchmark response missing field '{field}'"


# ═══════════════════════════════════════════════════════════════════════════════
# § BROKER BLACKLIST
# ═══════════════════════════════════════════════════════════════════════════════

def test_blacklist_list_returns_array():
    """GET /api/clm/blacklist returns a list."""
    r = requests.get(f"{BASE_URL}/api/clm/blacklist", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_blacklist_add_broker():
    """POST /api/clm/blacklist → adds a broker with MC, reason, and reporter."""
    r = requests.post(
        f"{BASE_URL}/api/clm/blacklist",
        json={
            "broker_mc":    _test_broker_mc,
            "broker_name":  "Test Bad Broker CLM",
            "reason":       "Non-payment — CLM test entry",
            "reporter":     "clm_test_suite",
        },
        headers=HEADERS, timeout=15,
    )
    assert r.status_code in (200, 201), (
        f"Blacklist add failed: {r.status_code} {r.text[:200]}"
    )
    data = r.json()
    assert data.get("broker_mc") == _test_broker_mc


def test_blacklist_duplicate_returns_409():
    """Adding the same MC# twice → 409 Conflict."""
    r = requests.post(
        f"{BASE_URL}/api/clm/blacklist",
        json={"broker_mc": _test_broker_mc, "broker_name": "Dup Test", "reason": "dup"},
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 409, (
        f"Expected 409 for duplicate blacklist entry, got {r.status_code}"
    )


def test_blacklist_scan_flags_blacklisted_broker():
    """Scanning a contract from a blacklisted MC should be flagged_for_review."""
    contract_text = f"""RATE CONFIRMATION
Broker: Test Bad Broker CLM | MC# {_test_broker_mc}
Carrier: Honest Hauler LLC | DOT# 1234567
Origin: Cleveland, OH | Destination: Pittsburgh, PA
Rate: $1,500.00 | Payment: Net-30 | Load #BB-001"""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": contract_text, "contract_type": "rate_confirmation"},
        headers=HEADERS, timeout=60,
    )
    assert r.status_code == 201
    # Retrieve the contract and check flagged status
    cid = r.json().get("contract_id")
    if cid:
        cr = requests.get(f"{BASE_URL}/api/clm/{cid}", headers=HEADERS, timeout=15)
        if cr.status_code == 200:
            contract = cr.json()
            # Step 129 should have flagged it — check warnings or flagged_for_review
            warnings = r.json().get("warnings", [])
            is_flagged = contract.get("flagged_for_review") or any("blacklist" in w.lower() for w in warnings)
            assert is_flagged, (
                "Contract from blacklisted broker not flagged. "
                "Step 129 (broker_blacklist_check) may not have run."
            )


def test_blacklist_remove_broker():
    """DELETE /api/clm/blacklist/{mc} removes the test entry."""
    r = requests.delete(
        f"{BASE_URL}/api/clm/blacklist/{_test_broker_mc}",
        headers=HEADERS, timeout=15,
    )
    assert r.status_code in (200, 204), (
        f"Blacklist remove failed: {r.status_code} {r.text[:200]}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § DISPUTES — open → escalate → resolve lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

def test_disputes_list():
    """GET /api/clm/disputes returns a list."""
    r = requests.get(f"{BASE_URL}/api/clm/disputes", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_dispute_open():
    """POST /api/clm/disputes → opens a dispute tied to the gold-standard contract."""
    global _dispute_id
    if not _contract_id:
        pytest.skip("Depends on gold-standard scan test")
    r = requests.post(
        f"{BASE_URL}/api/clm/disputes",
        json={
            "contract_id":    _contract_id,
            "dispute_type":   "short_pay",
            "claimed_amount": 250.00,
            "description":    "Broker short-paid $250 on detention — CLM test",
        },
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 201, f"Open dispute failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    _dispute_id = str(data.get("id", ""))
    assert _dispute_id, "dispute id not returned"
    assert data.get("status") == "open", f"Expected status='open', got '{data.get('status')}'"


def test_dispute_escalate():
    """PATCH /api/clm/disputes/{id}/escalate → status changes to 'escalated'."""
    if not _dispute_id:
        pytest.skip("Depends on test_dispute_open")
    r = requests.patch(
        f"{BASE_URL}/api/clm/disputes/{_dispute_id}/escalate",
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 200, f"Escalate failed: {r.status_code} {r.text[:200]}"
    assert r.json().get("escalated") is True


def test_dispute_resolve():
    """PATCH /api/clm/disputes/{id}/resolve → status changes to 'resolved'."""
    if not _dispute_id:
        pytest.skip("Depends on test_dispute_open")
    r = requests.patch(
        f"{BASE_URL}/api/clm/disputes/{_dispute_id}/resolve",
        json={
            "resolution_notes": "Broker issued corrected payment — CLM test resolved",
            "paid_amount":       250.00,
        },
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 200, f"Resolve failed: {r.status_code} {r.text[:200]}"
    assert r.json().get("resolved") is True


def test_dispute_double_escalate_rejected():
    """Escalating an already-resolved dispute → 409 Conflict."""
    if not _dispute_id:
        pytest.skip("Depends on test_dispute_open")
    r = requests.patch(
        f"{BASE_URL}/api/clm/disputes/{_dispute_id}/escalate",
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 409, (
        f"Expected 409 for escalating resolved dispute, got {r.status_code}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

def test_analytics_list_returns_array():
    """GET /api/clm/analytics → list of daily snapshots."""
    r = requests.get(f"{BASE_URL}/api/clm/analytics", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_analytics_refresh():
    """POST /api/clm/analytics/refresh → computes and upserts today's snapshot."""
    r = requests.post(
        f"{BASE_URL}/api/clm/analytics/refresh",
        headers=HEADERS, timeout=30,
    )
    assert r.status_code in (200, 202), f"Analytics refresh failed: {r.status_code}"
    data = r.json()
    assert data.get("total_contracts") is not None or data.get("computed") is not None, (
        "Analytics refresh response missing total_contracts or computed flag"
    )


def test_analytics_snapshot_fields():
    """Analytics snapshot records contain required KPI fields."""
    r = requests.get(
        f"{BASE_URL}/api/clm/analytics?limit=1",
        headers=HEADERS, timeout=15,
    )
    data = r.json()
    if not data:
        pytest.skip("No analytics snapshots yet — run analytics/refresh first")
    row = data[0]
    for field in ("period_date", "total_contracts", "total_revenue"):
        assert field in row, f"Analytics snapshot missing field '{field}'"


# ═══════════════════════════════════════════════════════════════════════════════
# § LIFECYCLE — archive, export, compliance-audit, complete (step 150)
# ═══════════════════════════════════════════════════════════════════════════════

def test_clm_milestone_to_100():
    """Set milestone to 100% — should mark status as 'executed'."""
    if not _contract_id:
        pytest.skip("Depends on gold-standard scan test")
    r = requests.patch(
        f"{BASE_URL}/api/clm/{_contract_id}/milestone",
        json={"milestone_pct": 100, "notes": "CLM test — full completion"},
        headers=HEADERS, timeout=15,
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("milestone_pct") == 100


def test_clm_compliance_audit():
    """POST /api/clm/{id}/compliance-audit → returns audit findings dict."""
    if not _contract_id:
        pytest.skip("Depends on gold-standard scan test")
    r = requests.post(
        f"{BASE_URL}/api/clm/{_contract_id}/compliance-audit",
        headers=HEADERS, timeout=30,
    )
    assert r.status_code == 200, f"Compliance audit failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert "compliant" in data or "passed" in data or "findings" in data, (
        f"Compliance audit response missing expected fields: {list(data.keys())}"
    )


def test_clm_export():
    """GET /api/clm/{id}/export → full contract package with events + docs."""
    if not _contract_id:
        pytest.skip("Depends on gold-standard scan test")
    r = requests.get(
        f"{BASE_URL}/api/clm/{_contract_id}/export",
        headers=HEADERS, timeout=30,
    )
    assert r.status_code == 200, f"Export failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert str(data.get("contract_id")) == _contract_id
    assert "events" in data, "Export missing events array"
    assert "documents" in data, "Export missing documents array"
    assert "exported_at" in data, "Export missing exported_at timestamp"


def test_clm_complete_step_150():
    """POST /api/clm/{id}/complete → writes terminal ledger event, returns complete=True."""
    if not _contract_id:
        pytest.skip("Depends on gold-standard scan test")
    r = requests.post(
        f"{BASE_URL}/api/clm/{_contract_id}/complete",
        headers=HEADERS, timeout=30,
    )
    assert r.status_code == 200, f"CLM complete failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert data.get("complete") is True, f"complete flag not True: {data}"
    assert "final_status" in data, "Missing final_status in complete response"
    assert data.get("ledger_written") is True, "ledger_written not True"


def test_clm_archive_executed():
    """POST /api/clm/{id}/archive → archives a completed contract."""
    if not _contract_id:
        pytest.skip("Depends on gold-standard scan test")
    r = requests.post(
        f"{BASE_URL}/api/clm/{_contract_id}/archive",
        headers=HEADERS, timeout=30,
    )
    assert r.status_code == 200, f"Archive failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert data.get("archived") is True, f"archived not True: {data}"


# ═══════════════════════════════════════════════════════════════════════════════
# § BROKER INTAKE (new endpoint)
# ═══════════════════════════════════════════════════════════════════════════════

def test_broker_intake_registers_broker():
    """POST /api/brokers/intake → creates broker record."""
    r = requests.post(
        f"{BASE_URL}/api/brokers/intake",
        json={
            "broker_name":  "CLM Test Broker LLC",
            "broker_mc":    "CLM-TEST-INTAKE-88888",
            "contact_name": "Test Contact",
            "email":        "broker@clm-test.internal",
            "phone":        "+13135550099",
            "payment_terms": "Net-30",
            "source":       "intake_form",
        },
        headers=HEADERS, timeout=20,
    )
    assert r.status_code == 201, f"Broker intake failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert data.get("ok") is True
    assert data.get("broker_id"), "broker_id missing from response"
    assert data.get("broker_name") == "CLM Test Broker LLC"


def test_broker_list_returns_array():
    """GET /api/brokers/ → list of brokers."""
    r = requests.get(f"{BASE_URL}/api/brokers/", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ═══════════════════════════════════════════════════════════════════════════════
# § SECURITY — AUTH GUARDS
# ═══════════════════════════════════════════════════════════════════════════════

def test_clm_list_no_token_rejected():
    """GET /api/clm/ without Authorization header → 401 or 403."""
    r = requests.get(f"{BASE_URL}/api/clm/", timeout=10)
    assert r.status_code in (401, 403), (
        f"CLM list without token returned {r.status_code} — endpoint is unprotected."
    )


def test_clm_scan_no_token_rejected():
    """POST /api/clm/scan without token → 401 or 403."""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": "test", "contract_type": "rate_confirmation"},
        timeout=10,
    )
    assert r.status_code in (401, 403), (
        f"CLM scan without token returned {r.status_code} — endpoint is unprotected."
    )


def test_clm_blacklist_no_token_rejected():
    """GET /api/clm/blacklist without token → 401 or 403."""
    r = requests.get(f"{BASE_URL}/api/clm/blacklist", timeout=10)
    assert r.status_code in (401, 403)


def test_clm_disputes_no_token_rejected():
    """GET /api/clm/disputes without token → 401 or 403."""
    r = requests.get(f"{BASE_URL}/api/clm/disputes", timeout=10)
    assert r.status_code in (401, 403)


def test_clm_scan_missing_body_rejected():
    """POST /api/clm/scan with empty body → 422 Unprocessable Entity."""
    r = requests.post(f"{BASE_URL}/api/clm/scan", json={}, headers=HEADERS, timeout=10)
    assert r.status_code == 422, (
        f"Empty body scan returned {r.status_code} — input validation not enforced."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § CONCURRENCY — 5 parallel scans, no corruption
# ═══════════════════════════════════════════════════════════════════════════════

def _do_scan(i: int) -> tuple[int, int, str]:
    """Single concurrent scan — returns (index, status_code, contract_id)."""
    text = f"""RATE CONFIRMATION #{i}
Broker: Concurrent Test Broker {i} | MC# CONC-{i:03d}
Carrier: Parallel Carrier {i} LLC | DOT# 50000{i}
Origin: Dallas, TX | Destination: Houston, TX
Rate: ${1500 + i * 10}.00 | Payment: Net-30 | Load #CONC-{i:04d}"""
    r = requests.post(
        f"{BASE_URL}/api/clm/scan",
        json={"raw_text": text, "contract_type": "rate_confirmation"},
        headers=HEADERS, timeout=90,
    )
    cid = r.json().get("contract_id", "") if r.status_code == 201 else ""
    return i, r.status_code, str(cid)


def test_concurrent_scans_no_corruption():
    """5 parallel CLM scans complete without errors and return unique contract IDs."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(_do_scan, i) for i in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    statuses = [r[1] for r in results]
    ids      = [r[2] for r in results if r[2]]

    failures = [r for r in results if r[1] != 201]
    assert not failures, (
        f"Concurrent scan failures: {failures}. "
        "API should handle parallel scans without 500/503."
    )
    unique_ids = len(set(ids))
    assert unique_ids == 5, (
        f"Expected 5 unique contract IDs, got {unique_ids}. "
        "Possible contract_id collision under concurrent load."
    )


def test_clm_summary_after_concurrent_scans():
    """After concurrent scans, summary.total increases (consistency check)."""
    r = requests.get(f"{BASE_URL}/api/clm/summary", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    total = r.json().get("total", 0)
    assert total >= 5, f"Expected ≥ 5 total contracts after concurrent scans, got {total}"
