"""
Channel Resolver
================

Resolves any YouTube channel identifier (URL, handle, ID, or even video URL)
to a canonical channel ID and full metadata.

Supports:
- Direct channel IDs (UC...)
- Modern handles (@username)
- Legacy vanity URLs (/c/CustomName, /user/LegacyUser)
- Video URLs (extracts channel from video)
- Plain text search fallback
"""

import os
import re
import urllib.parse as up
from typing import Optional, Tuple, Dict

import requests

from .auth_helper import make_authenticated_request

YT_API_KEY = os.getenv("YT_API_KEY")
SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH")
YT_API = "https://www.googleapis.com/youtube/v3"

# Regex patterns
RE_CHANNEL_ID = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
RE_VIDEO_ID = re.compile(r"(?:(?:v=)|(?:youtu\.be/))([0-9A-Za-z_-]{11})")
RE_HANDLE = re.compile(r"^@[\w\.-]{3,}$")


def _api_get(path: str, **params) -> dict:
    """Make a GET request to YouTube Data API using service account or API key."""
    url = f"{YT_API}/{path}"
    
    # Prefer service account authentication
    if SERVICE_ACCOUNT_PATH:
        try:
            return make_authenticated_request(url, params, SERVICE_ACCOUNT_PATH)
        except Exception as e:
            raise RuntimeError(f"Service account auth failed: {e}")
    
    # Fallback to API key
    if not YT_API_KEY:
        raise RuntimeError("Missing YT_API_KEY or GOOGLE_SERVICE_ACCOUNT_PATH in environment. Set it in .env file.")
    params["key"] = YT_API_KEY
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from various YouTube URL formats."""
    # Handles youtu.be/VIDEO and watch?v=VIDEO
    m = RE_VIDEO_ID.search(url)
    if m:
        return m.group(1)
    # Parse query param fallback
    parsed = up.urlparse(url)
    q = up.parse_qs(parsed.query)
    if "v" in q and q["v"]:
        v = q["v"][0]
        if re.fullmatch(r"[0-9A-Za-z_-]{11}", v):
            return v
    return None


def _channels_list_for_username(username: str) -> Optional[dict]:
    """Legacy username lookup (works for old /user/ URLs)."""
    try:
        data = _api_get(
            "channels",
            part="snippet,statistics,contentDetails,brandingSettings",
            forUsername=username,
            maxResults=1
        )
        if data.get("items"):
            return data["items"][0]
    except requests.HTTPError:
        pass
    return None


def _channels_list_by_id(channel_id: str) -> Optional[dict]:
    """Fetch full channel metadata by ID."""
    data = _api_get(
        "channels",
        part="snippet,statistics,contentDetails,brandingSettings",
        id=channel_id,
        maxResults=1
    )
    return data["items"][0] if data.get("items") else None


def _search_channel_best(q: str) -> Optional[dict]:
    """Use search API to find the most plausible channel by query/handle."""
    data = _api_get("search", part="snippet", q=q, type="channel", maxResults=5)
    items = data.get("items", [])
    if not items:
        return None
    
    # Prefer exact handle/customUrl match when q looks like a handle
    if q.startswith("@"):
        for it in items:
            cid = it["snippet"]["channelId"]
            ch = _channels_list_by_id(cid)
            if ch:
                custom = ch["snippet"].get("customUrl") or ch.get("brandingSettings", {}).get("channel", {}).get("vanityUrl")
                if custom and custom.lower() == q.lower().lstrip("@"):
                    return ch
        # Fallback to first result
        return _channels_list_by_id(items[0]["snippet"]["channelId"])
    
    # Otherwise, pick top result
    return _channels_list_by_id(items[0]["snippet"]["channelId"])


def _handle_to_channel_id(handle: str) -> Tuple[str, Dict]:
    """
    Resolve @handle to channel.
    
    Note: There's no official 'forHandle' param in YouTube API v3,
    so we search and verify via customUrl/brandingSettings.
    """
    ch = _search_channel_best(handle)
    if not ch:
        raise ValueError(f"Handle not found: {handle}")
    
    # Best-effort verification
    custom = ch["snippet"].get("customUrl") or ch.get("brandingSettings", {}).get("channel", {}).get("vanityUrl")
    if custom and custom.lower() == handle.lower().lstrip("@"):
        return ch["id"], ch
    
    # Fallback even if customUrl isn't exposed
    return ch["id"], ch


def resolve_channel(input_str: str) -> Tuple[str, Dict]:
    """
    Resolve any YouTube channel identifier to (channel_id, channel_metadata).
    
    Accepts:
    - Channel ID (UC...)
    - @handle
    - Full channel URL (/channel/UC..., /@handle, /c/..., /user/...)
    - Video URL (extracts channel from video)
    - Plain name (searches)
    
    Returns:
        (channel_id, channel_object) where channel_object includes:
        - snippet (title, description, customUrl, thumbnails, publishedAt)
        - statistics (subscriberCount, videoCount, viewCount)
        - contentDetails (relatedPlaylists.uploads)
        - brandingSettings (optional)
    
    Raises:
        ValueError if not resolvable
        RuntimeError if YT_API_KEY not set
    """
    s = input_str.strip()
    
    # 1) Already a channel ID
    if RE_CHANNEL_ID.match(s):
        ch = _channels_list_by_id(s)
        if ch:
            return ch["id"], ch
        raise ValueError("Channel ID not found via API")
    
    # 2) Looks like a URL?
    if s.startswith("http"):
        parsed = up.urlparse(s)
        path = parsed.path.rstrip("/")
        
        # a) /channel/UC...
        if "/channel/" in path:
            cid = path.split("/channel/")[-1]
            if RE_CHANNEL_ID.match(cid):
                ch = _channels_list_by_id(cid)
                if ch:
                    return ch["id"], ch
                raise ValueError("Channel URL contained invalid/unknown channel ID")
        
        # b) /@handle
        if path.startswith("/@"):
            handle = path.split("/@")[-1]
            return _handle_to_channel_id(f"@{handle}")
        
        # c) /c/CustomName (legacy vanity)
        if "/c/" in path:
            vanity = path.split("/c/")[-1]
            ch = _channels_list_for_username(vanity) or _search_channel_best(vanity)
            if ch:
                return ch["id"], ch
            raise ValueError("Could not resolve /c/ vanity URL")
        
        # d) /user/LegacyUser (very old)
        if "/user/" in path:
            username = path.split("/user/")[-1]
            ch = _channels_list_for_username(username) or _search_channel_best(username)
            if ch:
                return ch["id"], ch
            raise ValueError("Could not resolve /user/ URL")
        
        # e) Video URL
        vid = _extract_video_id(s)
        if vid:
            data = _api_get("videos", part="snippet", id=vid)
            items = data.get("items", [])
            if items:
                cid = items[0]["snippet"]["channelId"]
                ch = _channels_list_by_id(cid)
                if ch:
                    return ch["id"], ch
        
        # f) Last resort: search the whole URL text
        ch = _search_channel_best(s)
        if ch:
            return ch["id"], ch
        raise ValueError("Unable to resolve channel from URL")
    
    # 3) Handle like @foo
    if RE_HANDLE.match(s):
        return _handle_to_channel_id(s)
    
    # 4) Plain name or legacy username
    ch = _channels_list_for_username(s) or _search_channel_best(s)
    if ch:
        return ch["id"], ch
    
    raise ValueError("Could not resolve channel from the provided input")

