"""
YouTube Orchestrator MCP Server
================================

Model Context Protocol (MCP) server exposing YouTube orchestrator tools
to AI agents (Claude Desktop, Cursor, Windsurf, etc.)

Transport: stdio (secure, local-first)

Tools:
- resolve_channel: Resolve any YouTube identifier to channel metadata
- register_channel: Create/load channel registry
- sync_channel: Fetch and merge videos into registry
- get_pending: List videos needing work
- process_video: Full processing pipeline for one video
- build_index: Regenerate index.json
"""

import os
import json
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# Import core modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

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
from core.antenna_registry import registry_path

DEFAULT_VAULT = Path(os.getenv("DEFAULT_OUTPUT", "./vault")).resolve()

server = Server("youtube-orchestrator")


# --------- TOOL DECLARATIONS ---------

@server.tool(
    name="resolve_channel",
    description="Resolve any YouTube channel URL/handle/ID/name (or video URL) to canonical channel metadata"
)
async def tool_resolve_channel(input: str) -> types.CallToolResult:
    """Resolve channel from any identifier."""
    try:
        channel_id, ch = resolve_channel(input)
        return types.CallToolResult(
            content=[types.TextContent(
                type="text",
                text=json.dumps({
                    "channel_id": channel_id,
                    "channel_name": ch["snippet"].get("title"),
                    "handle": ch["snippet"].get("customUrl"),
                    "subscribers": ch.get("statistics", {}).get("subscriberCount"),
                    "video_count": ch.get("statistics", {}).get("videoCount"),
                }, ensure_ascii=False, indent=2)
            )]
        )
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error: {str(e)}")]
        )


@server.tool(
    name="register_channel",
    description="Create or load a per-channel registry under the vault"
)
async def tool_register_channel(
    channel_id: str,
    channel_name: Optional[str] = None,
    handle: Optional[str] = None,
    vault_dir: Optional[str] = None
) -> types.CallToolResult:
    """Initialize or load channel registry."""
    try:
        root = Path(vault_dir or DEFAULT_VAULT)
        chan_dir = root / (channel_name or channel_id)
        reg = init_registry(
            chan_dir,
            channel_id=channel_id,
            channel_name=channel_name,
            handle=handle
        )
        return types.CallToolResult(
            content=[types.TextContent(
                type="text",
                text=json.dumps({
                    "channel_dir": str(chan_dir),
                    "registry_path": str(registry_path(chan_dir)),
                    "total_videos": len(reg.videos),
                }, ensure_ascii=False, indent=2)
            )]
        )
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error: {str(e)}")]
        )


@server.tool(
    name="sync_channel",
    description="Fetch video list (with filters) and merge new ones into registry"
)
async def tool_sync_channel(
    channel_id: str,
    channel_name: Optional[str] = None,
    sort: str = "date",
    limit: int = 50,
    after: Optional[str] = None,
    before: Optional[str] = None,
    min_duration: Optional[int] = None,
    max_duration: Optional[int] = None,
    vault_dir: Optional[str] = None
) -> types.CallToolResult:
    """Sync channel videos with registry."""
    try:
        root = Path(vault_dir or DEFAULT_VAULT)
        chan_dir = root / (channel_name or channel_id)
        
        # Collect videos
        items = collect_videos(
            channel_id=channel_id,
            limit=limit,
            sort=sort,
            after=after,
            before=before,
            min_duration=min_duration,
            max_duration=max_duration
        )
        
        # Sync registry
        reg = sync_registry(chan_dir, items)
        
        return types.CallToolResult(
            content=[types.TextContent(
                type="text",
                text=json.dumps({
                    "synced_videos": len(items),
                    "total_known": len(reg.videos),
                    "registry_path": str(registry_path(chan_dir)),
                }, ensure_ascii=False, indent=2)
            )]
        )
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error: {str(e)}")]
        )


@server.tool(
    name="get_pending",
    description="Return videos pending work (transcript | markdown | summary)"
)
async def tool_get_pending(
    channel_id: str,
    channel_name: Optional[str] = None,
    need: str = "transcript",
    vault_dir: Optional[str] = None
) -> types.CallToolResult:
    """List pending videos."""
    try:
        root = Path(vault_dir or DEFAULT_VAULT)
        chan_dir = root / (channel_name or channel_id)
        
        pending = list_pending(chan_dir, need=need)
        
        return types.CallToolResult(
            content=[types.TextContent(
                type="text",
                text=json.dumps({
                    "count": len(pending),
                    "videos": [
                        {
                            "video_id": v.video_id,
                            "title": v.title,
                            "published_at": v.published_at,
                            "duration_sec": v.duration_sec,
                        }
                        for v in pending[:20]  # Limit to first 20 for readability
                    ],
                }, ensure_ascii=False, indent=2)
            )]
        )
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error: {str(e)}")]
        )


@server.tool(
    name="process_video",
    description="Fetch transcript, optionally summarize via LLM, write Markdown, update registry"
)
async def tool_process_video(
    channel_id: str,
    channel_name: str,
    video_id: str,
    summarize: bool = False,
    vault_dir: Optional[str] = None,
    summarizer_verbose: bool = False
) -> types.CallToolResult:
    """Process a single video."""
    try:
        load_dotenv()
        root = Path(vault_dir or DEFAULT_VAULT)
        chan_dir = root / channel_name
        
        # Load registry + compute next filename index
        reg = load_registry(chan_dir)
        transcripts_dir = chan_dir / "transcripts"
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        next_idx = len(list(transcripts_dir.glob("*.md"))) + 1
        
        v = reg.videos.get(video_id)
        if not v:
            return types.CallToolResult(
                content=[types.TextContent(
                    type="text",
                    text="Error: Video not found in registry. Run sync_channel first."
                )]
            )
        
        # Fetch transcript
        text, source, lang = fetch_transcript_text(video_id)
        if not text:
            update_status(chan_dir, video_id=video_id, transcript_downloaded=False)
            return types.CallToolResult(
                content=[types.TextContent(
                    type="text",
                    text=json.dumps({
                        "video_id": video_id,
                        "status": "no_transcript_available"
                    }, indent=2)
                )]
            )
        
        # Optional LLM summary
        summary_text = None
        if summarize:
            summary_text = summarize_transcript(text, verbose=summarizer_verbose)
        
        # Write markdown
        meta = {
            "video_id": video_id,
            "title": v.title,
            "published_at": v.published_at,
            "duration_sec": v.duration_sec,
            "view_count": v.view_count,
            "like_count": v.like_count,
            "comment_count": v.comment_count,
            "tags": v.tags,
            "channel_name": channel_name,
            "url": f"https://youtu.be/{video_id}",
        }
        fpath = generate_markdown(chan_dir, next_idx, meta, text, summary=summary_text)
        
        # Update registry
        update_status(
            chan_dir,
            video_id=video_id,
            transcript_downloaded=True,
            markdown_generated=True,
            summarized=bool(summary_text),
            transcript_source=source,
            transcript_language=lang,
            path_md=str(fpath.relative_to(chan_dir))
        )
        
        return types.CallToolResult(
            content=[types.TextContent(
                type="text",
                text=json.dumps({
                    "video_id": video_id,
                    "markdown_path": str(fpath),
                    "summarized": bool(summary_text),
                    "status": "completed"
                }, ensure_ascii=False, indent=2)
            )]
        )
    
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error: {str(e)}")]
        )


@server.tool(
    name="build_index",
    description="Rebuild index.json for a channel (summary stats)"
)
async def tool_build_index(
    channel_id: str,
    channel_name: Optional[str] = None,
    vault_dir: Optional[str] = None
) -> types.CallToolResult:
    """Rebuild channel index."""
    try:
        root = Path(vault_dir or DEFAULT_VAULT)
        chan_dir = root / (channel_name or channel_id)
        out = build_index(chan_dir)
        
        return types.CallToolResult(
            content=[types.TextContent(
                type="text",
                text=json.dumps({
                    "index_path": str(out)
                }, indent=2)
            )]
        )
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error: {str(e)}")]
        )


# --------- SERVER STARTUP ---------

async def main():
    """Run MCP server on stdio."""
    load_dotenv()
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
