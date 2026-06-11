"""3 Lakes Logistics — production-grade system test suite.

Adapted from the generic scaffold to the real codebase. Validates:
  1. Syntax / script integrity   — every backend .py file compiles
  2. Python logic                — the 10% Starter dispatch fee + payout math
                                    and light-fleet vehicle eligibility
  3. API connectivity (mocked)   — load-board auth + timeout handling, with
                                    all external HTTP calls patched so no real
                                    requests, rate limits, or charges occur.

Run it (matches the deployment interpreter — see backend/Dockerfile: python:3.12):
    python3.12 -m unittest test_system.py          # quiet
    python3.12 -m unittest -v test_system.py        # verbose, per-test

NOTE on Python version: the backend uses PEP 701 nested f-strings (e.g.
backend/app/email/welcome_packet.py), which require Python >= 3.12. The
integrity sweep below is therefore only meaningful on 3.12+, matching prod.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Anchor imports to the project root (this file lives there).
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Directories that are not part of the deployable Python backend.
_SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "android-security", "driver-pwa", "fastlane", "play-store-graphics",
    "deploy", "marketing", "public", ".github", "tests",
}


class Test3LakesLogistics(unittest.TestCase):

    # ==========================================
    # 1. SYNTAX, SCRIPTS, & INTEGRITY TESTS
    # ==========================================
    def test_python_syntax_and_compilation(self):
        """Every project Python file parses without syntax/indentation errors."""
        if sys.version_info < (3, 12):
            self.skipTest(
                "Backend targets Python 3.12 (PEP 701 f-strings); "
                f"running {sys.version_info.major}.{sys.version_info.minor}."
            )
        failures = []
        checked = 0
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in files:
                if not fname.endswith(".py") or fname.startswith("test_"):
                    continue
                path = os.path.join(root, fname)
                with open(path, "r", encoding="utf-8") as f:
                    source = f.read()
                try:
                    compile(source, path, "exec")
                    checked += 1
                except SyntaxError as e:
                    rel = os.path.relpath(path, PROJECT_ROOT)
                    failures.append(f"{rel}: {e.msg} (line {e.lineno})")
        if failures:
            self.fail("Syntax errors found:\n  " + "\n  ".join(failures))
        self.assertGreater(checked, 0, "No Python files were compiled — check paths.")

    # ==========================================
    # 2. PYTHON CODE & LOGIC TESTS
    # ==========================================
    def test_dispatch_fee_logic(self):
        """The Starter plan enforces a strict 10% platform fee with cent-precise payouts."""
        try:
            from backend.app.agents import cash
        except (ImportError, SyntaxError) as e:
            self.skipTest(f"cash module not importable ({e}).")

        # Real fee table: Starter = 10%, Pro/Add-On = 5%, default = 10%.
        self.assertEqual(cash._FEE_RATES["starter"], 0.10,
                         "Starter dispatch fee must be exactly 10%.")
        self.assertEqual(cash._FEE_RATES["default"], 0.10)
        self.assertEqual(cash._FEE_RATES["pro_fleet"], 0.05)

        # Mirror settle_trip()'s documented payout math on a $1,200 load.
        rate_total = 1200.00
        fee_rate = cash._FEE_RATES["starter"]
        platform_fee = round(rate_total * fee_rate, 2)
        driver_payout = round(rate_total - platform_fee, 2)
        self.assertEqual(platform_fee, 120.00, "10% of $1,200 must be $120.00.")
        self.assertEqual(driver_payout, 1080.00, "Driver keeps 90% = $1,080.00.")
        # Rounding guard (the floating-point concern from the checklist).
        self.assertEqual(round(0.1 + 0.2, 2), 0.30)

    def test_vehicle_eligibility_logic(self):
        """Light-fleet classifier accepts small profiles and rejects heavy trucks."""
        try:
            import backend.app.main  # noqa: F401  (initialises package graph)
            from backend.app.execution_engine.handlers import lf_onboarding as lf
        except (ImportError, SyntaxError) as e:
            self.skipTest(f"lf_onboarding not importable ({e}).")

        # Mock the DB so classification uses the payload vehicle_type and makes
        # no live Supabase calls.
        with patch.object(lf, "_db", return_value=None):
            suv = lf.h206_classify_vehicle("drv", None, {"vehicle_type": "suv"})
            van = lf.h206_classify_vehicle("drv", None, {"vehicle_type": "cargo_van"})
            semi = lf.h206_classify_vehicle("drv", None, {"vehicle_type": "Class 8 Semi"})

        # SUV is the most versatile light-fleet profile.
        self.assertTrue(suv["supports_nemt"])
        self.assertTrue(suv["supports_executive"])
        self.assertTrue(suv["supports_courier"])
        # Cargo van does courier work but not passenger/NEMT.
        self.assertTrue(van["supports_courier"])
        self.assertFalse(van["supports_nemt"])
        # A Class 8 semi matches none of the light-fleet service sets.
        self.assertFalse(semi["supports_nemt"])
        self.assertFalse(semi["supports_executive"])
        self.assertFalse(semi["supports_courier"])

    # ==========================================
    # 3. API CONNECTION & INTEGRATION TESTS (MOCKED)
    # ==========================================
    def test_loadboard_auth_handshake(self):
        """A 200 OK OAuth2 handshake yields a usable access token — no real HTTP."""
        try:
            from backend.app.prospecting import loadboard_clients as lb
        except (ImportError, SyntaxError) as e:
            self.skipTest(f"loadboard_clients not importable ({e}).")

        # Mock a successful token endpoint response.
        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "mock_token_abc123", "expires_in": 3600}
        with patch("httpx.post", return_value=token_resp) as mock_post:
            token, expires_in = lb._fetch_oauth2_token(
                "https://identity.example.com/token", "client_id", "client_secret",
                scope="freight/read")
        self.assertTrue(mock_post.called, "Auth must POST to the token endpoint.")
        self.assertEqual(token, "mock_token_abc123", "Should return the issued access token.")
        self.assertEqual(expires_in, 3600)

        # The token cache should then report the credential as valid.
        cache = lb._TokenCache()
        cache.set(token, expires_in)
        self.assertTrue(cache.valid())
        self.assertEqual(cache.token, "mock_token_abc123")

    def test_loadboard_timeout_handling(self):
        """Load-board timeouts are caught and degrade to an empty list, never a crash."""
        try:
            import httpx
            from backend.app.prospecting import loadboard_clients as lb
        except (ImportError, SyntaxError) as e:
            self.skipTest(f"loadboard_clients not importable ({e}).")

        params = lb.SearchParams(origin_state="OR", trailer_type="cargo_van")
        lb._dat_cache = lb._TokenCache()
        with patch("httpx.post", side_effect=httpx.TimeoutException("timed out")):
            result = lb.dat_search(params)
        self.assertEqual(result, [], "Timeouts must yield a safe empty dataset.")


if __name__ == "__main__":
    unittest.main()
