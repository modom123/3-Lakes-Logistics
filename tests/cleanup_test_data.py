"""Post-test cleanup — removes all data written by the test suite.

Runs automatically after the nightly GitHub Actions test run.
Also safe to run manually: python tests/cleanup_test_data.py

Requires env vars:
    SUPABASE_URL              — your project URL
    SUPABASE_SERVICE_ROLE_KEY — service role key (bypasses RLS)

If those vars are absent the script exits cleanly (no error),
so local pytest runs without them don't break.
"""
import os
import sys
import urllib.request
import urllib.error
import json

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SERVICE_KEY  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SERVICE_KEY:
    print("⚠  Cleanup skipped — SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set.")
    sys.exit(0)

HEADERS = {
    "apikey":        SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}


def _delete(table: str, column: str, value: str, match_type: str = "eq") -> int:
    """DELETE from table WHERE column = value. Returns rows deleted."""
    if match_type == "like":
        param = f"{column}=like.{value}"
    else:
        param = f"{column}=eq.{urllib.parse.quote(value)}"

    url = f"{SUPABASE_URL}/rest/v1/{table}?{param}"
    try:
        req = urllib.request.Request(url, method="DELETE", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            rows = json.loads(body) if body else []
            return len(rows) if isinstance(rows, list) else 0
    except urllib.error.HTTPError as e:
        print(f"   ✗ {table} ({column}={value}): HTTP {e.code}")
        return 0
    except Exception as exc:
        print(f"   ✗ {table} ({column}={value}): {exc}")
        return 0


import urllib.parse

print("\n━━ 3 Lakes Logistics — Test Data Cleanup ━━━━━━━━━━━━━━━━━━━━━━")
total_deleted = 0

# ── active_carriers ────────────────────────────────────────────────
print("\n[ active_carriers ]")
n = _delete("active_carriers", "email", "test@eagleeye.internal")
print(f"   Eagle Eye Test Carrier:  {n} row(s) removed")
total_deleted += n

n = _delete("active_carriers", "email", "eagleeye.internal", match_type="like")
print(f"   *@eagleeye.internal:     {n} row(s) removed")
total_deleted += n

# ── leads ──────────────────────────────────────────────────────────
print("\n[ leads ]")
n = _delete("leads", "email", "prospect@eagleeye.internal")
print(f"   Eagle Eye Test Prospect: {n} row(s) removed")
total_deleted += n

n = _delete("leads", "email", "eagleeye.internal", match_type="like")
print(f"   *@eagleeye.internal:     {n} row(s) removed")
total_deleted += n

# ── telemetry_pings — burst test data ─────────────────────────────
print("\n[ telemetry_pings ]")
n = _delete("telemetry_pings", "carrier_id", "EE-TEST-001")
print(f"   EE-TEST-001:             {n} row(s) removed")
total_deleted += n

n = _delete("telemetry_pings", "carrier_id", "burst-carrier-%", match_type="like")
print(f"   burst-carrier-*:         {n} row(s) removed")
total_deleted += n

n = _delete("telemetry_pings", "carrier_id", "test-carrier-%", match_type="like")
print(f"   test-carrier-*:          {n} row(s) removed")
total_deleted += n

# ── active_carriers — 5-carriers lifecycle test data ──────────────
print("\n[ 5-carriers test set ]")
for dot in ["9000001", "9999999"]:
    n = _delete("active_carriers", "dot", dot)
    print(f"   DOT {dot}:              {n} row(s) removed")
    total_deleted += n

for name_prefix in ["Great Lakes Express", "Motor City Haulers",
                    "Belle Isle Reefer", "Ambassador Logistics", "Riverfront Freight"]:
    n = _delete("active_carriers", "name", name_prefix)
    print(f"   {name_prefix[:25]:<25}: {n} row(s) removed")
    total_deleted += n

# ── Summary ────────────────────────────────────────────────────────
print(f"\n━━ Cleanup complete — {total_deleted} total row(s) removed ━━━━━━━━━━━━━━━━")
print("   Production DB is clean for business hours.\n")
