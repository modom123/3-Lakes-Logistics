"""
5-Carrier Full System Test
Submits all 5 test carriers through intake, then fires execution engine
steps and reports which of the 200 automation steps respond correctly.

Run from repo root:
    py -m pytest tests/test_5_carriers_full.py -v -s
"""
import time
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = "https://three-lakes-logistics-api.onrender.com"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE",
}

# ── 5 Carrier Payloads from PDF ───────────────────────────────────────────────

CARRIERS = [
    {
        "company_name": "Great Lakes Express",
        "legal_entity": "Great Lakes Express LLC",
        "dot_number": "3928174",
        "mc_number": "882910",
        "email": "m.sterling@glexpress.test",
        "phone": "+13135550001",
        "address": "1500 Woodward Ave, Detroit, MI 48226",
        "years_in_business": 5,
        "plan": "founders",
        "founders_truck_count": 1,
        # Fleet
        "make": "Freightliner", "model": "Cascadia", "year": 2024,
        "trailer_type": "dry_van", "equipment_count": 1,
        "truck_id": "GLE-001",
        # ELD
        "eld_provider": "samsara",
        # CDL
        "driver_name": "Marcus Sterling",
        "cdl_number": "MI-S882-991-02", "cdl_state": "MI",
        "cdl_class": "A", "cdl_expiry": "2028-05-31",
        # Insurance
        "insurance_carrier": "Progressive Commercial",
        "policy_number": "GLE-POL-001",
        "policy_expiry": "2027-01-01",
        "bmc91_ack": True, "mcs90_ack": True,
        "safer_consent": True, "csa_consent": True,
        "clearinghouse_consent": True, "psp_consent": True,
        # Banking
        "bank_routing": "021000021",
        "bank_account": "9901000001",
        "account_type": "checking",
        "payee_name": "Marcus Sterling",
        # E-sign
        "esign_name": "Marcus Sterling",
        "esign_ip": "192.168.1.1",
    },
    {
        "company_name": "Motor City Haulers",
        "legal_entity": "Motor City Haulers Inc",
        "dot_number": "4102933",
        "mc_number": "774821",
        "email": "s.jenkins@mchaulers.test",
        "phone": "+13135550002",
        "address": "2801 Clark St, Detroit, MI 48209",
        "years_in_business": 8,
        "plan": "pro",
        "founders_truck_count": 1,
        # Fleet
        "make": "Kenworth", "model": "T680", "year": 2023,
        "trailer_type": "flatbed", "equipment_count": 1,
        "truck_id": "MCH-001",
        # ELD
        "eld_provider": "motive",
        # CDL
        "driver_name": "Sarah Jenkins",
        "cdl_number": "MI-J102-445-91", "cdl_state": "MI",
        "cdl_class": "A", "cdl_expiry": "2027-11-30",
        # Insurance
        "insurance_carrier": "Old Republic Insurance",
        "policy_number": "MCH-POL-001",
        "policy_expiry": "2027-01-01",
        "bmc91_ack": True, "mcs90_ack": True,
        "safer_consent": True, "csa_consent": True,
        "clearinghouse_consent": True, "psp_consent": True,
        # Banking
        "bank_routing": "044000037",
        "bank_account": "2284000001",
        "account_type": "checking",
        "payee_name": "Sarah Jenkins",
        # E-sign
        "esign_name": "Sarah Jenkins",
        "esign_ip": "192.168.1.2",
    },
    {
        "company_name": "Belle Isle Reefer",
        "legal_entity": "Belle Isle Reefer LLC",
        "dot_number": "3881029",
        "mc_number": "990122",
        "email": "d.wu@belleislereefer.test",
        "phone": "+13135550003",
        "address": "2000 E Jefferson, Detroit, MI 48207",
        "years_in_business": 4,
        "plan": "standard",
        "founders_truck_count": 1,
        # Fleet
        "make": "Peterbilt", "model": "579", "year": 2025,
        "trailer_type": "reefer", "equipment_count": 1,
        "truck_id": "BIR-001",
        # ELD
        "eld_provider": "geotab",
        # CDL
        "driver_name": "David Wu",
        "cdl_number": "MI-W990-112-23", "cdl_state": "MI",
        "cdl_class": "A", "cdl_expiry": "2029-08-31",
        # Insurance
        "insurance_carrier": "Sentry Insurance",
        "policy_number": "BIR-POL-001",
        "policy_expiry": "2027-01-01",
        "bmc91_ack": True, "mcs90_ack": True,
        "safer_consent": True, "csa_consent": True,
        "clearinghouse_consent": True, "psp_consent": True,
        # Banking
        "bank_routing": "124085066",
        "bank_account": "5567000001",
        "account_type": "checking",
        "payee_name": "David Wu",
        # E-sign
        "esign_name": "David Wu",
        "esign_ip": "192.168.1.3",
    },
    {
        "company_name": "Ambassador Logistics",
        "legal_entity": "Ambassador Logistics LLC",
        "dot_number": "4005921",
        "mc_number": "661029",
        "email": "e.rodriguez@ambassador.test",
        "phone": "+13135550004",
        "address": "400 Renaissance Center, Detroit, MI 48243",
        "years_in_business": 12,
        "plan": "founders",
        "founders_truck_count": 1,
        # Fleet
        "make": "Hino", "model": "268", "year": 2024,
        "trailer_type": "box_truck", "equipment_count": 1,
        "truck_id": "AMB-001",
        # ELD
        "eld_provider": "other",
        # CDL
        "driver_name": "Elena Rodriguez",
        "cdl_number": "MI-R400-592-11", "cdl_state": "MI",
        "cdl_class": "B", "cdl_expiry": "2027-01-31",
        # Insurance
        "insurance_carrier": "Canal Insurance",
        "policy_number": "AMB-POL-001",
        "policy_expiry": "2027-01-01",
        "bmc91_ack": True, "mcs90_ack": True,
        "safer_consent": True, "csa_consent": True,
        "clearinghouse_consent": True, "psp_consent": True,
        # Banking
        "bank_routing": "043000096",
        "bank_account": "4410000001",
        "account_type": "checking",
        "payee_name": "Elena Rodriguez",
        # E-sign
        "esign_name": "Elena Rodriguez",
        "esign_ip": "192.168.1.4",
    },
    {
        "company_name": "Riverfront Freight",
        "legal_entity": "Riverfront Freight LLC",
        "dot_number": "4229108",
        "mc_number": "554301",
        "email": "j.thorne@riverfront.test",
        "phone": "+13135550005",
        "address": "100 Riverfront Dr, Detroit, MI 48226",
        "years_in_business": 6,
        "plan": "standard",
        "founders_truck_count": 1,
        # Fleet
        "make": "Volvo", "model": "VNL", "year": 2022,
        "trailer_type": "flatbed", "equipment_count": 1,
        "truck_id": "RVF-001",
        # ELD
        "eld_provider": "samsara",
        # CDL
        "driver_name": "James Thorne",
        "cdl_number": "MI-T422-910-85", "cdl_state": "MI",
        "cdl_class": "A", "cdl_expiry": "2028-09-30",
        # Insurance
        "insurance_carrier": "Protective Insurance",
        "policy_number": "RVF-POL-001",
        "policy_expiry": "2027-01-01",
        "bmc91_ack": True, "mcs90_ack": True,
        "safer_consent": True, "csa_consent": True,
        "clearinghouse_consent": True, "psp_consent": True,
        # Banking
        "bank_routing": "026009593",
        "bank_account": "3321000001",
        "account_type": "checking",
        "payee_name": "James Thorne",
        # E-sign
        "esign_name": "James Thorne",
        "esign_ip": "192.168.1.5",
    },
]

# Store carrier_ids after intake
carrier_ids = {}

# Results tracker
results = {}

def log(step, carrier, status, detail=""):
    key = f"{step}:{carrier}"
    results[key] = {"status": status, "detail": detail}
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"  {icon}  [{carrier}] {step}: {detail or status}")


# ── PHASE 1: Intake (Steps 1-6) ───────────────────────────────────────────────

class TestPhase1Intake:
    """Steps 1-6: Carrier onboarding intake form."""

    def test_intake_great_lakes_express(self):
        r = requests.post(f"{BASE_URL}/api/carriers/intake", json=CARRIERS[0], headers=HEADERS)
        assert r.status_code == 201, f"Got {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data["ok"] is True
        carrier_ids["great_lakes"] = data["carrier_id"]
        log("intake", "Great Lakes Express", "PASS", f"carrier_id={data['carrier_id'][:8]}...")

    def test_intake_motor_city_haulers(self):
        r = requests.post(f"{BASE_URL}/api/carriers/intake", json=CARRIERS[1], headers=HEADERS)
        assert r.status_code == 201, f"Got {r.status_code}: {r.text[:200]}"
        data = r.json()
        carrier_ids["motor_city"] = data["carrier_id"]
        log("intake", "Motor City Haulers", "PASS", f"carrier_id={data['carrier_id'][:8]}...")

    def test_intake_belle_isle_reefer(self):
        r = requests.post(f"{BASE_URL}/api/carriers/intake", json=CARRIERS[2], headers=HEADERS)
        assert r.status_code == 201, f"Got {r.status_code}: {r.text[:200]}"
        data = r.json()
        carrier_ids["belle_isle"] = data["carrier_id"]
        log("intake", "Belle Isle Reefer", "PASS", f"carrier_id={data['carrier_id'][:8]}...")

    def test_intake_ambassador_logistics(self):
        r = requests.post(f"{BASE_URL}/api/carriers/intake", json=CARRIERS[3], headers=HEADERS)
        assert r.status_code == 201, f"Got {r.status_code}: {r.text[:200]}"
        data = r.json()
        carrier_ids["ambassador"] = data["carrier_id"]
        log("intake", "Ambassador Logistics", "PASS", f"carrier_id={data['carrier_id'][:8]}...")

    def test_intake_riverfront_freight(self):
        r = requests.post(f"{BASE_URL}/api/carriers/intake", json=CARRIERS[4], headers=HEADERS)
        assert r.status_code == 201, f"Got {r.status_code}: {r.text[:200]}"
        data = r.json()
        carrier_ids["riverfront"] = data["carrier_id"]
        log("intake", "Riverfront Freight", "PASS", f"carrier_id={data['carrier_id'][:8]}...")


# ── PHASE 2: Carrier + Fleet APIs (Steps 7-30) ───────────────────────────────

class TestPhase2CarrierFleet:
    """Steps 7-30: Carrier list, fleet assets, dashboard."""

    def test_carriers_list(self):
        r = requests.get(f"{BASE_URL}/api/carriers/", headers=HEADERS)
        assert r.status_code == 200
        log("carriers.list", "ALL", "PASS", f"{len(r.json())} carriers returned")

    def test_fleet_list(self):
        r = requests.get(f"{BASE_URL}/api/fleet/", headers=HEADERS)
        assert r.status_code == 200
        log("fleet.list", "ALL", "PASS", "fleet assets loaded")

    def test_dashboard_kpis(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/kpis", headers=HEADERS)
        assert r.status_code == 200
        log("dashboard.kpis", "ALL", "PASS", "KPI metrics returned")

    def test_founders_inventory(self):
        r = requests.get(f"{BASE_URL}/api/founders/inventory", headers=HEADERS)
        assert r.status_code == 200
        log("founders.inventory", "ALL", "PASS", "inventory loaded")


# ── PHASE 3: Telemetry — GPS Tracking (Steps 48-55) ──────────────────────────

class TestPhase3Telemetry:
    """Steps 48-55: GPS tracking for each carrier's truck."""

    TRUCK_POSITIONS = [
        ("GLE-001", "test-car-001", "samsara",   41.8781, -87.6298, 65.0),  # Chicago
        ("MCH-001", "test-car-002", "motive",    40.4406, -79.9959, 58.0),  # Pittsburgh
        ("BIR-001", "test-car-003", "geotab",    27.9944, -81.7603, 70.0),  # Florida
        ("AMB-001", "test-car-004", "other",     41.6611, -83.5552, 45.0),  # Toledo
        ("RVF-001", "test-car-005", "samsara",   42.3314, -83.0458, 35.0),  # Detroit
    ]

    def test_telemetry_all_trucks(self):
        for truck_id, carrier_id, eld, lat, lng, speed in self.TRUCK_POSITIONS:
            r = requests.post(
                f"{BASE_URL}/api/telemetry/ping",
                json={
                    "carrier_id": carrier_id,
                    "truck_id": truck_id,
                    "eld_provider": eld,
                    "lat": lat, "lng": lng,
                    "speed_mph": speed,
                    "heading_deg": 270.0,
                },
                headers=HEADERS,
            )
            assert r.status_code == 200, f"{truck_id}: {r.text}"
            log("telemetry.ping", truck_id, "PASS", f"lat={lat} lng={lng} speed={speed}mph")

    def test_telemetry_latest(self):
        r = requests.get(f"{BASE_URL}/api/telemetry/latest", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        log("telemetry.latest", "ALL", "PASS", f"{data['count']} trucks on map")


# ── PHASE 4: Leads + Prospecting (Steps 61-80) ───────────────────────────────

class TestPhase4Leads:
    """Steps 61-80: Lead management and prospecting."""

    def test_leads_list(self):
        r = requests.get(f"{BASE_URL}/api/leads/", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        log("leads.list", "ALL", "PASS", f"{data['count']} leads")

    def test_lead_create(self):
        r = requests.post(
            f"{BASE_URL}/api/leads/",
            json={
                "name": "Test Prospect",
                "phone": "+13135559999",
                "email": "prospect@test.com",
                "dot": "9999999",
                "source": "manual",
                "score": 85,
            },
            headers=HEADERS,
        )
        assert r.status_code in [200, 201]
        log("leads.create", "Test Prospect", "PASS", "lead created")


# ── PHASE 5: Execution Engine Triggers (Steps 1-200) ─────────────────────────

class TestPhase5ExecutionEngine:
    """Fire execution engine domain triggers and validate step coverage."""

    def test_trigger_compliance(self):
        """Steps 151-180: Compliance sweep across all carriers."""
        r = requests.post(
            f"{BASE_URL}/api/triggers/compliance",
            json={"carrier_ids": []},  # empty = all carriers
            headers=HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        log("trigger.compliance", "ALL", "PASS", str(data))

    def test_trigger_analytics(self):
        """Steps 181-200: Analytics update."""
        r = requests.post(f"{BASE_URL}/api/triggers/analytics", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        log("trigger.analytics", "ALL", "PASS", str(data))

    def test_trigger_status(self):
        """Execution engine status — shows steps queued/running/complete."""
        r = requests.get(f"{BASE_URL}/api/triggers/status", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        log("trigger.status", "ALL", "PASS", str(data)[:100])


# ── PHASE 6: HOS (Hours of Service) (Steps 41-47) ────────────────────────────

class TestPhase6HOS:
    """Steps 41-47: HOS status updates for each driver."""

    HOS_UPDATES = [
        ("GLE-001", "Marcus Sterling",   "driving",  420, 660),
        ("MCH-001", "Sarah Jenkins",     "on_duty",  0,   480),
        ("BIR-001", "David Wu",          "driving",  300, 540),
        ("AMB-001", "Elena Rodriguez",   "off_duty", 600, 840),
        ("RVF-001", "James Thorne",      "driving",  180, 420),
    ]

    def test_hos_updates(self):
        for truck_id, driver, status, drive_rem, shift_rem in self.HOS_UPDATES:
            r = requests.post(
                f"{BASE_URL}/api/telemetry/hos",
                json={
                    "carrier_id": truck_id,
                    "driver_code": driver,
                    "duty_status": status,
                    "drive_remaining_min": drive_rem,
                    "shift_remaining_min": shift_rem,
                },
                headers=HEADERS,
            )
            assert r.status_code == 200, f"{driver}: {r.text}"
            log("hos.update", driver, "PASS", f"status={status} drive_rem={drive_rem}min")


# ── PHASE 7: Health + Auth Guard ─────────────────────────────────────────────

class TestPhase7Health:

    def test_health_ping(self):
        r = requests.get(f"{BASE_URL}/api/health/ping")
        assert r.status_code == 200
        assert r.json() == "ok"
        log("health.ping", "SYSTEM", "PASS", "backend alive")

    def test_health_full(self):
        r = requests.get(f"{BASE_URL}/api/health/full")
        assert r.status_code == 200
        data = r.json()
        assert data["services"]["supabase"] == "ok"
        log("health.full", "SYSTEM", "PASS",
            f"supabase={data['services']['supabase']} stripe={data['services']['stripe']}")

    def test_unauthorized_blocked(self):
        r = requests.get(f"{BASE_URL}/api/leads/")
        assert r.status_code in [401, 403]
        log("auth.guard", "SYSTEM", "PASS", "unauthorized requests blocked")
