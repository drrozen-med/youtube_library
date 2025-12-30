"""
Index Builder
=============

Generate summary statistics for each channel.

Creates index.json with:
- Channel metadata
- Total videos tracked
- Processing status counts
- Last sync timestamp
"""

import json
from pathlib import Path
from typing import Dict

from .antenna_registry import load_registry


def build_index(channel_dir: Path) -> Path:
    """
    Build or rebuild index.json for a channel.
    
    Args:
        channel_dir: Channel directory containing antenna.json
    
    Returns:
        Path to created index.json
    """
    reg = load_registry(channel_dir)
    
    total = len(reg.videos)
    processed = sum(1 for v in reg.videos.values() if v.status.markdown_generated)
    pending = total - processed
    summarized = sum(1 for v in reg.videos.values() if v.status.summarized)
    
    info: Dict = {
        "channel_id": reg.header.channel_id,
        "channel_name": reg.header.channel_name,
        "handle": reg.header.handle,
        "last_synced": reg.header.last_synced,
        "total_videos_known": total,
        "processed_markdown": processed,
        "pending_markdown": pending,
        "summarized": summarized,
    }
    
    out = channel_dir / "index.json"
    out.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return out
