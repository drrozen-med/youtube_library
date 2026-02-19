"""
Browser-based YouTube Transcript Fetcher
=========================================
Uses CDP connection to Brave browser to extract transcripts
from YouTube's DOM (bypasses IP blocks via authenticated session).

Usage:
    python fetch_via_browser.py --channel "@IndyDevDan" --limit 50
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CDP_URL = "http://localhost:9222"
VAULT_DIR = Path("./vault")
YT_API_KEY = os.getenv("YT_API_KEY")
TAB_RECYCLE_INTERVAL = 8  # Close and reopen tab every N videos


def cdp(cmd: str, page_id: str = "", extra: str = "", timeout: int = 45) -> dict:
    """Run a cdp-cli command and return parsed JSON."""
    args = ["cdp-cli", "--cdp-url", CDP_URL, cmd]
    if page_id:
        args.append(page_id)
    if extra:
        args.append(extra)
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {"error": result.stderr or result.stdout, "raw": result.stdout}


def cdp_eval(page_id: str, js: str, timeout: int = 45) -> dict:
    """Evaluate JS on a page via cdp-cli."""
    result = subprocess.run(
        ["cdp-cli", "--cdp-url", CDP_URL, "eval", page_id, js],
        capture_output=True, text=True, timeout=timeout
    )
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {"error": result.stderr or result.stdout}


def open_tab() -> str:
    """Open a fresh browser tab and return its page_id."""
    tab = cdp("new", "", "https://www.youtube.com")
    page_id = tab.get("data", {}).get("id")
    if not page_id:
        raise RuntimeError(f"Failed to open tab: {tab}")
    time.sleep(2)
    return page_id


def close_tab(page_id: str):
    """Close a browser tab, ignoring errors."""
    try:
        cdp("close", page_id, timeout=10)
    except Exception:
        pass


def get_channel_videos(channel_id: str, limit: int = 50) -> list:
    """Fetch video list using YouTube Data API v3 (latest first)."""
    import requests

    videos = []
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "key": YT_API_KEY,
        "channelId": channel_id,
        "part": "snippet",
        "type": "video",
        "order": "date",
        "maxResults": min(limit, 50),
    }

    page_token = None
    while len(videos) < limit:
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("items", []):
            videos.append({
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"],
            })

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    # Get video details (duration, views, likes)
    video_ids = [v["video_id"] for v in videos[:limit]]
    details_url = "https://www.googleapis.com/youtube/v3/videos"
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = requests.get(details_url, params={
            "key": YT_API_KEY,
            "id": ",".join(batch),
            "part": "contentDetails,statistics",
        })
        resp.raise_for_status()
        detail_map = {item["id"]: item for item in resp.json().get("items", [])}
        for v in videos:
            if v["video_id"] in detail_map:
                d = detail_map[v["video_id"]]
                v["view_count"] = int(d.get("statistics", {}).get("viewCount", 0))
                v["like_count"] = int(d.get("statistics", {}).get("likeCount", 0))

    return videos[:limit]


def resolve_channel_id(handle: str) -> tuple:
    """Resolve @handle to channel ID using YouTube Data API."""
    import requests

    resp = requests.get("https://www.googleapis.com/youtube/v3/channels", params={
        "key": YT_API_KEY,
        "forHandle": handle.lstrip("@"),
        "part": "snippet,statistics",
    })
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if items:
        ch = items[0]
        return ch["id"], ch["snippet"]["title"]

    raise ValueError(f"Could not resolve channel: {handle}")


def extract_transcript_via_browser(page_id: str, video_id: str) -> str | None:
    """Navigate to video, open transcript, extract text."""
    # Navigate to the video
    result = cdp("go", page_id, f"https://www.youtube.com/watch?v={video_id}")
    if "error" in result:
        return None
    time.sleep(5)

    # Expand description and click Show transcript
    result = cdp_eval(page_id, """
    (async () => {
      // Try both expand methods: #expand button and "Show more" button
      var expand = document.querySelector('#expand');
      if (expand) expand.click();

      var buttons = document.querySelectorAll('button');
      for (var i = 0; i < buttons.length; i++) {
        if (buttons[i].textContent.trim() === 'Show more' && buttons[i].offsetParent !== null) {
          buttons[i].click();
          break;
        }
      }

      await new Promise(r => setTimeout(r, 2000));

      // Find and click Show transcript
      buttons = document.querySelectorAll('button');
      for (var i = 0; i < buttons.length; i++) {
        if (buttons[i].textContent.includes('Show transcript')) {
          buttons[i].click();
          return 'clicked';
        }
      }
      return 'not_found';
    })()
    """)

    if result.get("value") == "not_found":
        return None

    if "error" in result and "clicked" not in str(result.get("value", "")):
        return None

    # Wait for transcript segments to load
    time.sleep(5)

    # Extract text from within the transcript panel (not document root)
    result = cdp_eval(page_id, """
    (function() {
      var panel = document.querySelector('ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"]');
      var container = panel || document;
      var segments = container.querySelectorAll('ytd-transcript-segment-renderer');
      if (segments.length === 0) return '';
      var text = [];
      segments.forEach(function(seg) {
        var t = seg.querySelector('.segment-text, yt-formatted-string.segment-text');
        if (t) text.push(t.textContent.trim());
      });
      return text.join(' ');
    })()
    """)

    text = result.get("value", "")
    return text if text and len(text) > 50 else None


def save_transcript(output_dir: Path, video: dict, transcript: str) -> Path:
    """Save transcript as markdown file."""
    from slugify import slugify

    title = video["title"]
    slug = slugify(title, max_length=80)
    filename = f"{slug}.md"
    filepath = output_dir / filename

    views = video.get('view_count', 0)
    likes = video.get('like_count', 0)
    view_str = f"{views:,}" if isinstance(views, int) else str(views)
    like_str = f"{likes:,}" if isinstance(likes, int) else str(likes)

    content = f"""# {title}

**Video:** https://youtu.be/{video['video_id']}
**Published:** {video['published_at'][:10]}
**Views:** {view_str}
**Likes:** {like_str}

---

## Transcript

{transcript}
"""
    filepath.write_text(content)
    return filepath


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Browser-based YouTube transcript fetcher")
    parser.add_argument("--channel", required=True, help="Channel @handle or ID")
    parser.add_argument("--limit", type=int, default=50, help="Max videos")
    parser.add_argument("--output", default=str(VAULT_DIR), help="Output directory")
    parser.add_argument("--skip-existing", action="store_true", help="Skip already downloaded")
    args = parser.parse_args()

    # Resolve channel
    print(f"\n🔍 Resolving channel: {args.channel}")
    channel_id, channel_name = resolve_channel_id(args.channel)
    print(f"   ✅ {channel_name} ({channel_id})")

    # Get video list (already sorted latest first by API)
    print(f"\n🎥 Fetching video list (limit={args.limit}, latest first)...")
    videos = get_channel_videos(channel_id, limit=args.limit)
    print(f"   Found {len(videos)} videos")

    # Setup output
    output_dir = Path(args.output) / channel_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check existing transcripts
    from slugify import slugify
    existing = {f.stem for f in output_dir.glob("*.md")}
    if args.skip_existing and existing:
        before = len(videos)
        videos = [v for v in videos if slugify(v["title"], max_length=80) not in existing]
        print(f"   Skipping {before - len(videos)} already downloaded, {len(videos)} remaining")

    if not videos:
        print("\n✅ All transcripts already downloaded!")
        return

    # Open initial browser tab
    print(f"\n🌐 Opening browser tab...")
    page_id = open_tab()

    # Process videos (latest first)
    success = 0
    failed = 0
    failed_videos = []

    print(f"\n⚙️  Processing {len(videos)} videos (latest → oldest)...\n")
    for i, video in enumerate(videos):
        # Recycle tab every N videos to prevent memory/freeze issues
        if i > 0 and i % TAB_RECYCLE_INTERVAL == 0:
            print(f"\n   🔄 Recycling browser tab (after {TAB_RECYCLE_INTERVAL} videos)...")
            close_tab(page_id)
            time.sleep(2)
            page_id = open_tab()

        title_short = video["title"][:60].replace("&#39;", "'").replace("&amp;", "&")
        print(f"  [{i+1}/{len(videos)}] {title_short}...", end=" ", flush=True)

        try:
            transcript = extract_transcript_via_browser(page_id, video["video_id"])
            if transcript:
                save_transcript(output_dir, video, transcript)
                success += 1
                print(f"✅ ({len(transcript):,} chars)")
            else:
                failed += 1
                failed_videos.append(video)
                print("❌ (no transcript)")
        except subprocess.TimeoutExpired:
            failed += 1
            failed_videos.append(video)
            print("⏱️  (timeout — recycling tab)")
            # Tab is likely frozen, recycle it
            close_tab(page_id)
            time.sleep(2)
            page_id = open_tab()
        except Exception as e:
            failed += 1
            failed_videos.append(video)
            print(f"❌ ({e})")

        time.sleep(1)

    # Retry failed videos once with fresh tabs
    if failed_videos:
        print(f"\n🔁 Retrying {len(failed_videos)} failed videos...")
        close_tab(page_id)
        time.sleep(2)
        page_id = open_tab()

        retry_success = 0
        for i, video in enumerate(failed_videos):
            if i > 0 and i % TAB_RECYCLE_INTERVAL == 0:
                close_tab(page_id)
                time.sleep(2)
                page_id = open_tab()

            title_short = video["title"][:60].replace("&#39;", "'").replace("&amp;", "&")
            print(f"  [retry {i+1}/{len(failed_videos)}] {title_short}...", end=" ", flush=True)

            try:
                transcript = extract_transcript_via_browser(page_id, video["video_id"])
                if transcript:
                    save_transcript(output_dir, video, transcript)
                    retry_success += 1
                    failed -= 1
                    print(f"✅ ({len(transcript):,} chars)")
                else:
                    print("❌ (no transcript)")
            except subprocess.TimeoutExpired:
                print("⏱️  (timeout)")
                close_tab(page_id)
                time.sleep(2)
                page_id = open_tab()
            except Exception as e:
                print(f"❌ ({e})")

            time.sleep(1)

        success += retry_success

    # Cleanup
    close_tab(page_id)

    print(f"\n{'='*50}")
    print(f"✅ Done! Results:")
    print(f"   Success:  {success}/{len(videos) + len(existing if args.skip_existing else set())}")
    print(f"   Failed:   {failed}")
    print(f"   Output:   {output_dir}")
    print(f"   Files:    {len(list(output_dir.glob('*.md')))} markdown files")


if __name__ == "__main__":
    main()
