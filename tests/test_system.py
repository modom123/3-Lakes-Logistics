"""3 Lakes Logistics — core system test suite.

Modeled on the production-grade QA blueprint:
  1. Syntax / script / integrity  — every Python file compiles; config files parse.
  2. Python code & business logic  — dispatch margin, settlement margin, vehicle
                                     eligibility, driver registration passthrough.
  3. API connectivity (MOCKED)     — load-board (Curri) auth, fetch, timeout, and
                                     HTTP-error handling, with **no real network**.

Unlike the original scaffold (which used placeholder functions), every test here is
wired to the actual code in ``backend/app`` so a green run means the real system
behaves correctly. External HTTP is fully mocked — running this never hits a load
board, never spends money, and never trips a rate limit.

Run the whole suite (pytest — integrates with the existing tests/ config):
    pytest tests/test_system.py -v

Run standalone with the stdlib runner (matches the original blueprint):
    python -m unittest tests.test_system -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# ─────────────────────────────────────────────────────────────────────────────
# Path bootstrap — make ``app`` importable from the backend package, regardless
# of whether we're launched by pytest (rootdir = repo) or `python -m unittest`.
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Importing the FastAPI app first initializes the package graph in the correct
# order and avoids a circular import when later importing handler submodules.
# If backend dependencies aren't installed, every backend-dependent test is
# skipped (rather than erroring out the whole collection).
APP_IMPORT_ERROR: str | None = None
try:
    import httpx  # noqa: F401  (used by the mocked API tests)
    import app.main  # noqa: F401  (side effect: resolves import order)
    from app.agents import curri_client
    from app.execution_engine.handlers.dispatch import h49_penny_margin_preview
    from app.execution_engine.handlers.settlement import h104_penny_load_margin
    from app.execution_engine.handlers import lf_onboarding
    from app.email.welcome_packet import generate_welcome_packet_html
    from app.prospecting import loadboard_clients
except Exception as exc:  # noqa: BLE001
    APP_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _load_payloads() -> dict:
    """Load the mock load-board API payloads (cargo-van freight)."""
    with open(os.path.join(FIXTURES_DIR, "loadboard_payloads.json"), encoding="utf-8") as f:
        return json.load(f)


_needs_app = unittest.skipIf(
    APP_IMPORT_ERROR is not None,
    f"backend app not importable ({APP_IMPORT_ERROR}) — "
    "run `pip install -r backend/requirements.txt`",
)


def _curri_response(status: int, json_body=None, text: str = ""):
    """Build a real httpx.Response so the client's own raise_for_status()/json()
    paths execute exactly as in production (only the transport is faked)."""
    req = httpx.Request("GET", "https://api.curri.com/v1/orders/available")
    if json_body is not None:
        return httpx.Response(status, json=json_body, request=req)
    return httpx.Response(status, text=text, request=req)


# =============================================================================
# 1.  SYNTAX, SCRIPTS, & INTEGRITY
# =============================================================================
class TestSyntaxAndIntegrity(unittest.TestCase):
    """Static guarantees that hold even when the backend can't be imported."""

    # Directories that are never our source (deps, build output, caches, vcs).
    _PRUNE = {
        ".git", ".venv", "venv", "env", "__pycache__", "node_modules",
        "dist", "build", ".pytest_cache", ".mypy_cache", "site-packages",
    }

    def _iter_py_files(self):
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in self._PRUNE]
            for fname in files:
                if fname.endswith(".py"):
                    yield os.path.join(root, fname)

    def test_python_syntax_and_compilation(self):
        """Every project .py file compiles cleanly on the running interpreter.

        This is the regression guard for the kind of Python 3.11/3.12 f-string
        nesting bug that previously broke `welcome_packet.py` (and with it the
        whole backend import) on the CI interpreter.
        """
        failures: list[str] = []
        checked = 0
        for path in self._iter_py_files():
            rel = os.path.relpath(path, PROJECT_ROOT)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    source = fh.read()
                compile(source, path, "exec")
                checked += 1
            except SyntaxError as e:
                failures.append(f"{rel}:{e.lineno}: {e.msg}")
            except UnicodeDecodeError as e:
                failures.append(f"{rel}: not valid UTF-8 ({e})")
        self.assertGreater(checked, 0, "No Python files were scanned — path bug?")
        self.assertEqual(
            failures, [],
            "Python files with syntax/compile errors:\n  " + "\n  ".join(failures),
        )

    def test_config_json_files_parse(self):
        """Key JSON config files are well-formed (a stray comma breaks deploys)."""
        candidates = [
            "package.json", "firebase.json", "vercel.json",
            "capacitor.config.json", "capacitor-lf.config.json",
        ]
        failures = []
        present = 0
        for name in candidates:
            p = os.path.join(PROJECT_ROOT, name)
            if not os.path.exists(p):
                continue
            present += 1
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    json.load(fh)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                failures.append(f"{name}: {e}")
        self.assertGreater(present, 0, "No config JSON files found to validate.")
        self.assertEqual(failures, [], "Malformed JSON config:\n  " + "\n  ".join(failures))

    def test_eagleeye_dashboard_present_and_nonempty(self):
        """The Eagle Eye operator dashboard ships and isn't truncated."""
        p = os.path.join(PROJECT_ROOT, "eagleeye.html")
        self.assertTrue(os.path.exists(p), "eagleeye.html is missing from the repo root.")
        self.assertGreater(os.path.getsize(p), 10_000, "eagleeye.html looks truncated.")


# =============================================================================
# 2.  PYTHON CODE & BUSINESS LOGIC
# =============================================================================
@_needs_app
class TestDispatchMarginLogic(unittest.TestCase):
    """penny.margin_preview (step 49) — the pre-acceptance profitability check."""

    def test_margin_breakdown_with_explicit_fuel(self):
        out = h49_penny_margin_preview(None, None, {
            "rate_total": 1000, "miles": 500, "driver_pct": 0.75, "fuel_cost": 100,
        })
        # driver_pay = 1000 * 0.75 = 750; gross = 1000 - 750 - 100 = 150
        self.assertEqual(out["driver_pay"], 750.0)
        self.assertEqual(out["fuel_cost"], 100.0)
        self.assertEqual(out["gross_margin"], 150.0)
        self.assertEqual(out["margin_pct"], 15.0)
        self.assertEqual(out["rpm"], 2.0)  # 1000 / 500
        self.assertTrue(out["viable"])

    def test_default_driver_pct_is_75_percent(self):
        out = h49_penny_margin_preview(None, None, {"rate_total": 1000, "miles": 100, "fuel_cost": 0})
        self.assertEqual(out["driver_pay"], 750.0, "Default driver share must be 75%.")

    def test_default_fuel_estimate_is_55_cents_per_mile(self):
        out = h49_penny_margin_preview(None, None, {"rate_total": 2000, "miles": 1000, "driver_pct": 0.5})
        # driver_pay = 2000 * 0.5 = 1000 ; fuel default = 1000 * 0.55 = 550
        self.assertEqual(out["fuel_cost"], 550.0, "Default fuel must estimate $0.55/mi.")
        self.assertEqual(out["driver_pay"], 1000.0)
        self.assertEqual(out["gross_margin"], 450.0)

    def test_unprofitable_load_flagged_not_viable(self):
        out = h49_penny_margin_preview(None, None, {"rate_total": 400, "miles": 1000, "driver_pct": 0.75})
        self.assertLess(out["gross_margin"], 0)
        self.assertFalse(out["viable"], "Negative-margin loads must be flagged non-viable.")

    def test_zero_rate_does_not_divide_by_zero(self):
        out = h49_penny_margin_preview(None, None, {"rate_total": 0, "miles": 0})
        self.assertEqual(out["margin_pct"], 0)
        self.assertIsNone(out["rpm"])

    def test_string_numeric_inputs_are_coerced(self):
        out = h49_penny_margin_preview(None, None, {"rate_total": "1200", "miles": "600", "fuel_cost": "0"})
        self.assertEqual(out["rate_total"], 1200.0)
        self.assertEqual(out["rpm"], 2.0)


@_needs_app
class TestSettlementMarginLogic(unittest.TestCase):
    """penny.load_margin (step 104) — post-delivery realized margin."""

    def test_realized_margin_subtracts_costs_and_credits_accessorials(self):
        out = h104_penny_load_margin(None, None, {
            "rate_total": 2000, "net_pay": 1400, "fuel_cost": 300,
            "detention_added": 150, "lumper_added": 50, "miles": 500,
        })
        # total_cost = 1400 + 300 - 150 - 50 = 1500 ; margin = 2000 - 1500 = 500
        self.assertEqual(out["total_cost"], 1500.0)
        self.assertEqual(out["gross_margin"], 500.0)
        self.assertEqual(out["margin_pct"], 25.0)
        self.assertEqual(out["revenue_per_mile"], 4.0)

    def test_zero_rate_is_safe(self):
        out = h104_penny_load_margin(None, None, {"rate_total": 0})
        self.assertEqual(out["margin_pct"], 0)


@_needs_app
class TestVehicleEligibility(unittest.TestCase):
    """classify.vehicle (step 206) — which service lines a vehicle can run.

    The DB layer is mocked so this is a pure logic test (no Supabase needed).
    """

    def _classify(self, vehicle_type):
        # _driver() returns {} so the function falls back to the payload's
        # vehicle_type; _db() returns None so no write is attempted.
        with patch.object(lf_onboarding, "_driver", return_value={}), \
             patch.object(lf_onboarding, "_db", return_value=None):
            return lf_onboarding.h206_classify_vehicle(
                "drv-1", None, {"vehicle_type": vehicle_type}
            )

    def test_cargo_van_runs_courier_not_passenger_medical(self):
        r = self._classify("cargo_van")
        self.assertTrue(r["supports_courier"])
        self.assertFalse(r["supports_nemt"])
        self.assertFalse(r["supports_executive"])
        self.assertEqual(r["vehicle_cargo_type"], "cargo_van")

    def test_suv_is_eligible_across_lines(self):
        r = self._classify("SUV")  # case-insensitive
        self.assertTrue(r["supports_nemt"])
        self.assertTrue(r["supports_executive"])
        self.assertTrue(r["supports_courier"])

    def test_sedan_executive_only(self):
        r = self._classify("sedan")
        self.assertTrue(r["supports_executive"])
        self.assertFalse(r["supports_courier"])
        self.assertFalse(r["supports_nemt"])

    def test_unknown_vehicle_defaults_to_passenger_and_gig_only(self):
        r = self._classify("Class 8 Semi")
        self.assertFalse(r["supports_nemt"])
        self.assertFalse(r["supports_executive"])
        self.assertFalse(r["supports_courier"])
        self.assertTrue(r["supports_gig"], "Every classified vehicle can at least run gig.")
        self.assertEqual(r["vehicle_cargo_type"], "passenger")


@_needs_app
class TestWelcomePacketRendering(unittest.TestCase):
    """The driver welcome packet (the file that previously failed to compile)."""

    def test_packet_renders_with_driver_details(self):
        html = generate_welcome_packet_html(
            name="Jane Carrier", approved_services=["courier", "executive"],
            vehicle_type="Cargo Van", driver_id="drv-42",
        )
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Jane Carrier", html, "Driver name must render in the packet.")
        self.assertIn("Cargo Van", html, "Vehicle type must appear in standards section.")
        self.assertGreater(len(html), 10_000)

    def test_packet_escapes_html_injection_in_name(self):
        """Driver-supplied text must not be able to inject markup."""
        html = generate_welcome_packet_html(
            name="<script>alert(1)</script>", approved_services=["gig"], vehicle_type="Sedan",
        )
        self.assertNotIn("<script>alert(1)</script>", html, "Name must be HTML-escaped.")
        self.assertIn("&lt;script&gt;", html)


# =============================================================================
# 3.  API CONNECTION & INTEGRATION (MOCKED — no real network)
# =============================================================================
@_needs_app
class TestLoadBoardConnectivity(unittest.TestCase):
    """Curri load-board client. Every test patches httpx so nothing leaves the box."""

    def setUp(self):
        # Give the client a credential so _headers() doesn't short-circuit.
        self._settings_patch = patch.object(curri_client, "get_settings")
        gs = self._settings_patch.start()
        gs.return_value.curri_api_key = "test_key_abc123"

    def tearDown(self):
        self._settings_patch.stop()

    @patch("app.agents.curri_client.httpx.get")
    def test_authentication_success(self, mock_get):
        """ping() reports connected when credentials + endpoint return 200."""
        mock_get.return_value = _curri_response(200, json_body=[])
        result = curri_client.ping()
        self.assertTrue(result["connected"])
        self.assertEqual(result["platform"], "curri")

    def test_missing_api_key_fails_gracefully(self):
        """No credential → connected:False, no crash, clear error (RuntimeError path)."""
        self._settings_patch.stop()  # replace with an empty-key stub
        with patch.object(curri_client, "get_settings") as gs:
            gs.return_value.curri_api_key = ""
            result = curri_client.ping()
        self._settings_patch.start()  # keep tearDown balanced
        self.assertFalse(result["connected"])
        self.assertIn("CURRI_API_KEY", result["error"])

    @patch("app.agents.curri_client.httpx.get")
    def test_available_orders_parses_list_response(self, mock_get):
        mock_get.return_value = _curri_response(200, json_body=[{"id": "o1"}, {"id": "o2"}])
        orders = curri_client.available_orders(city="Chicago", limit=10)
        self.assertEqual([o["id"] for o in orders], ["o1", "o2"])
        # The city filter and limit must be forwarded as query params.
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"], {"limit": 10, "city": "Chicago"})

    @patch("app.agents.curri_client.httpx.get")
    def test_available_orders_unwraps_envelope_response(self, mock_get):
        """Some tiers return {"orders": [...]} instead of a bare list."""
        mock_get.return_value = _curri_response(200, json_body={"orders": [{"id": "x"}]})
        orders = curri_client.available_orders()
        self.assertEqual(orders, [{"id": "x"}])

    @patch("app.agents.curri_client.httpx.get")
    def test_timeout_returns_empty_list_safely(self, mock_get):
        """A load-board timeout must degrade to an empty dataset, never crash."""
        mock_get.side_effect = httpx.TimeoutException("connection timed out")
        orders = curri_client.available_orders()
        self.assertEqual(orders, [], "Timeouts must yield an empty, safe result.")

    @patch("app.agents.curri_client.httpx.get")
    def test_http_500_returns_empty_list_safely(self, mock_get):
        mock_get.return_value = _curri_response(500, text="upstream error")
        orders = curri_client.available_orders()
        self.assertEqual(orders, [])

    @patch("app.agents.curri_client.httpx.post")
    def test_accept_order_success(self, mock_post):
        mock_post.return_value = _curri_response(200, json_body={"id": "o1", "status": "accepted"})
        result = curri_client.accept_order("o1", driver_id="drv-9")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["order"]["status"], "accepted")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"], {"driver_id": "drv-9"})

    @patch("app.agents.curri_client.httpx.post")
    def test_accept_order_http_error_is_caught(self, mock_post):
        mock_post.return_value = _curri_response(409, text="already taken")
        result = curri_client.accept_order("o1")
        self.assertFalse(result["accepted"])
        self.assertIn("409", result["error"])

    @patch("app.agents.curri_client.httpx.post")
    def test_update_status_forwards_location(self, mock_post):
        mock_post.return_value = _curri_response(200, json_body={"ok": True})
        result = curri_client.update_status("o1", "delivered", location={"lat": 41.8, "lng": -87.6})
        self.assertTrue(result["updated"])
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["status"], "delivered")
        self.assertEqual(kwargs["json"]["location"], {"lat": 41.8, "lng": -87.6})

    @patch("app.agents.curri_client.httpx.post")
    def test_register_driver_passes_vehicle_type(self, mock_post):
        mock_post.return_value = _curri_response(200, json_body={"id": "curri-77"})
        result = curri_client.register_driver(
            "drv-1", "Sam Carrier", "sam@example.com", "+13125550100", vehicle_type="cargo_van",
        )
        self.assertTrue(result["registered"])
        self.assertEqual(result["curri_driver_id"], "curri-77")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["vehicle_type"], "cargo_van")

    @patch("app.agents.curri_client.httpx.post")
    def test_register_driver_404_means_fleet_eligible(self, mock_post):
        """If the carrier tier has no /fleet/drivers endpoint, the driver is still eligible."""
        mock_post.return_value = _curri_response(404, text="not found")
        result = curri_client.register_driver("drv-1", "Sam", "s@e.com", "+1312", vehicle_type="suv")
        self.assertTrue(result["registered"])
        self.assertEqual(result["note"], "fleet_eligible")


@_needs_app
class TestLoadBoardPayloadMapping(unittest.TestCase):
    """Mock cargo-van load-board responses flow end-to-end through the real
    search functions and LoadResult mappers — no live HTTP, spend, or rate limits.

    Payloads live in tests/fixtures/loadboard_payloads.json and mirror the real
    DAT and 123Loadboard endpoint shapes.
    """

    def setUp(self):
        self.payloads = _load_payloads()
        # Reset DAT's module-level token cache between tests.
        loadboard_clients._dat_cache = loadboard_clients._TokenCache()

    def test_dat_oauth_handshake_returns_token(self):
        """A 200 OK token endpoint yields a usable access token + expiry."""
        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "mock_token_abc123", "expires_in": 3600}
        with patch("httpx.post", return_value=token_resp) as mock_post:
            token, expires_in = loadboard_clients._fetch_oauth2_token(
                "https://identity.example.com/token", "cid", "secret", scope="freight/read")
        self.assertTrue(mock_post.called)
        self.assertEqual(token, "mock_token_abc123")
        self.assertEqual(expires_in, 3600)

    def test_dat_timeout_returns_empty_list_safely(self):
        """DAT search degrades to an empty list on timeout, never crashing."""
        params = loadboard_clients.SearchParams(origin_state="OR", trailer_type="cargo_van")
        with patch("httpx.post", side_effect=httpx.TimeoutException("timed out")):
            self.assertEqual(loadboard_clients.dat_search(params), [])

    def test_dat_cargo_van_payload_mapping(self):
        """Mock DAT cargo-van loads map field-for-field to LoadResult, with payout fields."""
        search_resp = MagicMock(status_code=200)
        search_resp.json.return_value = self.payloads["dat_search_response"]
        params = loadboard_clients.SearchParams(origin_state="OR", trailer_type="cargo_van")
        with patch.object(loadboard_clients, "_dat_token", return_value="mock_tok"), \
             patch("httpx.post", return_value=search_resp):
            results = loadboard_clients.dat_search(params)

        self.assertEqual(len(results), 2, "Both mock cargo-van loads should map.")
        first = results[0]
        for field_name, expected in self.payloads["expected"]["dat_first"].items():
            self.assertEqual(getattr(first, field_name), expected,
                             f"DAT mapping mismatch on '{field_name}'.")
        # Payout sanity: rate parses as a number consistent with rate/mile.
        self.assertEqual(first.rate_total, 525.00)
        self.assertAlmostEqual(first.rate_total / first.miles, first.rate_per_mile, places=1)

    def test_loadboard123_cargo_van_payload_mapping(self):
        """Mock 123Loadboard cargo-van load maps field-for-field to LoadResult."""
        get_resp = MagicMock(status_code=200)
        get_resp.json.return_value = self.payloads["loadboard123_search_response"]
        params = loadboard_clients.SearchParams(
            origin_state="OR", trailer_type="cargo_van", origin_city="Portland")
        fake_settings = MagicMock(loadboard_123_api_key="mock_key")
        with patch.object(loadboard_clients, "get_settings", return_value=fake_settings), \
             patch("httpx.get", return_value=get_resp):
            results = loadboard_clients.loadboard123_search(params)

        self.assertEqual(len(results), 1, "The single mock cargo-van load should map.")
        only = results[0]
        for field_name, expected in self.payloads["expected"]["loadboard123_first"].items():
            self.assertEqual(getattr(only, field_name), expected,
                             f"123Loadboard mapping mismatch on '{field_name}'.")
        self.assertEqual(only.trailer_type, "cargo_van", "Equipment must round-trip as cargo_van.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
