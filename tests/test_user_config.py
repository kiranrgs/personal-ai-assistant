import pytest

from src.core import settings as settings_mod
from src.core import user_config


@pytest.fixture(autouse=True)
def _isolated_users_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(user_config, "USERS_DIR", tmp_path)
    monkeypatch.setattr(user_config, "_isolated_chats", set())
    settings_mod._user_settings_cache.clear()
    yield
    settings_mod._user_settings_cache.clear()


def test_rejects_newline_injection():
    with pytest.raises(ValueError):
        user_config.set_user_override(1, "YOUTUBE_API_KEY", "abc\nFINANCE_BOT_PATH=\\\\evil\\share")
    assert user_config.load_user_overrides(1) == {}


def test_admin_only_key_requires_admin():
    with pytest.raises(ValueError):
        user_config.set_user_override(1, "VAULT_ACCOUNT_EMAIL", "victim@example.com")
    with pytest.raises(ValueError):
        user_config.unset_user_override(1, "VAULT_ACCOUNT_EMAIL")
    user_config.set_user_override(1, "VAULT_ACCOUNT_EMAIL", "me@example.com", admin=True)
    assert user_config.load_user_overrides(1)["VAULT_ACCOUNT_EMAIL"] == "me@example.com"


def test_unknown_keys_in_file_are_ignored(tmp_path):
    d = tmp_path / "1"
    d.mkdir()
    (d / "user.env").write_text("SUPABASE_SERVICE_KEY=stolen\nGROQ_MODEL=qwen/qwen3.8-27b\n")
    assert user_config.load_user_overrides(1) == {"GROQ_MODEL": "qwen/qwen3.8-27b"}


def test_display_masks_secrets_only():
    user_config.set_user_override(1, "YOUTUBE_API_KEY", "supersecretvalue")
    user_config.set_user_override(1, "FOOD_DEALS_CITY", "Seattle")
    shown = user_config.list_user_overrides_for_display(1)
    assert shown["FOOD_DEALS_CITY"] == "Seattle"
    assert "supersecretvalue" not in shown["YOUTUBE_API_KEY"]


def test_isolated_chat_does_not_inherit_owner_env(monkeypatch):
    monkeypatch.setenv("FINANCE_BOT_PATH", "C:\\owner\\finance-bot")
    settings_mod._base_settings.cache_clear()
    try:
        with user_config.set_current_chat(42):
            assert settings_mod.get_settings().finance_bot_path == "C:\\owner\\finance-bot"
        user_config.mark_isolated_chat(99)
        with user_config.set_current_chat(99):
            assert settings_mod.get_settings().finance_bot_path == ""
    finally:
        settings_mod._base_settings.cache_clear()
