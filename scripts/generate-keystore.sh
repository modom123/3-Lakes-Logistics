#!/usr/bin/env bash
# Generate Android release signing keystore for both 3 Lakes apps
# Run this ONCE locally. Store the .keystore file and passwords securely.
# NEVER commit the keystore or passwords to git.

set -e

KEYSTORE_FILE="3lakes-release.keystore"
ALIAS_DRIVER="threelakes"
ALIAS_LF="threelakes-lf"
VALIDITY_DAYS=10000   # ~27 years

echo "============================================="
echo " 3 Lakes Logistics — Android Keystore Setup"
echo "============================================="
echo ""
echo "This creates ONE keystore with TWO signing keys:"
echo "  • threelakes     → Truck Driver app (com.threelakes.driver)"
echo "  • threelakes-lf  → Light Fleet app  (com.threelakes.lightfleet)"
echo ""
echo "You will be prompted for passwords and name/org info."
echo "Use the SAME keystore password for both prompts."
echo ""
echo "Press Enter to start..."
read -r

# ── Key 1: Truck Driver ───────────────────────────────────────────────────────
echo ""
echo "─── Step 1/2: Generate Truck Driver signing key ───"
keytool -genkey -v \
  -keystore "$KEYSTORE_FILE" \
  -alias "$ALIAS_DRIVER" \
  -keyalg RSA \
  -keysize 2048 \
  -validity $VALIDITY_DAYS

# ── Key 2: Light Fleet ────────────────────────────────────────────────────────
echo ""
echo "─── Step 2/2: Generate Light Fleet signing key ───"
echo "(Use the SAME keystore password as before)"
keytool -genkey -v \
  -keystore "$KEYSTORE_FILE" \
  -alias "$ALIAS_LF" \
  -keyalg RSA \
  -keysize 2048 \
  -validity $VALIDITY_DAYS

# ── Output GitHub Secrets ─────────────────────────────────────────────────────
KEYSTORE_B64="$(base64 -w 0 "$KEYSTORE_FILE" 2>/dev/null || base64 "$KEYSTORE_FILE")"

echo ""
echo "✅ Keystore created: $KEYSTORE_FILE  (both keys inside)"
echo ""
echo "══════════════════════════════════════════════════"
echo " ADD THESE 7 SECRETS TO GITHUB:"
echo " GitHub repo → Settings → Secrets and variables → Actions"
echo "══════════════════════════════════════════════════"
echo ""
echo "  ANDROID_KEYSTORE_BASE64  ="
echo "$KEYSTORE_B64"
echo ""
echo "  ANDROID_KEY_ALIAS        =  $ALIAS_DRIVER"
echo "  ANDROID_LF_KEY_ALIAS     =  $ALIAS_LF"
echo "  ANDROID_STORE_PASSWORD   =  (keystore password you entered)"
echo "  ANDROID_KEY_PASSWORD     =  (key password for $ALIAS_DRIVER)"
echo "  ANDROID_LF_KEY_PASSWORD  =  (key password for $ALIAS_LF)"
echo "  GOOGLE_PLAY_KEY_BASE64   =  (see PLAY_STORE_SUBMISSION.md — Step 4)"
echo ""
echo "⚠️  Back up $KEYSTORE_FILE and all passwords in a password manager."
echo "    Losing them = losing the ability to update either app on Play Store."
