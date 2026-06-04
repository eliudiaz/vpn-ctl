#!/bin/bash
set -e

echo "[VPN Health] Starting health monitoring service..."
echo "[VPN Health] Python: $(python3 --version)"
echo "[VPN Health] Working dir: $(pwd)"

# Run the Flask app via gunicorn
exec gunicorn \
  --bind 0.0.0.0:8080 \
  --workers 2 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile - \
  "vpnctl.health.app:create_app()"
