#!/usr/bin/env python3
"""Verify Hostinger IMAP configuration.

Run this in your backend environment to test the connection:
    cd backend
    python3 verify_imap.py
"""
import imaplib
import sys
from dotenv import load_dotenv
import os

# Load .env
load_dotenv()

def test_imap():
    """Test IMAP connection with configured credentials."""
    host = os.getenv("HOSTINGER_IMAP_HOST", "imap.hostinger.com")
    port = int(os.getenv("HOSTINGER_IMAP_PORT", 993))
    username = os.getenv("HOSTINGER_IMAP_USERNAME", "")
    password = os.getenv("HOSTINGER_IMAP_PASSWORD", "")
    enabled = os.getenv("HOSTINGER_IMAP_ENABLED", "false").lower() == "true"

    print("=" * 60)
    print("HOSTINGER IMAP VERIFICATION")
    print("=" * 60)

    if not enabled:
        print("❌ HOSTINGER_IMAP_ENABLED=false")
        print("   Enable IMAP in .env: HOSTINGER_IMAP_ENABLED=true")
        return False

    if not username or not password:
        print("❌ Missing credentials:")
        if not username:
            print("   - HOSTINGER_IMAP_USERNAME not set")
        if not password:
            print("   - HOSTINGER_IMAP_PASSWORD not set")
        return False

    print(f"\n🔍 Testing connection:")
    print(f"   Host: {host}:{port}")
    print(f"   User: {username}")

    try:
        # Connect
        imap = imaplib.IMAP4_SSL(host, port, timeout=10)
        print("✅ Connected to IMAP server")

        # Login
        imap.login(username, password)
        print("✅ Authentication successful")

        # List mailboxes
        status, mailboxes = imap.list()
        print(f"✅ Found {len(mailboxes)} mailboxes")

        # Check INBOX
        imap.select("INBOX")
        status, msg_ids = imap.search(None, "ALL")
        total_emails = len(msg_ids[0].split()) if msg_ids[0] else 0

        status, unseen_ids = imap.search(None, "UNSEEN")
        unseen_count = len(unseen_ids[0].split()) if unseen_ids[0] else 0

        print(f"\n📬 INBOX Status:")
        print(f"   Total emails: {total_emails}")
        print(f"   Unseen emails: {unseen_count}")

        # Cleanup
        imap.close()
        imap.logout()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nYour Hostinger IMAP is configured correctly.")
        print("The system will automatically poll for emails every")
        print(f"{os.getenv('HOSTINGER_IMAP_POLL_INTERVAL_SECONDS', 300)} seconds.")
        print("\nNext step: Restart the API server")
        print("  uvicorn app.main:app --reload")
        return True

    except imaplib.IMAP4.error as e:
        print(f"\n❌ IMAP Error: {e}")
        print("\nPossible solutions:")
        print("  - Verify username is full email: info@3lakeslogistics.com")
        print("  - Verify password is correct")
        print("  - Check Hostinger control panel for account status")
        print("  - Ensure IMAP is enabled in Hostinger email settings")
        return False

    except TimeoutError:
        print("\n❌ Connection timeout")
        print("\nPossible solutions:")
        print("  - Check network connectivity")
        print("  - Verify IMAP server is accessible from your network")
        print("  - Try from a different network")
        return False

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    success = test_imap()
    sys.exit(0 if success else 1)
