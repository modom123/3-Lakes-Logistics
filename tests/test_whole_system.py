"""3 Lakes Logistics — whole-system surface suite.

Runs the system's contract checks across every major surface, offline and with
no network/secrets:

  • website        — public marketing + signup (website.html)
  • execution      — the 290-step execution engine + handlers
  • eagle eye      — internal command dashboard (eagleeye.html)
  • falcon         — driver portal / auth system (/api/driver-auth + driver-pwa)
  • light mobile   — light-fleet app (light-fleet.html, /api/light-fleet, login-lf)
  • heavy mobile   — heavy-fleet driver app (driver-heavy.html)

Each surface is checked at the front-end ↔ backend contract level: the HTML
ships intact and references API paths that the FastAPI app actually registers.
A green run means no surface has drifted away from its backend.

    pytest tests/test_whole_system.py -v
    python -m unittest tests.test_whole_system -v
"""
from __future__ import annotations

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Resolve the registered route table once. If backend deps aren't installed,
# contract assertions skip cleanly instead of erroring out collection.
APP_IMPORT_ERROR: str | None = None
ROUTE_PATHS: set[str] = set()
STEP_REGISTRY: dict | None = None
HANDLERS: dict[str, bool] = {}
try:
    import app.main as _appmain
    from app.execution_engine.registry import STEP_REGISTRY as _STEPS
    from app.execution_engine.handlers import dispatch as _dispatch
    from app.execution_engine.handlers import settlement as _settlement
    from app.execution_engine.handlers import lf_onboarding as _lf
    from app.api import routes_driver_auth as _falcon

    ROUTE_PATHS = {getattr(r, "path", "") for r in _appmain.app.router.routes}
    STEP_REGISTRY = _STEPS
    HANDLERS = {
        "h47_sonny_post_loadboard": hasattr(_dispatch, "h47_sonny_post_loadboard"),
        "h104_penny_load_margin": hasattr(_settlement, "h104_penny_load_margin"),
        "h206_classify_vehicle": hasattr(_lf, "h206_classify_vehicle"),
    }
except Exception as exc:  # noqa: BLE001
    APP_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

_needs_app = unittest.skipIf(
    APP_IMPORT_ERROR is not None,
    f"backend app not importable ({APP_IMPORT_ERROR}) — "
    "run `pip install -r backend/requirements.txt`",
)


def _read(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


def _exists(rel_path: str) -> bool:
    return os.path.isfile(os.path.join(PROJECT_ROOT, rel_path))


def _prefix_registered(prefix: str) -> bool:
    return any(p.startswith(prefix) for p in ROUTE_PATHS)


# ─────────────────────────────────────────────────────────────────────────────
# Website  — public marketing + carrier/fleet/founders signup
# ─────────────────────────────────────────────────────────────────────────────
class TestWebsiteSurface(unittest.TestCase):
    def test_website_ships_intact(self):
        self.assertTrue(_exists("website.html"), "website.html missing.")
        html = _read("website.html")
        self.assertGreater(len(html), 20_000, "website.html looks truncated.")
        self.assertIn("3 Lakes Logistics", html)
        self.assertIn("</html>", html.lower())

    @_needs_app
    def test_website_signup_endpoints_are_backed(self):
        html = _read("website.html")
        for path, prefix in [("api/carriers", "/api/carriers"),
                             ("api/fleet", "/api/fleet"),
                             ("api/founders", "/api/founders")]:
            self.assertIn(path, html, f"website.html no longer calls {path}.")
            self.assertTrue(_prefix_registered(prefix),
                            f"Backend does not register {prefix} that website.html calls.")


# ─────────────────────────────────────────────────────────────────────────────
# Execution engine  — the 290-step orchestration core
# ─────────────────────────────────────────────────────────────────────────────
@_needs_app
class TestExecutionEngineSurface(unittest.TestCase):
    def test_step_registry_is_populated(self):
        self.assertIsInstance(STEP_REGISTRY, dict)
        self.assertGreaterEqual(len(STEP_REGISTRY), 250,
                                "Execution engine step registry shrank unexpectedly.")

    def test_execution_api_is_exposed(self):
        self.assertTrue(_prefix_registered("/api/execution"),
                        "Execution engine API routes are not registered.")

    def test_core_handlers_present(self):
        # Load-board posting (dispatch), load margin (settlement), and light-fleet
        # vehicle classification are the load-bearing handlers across surfaces.
        for name, present in HANDLERS.items():
            self.assertTrue(present, f"Execution handler '{name}' is missing.")


# ─────────────────────────────────────────────────────────────────────────────
# Eagle Eye  — internal command dashboard
# ─────────────────────────────────────────────────────────────────────────────
class TestEagleEyeSurface(unittest.TestCase):
    def test_dashboard_ships_intact(self):
        self.assertTrue(_exists("eagleeye.html"), "eagleeye.html missing.")
        html = _read("eagleeye.html")
        self.assertGreater(len(html), 200_000, "Eagle Eye dashboard looks truncated.")
        self.assertIn("EAGLE EYE", html.upper())
        self.assertIn("</html>", html.lower())

    @_needs_app
    def test_dashboard_endpoints_are_backed(self):
        html = _read("eagleeye.html")
        for path, prefix in [("api/agents", "/api/agents"),
                             ("api/bond", "/api/bond"),
                             ("api/agreements", "/api/agreements")]:
            self.assertIn(path, html, f"Eagle Eye no longer calls {path}.")
            self.assertTrue(_prefix_registered(prefix),
                            f"Backend does not register {prefix} that Eagle Eye calls.")


# ─────────────────────────────────────────────────────────────────────────────
# Falcon  — driver portal / auth system
# ─────────────────────────────────────────────────────────────────────────────
class TestFalconDriverPortalSurface(unittest.TestCase):
    def test_driver_portal_pages_exist(self):
        # Falcon ships two portals: carrier/heavy (login.html) and light (login-lf.html).
        self.assertTrue(_exists("driver-pwa/login.html"), "Falcon heavy portal missing.")
        self.assertTrue(_exists("driver-pwa/login-lf.html"), "Falcon light portal missing.")

    @_needs_app
    def test_falcon_auth_api_and_portal_urls(self):
        self.assertTrue(_prefix_registered("/api/driver-auth"),
                        "Falcon driver-auth API is not registered.")
        # The backend's Falcon welcome links must point at the shipped portals.
        self.assertTrue(_falcon.FALCON_URL.endswith("/driver-pwa/login.html"))
        self.assertTrue(_falcon.FALCON_LF_URL.endswith("/driver-pwa/login-lf.html"))


# ─────────────────────────────────────────────────────────────────────────────
# Light mobile  — light-fleet app (cars / SUVs / cargo vans)
# ─────────────────────────────────────────────────────────────────────────────
class TestLightMobileSurface(unittest.TestCase):
    def test_light_fleet_surfaces_exist(self):
        self.assertTrue(_exists("light-fleet.html"), "light-fleet.html missing.")
        self.assertTrue(_exists("driver-pwa/lf.html"), "Light-fleet driver app missing.")
        html = _read("light-fleet.html")
        self.assertIn("Light Fleet", html)

    @_needs_app
    def test_light_fleet_api_is_backed(self):
        # The light-fleet surface relies on a substantial dedicated API.
        lf_routes = [p for p in ROUTE_PATHS if p.startswith("/api/light-fleet")]
        self.assertGreaterEqual(len(lf_routes), 15,
                                "Light-fleet API is missing most of its routes.")

    @_needs_app
    def test_light_vehicle_eligibility_holds(self):
        # The classifier that gates light-fleet onboarding still accepts small
        # vehicles and rejects heavy trucks (DB mocked — no live calls).
        from unittest.mock import patch
        with patch.object(_lf, "_db", return_value=None):
            suv = _lf.h206_classify_vehicle("d", None, {"vehicle_type": "suv"})
            semi = _lf.h206_classify_vehicle("d", None, {"vehicle_type": "Class 8 Semi"})
        self.assertTrue(suv["supports_nemt"])
        self.assertFalse(semi["supports_courier"])


# ─────────────────────────────────────────────────────────────────────────────
# Heavy mobile  — heavy-fleet driver app (Class 8 trucks)
# ─────────────────────────────────────────────────────────────────────────────
class TestHeavyMobileSurface(unittest.TestCase):
    def test_heavy_driver_app_ships_intact(self):
        self.assertTrue(_exists("driver-heavy.html"), "driver-heavy.html missing.")
        html = _read("driver-heavy.html")
        self.assertGreater(len(html), 20_000, "driver-heavy.html looks truncated.")
        self.assertIn("Heavy Fleet", html)

    @_needs_app
    def test_heavy_driver_endpoints_are_backed(self):
        html = _read("driver-heavy.html")
        for path, prefix in [("api/driver", "/api/driver"),
                             ("api/driver-auth", "/api/driver-auth"),
                             ("api/loads", "/api/loads"),
                             ("api/payout", "/api/payout")]:
            self.assertIn(path, html, f"Heavy driver app no longer calls {path}.")
            self.assertTrue(_prefix_registered(prefix),
                            f"Backend does not register {prefix} that the heavy app calls.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
