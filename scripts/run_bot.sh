#!/usr/bin/env bash
# Runs the Telegram bot (long polling). Keep this running to chat with the
# assistant. See ../README.md for full setup. macOS/Ubuntu equivalent of
# run_bot.bat.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m src.bot
