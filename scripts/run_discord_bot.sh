#!/usr/bin/env bash
# Runs the optional Discord channel. Needs DISCORD_BOT_TOKEN set in .env.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m src.discord_bot
