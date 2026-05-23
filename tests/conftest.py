"""Shared pytest configuration for 3 Lakes Logistics test suite.

Session-scoped teardown runs cleanup_test_data.py after the full suite
completes, but only when SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are set.
Local runs without those vars skip cleanup silently.
"""
import os
import subprocess
import pytest


@pytest.fixture(scope="session", autouse=True)
def cleanup_after_suite():
    """Run once after all tests in the session complete."""
    yield  # all tests run here

    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        print("\n\n── Post-session cleanup ──────────────────────────────────────")
        subprocess.run(
            ["python", "tests/cleanup_test_data.py"],
            check=False,
        )
    else:
        print(
            "\n\n── Cleanup skipped (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set) ──"
        )
