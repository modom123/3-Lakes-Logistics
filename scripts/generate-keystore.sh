#!/usr/bin/env bash
# Generate the Android release signing keystore for 3 Lakes Driver
# Run this ONCE locally. Store the .keystore file and passwords securely.
# NEVER commit the keystore or passwords to git.

set -e

KEYSTORE_FILE="3lakes-release.keystore"
KEY_ALIAS="threelakes"
VALIDITY_DAYS=10000   # ~27 years

echo "============================================"
echo " 3 Lakes Driver — Android Keystore Generator"
echo "============================================"
echo ""
echo "You will be prompted for:"
echo "  1. Keystore password  (choose a strong one, save it somewhere safe)"
echo "  2. Key password       (can be the same as keystore password)"
echo "  3. Your name / org info"
echo ""

keytool -genkey -v \
  -keystore "$KEYSTORE_FILE" \
  -alias "$KEY_ALIAS" \
  -keyalg RSA \
  -keysize 2048 \
  -validity $VALIDITY_DAYS

echo ""
echo "✅ Keystore created: $KEYSTORE_FILE"
echo ""
echo "=========================================="
echo " NEXT: Add these 4 GitHub Secrets"
echo " Go to: GitHub repo → Settings → Secrets → Actions"
echo "=========================================="
echo ""
echo "  ANDROID_KEYSTORE_BASE64   =  $(base64 -w 0 $KEYSTORE_FILE)"
echo "  ANDROID_KEY_ALIAS         =  $KEY_ALIAS"
echo "  ANDROID_STORE_PASSWORD    =  (the keystore password you entered)"
echo "  ANDROID_KEY_PASSWORD      =  (the key password you entered)"
echo ""
echo "⚠️  Store your keystore file and passwords in a password manager."
echo "    If you lose them you cannot publish updates to the same app."
