# Personal AI Assistant — Desktop client

A downloadable Windows/macOS chat client (Tauri + React) for
`personal-ai-assistant`. The user never sees any code or tool internals —
just a chat window, a bookmarks sidebar, and a settings page (cards,
overrides, Telegram linking). All requests go over HTTPS/loopback-HTTP to
`src/client_api_server.py`, which is the only thing that talks to this
project's Supabase project, the LLM providers, and the personal-key-vault
companion API.

## Prerequisites

- Node.js 18+ and npm.
- Rust + Cargo (for the native Tauri shell) — install via
  [rustup](https://rustup.rs/). **This was not installed/validated in the
  environment this scaffold was written in** — only the React/TypeScript
  frontend (`npm run build`) has been compiled/type-checked here. You must
  install Rust yourself and run a `tauri dev`/`tauri build` at least once
  before trusting the native shell compiles on your machine, exactly like
  this repo's sibling `personal-key-vault` app documents for its own
  hand-written native modules.
- A running instance of `src/client_api_server.py` (see the repo root
  `SETUP.md` for how to run it) reachable from wherever you run/build the
  client.

## First-time setup

```powershell
cd apps/desktop
npm install
copy .env.example .env
# edit .env and point VITE_SERVER_URL at your client_api_server.py instance
```

Generate real app icons (required before `tauri build`/`tauri dev` will
work — no icons are checked into this repo yet):

```powershell
npx tauri icon path/to/a-1024x1024-square-source-icon.png
```

## Run in development

```powershell
npm run tauri dev
```

## Build an installer

```powershell
npm run tauri build
```

Produces a signed-or-unsigned installer (`.msi`/`.exe` on Windows, `.dmg`/
`.app` on macOS) under `src-tauri/target/release/bundle/`. Code-signing
setup (Windows Authenticode / Apple Developer ID + notarization) is not
configured here — configure it in `src-tauri/tauri.conf.json` under
`bundle` before distributing outside your own machine.

## Security notes

- The client never stores a Supabase URL/API key, LLM API keys, or vault
  companion tokens — only its own Supabase Auth session (`access_token`/
  `refresh_token`) issued by `client_api_server.py`, persisted via
  `@tauri-apps/plugin-store` (a local JSON file under the OS app-data
  directory — not the OS keychain). If you need stronger local-at-rest
  protection, swap the store calls in `src/lib/apiClient.ts` for the
  `keyring` crate the way `personal-key-vault`'s desktop app does.
- `src/lib/apiClient.ts` refuses to run against a non-loopback
  `VITE_SERVER_URL` that isn't `https://` — this is a hard startup error,
  not a warning.
- Every request attaches `Authorization: Bearer <access_token>`; the server
  re-derives the caller's identity from that token on every single request
  and never trusts a client-supplied user/chat id — see
  `src/core/client_auth.py` and `src/client_api_server.py` in the repo root.
