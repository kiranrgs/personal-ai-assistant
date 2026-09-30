from src.core import llm_models


def test_catalog_has_all_three_tiers_and_small_default():
    models = llm_models.list_groq_models()
    assert {m["tier"] for m in models} == {"small", "medium", "high"}
    by_id = {m["id"]: m for m in models}
    assert by_id[llm_models.default_model()]["tier"] == "small"


def test_desktop_sees_all_models_telegram_only_small():
    assert len(llm_models.list_models_for_channel("desktop")) == len(llm_models.list_groq_models())
    telegram = llm_models.list_models_for_channel("telegram")
    assert telegram and all(m["tier"] == "small" for m in telegram)


def test_resolve_model_enforces_channel_and_catalog():
    high = next(m["id"] for m in llm_models.list_groq_models() if m["tier"] == "high")
    default = llm_models.default_model()
    assert llm_models.resolve_model("desktop", requested=high) == high
    assert llm_models.resolve_model("telegram", requested=high) == default
    assert llm_models.resolve_model("telegram", user_preferred=high) == default
    assert llm_models.resolve_model("desktop", requested="not-a-real-model") == default
    assert llm_models.resolve_model("desktop", requested="bad", user_preferred=high) == high


def test_pools_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("GROQ_SMALL_MODEL_POOL", "a/one,a/two")
    ids = [m["id"] for m in llm_models.list_models_for_channel("telegram")]
    assert ids == ["a/one", "a/two"]
