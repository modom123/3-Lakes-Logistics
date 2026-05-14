#!/usr/bin/env python3
"""
Airtable → Supabase Migration (129 leads)
Fixed version with proper error handling and debugging.
"""
import os
import json
import sys
from pathlib import Path

print("=" * 70)
print("AIRTABLE → SUPABASE MIGRATION (3Lakes Logistics)")
print("=" * 70)

# Step 1: Load .env
print("\n[1/5] Loading credentials from .env...")
env_file = Path(".env")
if not env_file.exists():
    print("❌ ERROR: .env file not found!")
    print("   Run this script from the project root directory")
    sys.exit(1)

config = {}
for line in env_file.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        key, val = line.split("=", 1)
        config[key.strip()] = val.strip()

AIRTABLE_API_KEY = config.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = config.get("AIRTABLE_BASE_ID")
SUPABASE_URL = config.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = config.get("SUPABASE_SERVICE_ROLE_KEY")

# Validate credentials
missing = []
if not AIRTABLE_API_KEY:
    missing.append("AIRTABLE_API_KEY")
if not AIRTABLE_BASE_ID:
    missing.append("AIRTABLE_BASE_ID")
if not SUPABASE_URL:
    missing.append("SUPABASE_URL")
if not SUPABASE_SERVICE_ROLE_KEY:
    missing.append("SUPABASE_SERVICE_ROLE_KEY")

if missing:
    print(f"❌ ERROR: Missing credentials: {', '.join(missing)}")
    print("   Update .env file with all required values")
    sys.exit(1)

print(f"✅ Credentials loaded")
print(f"   Airtable Base: {AIRTABLE_BASE_ID}")
print(f"   Supabase: {SUPABASE_URL.split('/')[2]}")

# Step 2: Test Airtable connection
print("\n[2/5] Testing Airtable connection...")
try:
    import urllib.request
    import urllib.error

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Carrier%20Leads?pageSize=1"
    req = urllib.request.Request(
        url,
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
    )

    with urllib.request.urlopen(req, timeout=10) as response:
        print("✅ Airtable connection OK")
except urllib.error.HTTPError as e:
    if e.code == 401:
        print(f"❌ ERROR 401: Invalid Airtable API key")
    elif e.code == 404:
        print(f"❌ ERROR 404: Base ID not found")
    else:
        print(f"❌ ERROR {e.code}: {e.reason}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Connection error: {str(e)}")
    sys.exit(1)

# Step 3: Fetch Airtable records
print("\n[3/5] Fetching 129 leads from Airtable...")
try:
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/table%201"
    req = urllib.request.Request(
        url,
        headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode())
        records = data.get('records', [])

    print(f"✅ Fetched {len(records)} records from Airtable")

    if len(records) == 0:
        print("⚠️  WARNING: No records found!")
        sys.exit(1)

except Exception as e:
    print(f"❌ ERROR: {str(e)}")
    sys.exit(1)

# Step 4: Transform records
print(f"\n[4/5] Transforming {len(records)} records...")
transformed = []

for i, record in enumerate(records, 1):
    try:
        fields = record.get('fields', {})

        company = fields.get('company name') or fields.get('Company Name') or 'Unknown'
        phone = fields.get('phone') or fields.get('Phone') or ''
        location = fields.get('location') or fields.get('Location') or ''
        truck_type = fields.get('truck type') or fields.get('Truck Type') or ''
        website = fields.get('website') or fields.get('Website') or ''
        rating = fields.get('rating') or fields.get('Rating') or ''

        notes_parts = []
        if location:
            notes_parts.append(f"Location: {location}")
        if truck_type:
            notes_parts.append(f"Truck: {truck_type}")
        if website:
            notes_parts.append(f"Website: {website}")
        if rating:
            notes_parts.append(f"Rating: {rating}")

        transformed.append({
            'prospect_name': company,
            'phone_number': phone,
            'status': 'new',
            'notes': ' | '.join(notes_parts) if notes_parts else None,
            'source': 'airtable_migration'
        })
    except Exception as e:
        print(f"⚠️  Skipped record {i}: {str(e)}")

print(f"✅ Transformed {len(transformed)} records")

# Show sample
print(f"\n   Sample records:")
for i, r in enumerate(transformed[:3], 1):
    print(f"   {i}. {r['prospect_name']} ({r['phone_number']})")

if len(transformed) > 3:
    print(f"   ... and {len(transformed) - 3} more\n")

# Step 5: Insert into Supabase
print(f"[5/5] Inserting into Supabase...")

try:
    from supabase import create_client
    print("✅ Supabase library imported")
except ImportError:
    print("❌ ERROR: Supabase library not installed")
    print("   Run: pip install supabase")
    sys.exit(1)

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    print("✅ Connected to Supabase")
except Exception as e:
    print(f"❌ ERROR: Could not connect to Supabase: {str(e)}")
    sys.exit(1)

# Insert records
inserted = 0
failed = 0
for i, record in enumerate(transformed, 1):
    try:
        supabase.table('leads').insert(record).execute()
        inserted += 1

        if i % 30 == 0:
            print(f"   ✓ Inserted {i}/{len(transformed)}...")
    except Exception as e:
        failed += 1
        print(f"   ⚠️  Failed: {record['prospect_name']} - {str(e)[:50]}")

print()
print("=" * 70)
print(f"✅ MIGRATION COMPLETE!")
print("=" * 70)
print(f"   Inserted: {inserted}/{len(transformed)} leads")
if failed > 0:
    print(f"   Failed: {failed}")
print()
print("🚀 Your 129 leads are now in Supabase!")
print("   Vance can start calling prospects!")
print()
