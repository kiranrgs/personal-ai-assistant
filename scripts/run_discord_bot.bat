@echo off
REM Runs the optional Discord channel. Needs DISCORD_BOT_TOKEN set in .env.
cd /d "%~dp0.."
python -m src.discord_bot
