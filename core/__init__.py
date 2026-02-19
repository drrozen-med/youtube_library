"""
YouTube Orchestrator Core Modules
==================================

This package contains the core functionality for YouTube transcript extraction,
metadata management, and Markdown generation.
"""

__version__ = "1.0.0"
import logging
import os

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
logger = logging.getLogger(__name__)

def fetch_transcript_text(video_id: str, languages: tuple = ('en', 'en-US', 'en-GB'),
                         max_retries: int = 3, initial_delay: float = 5.0):
    """
    Fetch transcript with proxy fallback.

    Tries proxy services first (ScrapingBee → ScrapeNinja → Firecrawl),
    falls back to original youtube-transcript-api if proxies fail.
    """
    mode = os.getenv("TRANSCRIPT_FETCH_MODE", "proxy_then_direct").strip().lower()
    valid_modes = {"proxy_then_direct", "proxy_only", "direct_only"}
    if mode not in valid_modes:
        logger.warning(
            "Unknown TRANSCRIPT_FETCH_MODE=%s. Falling back to proxy_then_direct.",
            mode
        )
        mode = "proxy_then_direct"

    if mode != "direct_only":
        try:
            from .proxy_transcript_fetcher import ProxyTranscriptFetcherV3

            logger.info("Trying proxy fetcher for %s", video_id)
            fetcher = ProxyTranscriptFetcherV3()
            text, source, lang = fetcher.fetch_transcript_sync(
                video_id,
                languages=languages,
            )

            if text:
                logger.info("Proxy transcript fetch succeeded for %s (%s)", video_id, source)
                return text, source, lang

            if mode == "proxy_only":
                logger.error(
                    "Proxy transcript fetch failed for %s with TRANSCRIPT_FETCH_MODE=proxy_only",
                    video_id
                )
                return None, None, None
        except Exception:
            logger.exception("Proxy fetcher raised an exception for %s", video_id)
            if mode == "proxy_only":
                return None, None, None

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
