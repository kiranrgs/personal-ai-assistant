# Setup guide (fresh machine)

This is the full, step-by-step guide for getting `personal-ai-assistant`
running from a clean checkout on **Windows, macOS (including Mac Studio),
or Ubuntu/Linux** - any always-on machine works, this isn't Windows-only.
Most steps are identical across all three; where a command differs, both
versions are shown. It's more detailed than the README's quick-start so you
can follow it on a machine that has never had this repo (or its
dependencies) on it before.

Estimated total time: 30-90 minutes, depending on how many integrations you
configure on day one. You do **not** need to configure everything before
first run - every integration degrades gracefully (the tool just reports
"not configured" if you skip it).

---

## 0. Prerequisites

- **An always-on machine**: Windows 10/11, macOS (Mac Studio or any Mac),
  or Ubuntu/other Linux.
- **Python 3.11 or 3.12** (64-bit). Check with:
  ```
  python --version        # Windows
  python3 --version       # macOS/Ubuntu
  ```
  - **Windows**: install from [python.org/downloads](https://www.python.org/downloads/)
    - check **"Add python.exe to PATH"** during install.
  - **macOS**: `brew install python@3.12` (install [Homebrew](https://brew.sh) first if needed), or the official installer from python.org.
  - **Ubuntu**: `sudo apt update && sudo apt install python3 python3-venv python3-pip`.
- **Git** (to clone the repo):
  - Windows: [git-scm.com](https://git-scm.com/download/win).
  - macOS: `brew install git` (or Xcode Command Line Tools: `xcode-select --install`).
  - Ubuntu: `sudo apt install git`.
- A **Telegram account** (for the primary interaction channel).
- Optional but recommended: a **free Supabase account**
  ([supabase.com](https://supabase.com)) for persistent memory/audit log.

---

## 1. Get the code and install dependencies

**Windows (PowerShell):**
```powershell
git clone https://github.com/kiranrgs/personal-ai-assistant.git
cd personal-ai-assistant
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**macOS / Ubuntu (bash/zsh):**
```bash
git clone https://github.com/kiranrgs/personal-ai-assistant.git
cd personal-ai-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

> **Corporate proxy / SSL certificate errors during `pip install`?**
> If you see `SSLCertVerificationError: unable to get local issuer
> certificate`, your network is intercepting TLS (common on corporate
> laptops/VPNs). Fixes, in order of preference:
> 1. Ask IT for the corporate root CA `.pem` and run
>    `pip config set global.cert /path/to/corporate-ca.pem`, or
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
```
pytest tests/ -v
```
You should see all tests passing. If any integration module fails to
import, the error will name the missing package - re-run
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
   tracking, LLM usage logging, and full-text conversation search).
4. Then paste and run
   [supabase/migrations/0003_tenants.sql](supabase/migrations/0003_tenants.sql)
   too (additive - adds the `tenants` table for multi-tenant Telegram bots,
   see section 3). Run 0001, then 0002, then 0003, in that order.
   Also run 0004 (section on the desktop client) and then
   [supabase/migrations/0005_enable_rls.sql](supabase/migrations/0005_enable_rls.sql)
   last - it turns on Row Level Security for every table so the public
   `anon` key / a user's own login token can't read other people's data
   through Supabase's REST API (the server's service-role key is unaffected).
5. **Project Settings -> API**: copy the **Project URL** and the
   **`service_role` secret key** (not the `anon` key - this runs entirely
   server-side, on your own machine, never exposed to a browser).
6. In `.env`:
   ```
   SUPABASE_URL=https://xxxxx.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=eyJ...
   ```

---

## 3. Telegram bot(s) & admin console (required)

There is no `.env`-configured default bot - every Telegram bot, including
your very first one, is registered through the small admin console
(`src/admin_server.py`) instead of environment variables. This also means
you can register more bots later (e.g. hosting this for a couple of
households, each with their own `@BotFather` bot and allow-list, fully
isolated conversation history from each other) without ever hand-editing
`.env` or losing what's already running.

1. Set an admin login in `.env` (this is the only credential needed to
   reach the console itself - it doesn't belong to any one Telegram bot):
   ```
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=<a real password - the console refuses all requests if this is blank>
   ```
2. Run it: `uvicorn src.admin_server:app --port 8090` (or
   `scripts/run_admin_server.sh` / `scripts\run_admin_server.bat` - these
   bind to `127.0.0.1` only by default). **Put it behind HTTPS** if it
   needs to be reachable beyond localhost (same ngrok/Cloudflare
   Tunnel/reverse-proxy caveat as the webhook server in section 7) - HTTP
   Basic Auth sends your password on every request and needs TLS to not be
   readable on the wire.
3. Open `http://localhost:8090` (or your tunnel URL), sign in with
   `ADMIN_USERNAME`/`ADMIN_PASSWORD`.
4. Create your first Telegram bot with [@BotFather](https://t.me/BotFather):
   send `/newbot`, follow the prompts, copy the token it gives you.
5. Send **any message** to your new bot from your personal Telegram account
   (so Telegram creates a chat record), then in a browser open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and find
   `"chat":{"id":123456789,...}` - that number is your chat ID.
6. Back in the admin console's **Tenants page**: give this bot a name,
   paste in the token, and its allowed chat IDs (comma-separated if
   multiple people/devices should be allowed - e.g. your phone + your
   spouse's). Submit, then start (or restart) `python -m src.bot` - new/
   changed tenants are picked up at startup, not hot-reloaded into an
   already-running process.
7. Repeat step 4-6 (a *different* `@BotFather` bot each time) for any
   additional, fully-isolated bot you want to run in the same process.
8. **Users page:** view every known chat (across all tenants) and its
   current per-user overrides (masked, same whitelist as `/set` - see
   section 10), and set an override on someone's behalf without them
   needing to type `/set` themselves.

Every tenant's users are fully isolated from each other (separate bot
token, separate allow-list, separate conversation history via the internal
`tenant_id` column on each chat row - see
`supabase/migrations/0003_tenants.sql`) even if two different people happen
to share the same numeric Telegram user ID under two different bots.

---

## 4. LLM provider

**Groq (default, cloud, fast, free tier):**
1. Sign up at [console.groq.com](https://console.groq.com), create an API key.
2. In `.env`: `GROQ_API_KEY=gsk_...`
3. Models come from tier pools that mirror finance-bot (`GROQ_SMALL_MODEL_POOL`,
   `GROQ_MEDIUM_MODEL_POOL`, `GROQ_HIGH_MODEL_POOL`; comma-separated, defaults
   `qwen/qwen3.8-27b`, `openai/gpt-oss-20b`, `openai/gpt-oss-120b`). Repoint a tier
   in `.env` if Groq retires a model.
4. Default is the small tier. Desktop users pick small / medium / higher token
   models in Settings or per chat; the dropdown is server-driven
   (`GET /llm/models`) and the server rejects ids outside the catalog.
5. Telegram, WhatsApp and Discord chats are restricted to small-tier models
   (enforced server-side, including `/set GROQ_MODEL`).

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

- **finance-bot**: set `FINANCE_BOT_PATH` to its own path on this machine
  (e.g. `C:\GitHub\finance-bot` on Windows, `/home/you/finance-bot` on
  Ubuntu, `/Users/you/finance-bot` on macOS). The assistant
  subprocess-invokes finance-bot's own `.venv` - so finance-bot must already
  be independently set up and working there.
- **personal-key-vault**: same idea, set `PERSONAL_KEY_VAULT_PATH` to its
  path on this machine. On macOS this is a `.app` bundle
  (`personal-key-vault.app`) rather than a plain executable - see the
  `sys.platform` branching in
  `src/integrations/vault_bridge/personal_key_vault_client.py` if it can't
  find it. By default the assistant only ever brings this app to the
  foreground for you to manually unlock and copy a card - it never reads
  its secrets. personal-key-vault has its **own, separate** Supabase Auth
  (its own email/password, unrelated to this app's Supabase project) -
  since this machine's one installed vault app could be signed into
  anyone's account, each person must link their own chat to their own
  vault account email once. The admin sets `VAULT_ACCOUNT_EMAIL` for that chat
  on the admin console's Users page (users can't `/set` it themselves) - `open_key_vault_app()` refuses to
  run for a chat that hasn't linked one, and always echoes back the linked
  email so you can visually confirm the unlocked vault matches before
  copying a card.
  - **Companion API (optional, opt-in upgrade)**: personal-key-vault also
    exposes a loopback-only, token-authenticated "Companion apps API" that
    lets this assistant create a linked user, fetch cards/credentials, and
    resolve a default card per spend category (so a purchase that doesn't
    name a card falls back to whatever's pinned - or most-used - for that
    category) instead of only bringing the vault to the foreground. It's
    off by default for every chat. After enabling it in personal-key-vault's
    own Security tab -> "Enable companion API", the admin sets these for the
    chat on the admin console's Users page (they're admin-only keys):
    ```
    VAULT_COMPANION_PORT = <port from companion.json>
    VAULT_COMPANION_TOKEN = <this app's token from the Security tab>
    ```
    then clicks "enable" in the Vault companion API column. The same page
    has a per-user "Card defaults" page for pinning/clearing a
    default card per spend category (e.g. "utilities", "online shopping").
    Turn it back off any time with the "disable" button.

Skip either if you didn't clone those sibling repos onto this machine.

---

## 10. Multi-user & households (optional - skip if it's just you)

Every allow-listed Telegram chat ID is automatically its own "user" - no
extra setup needed to isolate them. To let each person configure their
*own* accounts/integrations instead of sharing one `.env`:

1. Add everyone's chat ID to that tenant's allowed chat IDs on the admin
   console's Tenants page (comma-separated, see section 3).
2. Each person messages the bot `/whoami` to confirm their chat is
   recognized, then `/set KEY VALUE` for anything personal - e.g.
   `/set TWITTER_FOLLOWED_HANDLES handle1,handle2`. `/myconfig` lists what's saved (values masked);
   `/unset KEY` removes one. Only a whitelisted subset of settings can be
   set this way (personal API keys/integrations). Keys that pick shared
   server-side credentials or local paths (`GOOGLE_ACCOUNTS`, `MS_ACCOUNTS`,
   `ICLOUD_ACCOUNTS`, `YAHOO_ACCOUNTS`, `FINANCE_BOT_PATH`,
   `PERSONAL_KEY_VAULT_PATH`, `HOMEBRIDGE_URL`, `VAULT_*`, ...) are
   admin-only - set them on the admin console's Users page. Shared settings
   (bot tokens, Supabase key, allow-lists) always stay in the
   root `.env`/admin console.
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
5. Run it as its own process: `python -m src.discord_bot` (or
   `scripts/run_discord_bot.sh` / `scripts\run_discord_bot.bat`).

---

## 14. Job search (optional)

Searches multiple job portals (LinkedIn, Indeed, Glassdoor, ZipRecruiter by
default) for openings matching role keywords you save once, via web search
- reuses the same `SEARCH_API_KEY` from step 8, no separate credential
needed.

1. Make sure `SEARCH_API_KEY` is set (section 8).
2. Optionally customize the portal list / a default location, in `.env`:
   ```
   JOB_SEARCH_PORTALS=linkedin.com/jobs,indeed.com,glassdoor.com/job-listing,ziprecruiter.com
   JOB_SEARCH_DEFAULT_LOCATION=
   ```
   or per-user via `/set JOB_SEARCH_PORTALS ...` / `/set JOB_SEARCH_DEFAULT_LOCATION ...`.
3. In chat, tell it your profile once, e.g. *"my job search profile is
   senior backend engineer, staff software engineer, based in Austin TX,
   remote ok"* - this calls `set_job_search_profile` and saves it (a real
   web search + summarize pass, not fabricated matches).
4. Then just ask *"any new job matches for me?"* any time, or let the daily
   `jobsearch` job (see section 15) check every morning at 9am.

This is web-search-based, not a live ATS/portal feed - none of these sites
offer a personal-use "search jobs" API, same honesty tradeoff as the ticket
search and food-deals integrations.

---

## 15. Run it

Up to four independent long-running processes, depending on which channels/
features you configured:

```powershell
# Terminal 1 - Telegram bot (always needed) - runs every configured tenant
python -m src.bot

# Terminal 2 - WhatsApp + interactive-call webhooks + geofencing presence endpoint (only if configured)
uvicorn src.webhook_server:app --port 8000

# Terminal 3 - Discord channel (only if configured)
python -m src.discord_bot

# Terminal 4 - Admin console: only needed when adding/editing tenants or user overrides
uvicorn src.admin_server:app --port 8090

# Terminal 5 - Desktop client API: only needed if you're using the downloadable
# Mac/Windows client (see section 17)
uvicorn src.client_api_server:app --port 8092
```

Windows: `scripts\run_bot.bat`, `scripts\run_webhook_server.bat`,
`scripts\run_discord_bot.bat`, `scripts\run_admin_server.bat`.
macOS/Ubuntu: the `.sh` equivalents in `scripts/` (`chmod +x scripts/*.sh`
once, then run them directly, or `bash scripts/run_bot.sh`).

**Smoke test:** message your Telegram bot "what can you help me with?" - you
should get a reply. Try something read-only like "what's on my calendar
today" to confirm an integration is wired up correctly. You can also send a
Telegram **voice note** instead of typing - it's transcribed automatically.

---

## 16. Keep it running after reboot/login

### Windows (Task Scheduler)

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
6. Repeat steps 1-5 for `run_webhook_server.bat` (and `run_admin_server.bat`,
   `run_discord_bot.bat`) as additional tasks, for whichever other
   processes you configured.

This mirrors the same Task Scheduler pattern used by the sibling
`finance-bot` project - see its `setup_task_scheduler.bat` if you want a
scripted version of the above instead of the GUI.

### macOS (launchd)

1. Create `~/Library/LaunchAgents/com.personal-ai-assistant.bot.plist`:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0"><dict>
     <key>Label</key><string>com.personal-ai-assistant.bot</string>
     <key>ProgramArguments</key>
     <array>
       <string>/Users/you/personal-ai-assistant/scripts/run_bot.sh</string>
     </array>
     <key>WorkingDirectory</key><string>/Users/you/personal-ai-assistant</string>
     <key>RunAtLoad</key><true/>
     <key>KeepAlive</key><true/>
     <key>StandardOutPath</key><string>/tmp/personal-ai-assistant-bot.log</string>
     <key>StandardErrorPath</key><string>/tmp/personal-ai-assistant-bot.err</string>
   </dict></plist>
   ```
   (adjust the paths to wherever you cloned the repo; `chmod +x
   scripts/run_bot.sh` first).
2. Load it: `launchctl load ~/Library/LaunchAgents/com.personal-ai-assistant.bot.plist`.
3. Repeat for `run_webhook_server.sh`/`run_admin_server.sh`/
   `run_discord_bot.sh` as separate `.plist` files (different `Label`,
   `ProgramArguments`, log paths) for whichever other processes you
   configured.
4. `launchctl unload <plist>` to stop; check logs at the `StandardOutPath`/
   `StandardErrorPath` you set if it's not responding.

### Ubuntu (systemd user service)

1. Create `~/.config/systemd/user/personal-ai-assistant-bot.service`:
   ```ini
   [Unit]
   Description=personal-ai-assistant Telegram bot
   After=network-online.target

   [Service]
   WorkingDirectory=/home/you/personal-ai-assistant
   ExecStart=/home/you/personal-ai-assistant/scripts/run_bot.sh
   Restart=on-failure

   [Install]
   WantedBy=default.target
   ```
   (adjust the path; `chmod +x scripts/run_bot.sh` first).
2. `systemctl --user daemon-reload && systemctl --user enable --now personal-ai-assistant-bot`.
3. `loginctl enable-linger $USER` so it keeps running after you log out of
   the desktop session (not just while a terminal is open).
4. Repeat with a new unit file (different name, `ExecStart`) for
   `run_webhook_server.sh`/`run_admin_server.sh`/`run_discord_bot.sh` for
   whichever other processes you configured.
5. `journalctl --user -u personal-ai-assistant-bot -f` to tail logs.

---

## 17. Desktop client (optional download for Mac/Windows users)

A downloadable chat client under [apps/desktop](apps/desktop) - the user
sees only a chat window, a bookmarks sidebar, and a settings page (no code,
no tool internals). It talks to a dedicated backend, `src/client_api_server.py`,
over HTTPS/loopback-HTTP - this is the only process that needs to run on a
server you control for the desktop client to work; it doesn't touch
`bot.py`/`webhook_server.py`/`discord_bot.py` at all.

1. **Enable email/password sign-in in this project's own Supabase project**
   (Authentication -> Providers -> Email, in the Supabase dashboard for the
   *same* project you set up in section 2 - this is separate from any
   `personal-key-vault` Supabase project). Decide whether to require email
   confirmation there; if enabled, new desktop sign-ups get a
   `confirmation_required` response and must click the emailed link before
   they can sign in.
2. **Run the client API server**: `uvicorn src.client_api_server:app --port 8092`
   (Terminal 5 above, or `scripts\run_client_api_server.bat` /
   `scripts/run_client_api_server.sh` if present). Put this behind HTTPS
   (e.g. a reverse proxy or tunnel) before pointing a real client at
   anything other than `127.0.0.1`.
3. **Run the migration** [supabase/migrations/0004_desktop_accounts.sql](supabase/migrations/0004_desktop_accounts.sql)
   in the Supabase SQL editor (adds the `desktop` chat channel and the
   `chat_bookmarks` table), same manual-run convention as the other
   `supabase/migrations/*.sql` files in this repo.
4. **Build/run the desktop client**: see [apps/desktop/README.md](apps/desktop/README.md)
   for full instructions (`npm install`, `.env` setup pointing
   `VITE_SERVER_URL` at step 2's server, `npm run tauri dev`/`npm run tauri build`).
   Building the native shell requires Rust/Cargo (`rustup.rs`) in addition
   to Node.js - only the React/TypeScript frontend has been build-verified
   in this repo so far, the Rust/Tauri packaging step needs to be verified
   on your own machine.
5. Each person who signs up in the desktop app gets their own `chats` row
   (channel `desktop`) and their own isolated settings/bookmarks/vault
   defaults - identical per-user isolation model to Telegram/WhatsApp/Discord
   chats, just keyed by their Supabase Auth user id instead of a chat platform id.
6. To let a desktop user also receive Telegram-only notifications (e.g.
   wishlist price alerts), they click **Get link code** in the desktop app's
   Settings page and send `/link CODE` to the Telegram bot from their
   (allow-listed) Telegram chat within 10 minutes. The code is single-use,
   so nobody can link a Telegram chat they don't control. This is a one-way
   notification link, not a merged chat history.
7. The desktop app keeps only its refresh token, in the OS credential store
   (Windows Credential Manager / macOS Keychain / Linux Secret Service); the
   access token lives in memory only. Production builds also restrict the
   app's network access to the `VITE_SERVER_URL` origin.
8. `client_api_server.py`, `webhook_server.py` and the admin console refuse
   plain-HTTP requests from other machines - use a TLS reverse proxy or
   tunnel on the same host. If the proxy forwards the real client IP, start
   uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy ip>` so login
   rate limits apply per real client. The admin console only answers
   localhost unless `ADMIN_ALLOW_REMOTE=true`.

---

## Troubleshooting quick reference

| Symptom | Likely cause / fix |
|---|---|
| `SSLCertVerificationError` during `pip install` | Corporate proxy intercepting TLS - point pip at the corporate CA, or use a Python install that already trusts it. |
| `ResolutionImpossible` during `pip install` | A dependency pin was tightened to `==` somewhere - use `>=` pins in `requirements.txt`. |
| Bot never replies on Telegram | Check your chat ID is in that tenant's allowed chat IDs on the admin console's Tenants page (see section 3); check the bot process's console for errors. |
| "No Telegram bot configured" on `python -m src.bot` startup | No tenant exists in Supabase yet - open the admin console and add one on the Tenants page first (section 3). |
| "not configured" tool errors | Expected for any integration you haven't filled in `.env` yet - not a bug. |
| Device-code sign-in link never appears (MS365) | Run `python -m src.bot` directly in a visible terminal at least once - the link is printed to console, not sent via Telegram. |
| Interactive calls / WhatsApp don't respond | `PUBLIC_WEBHOOK_BASE_URL` must be a live, currently-running tunnel URL that matches what's set in the Twilio console - ngrok URLs rotate on restart. |
| `SyntaxWarning: invalid escape sequence` on startup | Harmless - cosmetic Python warning, doesn't affect behavior. |
| Admin console returns `503` on every request | `ADMIN_PASSWORD` is blank in `.env` - it fails closed on purpose until you set a real password. |
| New/edited tenant in the admin console isn't picked up | Tenants are only loaded at `python -m src.bot` startup, not hot-reloaded - restart the bot process. |
| `python-key-vault`/`finance-bot` "not found" on macOS/Ubuntu | Set `PERSONAL_KEY_VAULT_PATH`/`FINANCE_BOT_PATH` to that sibling repo's actual location on this machine (any OS path works, not just Windows). |
| `open_key_vault_app` returns `not_linked` | That chat hasn't linked a personal-key-vault account yet - send `/set VAULT_ACCOUNT_EMAIL you@example.com` (section 9) once. |
| Desktop client shows "Missing VITE_SERVER_URL" | Copy `apps/desktop/.env.example` to `apps/desktop/.env` and set it before running `npm run dev`/`tauri dev` (section 17). |
| Desktop client startup throws "is plain HTTP but points at a non-local host" | `VITE_SERVER_URL` points at a non-loopback host over `http://` - use `https://`, or point it at `127.0.0.1`/`localhost` for local testing only (section 17). |
| Desktop sign-up returns `confirmation_required` and login then fails | Email confirmation is enabled on the Supabase project - click the emailed confirmation link before signing in (section 17). |

## Security reminders (see README's "Security model" for full detail)

- `.env`, `config/tokens/`, and any downloaded OAuth client secret JSON are
  already in `.gitignore` - never commit them.
- The assistant never reads or stores your `personal-key-vault` secrets -
  it only foregrounds the app for you to unlock manually.
- Every money-moving, call-placing, or device-actuating tool always drafts
  first and waits for your explicit Telegram Confirm tap - review the
  "Security model" section in [README.md](README.md) before relying on this
  day-to-day.
