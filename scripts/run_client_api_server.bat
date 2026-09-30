@echo off
REM Runs the desktop-client API server (backend for apps/desktop). Needs a
REM Supabase project with email/password auth enabled - see SETUP.md section 17.
cd /d "%~dp0.."
uvicorn src.client_api_server:app --host 127.0.0.1 --port 8092
