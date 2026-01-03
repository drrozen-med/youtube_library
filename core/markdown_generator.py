"""
Markdown Generator
==================

Create Markdown files with YAML frontmatter and clean formatting.

Features:
- YAML frontmatter with comprehensive metadata
- Sequential numbering (001-slug.md, 002-slug.md)
- Optional TL;DR summary section
- Safe filename slugification
- Obsidian-compatible format
"""

from pathlib import Path
from typing import Dict, Optional
from datetime import timedelta, datetime

from slugify import slugify


def _sec_to_hms(s: Optional[int]) -> Optional[str]:
    """Convert seconds to HH:MM:SS format."""
    if s is None:
        return None
    return str(timedelta(seconds=int(s)))


def generate_markdown(
    channel_dir: Path,
    index_number: int,
    meta: Dict,
    transcript_text: str,
    summary: Optional[str] = None
) -> Path:
    """
    Create a Markdown file with YAML frontmatter + transcript.
    
    Args:
        channel_dir: Channel directory
        index_number: Sequential number for filename (e.g., 1 -> 001)
        meta: Video metadata dict
        transcript_text: Full transcript text
        summary: Optional TL;DR summary from LLM
    
    Returns:
        Path to created Markdown file
    """
    transcripts_dir = channel_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    
    # Parse published date and format as dd-mm-yyyy
    date_str = ""
    published_at = meta.get("published_at")
    if published_at:
        try:
            # Parse ISO 8601 date (e.g., "2025-12-29T14:01:16Z")
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            date_str = dt.strftime("%d-%m-%Y")
        except Exception:
            # Fallback if date parsing fails
            date_str = ""
    
    # Create safe filename: 001-dd-mm-yyyy-video-title.md
    title = meta.get("title", "") or meta["video_id"]
    safe = slugify(title)[:80] or meta["video_id"]
    if date_str:
        fname = f"{index_number:03d}-{date_str}-{safe}.md"
    else:
        fname = f"{index_number:03d}-{safe}.md"
    fpath = transcripts_dir / fname
    
    # Build YAML frontmatter
    yaml_lines = ["---"]
    
    def y(k, v):
        """Add YAML field if value is not None."""
        if v is None:
            return
        if isinstance(v, list):
            yaml_lines.append(f"{k}: [{', '.join(map(str, v))}]")
        else:
            yaml_lines.append(f"{k}: {v!r}".replace("'", '"'))
    
    y("title", title)
    y("channel", meta.get("channel_name"))
    y("video_id", meta.get("video_id"))
    y("url", meta.get("url"))
    y("published_at", meta.get("published_at"))
    y("duration", _sec_to_hms(meta.get("duration_sec")))
    y("view_count", meta.get("view_count"))
    y("like_count", meta.get("like_count"))
    y("comment_count", meta.get("comment_count"))
    y("tags", meta.get("tags"))
    
    yaml_lines.append("---\n")
    
    # Build body
    body = ""
    
    # Optional TL;DR section
    if summary:
        body += "# TL;DR\n\n" + summary + "\n\n"
    
    # Main transcript
    body += "# Transcript\n\n"
    body += (transcript_text or "_Transcript unavailable._") + "\n"
    
    # Write file
    fpath.write_text("\n".join(yaml_lines) + body, encoding="utf-8")
    
    return fpath
