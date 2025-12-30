# YouTube Orchestrator MCP

**Automated YouTube transcript extraction and Markdown generation with AI agent integration.**

Extract transcripts from any YouTube channel, optionally summarize them with LLMs, and organize everything as beautifully formatted Markdown files in your local knowledge base (Obsidian-compatible).

Includes a Model Context Protocol (MCP) server so AI agents (Claude, Cursor, Windsurf) can orchestrate the entire pipeline programmatically.

---

## Features

✅ **Universal Channel Resolution** - Paste any YouTube URL, @handle, channel ID, or even a video URL  
✅ **Smart Transcript Fetching** - Prefers manual transcripts, falls back to auto-generated  
✅ **Advanced Filtering** - By date range, duration, popularity, or upload date  
✅ **LLM Summarization** - Auto-generates TL;DR summaries (Ollama or OpenAI)  
✅ **Obsidian-Ready** - YAML frontmatter + clean Markdown format  
✅ **Resume-Safe** - Tracks processing status; interrupted runs resume cleanly  
✅ **MCP Integration** - Expose as tools to AI agents  

---

## Quick Start

### 1. Prerequisites

- Python 3.9+
- YouTube Data API key ([get one here](https://console.cloud.google.com/apis/credentials))
- (Optional) OpenAI API key or local Ollama for summarization

### 2. Installation

```bash
cd /Users/urirozen/projects/youtube_library

# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Edit .env and add your API key
# YT_API_KEY=your_youtube_api_key_here
```

### 3. Basic Usage (CLI)

```bash
# Fetch 10 most popular videos from Kurzgesagt
python orchestrator.py "https://www.youtube.com/@kurzgesagt" --limit 10 --sort popular

# Fetch recent videos with AI summarization
python orchestrator.py "@AliAbdaal" --limit 20 --summarize

# Fetch videos from specific date range
python orchestrator.py "Kurzgesagt" --after 2024-01-01 --before 2024-12-31

# Fetch only long-form content (1+ hour)
python orchestrator.py "@lexfridman" --min-duration 3600 --summarize
```

**Output:**
```
vault/
  Kurzgesagt – In a Nutshell/
    transcripts/
      001-the-origin-of-life.md
      002-how-time-works.md
      003-black-hole-facts.md
    antenna.json          # Status tracking
    index.json           # Summary stats
```

---

## CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `input` | Channel URL, @handle, ID, or name | *required* |
| `--output` | Root directory for vault | `./vault` |
| `--limit` | Max videos to fetch | `50` |
| `--sort` | `date` (newest) or `popular` (by views) | `date` |
| `--after` | Only videos published after YYYY-MM-DD | - |
| `--before` | Only videos published before YYYY-MM-DD | - |
| `--min-duration` | Minimum video length (seconds) | - |
| `--max-duration` | Maximum video length (seconds) | - |
| `--summarize` | Generate TL;DR with LLM | `false` |
| `--skip-existing` | Skip already-processed videos | `false` |
| `--verbose` | Detailed logging | `false` |

---

## Markdown Output Format

Each video generates a file like this:

```markdown
---
title: "How Dopamine Works"
channel: "Ali Abdaal"
video_id: "abc123"
url: "https://youtu.be/abc123"
published_at: "2024-03-01T12:00:00Z"
duration: "00:12:45"
view_count: 1203948
like_count: 43221
tags: [neuroscience, dopamine, productivity]
---

# TL;DR

- Dopamine drives motivation by predicting rewards, not pleasure itself.
- It's released during anticipation and learning, not achievement.
- Key quote: "You don't get dopamine for success; you get it for progress."

# Transcript

Welcome back to another video...
```

---

## MCP Integration (AI Agents)

The system includes an MCP server so AI agents can use YouTube orchestration as tools.

### Setup for Claude Desktop

1. Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
2. Add the configuration from `mcp_config_examples/claude_desktop.json`
3. Replace placeholder API keys
4. Restart Claude Desktop

### Setup for Cursor IDE

1. Open Cursor Settings → MCP Servers
2. Use configuration from `mcp_config_examples/cursor_mcp.json`
3. Restart Cursor

### Available MCP Tools

- `resolve_channel` - Resolve any YouTube identifier to channel metadata
- `register_channel` - Create/load channel registry
- `sync_channel` - Fetch and merge videos
- `get_pending` - List videos needing work
- `process_video` - Full pipeline for one video
- `build_index` - Regenerate index.json

### Example Agent Query

> "Use the YouTube orchestrator to fetch the 10 most popular videos from @kurzgesagt and summarize them."

The agent will automatically:
1. Resolve the channel
2. Register it
3. Fetch metadata
4. Download transcripts
5. Generate summaries
6. Create Markdown files

---

## Architecture

```
youtube_library/
├── core/                      # Core modules
│   ├── channel_resolver.py    # URL/handle → channel ID
│   ├── antenna_registry.py    # Local persistence layer
│   ├── video_collector.py     # YouTube API fetching
│   ├── transcript_fetcher.py  # Transcript download
│   ├── markdown_generator.py  # .md file creation
│   ├── index_builder.py       # Summary statistics
│   └── summarizer.py          # LLM summarization
├── mcp/
│   └── youtube_mcp_server.py  # MCP server (stdio)
├── orchestrator.py            # Main CLI entrypoint
├── requirements.txt
├── .env.example
└── vault/                     # Generated content
    └── [Channel Name]/
        ├── transcripts/
        ├── antenna.json
        └── index.json
```

---

## Obsidian Integration

The Markdown files are instantly compatible with Obsidian:

1. **Import vault:**
   - Open Obsidian
   - Open folder as vault: `/Users/urirozen/projects/youtube_library/vault`

2. **Search:**
   - Built-in search (Cmd+Shift+F) works immediately
   - Install **Omnisearch** plugin for semantic-ish search
   - Use Dataview plugin to query metadata

3. **Syncing:**
   - Use Syncthing to keep vault synced across devices
   - Or use Obsidian Sync (paid)

---

## Advanced Features

### Multi-Creator Configuration

Create a `channels.yaml`:

```yaml
channels:
  - handle: "@kurzgesagt"
    limit: 100
    sort: "date"
    summarize: true
  
  - handle: "@AliAbdaal"
    limit: 50
    sort: "popular"
    after: "2024-01-01"
```

### Incremental Updates

Re-run the same command to fetch new videos:

```bash
python orchestrator.py "@kurzgesagt" --limit 50
```

Only **new** videos are processed (tracked via `antenna.json`).

### Local LLM (Ollama)

For privacy and cost savings:

```bash
# Install Ollama
brew install ollama

# Pull a model
ollama pull mistral

# Set in .env
OLLAMA_MODEL=mistral

# Run orchestrator
python orchestrator.py "@AliAbdaal" --summarize
```

---

## Troubleshooting

### "Missing YT_API_KEY"

Set it in `.env`:
```bash
YT_API_KEY=your_actual_key_here
```

### "No transcript available"

Some videos don't have transcripts. The system will skip them and mark status as `transcript_downloaded: false` in `antenna.json`.

### LLM Summarization Not Working

Check:
1. Is `OPENAI_API_KEY` set? (for OpenAI)
2. Is Ollama running? (`ollama list`)
3. Run with `--verbose` to see detailed errors

### MCP Tools Not Showing

1. Verify config file syntax (valid JSON)
2. Check `cwd` path is correct
3. Restart the AI agent completely
4. Check agent logs for MCP connection errors

---

## API Quotas

**YouTube Data API** (free tier):
- 10,000 units/day
- Each video fetch ≈ 1-3 units
- Reasonable limit: ~500-1000 videos/day

**OpenAI API** (paid):
- gpt-3.5-turbo: ~$0.001 per summary
- 100 summaries ≈ $0.10

**Ollama** (local):
- Completely free
- Requires local compute

---

## Roadmap / Future Enhancements

- [ ] Batch processing from `channels.yaml`
- [ ] Automatic weekly cron sync
- [ ] Semantic search with embeddings (Chroma/FAISS)
- [ ] Web dashboard for vault health
- [ ] Multi-language transcript support
- [ ] Chapter/timestamp extraction
- [ ] Auto-tagging via NLP

---

## License

MIT - Use freely for personal or commercial projects.

---

## Contributing

This is a personal tool, but PRs welcome for:
- Bug fixes
- New LLM backends (Anthropic, Gemini, etc.)
- Better error handling
- Additional metadata extraction

---

## Credits

Built with:
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api)
- [LangChain](https://github.com/langchain-ai/langchain)
- [MCP SDK](https://modelcontextprotocol.io/)
- [Pydantic](https://docs.pydantic.dev/)

---

**Questions?** Open an issue or check the examples in `/mcp_config_examples/`.
