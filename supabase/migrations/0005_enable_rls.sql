-- Lock every table down with Row Level Security.
--
-- The backend only ever talks to Supabase with the service-role key (which
-- bypasses RLS), so this changes nothing for the app itself. What it DOES do
-- is stop anyone holding the public anon key - or a signed-in desktop user's
-- own JWT - from reading/writing these tables directly over the Supabase REST
-- API (PostgREST), where without RLS every row (all users' chats, messages,
-- tenants' Telegram bot tokens, pending actions...) would be exposed.
--
-- No policies are added on purpose: with RLS enabled and no policy, the anon
-- and authenticated roles get zero rows.

alter table if exists chats               enable row level security;
alter table if exists messages            enable row level security;
alter table if exists context_snapshots   enable row level security;
alter table if exists pending_actions     enable row level security;
alter table if exists audit_log           enable row level security;
alter table if exists scheduled_jobs      enable row level security;
alter table if exists integration_status  enable row level security;
alter table if exists users               enable row level security;
alter table if exists presence            enable row level security;
alter table if exists preferences         enable row level security;
alter table if exists wishlist_items      enable row level security;
alter table if exists llm_usage           enable row level security;
alter table if exists tenants             enable row level security;
alter table if exists chat_bookmarks      enable row level security;
