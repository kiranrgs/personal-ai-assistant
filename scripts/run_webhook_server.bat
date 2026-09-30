@echo off
REM Runs the webhook server (WhatsApp inbound + interactive voice calls).
REM Needs a public HTTPS URL pointed at this (ngrok/cloudflared) - see README.
REM Bound to loopback only: the tunnel connects locally, nothing else should.
cd /d "%~dp0.."
uvicorn src.webhook_server:app --host 127.0.0.1 --port 8000
