"""
YouTube Orchestrator Core Modules
==================================

This package contains the core functionality for YouTube transcript extraction,
metadata management, and Markdown generation.
"""

__version__ = "1.0.0"

from .channel_resolver import resolve_channel
from .antenna_registry import (
    init_registry,
    load_registry,
    save_registry,
    sync_registry,
    list_pending,
    update_status,
)
from .video_collector import collect_videos
from .transcript_fetcher import fetch_transcript_text as fetch_transcript_text_original

def fetch_transcript_text(video_id: str, languages: tuple = ('en', 'en-US', 'en-GB'),
                         max_retries: int = 3, initial_delay: float = 5.0):
    """
    Fetch transcript with proxy fallback.

    Tries proxy services first (ScrapingBee → ScrapeNinja → Firecrawl),
    falls back to original youtube-transcript-api if proxies fail.
    """
    try:
        from .proxy_transcript_fetcher import ProxyTranscriptFetcherV3

        print(f"   Trying proxy fetcher for {video_id}...")
        fetcher = ProxyTranscriptFetcherV3()
        text, source, lang = fetcher.fetch_transcript_sync(video_id)

        if text:
            print(f"   ✓ Proxy fetcher succeeded: {source}")
            return text, source, lang
        else:
            print(f"   ✗ Proxy fetcher failed, falling back to original method...")
    except Exception as e:
        print(f"   ✗ Proxy fetcher error: {e}, falling back to original method...")

    # Fallback to original method
    return fetch_transcript_text_original(video_id, languages, max_retries, initial_delay)
from .markdown_generator import generate_markdown
from .index_builder import build_index
from .summarizer import summarize_transcript

__all__ = [
    "resolve_channel",
    "init_registry",
    "load_registry",
    "save_registry",
    "sync_registry",
    "list_pending",
    "update_status",
    "collect_videos",
    "fetch_transcript_text",
    "generate_markdown",
    "build_index",
    "summarize_transcript",
]

