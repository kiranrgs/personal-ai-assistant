@echo off
REM Runs the Telegram bot (long polling). Keep this running to chat with the
REM assistant. See ..\README.md for full setup.
cd /d "%~dp0.."
python -m src.bot
