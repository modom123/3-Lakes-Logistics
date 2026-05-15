#!/usr/bin/env python3
"""
Deploy Phase 9 database schema for driver mobile app.
This script safely deploys all missing tables and columns.

Usage:
  python deploy_driver_schema.py --dry-run    # Preview changes
  python deploy_driver_schema.py --deploy     # Execute schema
"""

import sys
import os
from pathlib import Path
import argparse
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Extract connection parameters from Supabase URL
# URL format: https://xxxx.supabase.co
if SUPABASE_URL:
    project_id = SUPABASE_URL.split("//")[1].split(".")[0]
    db_host = f"{project_id}.supabase.co"
    db_port = 5432
    db_name = "postgres"
    db_user = "postgres"
    db_password = SUPABASE_SERVICE_ROLE_KEY
else:
    print("❌ ERROR: SUPABASE_URL not found in .env")
    print("Please ensure .env is configured with SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    sys.exit(1)


def load_schema_file():
    """Load the driver schema SQL file."""
    schema_path = Path(__file__).parent.parent.parent / "sql" / "driver_schema_additions.sql"

    if not schema_path.exists():
        print(f"❌ ERROR: Schema file not found: {schema_path}")
        sys.exit(1)

    with open(schema_path, 'r') as f:
        return f.read()


def parse_statements(sql_script):
    """Parse SQL script into individual statements."""
    statements = []
    current = ""

    for line in sql_script.split('\n'):
        # Skip comments
        if line.strip().startswith('--'):
            continue

        current += line + "\n"

        # End of statement
        if line.rstrip().endswith(';'):
            stmt = current.strip()
            if stmt:
                statements.append(stmt)
            current = ""

    return [s for s in statements if s.strip()]


def connect_db():
    """Connect to Supabase PostgreSQL."""
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            sslmode="require"
        )
        print(f"✅ Connected to {db_host}")
        return conn
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print(f"   Host: {db_host}")
        print(f"   Database: {db_name}")
        print(f"   User: {db_user}")
        sys.exit(1)


def dry_run(statements):
    """Preview statements without executing."""
    print("\n" + "="*60)
    print("DRY RUN: Statements to be executed")
    print("="*60)

    for i, stmt in enumerate(statements, 1):
        # Truncate for display
        display = stmt[:100] + "..." if len(stmt) > 100 else stmt
        print(f"\n[{i}] {display}")

    print(f"\n{'='*60}")
    print(f"Total: {len(statements)} SQL statements")
    print("="*60)
    print("\nTo execute, run: python deploy_driver_schema.py --deploy")


def deploy(statements):
    """Execute schema deployment."""
    conn = connect_db()
    cursor = conn.cursor()

    success_count = 0
    failed_count = 0
    errors = []

    print("\n" + "="*60)
    print("DEPLOYING SCHEMA")
    print("="*60)

    for i, stmt in enumerate(statements, 1):
        try:
            cursor.execute(stmt)
            # Show abbreviated statement
            display = stmt[:70] + "..." if len(stmt) > 70 else stmt
            print(f"[{i}/{len(statements)}] ✅ {display}")
            success_count += 1
        except psycopg2.Error as e:
            display = stmt[:70] + "..." if len(stmt) > 70 else stmt
            print(f"[{i}/{len(statements)}] ❌ {display}")
            print(f"         Error: {e.pgerror if hasattr(e, 'pgerror') else str(e)}")
            failed_count += 1
            errors.append((stmt, e))

    # Commit all changes
    try:
        conn.commit()
        print("\n" + "="*60)
        print(f"✅ DEPLOYMENT COMPLETE")
        print(f"   Succeeded: {success_count}")
        print(f"   Failed: {failed_count}")
        print("="*60)

        if failed_count > 0:
            print("\n⚠️  Some statements failed (usually non-blocking, e.g., IF NOT EXISTS):")
            for stmt, err in errors:
                print(f"   - {err.pgerror.split('ERROR')[0] if hasattr(err, 'pgerror') else str(err)}")
    except Exception as e:
        print(f"\n❌ COMMIT FAILED: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()


def verify():
    """Verify schema was deployed correctly."""
    conn = connect_db()
    cursor = conn.cursor()

    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)

    checks = [
        ("driver_messages table", "SELECT COUNT(*) FROM driver_messages;"),
        ("driver_sessions table", "SELECT COUNT(*) FROM driver_sessions;"),
        ("driver_payouts table", "SELECT COUNT(*) FROM driver_payouts;"),
        ("drivers.stripe_account_id", "SELECT stripe_account_id FROM drivers LIMIT 1;"),
        ("loads.pickup_address", "SELECT pickup_address FROM loads LIMIT 1;"),
    ]

    for check_name, query in checks:
        try:
            cursor.execute(query)
            cursor.fetchone()
            print(f"✅ {check_name}")
        except psycopg2.Error as e:
            print(f"❌ {check_name}: {e.pgerror if hasattr(e, 'pgerror') else str(e)}")

    cursor.close()
    conn.close()
    print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Deploy Phase 9 database schema for driver mobile app"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without executing'
    )
    parser.add_argument(
        '--deploy',
        action='store_true',
        help='Execute schema deployment'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify schema was deployed correctly'
    )

    args = parser.parse_args()

    if not args.dry_run and not args.deploy and not args.verify:
        parser.print_help()
        print("\nExample usage:")
        print("  python deploy_driver_schema.py --dry-run")
        print("  python deploy_driver_schema.py --deploy")
        print("  python deploy_driver_schema.py --verify")
        sys.exit(0)

    # Load schema
    schema_sql = load_schema_file()
    statements = parse_statements(schema_sql)

    if args.dry_run:
        dry_run(statements)

    if args.deploy:
        deploy(statements)
        verify()

    if args.verify and not args.deploy:
        verify()


if __name__ == "__main__":
    main()
