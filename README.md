# personal-ai-assistant

A personal AI assistant that runs on Windows, macOS, or Ubuntu/Linux (an
always-on machine, e.g. a desktop tower or Mac Studio), reachable via
Telegram (and WhatsApp/Discord), with Groq (default) or a local Ollama
model as the LLM, and tool integrations for email, calendar, smart home,
files, web research, rides/food, calls, job search, and social summaries.

## How it works

```
Telegram / WhatsApp  --->  orchestrator (LLM + tool-calling loop)  --->  integrations
                                   |
                                   v
                              Supabase (chat memory, context snapshots,
                              pending confirmations, audit log)
```

- **Orchestrator** ([src/core/orchestrator.py](src/core/orchestrator.py)) gives the LLM the full tool
  registry each turn; the LLM decides which tool(s) to call.
- **Tool registry** ([src/core/tool_registry.py](src/core/tool_registry.py)) - every integration
  registers its tools here at import time (see the imports at the top of
  [src/bot.py](src/bot.py)).
- **Confirm-before-execute** ([src/core/confirmation.py](src/core/confirmation.py)) - any tool that
  spends money, places a call, books a ride/order, or actuates a smart-home
  device returns a `PendingConfirmation` instead of acting immediately. The
  bot sends a Telegram message with Confirm/Cancel buttons; only tapping
  Confirm runs the tool's `executor`. This is a hard design rule, not a
  toggle - see "Security model" below.
- **Memory** ([src/db/supabase_client.py](src/db/supabase_client.py)) - conversation history and
  named "context snapshots" (e.g. today's email digest) are stored in
  Supabase so you can ask follow-up questions without re-fetching. A
  full-text index (`messages.content_tsv`) also lets you ask about things
  from further back (`search_past_conversations`).
- **Multi-user** ([src/core/user_config.py](src/core/user_config.py)) - every allow-listed chat is
  its own user. A `contextvars`-based overlay (`set_current_chat` /
  `get_settings()`) means each person can configure their *own* accounts
  (Google/M365/iCloud/Yahoo labels, smart-home tokens, Twitter handles,
  wishlist/food-deal location, etc) via `/set KEY VALUE` in Telegram,
  stored in `config/users/<chat_id>/user.env` - isolated from every other
  user's data and never able to touch shared admin-only settings (bot
  tokens, Supabase key, the allow-list itself). Use `/whoami`, `/myconfig`,
  `/set`, `/unset`, and `/household` to manage this.
- **Multi-tenant bots** ([src/admin_server.py](src/admin_server.py), [src/bot.py](src/bot.py)) - there is no
  `.env`-configured default bot. Every Telegram bot, including the very
  first one, is registered through a small password-protected admin web
  console ("tenants" - own `@BotFather` token + own allow-list, fully
  isolated chat history from each other), instead of hand-editing `.env`/
  restarting for each one - see SETUP.md section 3.

## Security model (read this before configuring real credentials)

1. **Never auto-copies real card numbers.** `personal-key-vault` is
   zero-knowledge encrypted by design - secrets only ever exist in plaintext
   inside its own unlocked UI. This assistant does not and should not build a
   new path to extract them. For purchases, it drafts everything else, asks
   you to confirm, then brings the vault app to the foreground
   ([src/integrations/vault_bridge/personal_key_vault_client.py](src/integrations/vault_bridge/personal_key_vault_client.py)) so *you*
   copy/paste the card. Since personal-key-vault has its own, separate
   Supabase Auth account (unrelated to this app's), every chat must first
   link its own vault account email via `/set VAULT_ACCOUNT_EMAIL ...` -
   this app refuses to open the vault for an unlinked chat, and always
   echoes back the linked email so you can confirm the unlocked vault
   matches before using a saved card, reducing the risk of one person
   using another's cards on a shared machine.
2. **No fully-autonomous purchases/bookings.** Uber, Lyft, DoorDash,
   GrubHub, Domino's, and ticket sites don't offer personal-use booking
   APIs; automating their web checkout would violate their Terms of Service
   and risk your accounts. Instead, the assistant drafts the request and, on
   confirmation, opens the right page/app pre-filled for one-tap checkout.
3. **Smart-home actuation always confirms.** Reading device state doesn't
   need confirmation; turning something on/off, locking/unlocking, etc.
   always does.
4. **Everything is audited.** Every tool call and every confirm/reject
   decision is written to the `audit_log` table.
5. **Access is allow-listed.** Only chat IDs on a tenant's own allowed-chat
   list (registered via the admin console - see the Multi-tenant bots
   bullet above) get responses.
6. **One deliberate, explicit exception to rule 3: household geofencing.**
   `src/integrations/smart_home/household_presence.py`'s auto-away/auto-home
   automation actuates Clare Home scenes *without* a Telegram confirm step.
   This is intentional - the entire point of geofencing is to run
   unattended while nobody's home to tap Confirm. It's still fully
   audit-logged (`household_auto_away`/`household_auto_home` events), only
   ever triggered by the authenticated `/presence/{chat_id}` webhook (shared
   secret via `PRESENCE_WEBHOOK_SECRET`, never from chat conversation), and
   scoped to actuating a scene - never money, calls, or anything else.
7. Treat `.env`, `config/tokens/`, `config/users/` (per-user overrides), and
   any downloaded OAuth client secret JSON as sensitive - they're already
   excluded via `.gitignore`.
8. **Admin console uses HTTP Basic Auth.** [src/admin_server.py](src/admin_server.py) refuses every
   request until `ADMIN_PASSWORD` is set, but Basic Auth alone offers no
   protection against network eavesdropping - always put it behind HTTPS
   (reverse proxy/tunnel) if it's reachable beyond `localhost`.

## Setup

Full, step-by-step instructions for setting this up on a fresh machine
(prerequisites for Windows/macOS/Ubuntu, every integration's credential
walkthrough, running it, keeping it alive after reboot/login on each OS,
and troubleshooting) live in **[SETUP.md](SETUP.md)**. Quick version if you
just want the shape of it (Windows PowerShell shown; see SETUP.md section 1
for the macOS/Ubuntu equivalent):

```powershell
git clone https://github.com/kiranrgs/personal-ai-assistant.git
cd personal-ai-assistant
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# fill in .env with the credentials you want (see SETUP.md), then:
uvicorn src.admin_server:app --port 8090        # 1. Admin console: register your first Telegram bot here
python -m src.bot                              # 2. Telegram bot(s) - reads tenants registered above
uvicorn src.webhook_server:app --port 8000      # WhatsApp + interactive calls (optional)
```

There's no `.env`-configured Telegram bot token anymore - every bot,
including your first one, is registered through the admin console (see
SETUP.md section 3). Every other integration still degrades gracefully -
you don't need every credential filled in before first run, only the ones
you plan to use.

## Implementation status

| Area | Status |
|---|---|
| Telegram bot, confirm/reject flow, memory, audit log | Working |
| LLM router (Groq default + local Ollama) | Working |
| Gmail, Google Calendar/Drive/Sheets | Working once OAuth client is set up |
| iCloud/Yahoo mail (IMAP), iCloud Calendar (CalDAV) | Working once app passwords are set |
| Microsoft 365 mail/calendar | Working once Azure app + device-code sign-in is done |
| SmartThings | Working once PAT is set |
| Nest, Wyze, HomeKit | Real request shapes, needs your own accounts/hardware to verify |
| YouTube summarization | Working (public transcripts) |
| Twitter/X digest | Working once a paid API tier + bearer token is set |
| Ticket price search | Working once a search API key is set; booking = confirm + open page (no auto-checkout) |
| Uber/Lyft/DoorDash/GrubHub/Domino's | Draft + open app/site for one-tap checkout (no personal-use booking APIs exist) |
| Twilio calls (announcement + interactive) | Working once Twilio is set up; interactive calls need the webhook server exposed publicly |
| WhatsApp | Working via Twilio WhatsApp + webhook server |
| Personal-key-vault bridge | Intentionally manual-unlock only (see Security model) |
| finance-bot trigger | Working - runs named jobs in finance-bot's own venv, always confirms first |
| Multi-user / per-user config | Working - `/set`, `/unset`, `/myconfig`, `/whoami`, `/household` |
| Clare Home | Real request shapes, exact endpoint paths vary by installation - verify against your hub/Fusion setup |
| Aladdin Connect (Genie garage doors) | Wiring template only - no stable public/community API exists yet, pick and plug in a client package yourself |
| iRobot (Roomba/Braava) | Working once you retrieve each robot's local BLID/password via `roombapy` |
| Household geofencing (iPhone Shortcuts -> Clare Home away/home) | Working - see Security model exception above |
| Wishlist price monitoring + Telegram-confirmed one-tap order | Working (best-effort price scraping; tell it the price if auto-detect fails) |
| Nearby food-delivery deal search | Working once a search API key + ZIP/city is set (web-search based, not a live retailer feed) |
| Package/delivery tracking (email-based) | Working via existing Gmail search |
| Morning briefing (email + calendar + weather) | Working; weather needs `BRIEFING_LATITUDE`/`LONGITUDE` |
| Twitter/X "who I follow" digest | Working once OAuth1 user-context is set, else falls back to `TWITTER_FOLLOWED_HANDLES` |
| YouTube video Q&A (`ask_about_youtube_video`) | Working (also covers YouTube-hosted podcasts); transcripts cached per-chat |
| Discord channel (optional) | Working once `DISCORD_BOT_TOKEN` is set - run `python -m src.discord_bot` separately |
| Telegram voice notes | Working - transcribed via Groq-hosted Whisper |
| Anomaly detection (tool-call rate limiting) | Working - tunable via `ANOMALY_TOOL_CALL_THRESHOLD`/`ANOMALY_WINDOW_MINUTES` |
| LLM usage/cost visibility | Working - `get_llm_usage_summary`, logged per chat/provider/model |
| CI (GitHub Actions) | Working - runs `pytest` on push/PR |
| Docker | Single-service image (bot only) - see `Dockerfile` for LAN-dependency caveats |
| Multi-tenant Telegram bots + admin console | Working - `src/admin_server.py`; new/changed tenants take effect on the next bot restart |
| Job search across multiple portals (LinkedIn/Indeed/Glassdoor/ZipRecruiter) | Working once a search API key is set (web-search based, not a live ATS feed); save your profile once via `set_job_search_profile` |
| Cross-platform (Windows/macOS/Ubuntu) | Working - pure Python + pathlib; see SETUP.md for OS-specific run/keep-alive steps |

## Adding a new integration
1. Add a module under `src/integrations/<area>/`.
2. Call `register(Tool(...))` for each capability; set
   `requires_confirmation=True` + `executor=` for anything sensitive.
3. Import the module (for its registration side effect) in `src/bot.py`.
