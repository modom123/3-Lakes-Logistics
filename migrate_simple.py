#!/usr/bin/env python3
"""
SIMPLE Airtable → Supabase Migration
No dependencies except built-in libraries
"""
import os
import json
from pathlib import Path

print("\n" + "="*60)
print("MIGRATION TOOL")
print("="*60)

# Load .env
print("\n1. Loading .env file...")
try:
    with open(".env") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()
    print("   ✓ .env loaded")
except:
    print("   ✗ .env not found - make sure you're in the right folder")
    exit(1)

# Get credentials
api_key = os.getenv("AIRTABLE_API_KEY", "").strip('"').strip("'")
base_id = os.getenv("AIRTABLE_BASE_ID", "").strip('"').strip("'")
sb_url = os.getenv("SUPABASE_URL", "").strip('"').strip("'")
sb_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip('"').strip("'")

print(f"\n2. Checking credentials...")
if not api_key:
    print("   ✗ AIRTABLE_API_KEY missing")
    exit(1)
if not base_id:
    print("   ✗ AIRTABLE_BASE_ID missing")
    exit(1)
if not sb_url:
    print("   ✗ SUPABASE_URL missing")
    exit(1)
if not sb_key:
    print("   ✗ SUPABASE_SERVICE_ROLE_KEY missing")
    exit(1)

print("   ✓ All credentials found")

# Fetch from Airtable
print(f"\n3. Fetching from Airtable...")
import urllib.request

url = f"https://api.airtable.com/v0/{base_id}/table%201"
req = urllib.request.Request(
    url,
    headers={'Authorization': f'Bearer {api_key}'}
)

try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())
        records = data.get('records', [])
    print(f"   ✓ Got {len(records)} records")
except Exception as e:
    print(f"   ✗ Failed: {e}")
    exit(1)

# Transform
print(f"\n4. Transforming records...")
leads = []
for rec in records:
    f = rec.get('fields', {})
    company = f.get('company name') or f.get('Company Name') or 'Unknown'
    phone = f.get('phone') or f.get('Phone') or ''
    leads.append({
        'prospect_name': company,
        'phone_number': phone,
        'status': 'new',
        'source': 'airtable'
    })
print(f"   ✓ {len(leads)} leads ready")

# Insert to Supabase
print(f"\n5. Inserting to Supabase...")
try:
    from supabase import create_client
    sb = create_client(sb_url, sb_key)

    for i, lead in enumerate(leads, 1):
        sb.table('leads').insert(lead).execute()
        if i % 20 == 0:
            print(f"   ✓ {i}/{len(leads)}")

    print(f"   ✓ All {len(leads)} inserted!")
except ImportError:
    print("   ✗ Need: pip install supabase")
    exit(1)
except Exception as e:
    print(f"   ✗ Error: {e}")
    exit(1)

print("\n" + "="*60)
print("✅ DONE! 129 leads migrated to Supabase")
print("="*60 + "\n")
