#!/usr/bin/env bash
# Build Light Fleet mobile web assets for Capacitor
# Outputs to www/ with lf.html as index.html (Capacitor entry point)
# Run before: npx cap sync android  OR  npx cap sync ios
set -e

echo "==> Building 3 Lakes Light Fleet mobile assets..."

# Clean output
rm -rf www
mkdir -p www/shared www/icons

# Light Fleet entry points — lf.html becomes index.html for Capacitor
cp driver-pwa/lf.html          www/index.html
cp driver-pwa/login-lf.html    www/login.html
cp driver-pwa/manifest-lf.json www/manifest.json
cp driver-pwa/sw.js            www/sw.js

# Copy shared scripts — fix ../shared/ → ./shared/
cp shared/config.js www/shared/config.js
cp shared/tk.js     www/shared/tk.js

# Patch script src references so they work from webview root
for f in www/index.html www/login.html; do
  sed -i 's|src="../shared/|src="./shared/|g'  "$f" 2>/dev/null || \
    sed -i '' 's|src="../shared/|src="./shared/|g' "$f" 2>/dev/null || true
  sed -i 's|href="../shared/|href="./shared/|g' "$f" 2>/dev/null || \
    sed -i '' 's|href="../shared/|href="./shared/|g' "$f" 2>/dev/null || true
  # manifest.json reference
  sed -i 's|href="manifest-lf.json"|href="manifest.json"|g' "$f" 2>/dev/null || true
  sed -i '' 's|href="manifest-lf.json"|href="manifest.json"|g' "$f" 2>/dev/null || true
done

# Copy LF icons — purple variant
if [ -d driver-pwa/icons ]; then
  cp driver-pwa/icons/icon-lf-192.png www/icons/icon-192.png
  cp driver-pwa/icons/icon-lf-512.png www/icons/icon-512.png
  echo "  LF icons copied from driver-pwa/icons/"
elif command -v convert &>/dev/null && [ -f play-store-graphics/icon-lf_512x512.png ]; then
  convert play-store-graphics/icon-lf_512x512.png -resize 192x192 www/icons/icon-192.png
  cp play-store-graphics/icon-lf_512x512.png www/icons/icon-512.png
  echo "  LF icons resized with ImageMagick"
elif [ -f play-store-graphics/icon-lf_512x512.png ]; then
  cp play-store-graphics/icon-lf_512x512.png www/icons/icon-192.png
  cp play-store-graphics/icon-lf_512x512.png www/icons/icon-512.png
  echo "  (ImageMagick not found — using 512x512 for all icon sizes)"
else
  echo "WARNING: No LF icon source found. Add driver-pwa/icons/icon-lf-192.png and icon-lf-512.png"
fi

echo "==> Done. www/ is ready for: npx cap sync android"
