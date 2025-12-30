# MCP Configuration Examples

These configuration files enable AI agents (Claude Desktop, Cursor, Windsurf) to use the YouTube Orchestrator as a tool.

## Claude Desktop

1. Locate your Claude Desktop config file:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. Merge the contents of `claude_desktop.json` into your config

3. Replace placeholder values:
   - `your_youtube_api_key_here` → your actual YouTube Data API key
   - `your_openai_key_here_optional` → optional OpenAI key for summarization
   - Update `cwd` path if you installed elsewhere

4. Restart Claude Desktop

5. Verify: You should see MCP tools available (🔧 icon)

## Cursor IDE

1. Open Cursor Settings → MCP Servers

2. Add a new server using the configuration from `cursor_mcp.json`

3. Replace placeholder values (same as above)

4. Restart Cursor

5. Test by asking: "List available MCP tools"

## Windsurf

Similar to Cursor - add the MCP server configuration to Windsurf's settings.

## Environment Variables

Instead of putting keys directly in the config, you can use a `.env` file in the project root:

```bash
YT_API_KEY=your_key_here
OPENAI_API_KEY=sk-...
OLLAMA_MODEL=mistral
DEFAULT_OUTPUT=./vault
```

Then remove the `env` section from the JSON config.

## Testing

Once configured, try asking your AI agent:

> "Use the YouTube orchestrator to fetch the 5 most popular videos from @kurzgesagt"

The agent will call the MCP tools to:
1. Resolve the channel
2. Register it
3. Sync videos
4. Process transcripts
5. Generate Markdown files
