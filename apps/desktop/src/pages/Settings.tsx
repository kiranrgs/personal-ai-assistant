import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  clearVaultCardDefault,
  deleteSetting,
  getLlmModels,
  modelOptionLabel,
  TIER_GROUPS,
  getSettings,
  getVaultCardDefaults,
  getVaultCards,
  LlmModel,
  Me,
  setSetting,
  setVaultCardDefault,
  VaultCard,
} from "../lib/apiClient";

const TELEGRAM_KEY = "LINKED_TELEGRAM_CHAT_ID";

export default function Settings({ me, onSignOut }: { me: Me; onSignOut: () => void }) {
  const [settings, setSettings] = useState<Record<string, string>>(me.settings);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [telegramId, setTelegramId] = useState(me.settings[TELEGRAM_KEY] ?? "");

  const [cards, setCards] = useState<VaultCard[]>([]);
  const [defaults, setDefaults] = useState<Record<string, VaultCard>>({});
  const [newCategory, setNewCategory] = useState("");
  const [newCardId, setNewCardId] = useState("");
  const [vaultError, setVaultError] = useState<string | null>(null);

  const [models, setModels] = useState<LlmModel[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [defaultModel, setDefaultModel] = useState("");
  const [modelsError, setModelsError] = useState<string | null>(null);

  useEffect(() => {
    void refreshSettings();
    void refreshVault();
    void refreshModels();
  }, []);

  async function refreshSettings() {
    const { settings } = await getSettings();
    setSettings(settings);
    setTelegramId(settings[TELEGRAM_KEY] ?? "");
  }

  async function refreshVault() {
    try {
      const [cardsResult, defaultsResult] = await Promise.all([getVaultCards(), getVaultCardDefaults()]);
      setCards(cardsResult.cards);
      setDefaults(defaultsResult.defaults);
      setVaultError(null);
    } catch {
      // Vault companion API may not be enabled/configured for this user -
      // that's an expected, non-fatal state, not a bug.
      setVaultError("Vault card defaults are unavailable. Enable the companion API for your account first.");
    }
  }

  async function refreshModels() {
    try {
      const result = await getLlmModels();
      setModels(result.models);
      setSelectedModel(result.selected_model);
      setDefaultModel(result.default_model);
      setModelsError(null);
    } catch {
      setModelsError("Couldn't load server model list right now.");
    }
  }

  async function handleSaveOverride(e: FormEvent) {
    e.preventDefault();
    if (!newKey.trim()) return;
    await setSetting(newKey.trim(), newValue);
    setNewKey("");
    setNewValue("");
    await refreshSettings();
  }

  async function handleDeleteOverride(key: string) {
    await deleteSetting(key);
    await refreshSettings();
  }

  async function handleSaveTelegram(e: FormEvent) {
    e.preventDefault();
    if (telegramId.trim()) {
      await setSetting(TELEGRAM_KEY, telegramId.trim());
    } else {
      await deleteSetting(TELEGRAM_KEY);
    }
    await refreshSettings();
  }

  async function handleSaveModel(e: FormEvent) {
    e.preventDefault();
    if (!selectedModel) return;
    await setSetting("GROQ_MODEL", selectedModel);
    await refreshSettings();
    await refreshModels();
  }

  async function handleSetDefault(e: FormEvent) {
    e.preventDefault();
    if (!newCategory.trim() || !newCardId) return;
    await setVaultCardDefault(newCategory.trim(), newCardId);
    setNewCategory("");
    setNewCardId("");
    await refreshVault();
  }

  async function handleClearDefault(category: string) {
    await clearVaultCardDefault(category);
    await refreshVault();
  }

  const otherSettings = Object.entries(settings).filter(
    ([key]) => key !== TELEGRAM_KEY && key !== "GROQ_MODEL"
  );

  return (
    <div className="settings-page">
      <div className="settings-header">
        <Link to="/chat">← Back to chat</Link>
        <button className="link-button" onClick={onSignOut}>
          Sign out
        </button>
      </div>
      <h1>Settings</h1>

      <section>
        <h2>Telegram notifications</h2>
        <p className="muted">
          Link your Telegram chat ID so scheduled alerts (e.g. wishlist notifications) can reach you there
          even while you're using the desktop app.
        </p>
        <form onSubmit={handleSaveTelegram} className="inline-form">
          <input
            placeholder="Telegram chat ID"
            value={telegramId}
            onChange={(e) => setTelegramId(e.target.value)}
          />
          <button type="submit">Save</button>
        </form>
      </section>

      <section>
        <h2>AI model</h2>
        <p className="muted">
          Choose a small, medium, or higher token-consumption model for your chat requests. Small is the
          default. Telegram always uses small-tier models only.
        </p>
        {modelsError && <p className="form-error">{modelsError}</p>}
        {!modelsError && (
          <form onSubmit={handleSaveModel} className="inline-form">
            <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
              <option value="">Select a model…</option>
              {TIER_GROUPS.map((group) => (
                <optgroup key={group.tier} label={group.label}>
                  {models
                    .filter((model) => model.tier === group.tier)
                    .map((model) => (
                      <option key={model.id} value={model.id}>
                        {modelOptionLabel(model)}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
            <button type="submit" disabled={!selectedModel}>
              Save model
            </button>
          </form>
        )}
        {defaultModel && <p className="muted">Server default: {defaultModel}</p>}
      </section>

      <section>
        <h2>Card defaults by category</h2>
        {vaultError && <p className="form-error">{vaultError}</p>}
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th>Default card</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(defaults).map(([category, card]) => (
              <tr key={category}>
                <td>{category}</td>
                <td>
                  {card.label} ({card.bankName} •••• {card.last4})
                </td>
                <td>
                  <button className="link-button" onClick={() => handleClearDefault(category)}>
                    Clear
                  </button>
                </td>
              </tr>
            ))}
            {Object.keys(defaults).length === 0 && !vaultError && (
              <tr>
                <td colSpan={3} className="muted">
                  No card defaults set yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {!vaultError && (
          <form onSubmit={handleSetDefault} className="inline-form">
            <input
              placeholder="Category (e.g. groceries)"
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
            />
            <select value={newCardId} onChange={(e) => setNewCardId(e.target.value)}>
              <option value="">Select a card…</option>
              {cards.map((card) => (
                <option key={card.id} value={card.id}>
                  {card.label} ({card.bankName} •••• {card.last4})
                </option>
              ))}
            </select>
            <button type="submit">Set default</button>
          </form>
        )}
      </section>

      <section>
        <h2>Other overrides</h2>
        <table>
          <thead>
            <tr>
              <th>Key</th>
              <th>Value</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {otherSettings.map(([key, value]) => (
              <tr key={key}>
                <td>{key}</td>
                <td>{value}</td>
                <td>
                  <button className="link-button" onClick={() => handleDeleteOverride(key)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {otherSettings.length === 0 && (
              <tr>
                <td colSpan={3} className="muted">
                  No other overrides set.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <form onSubmit={handleSaveOverride} className="inline-form">
          <input placeholder="Key" value={newKey} onChange={(e) => setNewKey(e.target.value)} />
          <input placeholder="Value" value={newValue} onChange={(e) => setNewValue(e.target.value)} />
          <button type="submit">Add / update</button>
        </form>
      </section>
    </div>
  );
}
