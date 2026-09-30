-- personal-ai-assistant: desktop client accounts (real end-user signup/
-- login via this project's own Supabase Auth - separate from
-- personal-key-vault's own, unrelated Supabase project) + message
-- bookmarking for the desktop client's chat window.
-- Additive to 0001/0002/0003. Run after those, in the same Supabase project.

-- Allow the new 'desktop' channel alongside Telegram/WhatsApp/Discord. A
-- desktop chat's `external_chat_id` is the Supabase Auth user's `id` (uuid,
-- as text) - see src/core/client_auth.py - so each signed-up person maps to
-- exactly one desktop `chats` row, looked up fresh from their verified
-- bearer token on every request (never trusted from the request body).
alter table chats drop constraint if exists chats_channel_check;
alter table chats add constraint chats_channel_check
  check (channel in ('telegram', 'whatsapp', 'discord', 'desktop'));

-- Lets the desktop client's chat window show a "Bookmarks" list alongside
-- the running conversation - star any message to find it again later.
create table if not exists chat_bookmarks (
  id bigserial primary key,
  chat_id bigint not null references chats(id) on delete cascade,
  message_id bigint not null references messages(id) on delete cascade,
  note text,
  created_at timestamptz not null default now(),
  unique (chat_id, message_id)
);
create index if not exists chat_bookmarks_chat_idx on chat_bookmarks (chat_id, created_at desc);
