"""Centralized configuration, loaded from .env / OS environment.

Every other module reads config through `get_settings()` instead of calling
os.environ directly, so there is one place that documents every credential
the assistant can use and whether it's actually configured.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    # WhatsApp (via Twilio)
    whatsapp_enabled: bool = Field(default=False, alias="WHATSAPP_ENABLED")
    twilio_whatsapp_from: str = Field(default="", alias="TWILIO_WHATSAPP_FROM")

    # LLM routing
    llm_default_provider: str = Field(default="groq", alias="LLM_DEFAULT_PROVIDER")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="qwen/qwen3.8-27b", alias="GROQ_MODEL")
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="llama3.1", alias="OLLAMA_MODEL")

    # Supabase
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")

    # Google
    google_oauth_client_secrets_file: str = Field(default="config/google_client_secret.json", alias="GOOGLE_OAUTH_CLIENT_SECRETS_FILE")
    google_accounts: str = Field(default="", alias="GOOGLE_ACCOUNTS")
    google_token_dir: str = Field(default="config/tokens/google", alias="GOOGLE_TOKEN_DIR")

    # Microsoft 365
    ms_client_id: str = Field(default="", alias="MS_CLIENT_ID")
    ms_tenant_id: str = Field(default="common", alias="MS_TENANT_ID")
    ms_accounts: str = Field(default="", alias="MS_ACCOUNTS")
    ms_token_dir: str = Field(default="config/tokens/ms", alias="MS_TOKEN_DIR")

    # iCloud / Yahoo (IMAP + CalDAV)
    icloud_accounts: str = Field(default="", alias="ICLOUD_ACCOUNTS")
    yahoo_accounts: str = Field(default="", alias="YAHOO_ACCOUNTS")

    # Smart home
    smartthings_pat: str = Field(default="", alias="SMARTTHINGS_PAT")
    nest_project_id: str = Field(default="", alias="NEST_PROJECT_ID")
    nest_client_id: str = Field(default="", alias="NEST_CLIENT_ID")
    nest_client_secret: str = Field(default="", alias="NEST_CLIENT_SECRET")
    nest_refresh_token: str = Field(default="", alias="NEST_REFRESH_TOKEN")
    wyze_email: str = Field(default="", alias="WYZE_EMAIL")
    wyze_password: str = Field(default="", alias="WYZE_PASSWORD")
    wyze_key_id: str = Field(default="", alias="WYZE_KEY_ID")
    wyze_api_key: str = Field(default="", alias="WYZE_API_KEY")
    homebridge_url: str = Field(default="", alias="HOMEBRIDGE_URL")
    homebridge_username: str = Field(default="", alias="HOMEBRIDGE_USERNAME")
    homebridge_password: str = Field(default="", alias="HOMEBRIDGE_PASSWORD")
    clarehome_base_url: str = Field(default="", alias="CLAREHOME_BASE_URL")
    clarehome_api_key: str = Field(default="", alias="CLAREHOME_API_KEY")
    aladdin_email: str = Field(default="", alias="ALADDIN_EMAIL")
    aladdin_password: str = Field(default="", alias="ALADDIN_PASSWORD")
    irobot_robot_ips: str = Field(default="", alias="IROBOT_ROBOT_IPS")

    # Telephony
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str = Field(default="", alias="TWILIO_FROM_NUMBER")
    public_webhook_base_url: str = Field(default="", alias="PUBLIC_WEBHOOK_BASE_URL")

    # Social
    twitter_bearer_token: str = Field(default="", alias="TWITTER_BEARER_TOKEN")
    twitter_consumer_key: str = Field(default="", alias="TWITTER_CONSUMER_KEY")
    twitter_consumer_secret: str = Field(default="", alias="TWITTER_CONSUMER_SECRET")
    twitter_access_token: str = Field(default="", alias="TWITTER_ACCESS_TOKEN")
    twitter_access_token_secret: str = Field(default="", alias="TWITTER_ACCESS_TOKEN_SECRET")
    twitter_followed_handles: str = Field(default="", alias="TWITTER_FOLLOWED_HANDLES")
    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")

    # Web research
    search_api_key: str = Field(default="", alias="SEARCH_API_KEY")
    search_provider: str = Field(default="bing", alias="SEARCH_PROVIDER")

    # Job search (reuses SEARCH_API_KEY above - no separate credential)
    job_search_portals: str = Field(
        default="linkedin.com/jobs,indeed.com,glassdoor.com/job-listing,ziprecruiter.com",
        alias="JOB_SEARCH_PORTALS",
    )
    job_search_default_location: str = Field(default="", alias="JOB_SEARCH_DEFAULT_LOCATION")

    # Wishlist price monitoring
    wishlist_check_interval_hours: int = Field(default=6, alias="WISHLIST_CHECK_INTERVAL_HOURS")

    # Nearby food-delivery deal monitoring
    food_deals_zip_code: str = Field(default="", alias="FOOD_DEALS_ZIP_CODE")
    food_deals_city: str = Field(default="", alias="FOOD_DEALS_CITY")

    # Morning briefing weather (Open-Meteo, no key needed - just coordinates)
    briefing_latitude: str = Field(default="", alias="BRIEFING_LATITUDE")
    briefing_longitude: str = Field(default="", alias="BRIEFING_LONGITUDE")

    # Geofencing / household presence webhook (see webhook_server.py's /presence endpoint)
    presence_webhook_secret: str = Field(default="", alias="PRESENCE_WEBHOOK_SECRET")

    # Anomaly detection (rate-limit unusually repetitive tool calls per chat)
    anomaly_tool_call_threshold: int = Field(default=15, alias="ANOMALY_TOOL_CALL_THRESHOLD")
    anomaly_window_minutes: int = Field(default=5, alias="ANOMALY_WINDOW_MINUTES")

    # Discord (optional additional channel alongside Telegram/WhatsApp)
    discord_bot_token: str = Field(default="", alias="DISCORD_BOT_TOKEN")
    discord_allowed_channel_ids: str = Field(default="", alias="DISCORD_ALLOWED_CHANNEL_IDS")

    # Admin console (src/admin_server.py) - multi-tenant Telegram bot
    # registration + editing any user's per-user overrides from a browser.
    # Left blank by default (fails closed: the console refuses every
    # request until you set a real password).
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="", alias="ADMIN_PASSWORD")

    # Sibling apps - no platform-specific default; this repo runs on
    # Windows, macOS, and Linux/Ubuntu, so point this at wherever you
    # actually cloned the sibling project on your machine.
    finance_bot_path: str = Field(default="", alias="FINANCE_BOT_PATH")
    personal_key_vault_path: str = Field(default="", alias="PERSONAL_KEY_VAULT_PATH")

    # personal-key-vault is a separate, zero-knowledge app with its own
    # Supabase Auth (its own email/password, unrelated to this app's
    # Supabase project). This is set per-user (via /set, never shared
    # admin-wide) to the email that person signed up with there, so
    # open_key_vault_app() can refuse to run for a chat that hasn't
    # explicitly linked an account - see
    # src/integrations/vault_bridge/personal_key_vault_client.py.
    vault_account_email: str = Field(default="", alias="VAULT_ACCOUNT_EMAIL")

    # personal-key-vault's "Companion apps API" - an opt-in, per-user upgrade
    # over the manual open_key_vault_app() flow above. When enabled, this
    # assistant can create/look up a companion-API user, fetch cards/
    # credentials, and resolve/manage per-category default cards, all over a
    # loopback-only token-authenticated socket (never Supabase directly).
    # Left OFF by default - a user opts in (and can opt back out any time)
    # with `/set VAULT_API_ENABLED true` (or the admin console), same as
    # VAULT_ACCOUNT_EMAIL above, which must also be set first. Host/port/
    # token come from that machine's companion.json + the Security tab in
    # personal-key-vault - see its README's "Companion apps API" section.
    vault_api_enabled: bool = Field(default=False, alias="VAULT_API_ENABLED")
    vault_companion_host: str = Field(default="127.0.0.1", alias="VAULT_COMPANION_HOST")
    vault_companion_port: int = Field(default=0, alias="VAULT_COMPANION_PORT")
    vault_companion_token: str = Field(default="", alias="VAULT_COMPANION_TOKEN")
    vault_app_name: str = Field(default="personal-ai-assistant", alias="VAULT_APP_NAME")

    @property
    def discord_allowed_channel_id_list(self) -> list[int]:
        return [int(v) for v in _split_csv(self.discord_allowed_channel_ids)]

    @property
    def google_account_labels(self) -> list[str]:
        return _split_csv(self.google_accounts)

    @property
    def ms_account_labels(self) -> list[str]:
        return _split_csv(self.ms_accounts)

    @property
    def icloud_account_labels(self) -> list[str]:
        return _split_csv(self.icloud_accounts)

    @property
    def yahoo_account_labels(self) -> list[str]:
        return _split_csv(self.yahoo_accounts)

    @property
    def twitter_followed_handle_list(self) -> list[str]:
        return _split_csv(self.twitter_followed_handles)

    @property
    def irobot_robot_entries(self) -> list[str]:
        return _split_csv(self.irobot_robot_ips)

    @property
    def job_search_portal_list(self) -> list[str]:
        return _split_csv(self.job_search_portals)


@lru_cache
def _base_settings() -> Settings:
    return Settings()


# Cache of per-user merged Settings, keyed by (chat_id, sorted override items).
_user_settings_cache: dict[tuple[Any, ...], Settings] = {}


def get_settings() -> Settings:
    """Returns the base process-wide Settings, UNLESS a per-user context is
    active (see core.user_config.set_current_chat) and that user has any
    override file - in which case a merged Settings instance (base .env,
    with that user's overrides layered on top for just the keys they set) is
    returned instead. This lets every integration module keep calling
    `get_settings()` unchanged while still being multi-user-aware.
    """
    try:
        from src.core.user_config import get_current_chat, load_user_overrides
    except ImportError:  # pragma: no cover - user_config always available in this repo
        return _base_settings()

    chat_id = get_current_chat()
    if chat_id is None:
        return _base_settings()

    overrides = load_user_overrides(chat_id)
    if not overrides:
        return _base_settings()

    cache_key = (chat_id, tuple(sorted(overrides.items())))
    cached = _user_settings_cache.get(cache_key)
    if cached is None:
        cached = Settings(**overrides)
        _user_settings_cache[cache_key] = cached
    return cached
