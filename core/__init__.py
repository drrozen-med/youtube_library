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
from .transcript_fetcher import fetch_transcript_text
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

