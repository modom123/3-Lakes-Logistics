#!/usr/bin/env bash
# Apply Android network security config after `npx cap add android`.
# Run once from project root: bash scripts/apply-android-security.sh

set -e

SRC="android-security/network_security_config.xml"
DEST="android/app/src/main/res/xml/network_security_config.xml"
MANIFEST="android/app/src/main/AndroidManifest.xml"

if [ ! -d "android" ]; then
  echo "✗ android/ directory not found. Run: npx cap add android"
  exit 1
fi

mkdir -p "$(dirname "$DEST")"
cp "$SRC" "$DEST"
echo "✓ Copied network_security_config.xml → $DEST"

# Inject android:networkSecurityConfig into <application> tag if not already present
if grep -q "networkSecurityConfig" "$MANIFEST"; then
  echo "✓ networkSecurityConfig already in AndroidManifest.xml — skipping"
else
  sed -i 's/<application/<application android:networkSecurityConfig="@xml\/network_security_config"/' "$MANIFEST"
  echo "✓ Injected networkSecurityConfig into AndroidManifest.xml"
fi

echo ""
echo "Android network security config applied."
echo "  → Blocks all cleartext HTTP (except localhost dev server)"
echo "  → Enforces system CA trust only (no user-installed certs)"
echo "  → Run: npx cap sync android"
