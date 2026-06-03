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
cp driver-pwa/index.html    www/index.html
cp driver-pwa/login.html    www/login.html
cp driver-pwa/lf.html       www/lf.html
cp driver-pwa/login-lf.html www/login-lf.html
cp driver-pwa/manifest.json www/manifest.json
cp driver-pwa/manifest-lf.json www/manifest-lf.json
cp driver-pwa/sw.js         www/sw.js
[ -f driver-pwa/index-v2.html ] && cp driver-pwa/index-v2.html www/index-v2.html || true

# Copy shared scripts — fix ../shared/ → ./shared/
cp shared/config.js www/shared/config.js
cp shared/tk.js     www/shared/tk.js

# Patch script src references so they work from webview root
for f in www/index.html www/login.html www/lf.html www/login-lf.html; do
  sed -i 's|src="../shared/|src="./shared/|g'  "$f" 2>/dev/null || \
    sed -i '' 's|src="../shared/|src="./shared/|g' "$f" 2>/dev/null || true
  sed -i 's|href="../shared/|href="./shared/|g' "$f" 2>/dev/null || \
    sed -i '' 's|href="../shared/|href="./shared/|g' "$f" 2>/dev/null || true
done

# Copy icons — use pre-built driver-pwa/icons/ if present, else fall back to play-store-graphics
if [ -d driver-pwa/icons ]; then
  cp driver-pwa/icons/icon-192.png    www/icons/icon-192.png
  cp driver-pwa/icons/icon-512.png    www/icons/icon-512.png
  cp driver-pwa/icons/icon-lf-192.png www/icons/icon-lf-192.png
  cp driver-pwa/icons/icon-lf-512.png www/icons/icon-lf-512.png
  echo "  Icons copied from driver-pwa/icons/"
elif command -v convert &>/dev/null; then
  convert play-store-graphics/icon_512x512.png   -resize 192x192 www/icons/icon-192.png
  cp play-store-graphics/icon_512x512.png         www/icons/icon-512.png
  convert play-store-graphics/icon-lf_512x512.png -resize 192x192 www/icons/icon-lf-192.png
  cp play-store-graphics/icon-lf_512x512.png       www/icons/icon-lf-512.png
  echo "  Icons resized with ImageMagick"
else
  cp play-store-graphics/icon_512x512.png    www/icons/icon-512.png
  cp play-store-graphics/icon_512x512.png    www/icons/icon-192.png
  cp play-store-graphics/icon-lf_512x512.png www/icons/icon-lf-512.png
  cp play-store-graphics/icon-lf_512x512.png www/icons/icon-lf-192.png
  echo "  (ImageMagick not found — using 512x512 for all icon sizes)"
fi

echo "==> Done. www/ is ready for: npx cap sync android"
