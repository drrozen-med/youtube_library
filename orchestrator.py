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
    print(f"\n🎥 Fetching video list (limit={args.limit}, sort={args.sort})...")
    try:
        videos = collect_videos(
            channel_id=channel_id,
            limit=args.limit,
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
    
    # 6) Determine pending work
    pend = list_pending(chan_dir, need="transcript")
    
    if not pend:
        print("\n✅ Nothing to process. All transcripts already downloaded.")
        build_index(chan_dir)
        sys.exit(0)
    
    print(f"\n📝 Found {len(pend)} videos needing transcripts.")
    
    # Calculate next index number for filenames
    transcripts_dir = chan_dir / "transcripts"
    transcripts_dir.mkdir(exist_ok=True)
    existing = sorted(transcripts_dir.glob("*.md"))
    next_idx = len(existing) + 1
    
    # 7) Process queue
    print(f"\n⚙️  Processing videos...")
    for v in tqdm(pend, desc="Processing", unit="video"):
        vid = v.video_id
        
        # Fetch transcript
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
            
            fpath = generate_markdown(chan_dir, next_idx, meta, text, summary=summary_text)
            
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
            
            next_idx += 1
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
