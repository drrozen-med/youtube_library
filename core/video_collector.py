"""
Video Collector
===============

Fetch video metadata from YouTube Data API v3 with advanced filtering.

Features:
- Paginated fetching (handles channels with thousands of videos)
- Sort by date or popularity (viewCount)
- Date range filtering (published_after, published_before)
- Duration filtering (min/max seconds)
- Full metadata enrichment (views, likes, comments, duration, tags)
"""

import os
from typing import Dict, List, Optional

import requests
from dateutil import parser as dtparser
import isodate

YT_API_KEY = os.getenv("YT_API_KEY")
BASE = "https://www.googleapis.com/youtube/v3"


class YTError(RuntimeError):
    """YouTube API error."""
    pass


def _get(path: str, **params) -> dict:
    """Make GET request to YouTube API."""
    if not YT_API_KEY:
        raise YTError("Missing YT_API_KEY in environment")
    params["key"] = YT_API_KEY
    r = requests.get(f"{BASE}/{path}", params=params, timeout=30)
    if r.status_code != 200:
        raise YTError(f"YT API error {r.status_code}: {r.text[:200]}")
    return r.json()


def _iso_to_seconds(iso_duration: str) -> int:
    """Convert ISO 8601 duration (e.g., PT1H2M3S) to seconds."""
    return int(isodate.parse_duration(iso_duration).total_seconds())


def fetch_video_ids(
    channel_id: str,
    order: str = "date",   # "date" | "viewCount"
    published_after: Optional[str] = None,   # "YYYY-MM-DD"
    published_before: Optional[str] = None,  # "YYYY-MM-DD"
    max_results: int = 50
) -> List[str]:
    """
    Use search.list to get video IDs with filters.
    Paginates up to max_results (50 per page max from API).
    
    Args:
        channel_id: YouTube channel ID
        order: "date" (newest first) or "viewCount" (most popular)
        published_after: ISO date string (inclusive)
        published_before: ISO date string (exclusive)
        max_results: Maximum videos to fetch
    
    Returns:
        List of video IDs
    """
    got: List[str] = []
    page_token = None
    
    while len(got) < max_results:
        page_size = min(50, max_results - len(got))
        params = {
            "part": "id",
            "channelId": channel_id,
            "type": "video",
            "maxResults": page_size,
            "order": order,
        }
        
        if published_after:
            params["publishedAfter"] = dtparser.parse(published_after).isoformat()
        if published_before:
            params["publishedBefore"] = dtparser.parse(published_before).isoformat()
        if page_token:
            params["pageToken"] = page_token
        
        data = _get("search", **params)
        
        for it in data.get("items", []):
            vid = it["id"].get("videoId")
            if vid:
                got.append(vid)
        
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    
    return got


def enrich_videos(video_ids: List[str]) -> List[Dict]:
    """
    Call videos.list to get full metadata in batches of 50.
    
    Args:
        video_ids: List of video IDs
    
    Returns:
        List of dicts with enriched metadata
    """
    out: List[Dict] = []
    
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        data = _get(
            "videos",
            part="snippet,contentDetails,statistics",
            id=",".join(batch),
            maxResults=50
        )
        
        for it in data.get("items", []):
            sn = it.get("snippet", {})
            cd = it.get("contentDetails", {})
            st = it.get("statistics", {})
            
            duration_sec = None
            if cd.get("duration"):
                duration_sec = _iso_to_seconds(cd["duration"])
            
            tags = sn.get("tags")
            
            out.append({
                "video_id": it["id"],
                "title": sn.get("title", ""),
                "published_at": sn.get("publishedAt", ""),
                "duration_sec": duration_sec,
                "view_count": int(st["viewCount"]) if "viewCount" in st else None,
                "like_count": int(st["likeCount"]) if "likeCount" in st else None,
                "comment_count": int(st["commentCount"]) if "commentCount" in st else None,
                "tags": tags if isinstance(tags, list) else None,
                "category": sn.get("categoryId"),
                "url": f"https://youtu.be/{it['id']}",
            })
    
    return out


def collect_videos(
    channel_id: str,
    limit: int = 50,
    sort: str = "date",  # "date" | "popular"
    after: Optional[str] = None,
    before: Optional[str] = None,
    min_duration: Optional[int] = None,
    max_duration: Optional[int] = None
) -> List[Dict]:
    """
    Fetch and filter videos from a YouTube channel.
    
    Args:
        channel_id: YouTube channel ID
        limit: Maximum number of videos to return
        sort: "date" (newest first) or "popular" (by view count)
        after: Fetch only videos published after this date (YYYY-MM-DD)
        before: Fetch only videos published before this date (YYYY-MM-DD)
        min_duration: Minimum video length in seconds
        max_duration: Maximum video length in seconds
    
    Returns:
        List of video metadata dicts ready for registry sync
    """
    order = "viewCount" if sort in ("popular", "viewCount") else "date"
    
    # Fetch video IDs with API-level filters
    ids = fetch_video_ids(
        channel_id=channel_id,
        order=order,
        published_after=after,
        published_before=before,
        max_results=limit
    )
    
    # Enrich with full metadata
    items = enrich_videos(ids)
    
    # Apply local duration filtering (API doesn't support duration filters)
    def ok(it: Dict) -> bool:
        d = it.get("duration_sec")
        if min_duration is not None and (d is None or d < min_duration):
            return False
        if max_duration is not None and (d is not None and d > max_duration):
            return False
        return True
    
    return [it for it in items if ok(it)]
