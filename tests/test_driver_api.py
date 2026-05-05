"""
Manual API test script — 3 Lakes Driver backend
Run: python3 tests/test_driver_api.py

Tests all driver endpoints using the test accounts from sql/test_accounts.sql
"""
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8080"
TOKEN = "test_token_driver_001_james"   # James Test Driver
TOKEN_2 = "test_token_driver_002_maria"

PASS = "✅"
FAIL = "❌"
SKIP = "⚠️ "

results = []


def req(method, path, body=None, token=None, multipart=False):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as ex:
        return 0, {"error": str(ex)}


def check(label, status, data, expect_status=200, expect_key=None):
    ok = status == expect_status
    if ok and expect_key:
        ok = expect_key in data
    icon = PASS if ok else FAIL
    results.append((icon, label, status, data if not ok else ""))
    print(f"{icon}  {label:<50} [{status}]")
    if not ok:
        print(f"     → {data}")
    return data


print("\n" + "="*65)
print("  3 Lakes Driver — API Tests")
print("="*65 + "\n")


# ── Health ─────────────────────────────────────────────────────
print("── Health ──────────────────────────────────────────────────")
s, d = req("GET", "/api/health")
check("GET /api/health", s, d, expect_key="ok")
print()

# ── Auth ───────────────────────────────────────────────────────
print("── Authentication ──────────────────────────────────────────")
s, d = req("POST", "/api/driver-auth/login", {"phone": "555-000-0001", "pin": "1234"})
check("POST /api/driver-auth/login  (valid credentials)", s, d, expect_key="token")

s, d = req("POST", "/api/driver-auth/login", {"phone": "555-000-0001", "pin": "9999"})
check("POST /api/driver-auth/login  (wrong PIN → 401)", s, d, expect_status=401)

s, d = req("POST", "/api/driver-auth/login", {"phone": "555-000-0003", "pin": "0000"})
check("POST /api/driver-auth/login  (inactive driver → 403)", s, d, expect_status=403)

s, d = req("GET", "/api/driver-auth/me", token=TOKEN)
check("GET  /api/driver-auth/me      (valid token)", s, d, expect_key="driver")

s, d = req("GET", "/api/driver-auth/me", token="bad_token_xyz")
check("GET  /api/driver-auth/me      (bad token → 401)", s, d, expect_status=401)
print()

# ── Driver Profile ─────────────────────────────────────────────
print("── Driver Profile ──────────────────────────────────────────")
s, d = req("GET", "/api/driver/profile", token=TOKEN)
check("GET  /api/driver/profile", s, d)
print()

# ── GPS Location ───────────────────────────────────────────────
print("── GPS / Location ──────────────────────────────────────────")
s, d = req("POST", "/api/driver/location", {
    "lat": 41.8781,
    "lng": -87.6298,
    "accuracy": 8.5,
    "speed_mph": 62.0,
    "heading": 270.0,
    "timestamp": "2026-05-05T07:00:00Z"
}, token=TOKEN)
check("POST /api/driver/location     (valid GPS ping)", s, d)

s, d = req("POST", "/api/driver/location", {
    "lat": 999,   # invalid latitude
    "lng": -87.6298,
}, token=TOKEN)
check("POST /api/driver/location     (invalid lat → 422)", s, d, expect_status=422)
print()

# ── Payout ─────────────────────────────────────────────────────
print("── Payouts ─────────────────────────────────────────────────")
s, d = req("GET", "/api/payout/history", token=TOKEN)
check("GET  /api/payout/history", s, d)

s, d = req("GET", "/api/payout/status", token=TOKEN)
check("GET  /api/payout/status", s, d)

# Test payout math: $1850 gross → 8% dispatch = $148, $45 insurance → net $1657
s, d = req("POST", "/api/payout/request", {
    "load_id": "cccccccc-0001-4000-c000-000000000001",
    "gross_amount": 1850.00
}, token=TOKEN)
check("POST /api/payout/request      ($1850 → net $1657)", s, d)
if s == 200:
    net = d.get("net_amount", 0)
    expected = 1850 - (1850 * 0.08) - 45
    ok = abs(net - expected) < 1
    icon = PASS if ok else FAIL
    print(f"{icon}    Payout math: gross=$1850 dispatch=${1850*0.08:.0f} ins=$45 net=${net} (expected ${expected:.2f})")
print()

# ── Notifications ──────────────────────────────────────────────
print("── Notifications ───────────────────────────────────────────")
s, d = req("POST", "/api/notifications/register-fcm", {
    "fcm_token": "test_fcm_token_abc123"
}, token=TOKEN)
check("POST /api/notifications/register-fcm", s, d)
print()

# ── Unauthorized access ────────────────────────────────────────
print("── Security ────────────────────────────────────────────────")
s, d = req("GET", "/api/driver/profile")   # no token
check("GET  /api/driver/profile  (no token → 401)", s, d, expect_status=401)

s, d = req("GET", "/api/payout/history")   # no token
check("GET  /api/payout/history  (no token → 401)", s, d, expect_status=401)
print()


# ── Summary ────────────────────────────────────────────────────
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
total  = len(results)

print("="*65)
print(f"  Results: {passed}/{total} passed  |  {failed} failed")
print("="*65)
if failed == 0:
    print("\n  🎉 All tests passed — backend is ready!\n")
else:
    print(f"\n  Fix {failed} failing test(s) before deployment.\n")
