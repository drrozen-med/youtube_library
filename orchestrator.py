"""
YouTube Orchestrator - Main CLI
================================

End-to-end pipeline for YouTube transcript extraction.

Usage:
    python orchestrator.py "https://www.youtube.com/@kurzgesagt" --limit 20 --summarize

Flow:
    1. Resolve channel from any input (URL, handle, ID)
    2. Create/load antenna registry
    3. Fetch video metadata with filters
    4. Sync registry with discovered videos
    5. Process pending videos (fetch transcript → summarize → generate markdown)
    6. Update registry status
    7. Build index.json
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from core import (
    resolve_channel,
    init_registry,
    sync_registry,
    list_pending,
    update_status,
    load_registry,
    collect_videos,
    fetch_transcript_text,
    generate_markdown,
    build_index,
    summarize_transcript,
)
from core.transcript_fetcher import check_ip_block_status

DEFAULT_VAULT = Path("./vault")


def _confirm(prompt: str) -> bool:
    """Ask user for confirmation."""
    ans = input(f"{prompt} [Y/n]: ").strip().lower()
    return ans in ("", "y", "yes")


def main():
    import argparse
    
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="YouTube → Markdown Orchestrator (with MCP support)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch 10 most popular videos from a channel
  python orchestrator.py "https://www.youtube.com/@kurzgesagt" --limit 10 --sort popular

  # Fetch recent videos with summarization
  python orchestrator.py "@AliAbdaal" --limit 20 --summarize

  # Fetch videos from specific date range
  python orchestrator.py "Kurzgesagt" --after 2024-01-01 --before 2024-12-31

  # Fetch only long-form content
  python orchestrator.py "@lexfridman" --min-duration 3600
        """
    )
    
    parser.add_argument(
        "input",
        help="Channel URL, @handle, channel ID, or name"
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_VAULT),
        help="Root output directory (default: ./vault)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max videos to fetch (default: 50)"
    )
    parser.add_argument(
        "--sort",
        choices=["date", "popular"],
        default="date",
        help="Sort order: 'date' (newest first) or 'popular' (by views)"
    )
    parser.add_argument(
        "--after",
        default=None,
        help="Filter published after YYYY-MM-DD"
    )
    parser.add_argument(
        "--before",
        default=None,
        help="Filter published before YYYY-MM-DD"
    )
    parser.add_argument(
        "--min-duration",
        type=int,
        default=None,
        help="Min duration in seconds"
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=None,
        help="Max duration in seconds"
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Generate TL;DR summary using LLM (LangChain)"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip items that already have markdown"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # 1) Resolve channel from input
    print(f"\n🔍 Resolving channel: {args.input}")
    try:
        channel_id, ch = resolve_channel(args.input)
    except Exception as e:
        print(f"❌ Error resolving channel: {e}")
        sys.exit(1)
    
    ch_name = ch["snippet"].get("title")
    handle = ch["snippet"].get("customUrl") or ch.get("brandingSettings", {}).get("channel", {}).get("vanityUrl")
    subs = ch.get("statistics", {}).get("subscriberCount", "N/A")
    video_count = ch.get("statistics", {}).get("videoCount", "N/A")
    
    print(f"\n✅ Resolved channel:")
    print(f"   Title:       {ch_name}")
    print(f"   ID:          {channel_id}")
    print(f"   Handle:      @{handle if handle else 'N/A'}")
    print(f"   Subscribers: {subs}")
    print(f"   Videos:      {video_count}")
    
    if not _confirm("\nProceed with this channel?"):
        print("Aborted.")
        sys.exit(1)
    
    # 2) Setup channel directory
    out_root = Path(args.output)
    chan_dir = out_root / (ch_name or channel_id)
    chan_dir.mkdir(parents=True, exist_ok=True)
    
    # 3) Init/load registry
    print(f"\n📋 Initializing registry at: {chan_dir}")
    reg = init_registry(
        chan_dir,
        channel_id=channel_id,
        channel_name=ch_name,
        handle=f"@{handle}" if handle else None
    )
    
    # 4) Collect videos with filters
    # If processing newest first with a small limit, fetch more videos to ensure we get newest pending ones
    # Otherwise the limit might only fetch videos that are already processed
    fetch_limit = args.limit
    if args.limit and args.limit < 50:
        # Fetch at least 50 videos to ensure we get the newest pending ones
        fetch_limit = 50
        print(f"   Note: Fetching {fetch_limit} videos (instead of {args.limit}) to ensure newest pending videos are included")
    print(f"\n🎥 Fetching video list (limit={fetch_limit or 'all'}, sort={args.sort})...")
    try:
        videos = collect_videos(
            channel_id=channel_id,
            limit=fetch_limit,
            sort=args.sort,
            after=args.after,
            before=args.before,
            min_duration=args.min_duration,
            max_duration=args.max_duration
        )
        print(f"   Found {len(videos)} videos matching filters.")
    except Exception as e:
        print(f"❌ Error fetching videos: {e}")
        sys.exit(1)
    
    # 5) Sync registry
    print(f"\n🔄 Syncing registry...")
    reg = sync_registry(chan_dir, videos)
    
    # 6) Check IP block status before processing
    print(f"\n🔍 Checking IP block status...")
    is_blocked, block_message = check_ip_block_status()
    if is_blocked:
        print(f"⚠️  IP is currently BLOCKED by YouTube!")
        print(f"   Error: {block_message[:200]}...")
        print(f"\n💡 Recommendation: Wait 1-2 hours before retrying.")
        print(f"   The system will automatically retry with backoff, but it's better to wait.")
        response = input("\nContinue anyway? (y/N): ").strip().lower()
        if response != 'y':
            print("Aborted. Please wait and try again later.")
            sys.exit(1)
        print("Continuing with automatic retry logic...")
    else:
        print(f"✅ IP is accessible - proceeding with downloads")
    
    # 7) Determine pending work
    pend = list_pending(chan_dir, need="transcript")
    
    if not pend:
        print("\n✅ Nothing to process. All transcripts already downloaded.")
        build_index(chan_dir)
        sys.exit(0)
    
    print(f"\n📝 Found {len(pend)} videos needing transcripts.")
    
    # Sort pending videos by published_at in DESCENDING order (newest first)
    # This processes latest videos first, but indices are still assigned chronologically
    pend_sorted = sorted(pend, key=lambda x: x.published_at, reverse=True)
    
    # Limit to newest N videos if user wants latest first
    if args.limit and len(pend_sorted) > args.limit:
        pend_sorted = pend_sorted[:args.limit]
        print(f"   Limiting to newest {args.limit} videos (processing latest first)")
    
    # Get all videos (including already processed) to determine correct index numbers
    reg = load_registry(chan_dir)
    all_videos = sorted(reg.videos.values(), key=lambda x: x.published_at)
    
    # Create a mapping of video_id to chronological index
    video_to_index = {}
    for idx, video in enumerate(all_videos, start=1):
        video_to_index[video.video_id] = idx
    
    # 8) Process queue (newest first, but numbered chronologically)
    print(f"\n⚙️  Processing videos (newest first, numbered chronologically)...")
    for v in tqdm(pend_sorted, desc="Processing", unit="video"):
        vid = v.video_id
        
        # Get chronological index for this video
        idx = video_to_index.get(vid, len(all_videos) + 1)
        
        # Fetch transcript with detailed error logging
        print(f"\n   Processing video {vid} (index {idx})...")
        import logging
        import sys
        # Configure logging to show warnings/errors to stderr with full messages
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter('   %(levelname)s: %(message)s'))
        logger = logging.getLogger('core.transcript_fetcher')
        logger.setLevel(logging.WARNING)
        if not logger.handlers:  # Avoid duplicate handlers
            logger.addHandler(handler)
        
        text, source, lang = fetch_transcript_text(vid)
        if text:
            print(f"   ✓ Transcript fetched: source={source}, lang={lang}, length={len(text)} chars")
        else:
            print(f"   ✗ Transcript NOT available for {vid} (see warnings above for details)")
            # Log the actual error - warnings should be visible
            import logging
            logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s', force=True)
            # Re-fetch with logging to see the error
            text, source, lang = fetch_transcript_text(vid)
        
        if text:
            # Optional summarization
            summary_text = None
            if args.summarize:
                summary_text = summarize_transcript(text, verbose=args.verbose)
            
            # Generate markdown
            meta = {
                "video_id": v.video_id,
                "title": v.title,
                "published_at": v.published_at,
                "duration_sec": v.duration_sec,
                "view_count": v.view_count,
                "like_count": v.like_count,
                "comment_count": v.comment_count,
                "tags": v.tags,
                "channel_name": ch_name,
                "url": f"https://youtu.be/{v.video_id}",
            }
            
            try:
                fpath = generate_markdown(chan_dir, idx, meta, text, summary=summary_text)
                print(f"\n   ✓ Created file: {fpath.name}")
                if not fpath.exists():
                    print(f"   ⚠️  WARNING: File was created but doesn't exist at {fpath}")
            except Exception as e:
                print(f"\n   ✗ ERROR creating markdown for video {vid} (index {idx}): {e}")
                import traceback
                traceback.print_exc()
                continue  # Skip this video if file creation failed
            
            # Update registry
            update_status(
                chan_dir,
                video_id=vid,
                transcript_downloaded=True,
                markdown_generated=True,
                summarized=bool(summary_text),
                transcript_source=source,
                transcript_language=lang,
                path_md=str(fpath.relative_to(chan_dir))
            )
        else:
            # Mark transcript attempt (unavailable)
            update_status(
                chan_dir,
                video_id=vid,
                transcript_downloaded=False,
                transcript_source=None,
                transcript_language=None
            )
    
    # 8) Build/refresh index
    idx_path = build_index(chan_dir)
    
    print(f"\n✅ Done!")
    print(f"   Channel dir: {chan_dir}")
    print(f"   Index:       {idx_path}")
    print(f"\n💡 Tip: Open {chan_dir} in Obsidian to view your vault.\n")


if __name__ == "__main__":
    main()
