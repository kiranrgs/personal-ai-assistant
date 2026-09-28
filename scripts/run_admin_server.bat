@echo off
REM Runs the admin console (multi-tenant bot registration + editing users'
REM config from a browser). Needs ADMIN_USERNAME/ADMIN_PASSWORD set in .env.
cd /d "%~dp0.."
uvicorn src.admin_server:app --host 127.0.0.1 --port 8090
