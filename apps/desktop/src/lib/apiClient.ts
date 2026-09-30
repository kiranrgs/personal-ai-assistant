// Client for this project's client_api_server.py. The desktop app never
// talks to Supabase directly and never holds Supabase project credentials -
// it only ever calls this server over HTTP, with a bearer token attached to
// every request after sign-in.
import { invoke } from "@tauri-apps/api/core";

const SERVER_URL = (import.meta.env.VITE_SERVER_URL as string | undefined)?.replace(/\/+$/, "");

if (!SERVER_URL) {
  throw new Error(
    "Missing VITE_SERVER_URL. Copy .env.example to .env and point it at your client_api_server.py instance."
  );
}

// Refuse to ship/run a build that would send login passwords and session
// tokens over plaintext HTTP to a non-local server. Loopback
// (127.0.0.1/localhost) is exempt since that traffic never leaves the
// machine; anything else MUST be https://.
{
  const url = new URL(SERVER_URL);
  const isLoopback = ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
  if (url.protocol === "http:" && !isLoopback) {
    throw new Error(
      `VITE_SERVER_URL (${SERVER_URL}) is plain HTTP but points at a non-local host. ` +
        "Use an https:// URL for anything other than 127.0.0.1/localhost."
    );
  }
}

export interface Session {
  access_token: string;
  refresh_token: string;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

// Session storage: only the refresh token is persisted, and it lives in the
// OS credential store (Windows Credential Manager / macOS Keychain / Linux
// Secret Service) via the Rust commands in src-tauri/src/main.rs - never in
// a plaintext file. The short-lived access token is kept in memory only; on
// app start the stored refresh token is exchanged for a fresh session.
let cachedSession: Session | null = null;
let sessionLoad: Promise<Session | null> | null = null;

async function saveRefreshToken(token: string | null): Promise<void> {
  if (token) {
    await invoke("save_refresh_token", { token });
  } else {
    await invoke("clear_refresh_token");
  }
}

export async function setSession(session: Session): Promise<void> {
  cachedSession = session;
  sessionLoad = Promise.resolve(session);
  await saveRefreshToken(session.refresh_token);
}

export async function clearSession(): Promise<void> {
  cachedSession = null;
  sessionLoad = Promise.resolve(null);
  await saveRefreshToken(null);
}

async function restoreSession(): Promise<Session | null> {
  const stored = await invoke<string | null>("load_refresh_token");
  if (!stored) {
    return null;
  }
  const response = await fetch(`${SERVER_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: stored }),
  });
  if (!response.ok) {
    // Only forget the token when the server actually rejected it - not on a
    // transient network/server error.
    if (response.status === 401 || response.status === 400) {
      await saveRefreshToken(null);
    }
    return null;
  }
  const session = (await response.json()) as Session;
  cachedSession = session;
  await saveRefreshToken(session.refresh_token);
  return session;
}

export async function getSession(): Promise<Session | null> {
  if (!sessionLoad) {
    sessionLoad = restoreSession().catch(() => null);
  }
  await sessionLoad;
  return cachedSession;
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const session = await getSession();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (session) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }

  const response = await fetch(`${SERVER_URL}${path}`, { ...init, headers });

  if (response.status === 401 && session && retry) {
    // Access token likely expired - try a single refresh-and-retry before
    // giving up and forcing the caller to sign in again.
    try {
      const refreshed = await refreshSession(session.refresh_token);
      await setSession(refreshed);
      return request<T>(path, init, false);
    } catch {
      await clearSession();
    }
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (Array.isArray(body.detail)) {
        // FastAPI validation errors: [{ loc, msg, ... }]
        detail = body.detail.map((d: { msg?: string }) => d.msg ?? "Invalid input").join("; ");
      } else {
        detail = body.detail ?? detail;
      }
    } catch {
      // ignore - not JSON
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function signUp(email: string, password: string) {
  return request<{ status: string; access_token?: string; refresh_token?: string; chat_id: number }>(
    "/auth/signup",
    { method: "POST", body: JSON.stringify({ email, password }) }
  );
}

export async function login(email: string, password: string) {
  return request<{ status: string; access_token: string; refresh_token: string; chat_id: number; email: string }>(
    "/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) }
  );
}

export async function refreshSession(refresh_token: string) {
  return request<Session>("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token }),
  });
}

export interface Me {
  chat_id: number;
  email: string;
  settings: Record<string, string>;
}

export function getMe() {
  return request<Me>("/me");
}

export interface ChatReply {
  reply: string;
  pending_action: { action_id: string; summary: string } | null;
}

export function sendChatMessage(message: string, model_id?: string) {
  return request<ChatReply>("/chat", { method: "POST", body: JSON.stringify({ message, model_id }) });
}

export interface LlmModel {
  id: string;
  label: string;
  tier: "small" | "medium" | "high";
  token_profile: "low" | "medium" | "high";
}

export const TIER_GROUPS: { tier: LlmModel["tier"]; label: string }[] = [
  { tier: "small", label: "Small (low token use)" },
  { tier: "medium", label: "Medium (medium token use)" },
  { tier: "high", label: "Higher (high token use)" },
];

export function modelOptionLabel(model: LlmModel) {
  return `${model.label} - ${model.tier} tier, ${model.token_profile} token consumption`;
}

export function getLlmModels() {
  return request<{
    provider: string;
    default_model: string;
    selected_model: string;
    models: LlmModel[];
  }>("/llm/models");
}

export interface ChatMessage {
  id: number;
  chat_id: number;
  role: string;
  content: string;
  created_at: string;
}

export function getChatHistory(limit = 50) {
  return request<{ messages: ChatMessage[] }>(`/chat/history?limit=${limit}`);
}

export function confirmAction(action_id: string, approved: boolean) {
  return request<Record<string, unknown>>("/chat/confirm", {
    method: "POST",
    body: JSON.stringify({ action_id, approved }),
  });
}

export interface Bookmark {
  id: number;
  chat_id: number;
  message_id: number;
  note: string | null;
  created_at: string;
  messages?: ChatMessage;
}

export function listBookmarks() {
  return request<{ bookmarks: Bookmark[] }>("/bookmarks");
}

export function addBookmark(message_id: number, note?: string) {
  return request<Bookmark>("/bookmarks", { method: "POST", body: JSON.stringify({ message_id, note }) });
}

export function removeBookmark(bookmark_id: number) {
  return request<{ ok: boolean }>(`/bookmarks/${bookmark_id}`, { method: "DELETE" });
}

export function getSettings() {
  return request<{ settings: Record<string, string> }>("/settings");
}

export function setSetting(key: string, value: string) {
  return request<{ ok: boolean }>("/settings", { method: "POST", body: JSON.stringify({ key, value }) });
}

export function deleteSetting(key: string) {
  return request<{ ok: boolean }>(`/settings/${encodeURIComponent(key)}`, { method: "DELETE" });
}

export function startTelegramLink() {
  return request<{ code: string; expires_in_seconds: number }>("/telegram-link", { method: "POST" });
}

export function removeTelegramLink() {
  return request<{ ok: boolean }>("/telegram-link", { method: "DELETE" });
}

export interface VaultCard {
  id: string;
  label: string;
  bankName: string;
  last4: string;
}

export function getVaultCards(query = "") {
  return request<{ cards: VaultCard[] }>(`/vault/cards?query=${encodeURIComponent(query)}`);
}

export function getVaultCardDefaults() {
  return request<{ defaults: Record<string, VaultCard> }>("/vault/card-defaults");
}

export function setVaultCardDefault(category: string, card_id: string) {
  return request<{ ok: boolean }>("/vault/card-defaults", {
    method: "POST",
    body: JSON.stringify({ category, card_id }),
  });
}

export function clearVaultCardDefault(category: string) {
  return request<{ ok: boolean }>(`/vault/card-defaults/${encodeURIComponent(category)}`, {
    method: "DELETE",
  });
}
