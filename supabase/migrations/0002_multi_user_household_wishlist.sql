-- personal-ai-assistant: multi-user, household presence/geofencing,
-- wishlist price monitoring, LLM usage tracking, and full-text conversation
-- recall. Additive to 0001_init.sql - run this after it, in the same
-- Supabase project.

-- Allow the optional Discord channel alongside Telegram/WhatsApp.
alter table chats drop constraint if exists chats_channel_check;
alter table chats add constraint chats_channel_check check (channel in ('telegram', 'whatsapp', 'discord'));

-- One row per person the assistant talks to (one per `chats` row - a person
-- using multiple channels gets multiple user rows, same as multiple chats).
-- `household` groups people for the geofencing "everyone's away" automation
-- (see src/integrations/smart_home/household_presence.py); `role` is
-- reserved for a future admin/member distinction, unused by app logic today.
create table if not exists users (
  chat_id bigint primary key references chats(id) on delete cascade,
  household text,
  role text not null default 'member',
  created_at timestamptz not null default now()
);
create index if not exists users_household_idx on users (household);

-- Latest known home/away state per person, reported by an iPhone Shortcuts
-- geofencing automation via POST /presence/{chat_id} (see webhook_server.py).
create table if not exists presence (
  chat_id bigint primary key references chats(id) on delete cascade,
  state text not null check (state in ('home', 'away')),
  updated_at timestamptz not null default now()
);

-- Free-form per-chat preferences (tone, default account, recurring
-- instructions) - injected into the system prompt, never able to bypass the
-- confirm-before-execute rule (enforced in code, not by preference text).
create table if not exists preferences (
  chat_id bigint not null references chats(id) on delete cascade,
  key text not null,
  value text not null,
  updated_at timestamptz not null default now(),
  primary key (chat_id, key)
);

-- Wishlist price-monitoring items (see src/integrations/shopping/wishlist.py).
create table if not exists wishlist_items (
  id bigserial primary key,
  chat_id bigint not null references chats(id) on delete cascade,
  title text not null,
  url text not null,
  target_price numeric,
  current_price numeric,
  currency text not null default 'USD',
  status text not null default 'active' check (status in ('active', 'ordered', 'removed')),
  last_checked_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists wishlist_items_status_idx on wishlist_items (status);
create index if not exists wishlist_items_chat_idx on wishlist_items (chat_id);

-- LLM token usage per chat, for the usage/cost dashboard tool
-- (src/core/usage_tool.py). Not a precise dollar-cost audit - provider
-- pricing changes independently of this table.
create table if not exists llm_usage (
  id bigserial primary key,
  chat_id bigint references chats(id) on delete set null,
  provider text not null,
  model text not null,
  prompt_tokens integer not null default 0,
  completion_tokens integer not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists llm_usage_chat_created_idx on llm_usage (chat_id, created_at);

-- Full-text search over conversation history (src/core/memory_search.py).
-- Chosen over pgvector + embeddings to avoid adding a heavy ML dependency;
-- revisit with real vector search only if keyword/phrase recall proves
-- insufficient in practice.
alter table messages add column if not exists content_tsv tsvector
  generated always as (to_tsvector('english', coalesce(content, ''))) stored;
create index if not exists messages_content_tsv_idx on messages using gin (content_tsv);
