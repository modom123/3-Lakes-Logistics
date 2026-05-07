#!/bin/bash
# Deploy 3 Lakes API to Primary + Backup regions
# Usage: bash deploy/deploy.sh

set -e

echo "================================================"
echo "  3 Lakes Logistics — Multi-Region Deploy"
echo "================================================"

# ── Deploy primary (us-west / LAX) ───────────────────────────────────────────
echo ""
echo "▶ Deploying PRIMARY (lax — us-west)..."
fly deploy --config deploy/fly.toml --wait-timeout 120

echo ""
echo "▶ Verifying PRIMARY health..."
sleep 5
curl -sf https://3lakes-api-primary.fly.dev/api/health/ping && echo " ✓ Primary OK" || echo " ✗ Primary health check failed"

# ── Deploy backup (eu-central / AMS) ─────────────────────────────────────────
echo ""
echo "▶ Deploying BACKUP (ams — eu-central)..."
fly deploy --config deploy/fly-backup.toml --wait-timeout 120

echo ""
echo "▶ Verifying BACKUP health..."
sleep 5
curl -sf https://3lakes-api-backup.fly.dev/api/health/ping && echo " ✓ Backup OK" || echo " ✗ Backup health check failed"

# ── Full health check ─────────────────────────────────────────────────────────
echo ""
echo "▶ Full system health check..."
curl -s https://3lakes-api-primary.fly.dev/api/health/full | python3 -m json.tool

echo ""
echo "================================================"
echo "  Deploy complete!"
echo "  Primary:  https://3lakes-api-primary.fly.dev"
echo "  Backup:   https://3lakes-api-backup.fly.dev"
echo "================================================"
