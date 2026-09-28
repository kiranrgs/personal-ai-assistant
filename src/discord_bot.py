"""Optional Discord channel, mirroring the Telegram bot's confirm/cancel
button flow via discord.ui.View. Discord was chosen over Slack for the
optional "extra channel" since it's free for personal use with no
workspace-seat limits and has a first-class async Python library
(discord.py) that already matches this project's asyncio-based Telegram
bot, whereas Slack's Bolt SDK leans more toward its own (sync-first) runner
loop - similar value, less integration effort.

Run with: python -m src.discord_bot (separate process from bot.py/webhook_server.py).
Requires DISCORD_BOT_TOKEN and DISCORD_ALLOWED_CHANNEL_IDS in .env.
"""
from __future__ import annotations

import logging

import discord

from src.core import confirmation
from src.core.orchestrator import handle_user_message
from src.core.settings import get_settings
from src.db import supabase_client as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("discord_bot")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


class ConfirmView(discord.ui.View):
    def __init__(self, action_id: str):
        super().__init__(timeout=3600)
        self.action_id = action_id

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        outcome = confirmation.resolve(self.action_id, approved=True)
        await interaction.response.edit_message(view=None)
        await interaction.followup.send(outcome["message"])

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        outcome = confirmation.resolve(self.action_id, approved=False)
        await interaction.response.edit_message(view=None)
        await interaction.followup.send(outcome["message"])


def _is_allowed(channel_id: int) -> bool:
    allowed = get_settings().discord_allowed_channel_id_list
    return not allowed or channel_id in allowed


@client.event
async def on_ready() -> None:
    log.info("Discord bot logged in as %s", client.user)


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot or not _is_allowed(message.channel.id):
        return

    chat_row = db.get_or_create_chat("discord", str(message.channel.id), str(message.author))
    result = handle_user_message(chat_row["id"], message.content)

    if result.pending_action:
        action_id = result.pending_action["id"]
        await message.channel.send(result.pending_action["summary"], view=ConfirmView(action_id))
    if result.reply:
        await message.channel.send(result.reply)


def main() -> None:
    settings = get_settings()
    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set in .env")
    client.run(settings.discord_bot_token)


if __name__ == "__main__":
    main()
