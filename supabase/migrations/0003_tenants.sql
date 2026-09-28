-- personal-ai-assistant: multi-tenant Telegram bots (own bot token + own
-- allow-list per tenant, registered via the admin console -
-- src/admin_server.py - instead of editing .env for every additional bot).
-- Job search (src/integrations/jobs/job_search.py) needs no new table -
-- it reuses the existing `preferences` table from 0002.
-- Additive to 0001_init.sql / 0002_multi_user_household_wishlist.sql.

create table if not exists tenants (
  id bigserial primary key,
  name text not null unique,
  telegram_bot_token text not null default '',
  telegram_allowed_chat_ids text not null default '',
  active boolean not null default true,
  created_at timestamptz not null default now()
);

-- There is no .env-configured default bot - every tenant (including the
-- very first one) is registered through the admin console and gets its own
-- positive `tenants.id`, starting at 1. `tenant_id` defaults to 0 purely to
-- satisfy the NOT NULL constraint on any pre-existing/legacy row; 0 is
-- never a real tenant and no bot ever runs as tenant 0.
alter table chats add column if not exists tenant_id bigint not null default 0;

-- The same Telegram numeric chat id can legitimately appear under two
-- different tenants (a person messaging two different tenant bots reuses
-- their own Telegram user id as the chat id for each bot), so tenant_id
-- must be part of the uniqueness key - otherwise their conversation history
-- with two unrelated bots/tenants would collide into one row.
alter table chats drop constraint if exists chats_channel_external_chat_id_key;
alter table chats add constraint chats_tenant_channel_external_chat_id_key
  unique (tenant_id, channel, external_chat_id);
