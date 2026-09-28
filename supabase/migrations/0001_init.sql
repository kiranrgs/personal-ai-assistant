-- personal-ai-assistant: core schema
-- Run in the Supabase SQL editor of a NEW, separate project (not the
-- personal-key-vault project).

create extension if not exists pgcrypto;

-- One row per Telegram/WhatsApp chat this assistant talks to.
create table if not exists chats (
  id bigserial primary key,
  channel text not null check (channel in ('telegram', 'whatsapp')),
  external_chat_id text not null,
  display_name text,
  created_at timestamptz not null default now(),
  unique (channel, external_chat_id)
);

-- Rolling conversation history, used for follow-up questions
-- ("summarize today's emails" -> "what about the one from Alice?").
create table if not exists messages (
  id bigserial primary key,
  chat_id bigint not null references chats(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'tool', 'system')),
  content text not null,
  tool_name text,
  created_at timestamptz not null default now()
);
create index if not exists messages_chat_id_created_at_idx on messages (chat_id, created_at);

-- Named context blobs a conversation can refer back to, e.g. the full list of
-- today's emails, a Twitter digest, a video summary - so "any follow-up
-- questions" can be answered without re-fetching.
create table if not exists context_snapshots (
  id bigserial primary key,
  chat_id bigint not null references chats(id) on delete cascade,
  kind text not null,              -- e.g. 'email_summary', 'twitter_digest', 'video_summary'
  label text,                      -- e.g. the date, or a video title
  payload jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists context_snapshots_chat_kind_idx on context_snapshots (chat_id, kind, created_at desc);

-- Draft actions awaiting explicit user confirmation (ticket purchase, ride
-- booking, food order, outbound call, smart-home actuation, etc). Nothing in
-- `payload` ever contains a raw card number/CVV.
create table if not exists pending_actions (
  id uuid primary key default gen_random_uuid(),
  chat_id bigint not null references chats(id) on delete cascade,
  action_type text not null,       -- e.g. 'book_tickets', 'order_food', 'place_call'
  summary text not null,           -- human-readable text shown in the Telegram confirm prompt
  payload jsonb not null,
  status text not null default 'pending' check (status in ('pending', 'confirmed', 'rejected', 'expired', 'executed', 'failed')),
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);
create index if not exists pending_actions_status_idx on pending_actions (status, created_at);

-- Audit log: every tool invocation and every confirm/reject decision, for
-- security review given how many accounts this assistant touches.
create table if not exists audit_log (
  id bigserial primary key,
  chat_id bigint references chats(id) on delete set null,
  event_type text not null,        -- e.g. 'tool_call', 'confirmation_approved', 'confirmation_rejected'
  detail jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists audit_log_created_at_idx on audit_log (created_at desc);

-- Recurring reminders / scheduled jobs the assistant owns (distinct from
-- finance-bot's own scheduler, which is triggered, not duplicated).
create table if not exists scheduled_jobs (
  id bigserial primary key,
  chat_id bigint not null references chats(id) on delete cascade,
  job_type text not null,          -- e.g. 'daily_email_summary', 'daily_twitter_digest'
  cron_expression text not null,
  enabled boolean not null default true,
  last_run_at timestamptz,
  created_at timestamptz not null default now()
);

-- Per-integration connection status, so the bot can tell the user what's
-- configured vs. not, without ever storing raw secrets here (those live only
-- in .env / OS-level token caches on this machine).
create table if not exists integration_status (
  integration text primary key,    -- e.g. 'gmail:personal', 'smartthings', 'twilio'
  connected boolean not null default false,
  last_checked_at timestamptz,
  detail text
);
