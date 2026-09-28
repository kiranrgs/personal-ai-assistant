"""Twitter/X digest via the official API (tweepy). Meaningful read access
(home timeline / mentions / user tweets) requires at least the Basic paid
API tier now - the free tier is essentially write-only. Set
TWITTER_BEARER_TOKEN once you have that.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from src.core.settings import get_settings
from src.core.tool_registry import Tool, register
from src.integrations.email.summarizer import summarize_items


def _is_configured() -> bool:
    return bool(get_settings().twitter_bearer_token)


def _client():
    import tweepy

    return tweepy.Client(bearer_token=get_settings().twitter_bearer_token)


def _user_context_client():
    """OAuth1 user-context client, needed for endpoints tied to a specific
    logged-in account (like "who do I follow") rather than app-only bearer
    token access."""
    import tweepy

    s = get_settings()
    return tweepy.Client(
        consumer_key=s.twitter_consumer_key,
        consumer_secret=s.twitter_consumer_secret,
        access_token=s.twitter_access_token,
        access_token_secret=s.twitter_access_token_secret,
    )


def _is_user_context_configured() -> bool:
    s = get_settings()
    return bool(s.twitter_consumer_key and s.twitter_consumer_secret and s.twitter_access_token and s.twitter_access_token_secret)


def _followed_usernames() -> list[str]:
    """Prefer the real "following" list via OAuth1 user-context; fall back
    to a manually configured list (TWITTER_FOLLOWED_HANDLES) since the
    following-list endpoint requires the elevated user-context tier/consent
    that not everyone will have set up."""
    if _is_user_context_configured():
        try:
            client = _user_context_client()
            me = client.get_me()
            if me.data is not None:
                following = client.get_users_following(me.data.id, max_results=1000)
                if following.data:
                    return [u.username for u in following.data]
        except Exception:  # noqa: BLE001
            pass
    return get_settings().twitter_followed_handle_list


def _fetch_recent_tweets(username: str, since_days: int) -> list[dict[str, Any]]:
    client = _client()
    user = client.get_user(username=username)
    if user.data is None:
        raise ValueError(f"User '{username}' not found")
    start_time = (dt.datetime.utcnow() - dt.timedelta(days=since_days)).isoformat("T") + "Z"
    tweets = client.get_users_tweets(user.data.id, start_time=start_time, max_results=100, tweet_fields=["created_at"])
    return [{"text": t.text, "created_at": str(t.created_at)} for t in (tweets.data or [])]


def summarize_twitter_digest(username: str, period: str = "day") -> dict[str, Any]:
    if not _is_configured():
        return {"error": "Twitter/X isn't configured yet. Set TWITTER_BEARER_TOKEN in .env (requires a paid API tier for reads)."}
    since_days = 1 if period == "day" else 7
    tweets = _fetch_recent_tweets(username, since_days)
    if not tweets:
        return {"summary": f"No tweets from @{username} in the last {since_days} day(s)."}
    text = "\n".join(f"- {t['created_at']}: {t['text']}" for t in tweets)
    summary = summarize_items(f"tweets from @{username}", text)
    return {"summary": summary, "count": len(tweets)}


register(Tool(
    name="summarize_twitter_digest",
    description="Summarize what a given X/Twitter account posted in the last day or week (period='day'|'week').",
    parameters={
        "type": "object",
        "properties": {"username": {"type": "string"}, "period": {"type": "string", "enum": ["day", "week"]}},
        "required": ["username"],
    },
    handler=summarize_twitter_digest,
))


def summarize_followed_twitter_digest(period: str = "day") -> dict[str, Any]:
    if not _is_configured():
        return {"error": "Twitter/X isn't configured yet. Set TWITTER_BEARER_TOKEN in .env (requires a paid API tier for reads)."}
    usernames = _followed_usernames()
    if not usernames:
        return {
            "error": (
                "No followed accounts to summarize. Either configure OAuth1 user-context "
                "(TWITTER_CONSUMER_KEY/SECRET + TWITTER_ACCESS_TOKEN/SECRET) so I can read your real following list, "
                "or set TWITTER_FOLLOWED_HANDLES to a comma-separated list of usernames."
            )
        }
    since_days = 1 if period == "day" else 7
    per_account_summaries = []
    for username in usernames:
        try:
            tweets = _fetch_recent_tweets(username, since_days)
        except Exception as exc:  # noqa: BLE001
            per_account_summaries.append(f"@{username}: couldn't fetch ({exc})")
            continue
        if not tweets:
            continue
        text = "\n".join(f"- {t['created_at']}: {t['text']}" for t in tweets)
        per_account_summaries.append(f"@{username}:\n{text}")

    if not per_account_summaries:
        return {"summary": f"No activity from followed accounts in the last {since_days} day(s)."}
    combined = "\n\n".join(per_account_summaries)
    summary = summarize_items(
        "tweets from accounts you follow", combined,
        instructions="Group the digest by account, keep it skimmable, call out anything time-sensitive.",
    )
    return {"summary": summary, "accounts_checked": len(usernames)}


register(Tool(
    name="summarize_followed_twitter_digest",
    description="Summarize recent posts from all X/Twitter accounts you follow (period='day'|'week'), as a daily/weekly digest.",
    parameters={"type": "object", "properties": {"period": {"type": "string", "enum": ["day", "week"]}}},
    handler=summarize_followed_twitter_digest,
))
