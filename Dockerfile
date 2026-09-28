# Single-service image: runs the Telegram bot (src/bot.py) only.
#
# NOT included: webhook_server.py (WhatsApp/voice-call webhooks) and
# discord_bot.py, since they're separate processes - run them as additional
# containers from this same image if you need them
# (`docker run <image> python -m src.webhook_server` /
#  `docker run <image> python -m src.discord_bot`).
#
# Several integrations in this repo talk to devices/services on your LOCAL
# network (Homebridge, iRobot's local MQTT, a local ClareOne hub) - those
# won't be reachable from inside a container unless you run with
# `--network host` (Linux only) or otherwise bridge the container onto your
# LAN. Cloud-only integrations (Gmail, Twilio, Twitter, SmartThings, Nest,
# Wyze, Supabase) work fine unmodified.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "src.bot"]
