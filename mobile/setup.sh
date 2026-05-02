#!/usr/bin/env bash
set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${BLUE}[3 Lakes]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; exit 1; }

echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     3 Lakes Driver — Expo Setup      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

# ── 1. Node.js version check ──────────────────────────────────────────────────
info "Checking Node.js..."
NODE_MAJOR=$(node --version 2>/dev/null | sed 's/v\([0-9]*\).*/\1/' || echo "0")
if [ "$NODE_MAJOR" -lt 18 ]; then
  error "Node.js 18+ is required (found: $(node --version 2>/dev/null || echo 'none')). Install from https://nodejs.org"
fi
success "Node.js $(node --version)"

# ── 2. Install npm dependencies ───────────────────────────────────────────────
info "Installing dependencies..."
npm install
success "Dependencies installed"

# ── 3. EAS CLI ────────────────────────────────────────────────────────────────
info "Checking EAS CLI..."
if ! command -v eas &>/dev/null; then
  info "Installing EAS CLI globally..."
  npm install -g eas-cli
fi
EAS_VERSION=$(eas --version 2>/dev/null | head -1)
success "EAS CLI: $EAS_VERSION"

# ── 4. Expo login ─────────────────────────────────────────────────────────────
info "Checking Expo login status..."
if ! eas whoami &>/dev/null 2>&1; then
  warn "Not logged in — opening Expo login..."
  eas login
fi
EXPO_USER=$(eas whoami 2>/dev/null || echo "unknown")
success "Logged in as: $EXPO_USER"

# ── 5. Link project (fills in projectId in app.json) ─────────────────────────
info "Initializing EAS project..."
if grep -q "REPLACE_WITH_PROJECT_ID" app.json 2>/dev/null; then
  warn "app.json contains placeholder project ID — running 'eas init'..."
  eas init --id "$(eas project:info 2>/dev/null | grep 'Project ID' | awk '{print $NF}')" 2>/dev/null || eas init
  success "EAS project linked"
else
  success "EAS project already configured"
fi

# ── 6. Verify google-services.json ───────────────────────────────────────────
if [ ! -f "google-services.json" ]; then
  warn "google-services.json not found — push notifications won't work until you add it."
  warn "Get it from Firebase Console → Project Settings → Your Android App."
fi

# ── 7. Done ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Setup Complete!                     ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}Start dev server:${NC}"
echo -e "    npm start"
echo ""
echo -e "  ${BLUE}Build preview APK (internal testers):${NC}"
echo -e "    npm run build:apk"
echo ""
echo -e "  ${BLUE}Build production AAB (Play Store):${NC}"
echo -e "    npm run build:aab"
echo ""
echo -e "  ${BLUE}Push an OTA update (no new build needed):${NC}"
echo -e "    npm run update:production"
echo ""
echo -e "  ${BLUE}Monitor builds:${NC}"
echo -e "    https://expo.dev/accounts/${EXPO_USER}/projects/3-lakes-driver/builds"
echo ""
