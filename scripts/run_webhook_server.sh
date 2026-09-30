#!/usr/bin/env bash
# Runs the webhook server (WhatsApp inbound + interactive voice calls +
# geofencing presence endpoint). Needs a public HTTPS URL pointed at this
# (ngrok/cloudflared) - see README.md. macOS/Ubuntu equivalent of
# run_webhook_server.bat. Bound to loopback only: the tunnel connects locally.
set -euo pipefail
cd "$(dirname "$0")/.."
uvicorn src.webhook_server:app --host 127.0.0.1 --port 8000
