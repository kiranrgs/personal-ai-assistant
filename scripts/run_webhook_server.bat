@echo off
REM Runs the webhook server (WhatsApp inbound + interactive voice calls).
REM Needs a public HTTPS URL pointed at this (ngrok/cloudflared) - see README.
cd /d "%~dp0.."
uvicorn src.webhook_server:app --host 0.0.0.0 --port 8000
