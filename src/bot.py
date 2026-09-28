"""Entrypoint: Telegram bot that routes messages through the orchestrator,
renders confirm/reject prompts for sensitive actions, and owns the daily
scheduled jobs (email/briefing summary, Twitter/X digest, wishlist price
checks, food deals).

Run with: python -m src.bot
"""
from __future__ import annotations

import datetime as dt
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.core import confirmation, user_config
from src.core.llm_router import transcribe_audio
from src.core.orchestrator import handle_user_message
from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation
from src.core.user_config import set_current_chat
from src.db import supabase_client as db

# Importing these registers their tools with src.core.tool_registry as a
# side effect. Add new integration modules here as they're built out.
from src.core import memory_search, preferences, usage_tool  # noqa: F401
from src.integrations.automation_hub import finance_bot_trigger  # noqa: F401
from src.integrations.briefing import daily_briefing  # noqa: F401
from src.integrations.calendar_ import google_calendar, icloud_calendar, outlook_calendar  # noqa: F401
from src.integrations.email import gmail, icloud_yahoo_imap, outlook, package_tracking  # noqa: F401
from src.integrations.files import google_drive, google_sheets, icloud_files  # noqa: F401
from src.integrations.rides_food import dominos, food_delivery, food_deals, rides  # noqa: F401
from src.integrations.shopping import wishlist  # noqa: F401
from src.integrations.smart_home import (  # noqa: F401
    aladdin_connect,
    clare_home,
    homekit_bridge,
    household_presence,
    irobot,
    nest,
    smartthings,
    wyze,
)
from src.integrations.social import twitter, youtube  # noqa: F401
from src.integrations.telephony import twilio_calls  # noqa: F401
from src.integrations.vault_bridge import personal_key_vault_client  # noqa: F401
from src.integrations.web_research import ticket_search  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bot")


def _is_allowed(chat_id: int) -> bool:
    settings = get_settings()
    allowed = settings.telegram_allowed_chat_id_list
    return not allowed or chat_id in allowed


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    await update.effective_chat.send_message(
        "Hi, I'm your personal AI assistant. Ask me about your email, calendar, "
        "smart home, files, or anything else I'm connected to. For anything "
        "involving money, calls, or smart-home actions I'll always ask you to "
        "confirm first.\n\nUse /whoami to see your chat id, /myconfig to see your "
        "personal settings, /set KEY VALUE and /unset KEY to configure them, and "
        "/household NAME to join a household for shared geofencing."
    )


async def whoami_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    chat_row = db.get_or_create_chat("telegram", str(update.effective_chat.id), update.effective_chat.full_name)
    user = db.get_or_create_user(chat_row["id"])
    await update.effective_chat.send_message(
        f"Telegram chat id: {update.effective_chat.id}\n"
        f"Internal chat id: {chat_row['id']}\n"
        f"Household: {user.get('household') or '(none - use /household NAME to set one)'}"
    )


async def myconfig_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    chat_row = db.get_or_create_chat("telegram", str(update.effective_chat.id), update.effective_chat.full_name)
    overrides = user_config.list_user_overrides_masked(chat_row["id"])
    if not overrides:
        await update.effective_chat.send_message(
            "No personal overrides set yet. Use /set KEY VALUE to configure your own accounts/integrations "
            "(shared bot-wide settings stay admin-only)."
        )
        return
    lines = "\n".join(f"- {k} = {v}" for k, v in overrides.items())
    await update.effective_chat.send_message(f"Your personal config overrides:\n{lines}")


async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    if len(context.args or []) < 2:
        await update.effective_chat.send_message("Usage: /set KEY VALUE")
        return
    chat_row = db.get_or_create_chat("telegram", str(update.effective_chat.id), update.effective_chat.full_name)
    key, value = context.args[0], " ".join(context.args[1:])
    try:
        user_config.set_user_override(chat_row["id"], key, value)
        await update.effective_chat.send_message(f"Saved {key.upper()} for your chat only.")
    except ValueError as exc:
        await update.effective_chat.send_message(str(exc))


async def unset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /unset KEY")
        return
    chat_row = db.get_or_create_chat("telegram", str(update.effective_chat.id), update.effective_chat.full_name)
    user_config.unset_user_override(chat_row["id"], context.args[0])
    await update.effective_chat.send_message(f"Removed your override for {context.args[0].upper()}.")


async def household_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    if not context.args:
        await update.effective_chat.send_message("Usage: /household NAME (everyone using the same NAME shares geofencing away/home automation)")
        return
    chat_row = db.get_or_create_chat("telegram", str(update.effective_chat.id), update.effective_chat.full_name)
    household = " ".join(context.args)
    db.set_user_household(chat_row["id"], household)
    await update.effective_chat.send_message(f"You're now part of household '{household}'.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None or update.message.text is None:
        return
    chat_id = update.effective_chat.id
    if not _is_allowed(chat_id):
        await update.effective_chat.send_message("This bot isn't configured to respond to this chat.")
        return

    chat_row = db.get_or_create_chat("telegram", str(chat_id), update.effective_chat.full_name)
    result = handle_user_message(chat_row["id"], update.message.text)
    await _reply_with_pending_action(update, result)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None or update.message.voice is None:
        return
    chat_id = update.effective_chat.id
    if not _is_allowed(chat_id):
        await update.effective_chat.send_message("This bot isn't configured to respond to this chat.")
        return

    tg_file = await update.message.voice.get_file()
    audio_bytes = bytes(await tg_file.download_as_bytearray())
    try:
        text = transcribe_audio(audio_bytes, filename="voice.ogg")
    except Exception:
        log.exception("Voice transcription failed")
        await update.effective_chat.send_message("Sorry, I couldn't transcribe that voice note.")
        return
    if not text.strip():
        await update.effective_chat.send_message("I couldn't make out any speech in that voice note.")
        return

    chat_row = db.get_or_create_chat("telegram", str(chat_id), update.effective_chat.full_name)
    result = handle_user_message(chat_row["id"], text)
    await update.effective_chat.send_message(f"🎙️ Heard: \"{text}\"")
    await _reply_with_pending_action(update, result)


async def _reply_with_pending_action(update: Update, result) -> None:
    if update.effective_chat is None:
        return
    if result.pending_action:
        action_id = result.pending_action["id"]
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Confirm", callback_data=f"confirm:{action_id}"),
              InlineKeyboardButton("❌ Cancel", callback_data=f"reject:{action_id}")]]
        )
        await update.effective_chat.send_message(result.pending_action["summary"], reply_markup=keyboard)
    if result.reply:
        await update.effective_chat.send_message(result.reply)


async def on_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()
    action, action_id = query.data.split(":", 1)
    outcome = confirmation.resolve(action_id, approved=(action == "confirm"))
    await query.edit_message_reply_markup(reply_markup=None)
    if query.message is not None:
        await query.message.reply_text(outcome["message"])


async def _send_daily_summary(context: ContextTypes.DEFAULT_TYPE) -> None:
    """job.data: {'chat_id': int, 'kind': 'email' | 'briefing' | 'twitter_followed' | 'fooddeals'}.
    Runs the matching prompt and posts the result."""
    job = context.job
    assert job is not None and job.data is not None
    chat_id, kind = job.data["chat_id"], job.data["kind"]
    chat_row = db.get_or_create_chat("telegram", str(chat_id))
    prompts = {
        "email": "Summarize all of today's emails across every configured account.",
        "briefing": "Generate my daily briefing (email, calendar, weather).",
        "twitter_followed": "Summarize what I missed today on Twitter/X across the accounts I follow.",
        "fooddeals": "Check for any good nearby restaurant/food-delivery deals today.",
    }
    result = handle_user_message(chat_row["id"], prompts[kind])
    try:
        await context.bot.send_message(chat_id=chat_id, text=result.reply)
    except Exception:
        log.exception("Failed to send scheduled %s summary to chat %s", kind, chat_id)


async def _check_wishlist_prices(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global job (not per-chat): scans every user's active wishlist items,
    and for any that hit their target price, pushes a Telegram alert with a
    Confirm-to-order button to that item's owning chat.
    """
    with set_current_chat(None):
        alerts = wishlist.check_all_wishlist_prices()
    for item in alerts:
        chat_row = db.get_chat_by_internal_id(item["chat_id"])
        if chat_row is None or chat_row["channel"] != "telegram":
            continue  # push notifications are only wired up for Telegram/WhatsApp-via-poll today
        pending = wishlist.request_place_wishlist_order(item["id"])
        if not isinstance(pending, PendingConfirmation):
            continue
        pending.action_type = "request_place_wishlist_order"
        action = confirmation.create(item["chat_id"], pending)
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Order now", callback_data=f"confirm:{action['id']}"),
              InlineKeyboardButton("❌ Not now", callback_data=f"reject:{action['id']}")]]
        )
        try:
            await context.bot.send_message(
                chat_id=int(chat_row["external_chat_id"]),
                text=f"💰 Price drop! '{item['title']}' is now ${item['current_price']} (target ${item['target_price']}).",
                reply_markup=keyboard,
            )
        except Exception:
            log.exception("Failed to send wishlist alert for item %s", item["id"])


def _register_default_jobs(app: Application) -> None:
    """Daily jobs run in UTC by default (PTB's job_queue default timezone).
    Adjust the hour/minute below to match your local offset, or set
    `Application.builder().defaults(Defaults(tzinfo=...))` for a permanent fix.
    """
    settings = get_settings()
    for chat_id in settings.telegram_allowed_chat_id_list:
        app.job_queue.run_daily(
            _send_daily_summary, time=dt.time(hour=7, minute=0),
            data={"chat_id": chat_id, "kind": "briefing"}, name=f"daily_briefing_{chat_id}",
        )
        app.job_queue.run_daily(
            _send_daily_summary, time=dt.time(hour=8, minute=0),
            data={"chat_id": chat_id, "kind": "twitter_followed"}, name=f"daily_twitter_digest_{chat_id}",
        )
        app.job_queue.run_daily(
            _send_daily_summary, time=dt.time(hour=11, minute=30),
            data={"chat_id": chat_id, "kind": "fooddeals"}, name=f"daily_fooddeals_{chat_id}",
        )
    app.job_queue.run_repeating(
        _check_wishlist_prices,
        interval=dt.timedelta(hours=settings.wishlist_check_interval_hours),
        first=dt.timedelta(minutes=5),
        name="wishlist_price_check",
    )


def build_application() -> Application:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("whoami", whoami_command))
    app.add_handler(CommandHandler("myconfig", myconfig_command))
    app.add_handler(CommandHandler("set", set_command))
    app.add_handler(CommandHandler("unset", unset_command))
    app.add_handler(CommandHandler("household", household_command))
    app.add_handler(CallbackQueryHandler(on_confirmation_callback, pattern=r"^(confirm|reject):"))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def main() -> None:
    app = build_application()
    _register_default_jobs(app)
    log.info("Bot starting (long polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
