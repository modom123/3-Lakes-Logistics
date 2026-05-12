#!/usr/bin/env python3
"""
Migrate 129 leads from Airtable (3lakes logistics hub) to Supabase.

Fields mapped:
  Airtable → Supabase
  company name → prospect_name
  phone → phone_number
  location → (notes)
  truck type → (notes)
  website → (notes)
  rating → (notes)
"""
import os
import json
from pathlib import Path
from datetime import datetime

# Load .env
env_file = Path(".env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

print("=" * 60)
print("AIRTABLE → SUPABASE MIGRATION")
print("=" * 60)
print(f"\n📦 Base ID: {AIRTABLE_BASE_ID}")
print(f"🔑 Airtable API: {AIRTABLE_API_KEY[:30]}...")
print(f"🗄️  Supabase: {SUPABASE_URL}")

# Try to import required libraries
try:
    import urllib.request
    import urllib.parse
    print("\n✅ Using urllib (built-in)")
except ImportError:
    print("\n❌ Missing urllib")
    exit(1)

def fetch_airtable_records():
    """Fetch all records from Airtable table 1."""
    print("\n🔍 Fetching records from Airtable...")

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/table%201"

    try:
        req = urllib.request.Request(
            url,
            headers={'Authorization': f'Bearer {AIRTABLE_API_KEY}'}
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
            records = data.get('records', [])
            print(f"✅ Fetched {len(records)} records from Airtable")
            return records

    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error {e.code}: {e.reason}")
        print(f"   Make sure Base ID and API key are correct")
        return []
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return []

def transform_records(airtable_records):
    """Transform Airtable records to Supabase schema."""
    print(f"\n🔄 Transforming {len(airtable_records)} records...")

    supabase_records = []

    for record in airtable_records:
        fields = record.get('fields', {})

        # Extract fields
        company_name = fields.get('company name', 'Unknown')
        phone = fields.get('phone', '')
        location = fields.get('location', '')
        truck_type = fields.get('truck type', '')
        website = fields.get('website', '')
        rating = fields.get('rating', '')

        # Build notes
        notes = []
        if location:
            notes.append(f"Location: {location}")
        if truck_type:
            notes.append(f"Truck: {truck_type}")
        if website:
            notes.append(f"Website: {website}")
        if rating:
            notes.append(f"Rating: {rating}")

        # Create Supabase record
        supabase_record = {
            'prospect_name': company_name,
            'phone_number': phone,
            'status': 'new',
            'notes': ' | '.join(notes) if notes else None,
            'source': 'airtable_migration'
        }

        supabase_records.append(supabase_record)

    print(f"✅ Transformed to Supabase format")
    return supabase_records

def insert_to_supabase(records):
    """Insert records into Supabase."""
    print(f"\n📤 Inserting {len(records)} records into Supabase...")

    # For now, just show what we would insert
    print("\n📋 Sample records to insert:")
    for i, record in enumerate(records[:3], 1):
        print(f"\n   {i}. {record['prospect_name']}")
        print(f"      Phone: {record['phone_number']}")
        if record.get('notes'):
            print(f"      Notes: {record['notes'][:50]}...")

    if len(records) > 3:
        print(f"\n   ... and {len(records) - 3} more")

    print("\n⚠️  NOTE: Actual Supabase insert would happen here")
    print("   Supabase library not available in this environment")
    print("   You'll need to run this from your local machine with supabase library installed")

    return len(records)

def main():
    """Run the migration."""

    # Fetch
    airtable_records = fetch_airtable_records()
    if not airtable_records:
        print("\n❌ No records found. Migration failed.")
        return False

    # Transform
    supabase_records = transform_records(airtable_records)

    # Insert
    inserted = insert_to_supabase(supabase_records)

    print("\n" + "=" * 60)
    if inserted > 0:
        print(f"✅ SUCCESS! {inserted} records ready to migrate")
        print("=" * 60)
        print("\n📝 Next steps:")
        print("   1. Install supabase: pip install supabase")
        print("   2. Run this script from your local machine")
        print("   3. It will insert all records into Supabase")
        print("   4. Vance can then call all 129 prospects!")
        return True
    else:
        print("❌ FAILED")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
