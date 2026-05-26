#!/usr/bin/env bash
# Build mobile web assets for Capacitor
# Outputs to www/ which is the Capacitor webDir
# Run before: npx cap sync android  OR  npx cap sync ios
set -e

echo "==> Building 3 Lakes Driver mobile assets..."

# Clean output
rm -rf www
mkdir -p www/shared www/icons

# Copy PWA files
cp driver-pwa/index.html   www/index.html
cp driver-pwa/login.html   www/login.html
cp driver-pwa/manifest.json www/manifest.json
cp driver-pwa/sw.js        www/sw.js
[ -f driver-pwa/index-v2.html ] && cp driver-pwa/index-v2.html www/index-v2.html || true

# Copy shared scripts — fix ../shared/ → ./shared/
cp shared/config.js www/shared/config.js
cp shared/tk.js     www/shared/tk.js

# Patch script src references so they work from webview root
sed -i 's|src="../shared/|src="./shared/|g'  www/index.html www/login.html 2>/dev/null || \
  sed -i '' 's|src="../shared/|src="./shared/|g' www/index.html www/login.html 2>/dev/null || true

sed -i 's|href="../shared/|href="./shared/|g' www/index.html www/login.html 2>/dev/null || \
  sed -i '' 's|href="../shared/|href="./shared/|g' www/index.html www/login.html 2>/dev/null || true

# Copy icons (resize 512 → 192 using ImageMagick if available, else copy 512 for both)
if command -v convert &>/dev/null; then
  convert play-store-graphics/icon_512x512.png -resize 192x192 www/icons/icon-192.png
  cp play-store-graphics/icon_512x512.png www/icons/icon-512.png
else
  cp play-store-graphics/icon_512x512.png www/icons/icon-512.png
  cp play-store-graphics/icon_512x512.png www/icons/icon-192.png
  echo "  (ImageMagick not found — using 512x512 for both icon sizes)"
fi

echo "==> Done. www/ is ready for: npx cap sync android"
