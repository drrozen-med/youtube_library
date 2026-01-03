"""
Antenna Registry
================

Lightweight persistence layer for per-channel YouTube ingestion tracking.

Features:
- Creates and maintains per-channel `antenna.json` registry with schema versioning
- Atomic writes + optional file locking to avoid corruption on crash/parallel runs
- Tracks per-video processing status (metadata_fetched, transcript_downloaded, markdown_generated, summarized)
- Incremental sync: adds newly discovered videos, leaves processed ones intact
- Utilities to list pending work and update progress safely

Each YouTuber gets their own directory with antenna.json acting as ground truth.
"""

from __future__ import annotations
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Iterable

# Optional locking to prevent concurrent writers
try:
    from filelock import FileLock
except Exception:
    FileLock = None

from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator


SCHEMA_VERSION = "1.0.0"
REGISTRY_FILENAME = "antenna.json"


# ---------- Pydantic Models ----------

class VideoStatus(BaseModel):
    """Processing status flags for each video."""
    metadata_fetched: bool = False
    transcript_downloaded: bool = False
    markdown_generated: bool = False
    summarized: bool = False


class VideoEntry(BaseModel):
    """Complete metadata and status for one video."""
    video_id: str
    title: str
    published_at: str  # ISO 8601
    duration_sec: Optional[int] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    url: Optional[HttpUrl] = None
    transcript_source: Optional[str] = None  # "manual" | "auto-generated" | None
    transcript_language: Optional[str] = None
    
    # Local file paths
    path_md: Optional[str] = None
    path_json: Optional[str] = None
    
    status: VideoStatus = Field(default_factory=VideoStatus)
    last_updated: Optional[str] = None  # ISO 8601
    
    @field_validator("published_at")
    @classmethod
    def validate_iso(cls, v: str):
        """Ensure ISO8601-ish string (lenient)."""
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            raise ValueError("published_at must be ISO 8601")
        return v


class ChannelHeader(BaseModel):
    """Registry metadata."""
    schema_version: str = SCHEMA_VERSION
    channel_id: str
    channel_name: Optional[str] = None
    handle: Optional[str] = None
    last_synced: Optional[str] = None  # ISO 8601


class AntennaRegistry(BaseModel):
    """Complete registry for one channel."""
    header: ChannelHeader
    videos: Dict[str, VideoEntry] = Field(default_factory=dict)


# ---------- Helpers ----------

def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(target: Path, obj: dict) -> None:
    """
    Write JSON atomically: write to temp, fsync, move.
    Prevents partial writes on crash.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    
    # Convert Pydantic HttpUrl and other non-serializable types to strings
    def _serialize_value(v):
        # Handle Pydantic HttpUrl type (has __str__ but not JSON serializable)
        if hasattr(v, '__class__') and 'HttpUrl' in str(type(v)):
            return str(v)
        elif isinstance(v, dict):
            return {k: _serialize_value(val) for k, val in v.items()}
        elif isinstance(v, list):
            return [_serialize_value(item) for item in v]
        elif isinstance(v, (str, int, float, bool)) or v is None:
            return v
        else:
            # Fallback: try to convert to string for other types
            try:
                json.dumps(v)  # Test if it's JSON serializable
                return v
            except (TypeError, ValueError):
                return str(v)
    
    serialized = _serialize_value(obj)
    
    with temp.open("w", encoding="utf-8") as f:
        json.dump(serialized, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    # Atomic replace
    try:
        os.replace(temp, target)
    except Exception:
        shutil.move(str(temp), str(target))


def _with_lock(path: Path):
    """
    Context manager that uses FileLock if available, otherwise no-op.
    """
    class Noop:
        def __enter__(self): return None
        def __exit__(self, exc_type, exc, tb): return False
    
    if FileLock is None:
        return Noop()
    
    lock_path = str(path) + ".lock"
    return FileLock(lock_path, timeout=30)


# ---------- Public API ----------

def registry_path(channel_dir: Path) -> Path:
    """Return path to antenna.json for a channel directory."""
    return channel_dir / REGISTRY_FILENAME


def load_registry(channel_dir: Path) -> AntennaRegistry:
    """
    Load and validate registry from channel_dir/antenna.json.
    
    Raises:
        FileNotFoundError if registry doesn't exist
        ValueError if registry schema is invalid
    """
    path = registry_path(channel_dir)
    if not path.exists():
        raise FileNotFoundError(f"Registry not found at {path}")
    
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    try:
        return AntennaRegistry(**data)
    except ValidationError as e:
        raise ValueError(f"Invalid registry schema at {path}:\n{e}") from e


def save_registry(channel_dir: Path, reg: AntennaRegistry) -> None:
    """
    Save registry atomically with optional file lock.
    """
    path = registry_path(channel_dir)
    with _with_lock(path):
        _atomic_write_json(path, reg.model_dump())


def init_registry(
    channel_dir: Path,
    channel_id: str,
    channel_name: Optional[str] = None,
    handle: Optional[str] = None,
    initial_videos: Optional[Iterable[dict]] = None,
) -> AntennaRegistry:
    """
    Initialize a new registry for a channel.
    If registry already exists, load and return it (no-op).
    
    Args:
        channel_dir: Directory for this channel's data
        channel_id: YouTube channel ID
        channel_name: Display name
        handle: @handle
        initial_videos: Optional list of dicts with video metadata
    
    Returns:
        AntennaRegistry instance
    """
    path = registry_path(channel_dir)
    if path.exists():
        return load_registry(channel_dir)
    
    reg = AntennaRegistry(
        header=ChannelHeader(
            schema_version=SCHEMA_VERSION,
            channel_id=channel_id,
            channel_name=channel_name,
            handle=handle,
            last_synced=_now_iso(),
        ),
        videos={}
    )
    
    if initial_videos:
        for item in initial_videos:
            _upsert_video(reg, item, initialize_status=True)
    
    save_registry(channel_dir, reg)
    return reg


def sync_registry(
    channel_dir: Path,
    discovered_videos: Iterable[dict],
    touch_last_synced: bool = True,
) -> AntennaRegistry:
    """
    Incrementally merge discovered videos into existing registry.
    Adds new videos only; does not reset status of existing ones.
    
    Args:
        channel_dir: Channel directory
        discovered_videos: Iterable of video dicts from collector
        touch_last_synced: Update last_synced timestamp
    
    Returns:
        Updated registry
    """
    reg = load_registry(channel_dir)
    new_count = 0
    
    for item in discovered_videos:
        video_id = item.get("video_id")
        if not video_id:
            continue
        
        if video_id not in reg.videos:
            _upsert_video(reg, item, initialize_status=True)
            new_count += 1
        else:
            # Optional: refresh basic metadata without touching status
            _refresh_metadata(reg, item)
    
    if touch_last_synced and new_count > 0:
        reg.header.last_synced = _now_iso()
    
    save_registry(channel_dir, reg)
    return reg


def _upsert_video(reg: AntennaRegistry, item: dict, initialize_status: bool = False) -> None:
    """
    Insert or update a video entry.
    If initialize_status=True, status is set to defaults.
    """
    video_id = item["video_id"]
    entry = reg.videos.get(video_id)
    
    base = {
        "video_id": video_id,
        "title": item.get("title", ""),
        "published_at": item.get("published_at", _now_iso()),
        "duration_sec": item.get("duration_sec"),
        "view_count": item.get("view_count"),
        "like_count": item.get("like_count"),
        "comment_count": item.get("comment_count"),
        "tags": item.get("tags"),
        "category": item.get("category"),
        "url": item.get("url"),
        "transcript_source": item.get("transcript_source"),
        "transcript_language": item.get("transcript_language"),
        "path_md": item.get("path_md"),
        "path_json": item.get("path_json"),
        "last_updated": _now_iso(),
    }
    
    if entry is None:
        # New entry
        status = VideoStatus() if initialize_status else item.get("status", VideoStatus())
        reg.videos[video_id] = VideoEntry(**base, status=status)
    else:
        # Merge fields conservatively
        for k, v in base.items():
            if v is not None:
                setattr(entry, k, v)
        entry.last_updated = _now_iso()


def _refresh_metadata(reg: AntennaRegistry, item: dict) -> None:
    """
    For existing video, update non-destructive metadata
    without touching status flags or local paths.
    """
    video_id = item.get("video_id")
    if not video_id or video_id not in reg.videos:
        return
    
    entry = reg.videos[video_id]
    for k in ("title", "published_at", "duration_sec", "view_count", "like_count",
              "comment_count", "tags", "category", "url"):
        v = item.get(k)
        if v is not None:
            setattr(entry, k, v)
    entry.last_updated = _now_iso()


def list_pending(
    channel_dir: Path,
    need: str = "transcript",  # "transcript" | "markdown" | "summary"
) -> List[VideoEntry]:
    """
    Return list of videos that still need work.
    
    Args:
        channel_dir: Channel directory
        need: What type of work is needed
    
    Returns:
        List of VideoEntry objects sorted by published_at
    """
    reg = load_registry(channel_dir)
    pending: List[VideoEntry] = []
    
    for v in reg.videos.values():
        if need == "transcript" and not v.status.transcript_downloaded:
            pending.append(v)
        elif need == "markdown" and v.status.transcript_downloaded and not v.status.markdown_generated:
            pending.append(v)
        elif need == "summary" and v.status.markdown_generated and not v.status.summarized:
            pending.append(v)
    
    # Sort by published_at ascending, then title
    pending.sort(key=lambda x: (x.published_at, x.title))
    return pending


def update_status(
    channel_dir: Path,
    video_id: str,
    *,
    transcript_downloaded: Optional[bool] = None,
    markdown_generated: Optional[bool] = None,
    summarized: Optional[bool] = None,
    path_md: Optional[str] = None,
    path_json: Optional[str] = None,
    transcript_source: Optional[str] = None,
    transcript_language: Optional[str] = None,
) -> AntennaRegistry:
    """
    Update per-video status flags and optional paths/metadata.
    
    Args:
        channel_dir: Channel directory
        video_id: Video to update
        **kwargs: Status flags and metadata to update
    
    Returns:
        Updated registry
    
    Raises:
        KeyError if video not in registry
    """
    reg = load_registry(channel_dir)
    if video_id not in reg.videos:
        raise KeyError(f"Video '{video_id}' not in registry. Run sync first.")
    
    v = reg.videos[video_id]
    
    if transcript_downloaded is not None:
        v.status.transcript_downloaded = transcript_downloaded
    if markdown_generated is not None:
        v.status.markdown_generated = markdown_generated
    if summarized is not None:
        v.status.summarized = summarized
    if path_md is not None:
        v.path_md = path_md
    if path_json is not None:
        v.path_json = path_json
    if transcript_source is not None:
        v.transcript_source = transcript_source
    if transcript_language is not None:
        v.transcript_language = transcript_language
    
    v.last_updated = _now_iso()
    reg.header.last_synced = _now_iso()
    
    save_registry(channel_dir, reg)
    return reg


def list_channels(root_dir: Path) -> List[Path]:
    """
    Find all channel directories (those containing antenna.json).
    
    Args:
        root_dir: Root vault directory
    
    Returns:
        List of channel directory paths
    """
    out: List[Path] = []
    for p in root_dir.glob("**/"):
        if (p / REGISTRY_FILENAME).exists():
            out.append(p)
    return out

