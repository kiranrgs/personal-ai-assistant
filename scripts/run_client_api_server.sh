#!/usr/bin/env bash
# Runs the desktop-client API server (backend for apps/desktop). Needs a
# Supabase project with email/password auth enabled - see SETUP.md section 17.
# Binds to localhost only by default - put it behind a reverse proxy/tunnel
# with TLS if you need to reach it from elsewhere.
set -euo pipefail
cd "$(dirname "$0")/.."
uvicorn src.client_api_server:app --host 127.0.0.1 --port 8092
