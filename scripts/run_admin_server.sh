#!/usr/bin/env bash
# Runs the admin console (multi-tenant bot registration + editing users'
# config from a browser). Needs ADMIN_USERNAME/ADMIN_PASSWORD set in .env.
# Binds to localhost only by default - put it behind a reverse proxy/tunnel
# with TLS if you need to reach it from elsewhere.
set -euo pipefail
cd "$(dirname "$0")/.."
uvicorn src.admin_server:app --host 127.0.0.1 --port 8090
