# Setup guide (fresh machine)

This is the full, step-by-step guide for getting `personal-ai-assistant`
running on a Windows desktop tower from a clean checkout. It's more detailed
than the README's quick-start so you can follow it on a machine that has
never had this repo (or its dependencies) on it before.

Estimated total time: 30-90 minutes, depending on how many integrations you
configure on day one. You do **not** need to configure everything before
first run - every integration degrades gracefully (the tool just reports
"not configured" if you skip it).

---

## 0. Prerequisites

- **Windows 10/11**, always-on desktop tower (per the project's design).
- **Python 3.11 or 3.12** (64-bit). Check with:
  ```powershell
  python --version
  ```
  If missing, install from [python.org/downloads](https://www.python.org/downloads/)
  - check **"Add python.exe to PATH"** during install.
- **Git** (to clone the repo) - [git-scm.com](https://git-scm.com/download/win).
- A **Telegram account** (for the primary interaction channel).
- Optional but recommended: a **free Supabase account**
  ([supabase.com](https://supabase.com)) for persistent memory/audit log.

---

## 1. Get the code and install dependencies

```powershell
git clone https://github.com/kiranrgs/personal-ai-assistant.git
cd personal-ai-assistant
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

> **Corporate proxy / SSL certificate errors during `pip install`?**
> If you see `SSLCertVerificationError: unable to get local issuer
> certificate`, your network is intercepting TLS (common on corporate
> laptops/VPNs). Fixes, in order of preference:
> 1. Ask IT for the corporate root CA `.pem` and run
>    `pip config set global.cert C:\path\to\corporate-ca.pem`, or
> 2. Use a Python install that already trusts your corporate CA (e.g. one
>    provisioned by your company's IT imaging), instead of a brand-new venv.

> **`pip install` fails with `ResolutionImpossible` / conflicting
> dependencies?** This repo's `requirements.txt` intentionally uses `>=`
> (not `==`) pins so pip's resolver can reconcile versions across ~25
> packages, several from different vendors (Google, Twilio, Supabase,
> unofficial Wyze SDK, etc.). If you've edited `requirements.txt` and
> re-introduced strict `==` pins and hit this error, relax them back to
> `>=`.

Verify the install:
```powershell
pytest tests/ -v
```
You should see `23 passed`. If any integration module fails to import,
the error will name the missing package - re-run
`pip install -r requirements.txt`.

---

## 2. Supabase (persistent memory + audit log)

1. Create a **new, separate** Supabase project at
   [supabase.com](https://supabase.com) (do not reuse another project - this
   one stores chat history, pending confirmations, and an audit log).
2. In the Supabase dashboard: **SQL Editor** -> paste the contents of
   [supabase/migrations/0001_init.sql](supabase/migrations/0001_init.sql) -> **Run**.
3. Then paste and run
   [supabase/migrations/0002_multi_user_household_wishlist.sql](supabase/migrations/0002_multi_user_household_wishlist.sql)
   too (additive - adds multi-user/household/presence tables, wishlist
   tracking, LLM usage logging, and full-text conversation search). Run
   0001 first, then 0002, in that order.
4. **Project Settings -> API**: copy the **Project URL** and the
   **`service_role` secret key** (not the `anon` key - this runs entirely
   server-side, on your own tower, never exposed to a browser).
5. In `.env`:
   ```
   SUPABASE_URL=https://xxxxx.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=eyJ...
   ```

---

## 3. Telegram bot (primary interaction channel)

1. Open Telegram, message [@BotFather](https://t.me/BotFather), send
   `/newbot`, follow the prompts. Copy the token it gives you.
2. In `.env`: `TELEGRAM_BOT_TOKEN=123456:ABC-...`
3. Send **any message** to your new bot from your personal Telegram account
   (so Telegram creates a chat record).
4. In a browser, open:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   Find `"chat":{"id":123456789,...}` - that number is your chat ID.
5. In `.env`: `TELEGRAM_ALLOWED_CHAT_IDS=123456789` (comma-separate if
   multiple people/devices should be allowed - e.g. your phone + your
   spouse's).

---

## 4. LLM provider

**Groq (default, cloud, fast, free tier):**
1. Sign up at [console.groq.com](https://console.groq.com), create an API key.
2. In `.env`: `GROQ_API_KEY=gsk_...`

**Ollama (optional, fully local fallback):**
1. Install [Ollama](https://ollama.com) on the same tower.
2. `ollama pull llama3.1` (or another tool-calling-capable model).
3. In `.env`: `OLLAMA_MODEL=llama3.1`, `OLLAMA_HOST=http://localhost:11434`
   (defaults shown; only change if Ollama runs elsewhere on your network).
4. To make local the default: `LLM_DEFAULT_PROVIDER=ollama`. Otherwise Groq
   stays default and Ollama is just available as a fallback/manual switch.

---

## 5. Email + calendar accounts (configure any subset you use)

### Gmail + Google Calendar/Drive/Sheets
1. [console.cloud.google.com](https://console.cloud.google.com) -> create a
   project -> **APIs & Services -> Library** -> enable: Gmail API, Google
   Calendar API, Google Drive API, Google Sheets API.
2. **APIs & Services -> Credentials -> Create Credentials -> OAuth client
   ID** -> Application type **Desktop app**.
3. **OAuth consent screen**: add your own Google account as a **Test user**
   (unless you've verified the app for public use - you haven't, and don't
   need to, for personal use).
4. Download the client secret JSON, save it as
   `config/google_client_secret.json` (create the `config` folder if it
   doesn't exist).
5. In `.env`: `GOOGLE_ACCOUNTS=personal,work` (one short label per Google
   account you want to use - e.g. just `personal` if you only have one).
6. First time any Gmail/Calendar/Drive/Sheets tool runs for a given label, a
   browser window opens for you to sign in and consent - do this once per
   label. Tokens are cached under `config/tokens/google/<label>.json` after
   that.

### Microsoft 365 (Outlook mail/calendar)
1. [portal.azure.com](https://portal.azure.com) -> **Azure Active
   Directory -> App registrations -> New registration**. Name it anything;
   supported account type "Personal Microsoft accounts" (or your tenant, if
   using a work account); no redirect URI needed (device-code flow).
2. **API permissions -> Add a permission -> Microsoft Graph -> Delegated**:
   add `Mail.Read`, `Calendars.Read` (and `Calendars.ReadWrite` if you want
   the assistant to create events). Click **Grant admin consent** if you
   control the tenant, otherwise personal Microsoft accounts self-consent on
   first sign-in.
3. Copy the **Application (client) ID** from the app's Overview page.
4. In `.env`: `MS_CLIENT_ID=xxxxxxxx-...`, `MS_ACCOUNTS=personal` (one label
   per Microsoft account).
5. First call for a given label prints a device-code URL + code in the
   bot's console output (run `python -m src.bot` in a visible terminal the
   first time) - open the URL, enter the code, sign in once. Token cache is
   under `config/tokens/ms/`.

### iCloud Mail + Calendar
1. [appleid.apple.com](https://appleid.apple.com) -> Sign-In and Security ->
   **App-Specific Passwords -> Generate**.
2. In `.env`: `ICLOUD_ACCOUNTS=home`, `ICLOUD_HOME_EMAIL=you@icloud.com`,
   `ICLOUD_HOME_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx`.

### Yahoo Mail
1. [account.yahoo.com](https://account.yahoo.com) -> Account Security ->
   **Generate app password**.
2. In `.env`: `YAHOO_ACCOUNTS=personal`,
   `YAHOO_PERSONAL_EMAIL=you@yahoo.com`,
   `YAHOO_PERSONAL_APP_PASSWORD=xxxxxxxxxxxx`.

---

## 6. Smart home (configure any subset)

- **SmartThings**: [account.smartthings.com/tokens](https://account.smartthings.com/tokens)
  -> generate a Personal Access Token with device read/control scopes ->
  `.env`: `SMARTTHINGS_PAT=...`
- **Google Nest**: requires a one-time $5 **Device Access** project at
  [console.nest.google.com/device-access](https://console.nest.google.com/device-access).
  Follow Google's linking flow to get a refresh token -> `.env`:
  `NEST_PROJECT_ID=...`, `NEST_CLIENT_ID=...`, `NEST_CLIENT_SECRET=...`,
  `NEST_REFRESH_TOKEN=...`
- **Wyze**: [developer-api-console.wyze.com](https://developer-api-console.wyze.com)
  -> request a Key ID + API Key -> `.env`: `WYZE_EMAIL=...`,
  `WYZE_PASSWORD=...`, `WYZE_KEY_ID=...`, `WYZE_API_KEY=...`
- **HomeKit** (via Homebridge, needed since Apple has no direct personal
  cloud API): install [Homebridge](https://homebridge.io) + the
  `config-ui-x` plugin on this same tower (or any always-on device on your
  LAN), create a login for it, then `.env`: `HOMEBRIDGE_URL=http://127.0.0.1:8581`,
  `HOMEBRIDGE_USERNAME=...`, `HOMEBRIDGE_PASSWORD=...`

---

## 7. Twilio (phone calls + WhatsApp)

1. Create an account at [twilio.com](https://www.twilio.com), buy a phone
   number with Voice capability.
2. From the Twilio Console root: copy **Account SID** and **Auth Token**.
3. In `.env`: `TWILIO_ACCOUNT_SID=AC...`, `TWILIO_AUTH_TOKEN=...`,
   `TWILIO_FROM_NUMBER=+1XXXXXXXXXX`
4. For **interactive calls** and **WhatsApp**, the webhook server must be
   reachable from the internet:
   ```powershell
   uvicorn src.webhook_server:app --port 8000
   ```
   In another terminal, expose it (pick one):
   ```powershell
   ngrok http 8000
   ```
   or a persistent Cloudflare Tunnel. Copy the resulting `https://...` URL.
5. In `.env`: `PUBLIC_WEBHOOK_BASE_URL=https://your-tunnel-url`
6. In the Twilio Console, on your phone number's config page, set the
   **Voice webhook** to `<PUBLIC_WEBHOOK_BASE_URL>/voice/interactive`.
7. If using **Twilio WhatsApp Sandbox** (or a provisioned WhatsApp sender),
   set its inbound webhook to `<PUBLIC_WEBHOOK_BASE_URL>/whatsapp/inbound`.

> Note: `ngrok`'s URL changes every restart on the free tier - you'll need
> to re-paste it into `.env` and the Twilio console each time unless you
> use a paid static domain or a Cloudflare Tunnel with a fixed hostname.

---

## 8. Twitter/X, YouTube, web search

- **Twitter/X**: reading tweets requires a paid API tier now - get a bearer
  token from [developer.twitter.com](https://developer.twitter.com), set
  `TWITTER_BEARER_TOKEN`. Skip this if you don't want the recurring cost.
- **YouTube**: no key needed to summarize a specific video URL (uses public
  transcripts). `YOUTUBE_API_KEY` is only a placeholder for a future
  search-by-topic feature.
- **Web search** (for ticket price research): get a Bing Web Search (or
  similar) API key, set `SEARCH_API_KEY`.

---

## 9. Sibling app integrations (optional)

- **finance-bot**: set `FINANCE_BOT_PATH=C:\GitHub\finance-bot` (its own
  path on this machine). The assistant subprocess-invokes finance-bot's own
  `.venv` - so finance-bot must already be independently set up and working
  there.
- **personal-key-vault**: set `PERSONAL_KEY_VAULT_PATH=C:\GitHub\personal-key-vault`.
  The assistant only ever brings this app to the foreground for you to
  manually unlock and copy a card - it never reads its secrets.

Skip either if you didn't clone those sibling repos onto this machine.

---

## 10. Multi-user & households (optional - skip if it's just you)

Every allow-listed Telegram chat ID is automatically its own "user" - no
extra setup needed to isolate them. To let each person configure their
*own* accounts/integrations instead of sharing one `.env`:

1. Add everyone's chat ID to `TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated,
   see step 3).
2. Each person messages the bot `/whoami` to confirm their chat is
   recognized, then `/set KEY VALUE` for anything personal - e.g.
   `/set GOOGLE_ACCOUNTS personal` or `/set TWITTER_FOLLOWED_HANDLES
   handle1,handle2`. `/myconfig` lists what's saved (values masked);
   `/unset KEY` removes one. Only a whitelisted subset of settings can be
   set this way (personal accounts/integrations) - shared admin-only
   settings (bot tokens, Supabase key, the allow-list) always stay in the
   root `.env`.
3. For **household geofencing** (see next section and README's Security
   model), everyone in the same home runs `/household NAME` with the same
   `NAME` - this groups them so "everyone in this household is away" can be
   detected.

## 11. Household geofencing (Clare Home, Aladdin Connect, iRobot)

### Clare Home (ClareOne/Fusion)
Clare doesn't publish a standard consumer API - access is via your
installer's Clare Fusion dealer portal, or a local ClareOne hub REST
endpoint if your installation exposes one. Ask your installer for API
access/documentation, then in `.env`: `CLAREHOME_BASE_URL=...`,
`CLAREHOME_API_KEY=...`. Verify with `list_clarehome_scenes` in chat before
relying on it.

### Aladdin Connect (Genie garage doors)
Unlike this repo's other smart-home integrations, there's no stable public
API or established community Python client for Aladdin Connect yet. Search
PyPI for a currently-maintained client package, `pip install` it yourself,
then adapt `src/integrations/smart_home/aladdin_connect.py`'s `_client()`
to match its interface. Set `ALADDIN_EMAIL`/`ALADDIN_PASSWORD` in `.env`
once you've done that. This one is explicitly a wiring template, not a
verified drop-in.

### iRobot (Roomba/Braava)
1. `pip install roombapy` (already in `requirements.txt`).
2. Put your robot in pairing mode (hold **CLEAN** until it beeps/flashes blue).
3. Run `python -m roombapy.getpassword <robot-ip>` to get its BLID + local password.
4. In `.env`: `IROBOT_ROBOT_IPS=ip:blid:password` (comma-separate for
   multiple robots).

### Geofencing automation (iPhone Shortcuts)
1. In `.env`: `PRESENCE_WEBHOOK_SECRET=<a random string you make up>` and
   ensure `PUBLIC_WEBHOOK_BASE_URL` is set (same tunnel as Twilio/WhatsApp,
   see step 7) and `uvicorn src.webhook_server:app --port 8000` is running.
2. On each household member's iPhone: **Shortcuts app -> Automation -> New
   Personal Automation -> Arrive/Leave** a location (your home address).
3. Add action **Get Contents of URL**: URL =
   `<PUBLIC_WEBHOOK_BASE_URL>/presence/<their internal chat id from /whoami>`,
   Method = POST, Headers = `X-Presence-Secret: <your PRESENCE_WEBHOOK_SECRET>`,
   Request Body (JSON) = `{"state": "away"}` (or `"home"` for the Arrive automation).
4. Turn off "Ask Before Running" so it fires silently.

Once everyone in a `/household NAME` group reports `away`, Clare Home is
switched to its "Away" scene automatically (and back to "Home" the moment
anyone returns) - **without** a Telegram confirm step, by deliberate design
(see README's "Security model", point 6).

## 12. Wishlist price monitoring & nearby food deals

- **Wishlist**: no extra credentials needed - just say "track this for me
  at $X" with a product URL. Price checks run every
  `WISHLIST_CHECK_INTERVAL_HOURS` (default 6) and alert you in Telegram with
  a one-tap "Order now" button (opens the page for you to complete
  checkout - see Security model on why there's no auto-purchase).
- **Nearby food deals**: reuses the same `SEARCH_API_KEY` from step 8; set
  `FOOD_DEALS_ZIP_CODE` or `FOOD_DEALS_CITY` in `.env`.

## 13. Discord channel (optional)

1. [discord.com/developers/applications](https://discord.com/developers/applications)
   -> **New Application -> Bot -> Reset Token** -> copy it.
2. Enable **Message Content Intent** under the Bot tab (required to read
   messages).
3. **OAuth2 -> URL Generator**: scopes `bot`, permissions `Send Messages` +
   `Read Message History` -> open the generated URL to invite it to your
   server.
4. In `.env`: `DISCORD_BOT_TOKEN=...`, `DISCORD_ALLOWED_CHANNEL_IDS=...`
   (right-click a channel -> Copy Channel ID, needs Developer Mode enabled
   in Discord settings).
5. Run it as its own process: `python -m src.discord_bot`.

---

## 14. Run it

Up to three independent long-running processes, depending on which
channels you configured:

```powershell
# Terminal 1 - Telegram bot (always needed)
python -m src.bot

# Terminal 2 - WhatsApp + interactive-call webhooks + geofencing presence endpoint (only if configured)
uvicorn src.webhook_server:app --port 8000

# Terminal 3 - Discord channel (only if configured)
python -m src.discord_bot
```

Or the batch scripts: `scripts\run_bot.bat`, `scripts\run_webhook_server.bat`.

**Smoke test:** message your Telegram bot "what can you help me with?" - you
should get a reply. Try something read-only like "what's on my calendar
today" to confirm an integration is wired up correctly. You can also send a
Telegram **voice note** instead of typing - it's transcribed automatically.

---

## 15. Keep it running after reboot/login (Windows Task Scheduler)

1. Open **Task Scheduler** -> **Create Task** (not "Basic Task", so you get
   the full options dialog).
2. **General** tab: name it `personal-ai-assistant-bot`; check **"Run
   whether user is logged on or not"** and **"Run with highest privileges"**.
3. **Triggers** tab -> **New** -> **At log on** (or **At startup** if you
   want it running even before you log in).
4. **Actions** tab -> **New** -> Program/script:
   `C:\GitHub\personal-ai-assistant\scripts\run_bot.bat`; Start in:
   `C:\GitHub\personal-ai-assistant`.
5. **Conditions** tab: uncheck "Start the task only if the computer is on
   AC power" if this is a desktop tower (usually irrelevant, but check on
   laptops).
6. Repeat steps 1-5 for `run_webhook_server.bat` as a second task, if you
   configured Twilio/WhatsApp.

This mirrors the same Task Scheduler pattern used by the sibling
`finance-bot` project - see its `setup_task_scheduler.bat` if you want a
scripted version of the above instead of the GUI.

---

## Troubleshooting quick reference

| Symptom | Likely cause / fix |
|---|---|
| `SSLCertVerificationError` during `pip install` | Corporate proxy intercepting TLS - point pip at the corporate CA, or use a Python install that already trusts it. |
| `ResolutionImpossible` during `pip install` | A dependency pin was tightened to `==` somewhere - use `>=` pins in `requirements.txt`. |
| Bot never replies on Telegram | Check `TELEGRAM_ALLOWED_CHAT_IDS` includes your chat ID (see step 3); check the bot process's console for errors. |
| "not configured" tool errors | Expected for any integration you haven't filled in `.env` yet - not a bug. |
| Device-code sign-in link never appears (MS365) | Run `python -m src.bot` directly in a visible terminal at least once - the link is printed to console, not sent via Telegram. |
| Interactive calls / WhatsApp don't respond | `PUBLIC_WEBHOOK_BASE_URL` must be a live, currently-running tunnel URL that matches what's set in the Twilio console - ngrok URLs rotate on restart. |
| `SyntaxWarning: invalid escape sequence` on startup | Harmless - cosmetic Python warning, doesn't affect behavior. |

## Security reminders (see README's "Security model" for full detail)

- `.env`, `config/tokens/`, and any downloaded OAuth client secret JSON are
  already in `.gitignore` - never commit them.
- The assistant never reads or stores your `personal-key-vault` secrets -
  it only foregrounds the app for you to unlock manually.
- Every money-moving, call-placing, or device-actuating tool always drafts
  first and waits for your explicit Telegram Confirm tap - review the
  "Security model" section in [README.md](README.md) before relying on this
  day-to-day.
