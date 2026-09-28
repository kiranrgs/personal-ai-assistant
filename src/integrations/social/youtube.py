"""YouTube video summarization: pulls the transcript (captions) and asks the
LLM to summarize it - no download of the actual video needed. Works for any
public video ID; YOUTUBE_API_KEY is only needed for the optional
search-by-topic helper.

Transcripts are cached into Supabase (`context_snapshots`, kind
"video_transcript") keyed by video id, so a follow-up question about the
same video doesn't need to re-fetch captions, and so `ask_about_youtube_video`
can answer specific questions instead of only producing a fixed summary.
"podcast" support is scoped to YouTube-hosted podcasts/videos only - there's
no separate podcast-platform integration (Spotify/Apple Podcasts don't offer
a personal-use transcript API).
"""
from __future__ import annotations

import re
from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi

from src.core.tool_registry import Tool, register
from src.core.user_config import get_current_chat
from src.db import supabase_client as db
from src.integrations.email.summarizer import summarize_items

_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})")


def _extract_video_id(url_or_id: str) -> str:
    if len(url_or_id) == 11 and "/" not in url_or_id:
        return url_or_id
    match = _ID_RE.search(url_or_id)
    if not match:
        raise ValueError(f"Couldn't extract a video ID from '{url_or_id}'")
    return match.group(1)


def _get_transcript_text(video_id: str) -> str:
    chat_id = get_current_chat()
    if chat_id is not None:
        cached = db.get_context_snapshot_by_label(chat_id, "video_transcript", video_id)
        if cached is not None:
            return cached["payload"]["text"]
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    text = " ".join(chunk["text"] for chunk in transcript)
    if chat_id is not None:
        db.save_context_snapshot(chat_id, "video_transcript", {"text": text}, label=video_id)
    return text


def summarize_youtube_video(url_or_id: str) -> dict[str, Any]:
    video_id = _extract_video_id(url_or_id)
    try:
        text = _get_transcript_text(video_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Couldn't fetch a transcript for this video (captions may be disabled): {exc}"}
    summary = summarize_items("video transcript", text[:20000], instructions="Note the overall topic and key takeaways/timestamped highlights if inferable.")
    return {"video_id": video_id, "summary": summary}


def ask_about_youtube_video(url_or_id: str, question: str) -> dict[str, Any]:
    video_id = _extract_video_id(url_or_id)
    try:
        text = _get_transcript_text(video_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Couldn't fetch a transcript for this video (captions may be disabled): {exc}"}
    answer = summarize_items(
        "video transcript", text[:20000],
        instructions=f'Answer this specific question about the video, quoting/paraphrasing relevant parts: "{question}". '
                     "If the transcript doesn't cover it, say so plainly instead of guessing.",
    )
    return {"video_id": video_id, "question": question, "answer": answer}


register(Tool(
    name="summarize_youtube_video",
    description="Fetch a YouTube video's transcript and produce an LLM summary, given a video URL or ID.",
    parameters={"type": "object", "properties": {"url_or_id": {"type": "string"}}, "required": ["url_or_id"]},
    handler=summarize_youtube_video,
))

register(Tool(
    name="ask_about_youtube_video",
    description="Answer a specific question about a YouTube video's content (works for YouTube-hosted podcasts too), using its transcript.",
    parameters={
        "type": "object",
        "properties": {"url_or_id": {"type": "string"}, "question": {"type": "string"}},
        "required": ["url_or_id", "question"],
    },
    handler=ask_about_youtube_video,
))
