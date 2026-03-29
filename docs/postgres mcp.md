# PostgreSQL MCP Servers — Setup & Troubleshooting

## Current Architecture (as of 2026-03-29)

Two postgres MCP servers are configured. They use different connection strategies:

| Server | Database | How it starts | Transport |
|--------|----------|---------------|-----------|
| `postgres` | `trading_journal` | Claude Code starts it at launch (command-based) | stdio |
| `postgres_grail` | `grail_files` | You start it manually before launching Claude Code | Streamable HTTP |

**Why different strategies?** Claude Code reliably starts one command-based MCP server
but silently fails to invoke a second one (root cause unknown, confirmed 2026-03-29).
The grail server works around this by running as a persistent Docker container that
Claude Code connects to via HTTP URL.

**Why different Docker images?**
- `postgres` uses `crystaldba/postgres-mcp` — richer DBA tools (index analysis, health checks, workload analysis, explain plans)
- `postgres_grail` uses `bytebase/dbhub` — supports streamable HTTP transport (MCP 2025 spec); crystaldba only supports the old SSE protocol which Claude Code 2.x no longer connects to

---

## MCP Server Config (`~/.claude/settings.json`)

```json
"mcpServers": {
  "postgres": {
    "command": "/home/ericbell/.local/bin/postgres-mcp",
    "args": [],
    "env": {}
  },
  "postgres_grail": {
    "url": "http://localhost:8001/mcp"
  }
}
```

- `postgres` → command-based, wrapper script starts a Docker container via stdio
- `postgres_grail` → streamable HTTP URL, connects to a pre-running container on port 8001

**Important:** For streamable HTTP servers, omit the `"type"` field entirely — just use `"url"`.
Using `"type": "sse"` targets the old SSE protocol which Claude Code 2.x no longer supports.

---

## Starting the Grail MCP Server

Run this **before launching Claude Code** whenever you need grail tools:

```bash
postgres-mcp-grail
```

This starts a Docker container named `postgres-mcp-grail` on port 8001 in streamable HTTP mode.
Claude Code connects to it at `http://localhost:8001/mcp` on startup.

To stop it:
```bash
docker rm -f postgres-mcp-grail
```

Verify it's running and the endpoint responds:
```bash
docker ps | grep postgres-mcp
curl -s -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}},"id":1}'
# should return a jsonrpc response (not an error about transport)
```

---

## How the `postgres` Wrapper Works

`/home/ericbell/.local/bin/postgres-mcp`:

1. Reads credentials from `~/.config/postgres/default.toml` (never hardcoded)
2. If run interactively (stdin is a TTY), prints info and exits — does **not** kill
   a live MCP container
3. Runs `docker rm -f postgres-mcp` to clear any stale container
4. Uses `exec docker run -i --rm` — stdio transport, process stays alive while
   Claude Code communicates over stdin/stdout
5. Supports `POSTGRES_MCP_DB` env var to target a different database
6. Supports `POSTGRES_MCP_CONTAINER` env var to override the container name

## How the `postgres_grail` Wrapper Works

`/home/ericbell/.local/bin/postgres-mcp-grail`:

1. Reads credentials from `~/.config/postgres/default.toml`
2. Stops any existing `postgres-mcp-grail` container
3. Starts a detached `bytebase/dbhub` container with `-p 8001:8080` and `--transport=http`
4. Exits immediately — container runs in background until you stop it

**Tools exposed by dbhub:**
- `execute_sql` — run queries
- `search_objects` — explore schemas, tables, columns, indexes

---

## Verifying Both Servers Are Connected

At the start of a Claude Code session, the deferred tools list should include
both `mcp__postgres__*` AND `mcp__postgres_grail__*` tool families (if grail
was pre-started).

---

## Known Issues

### `env` Block in `mcpServers` Is Silently Ignored
**Confirmed 2026-03-28.** The `env` block in `mcpServers` config is silently ignored.
This is why both wrappers read credentials from a TOML file directly rather than
relying on environment variables passed through the config.

### Second Command-Based MCP Server Not Started
**Confirmed 2026-03-29.** When two `command`-based MCP servers are configured,
Claude Code reliably starts the first (`postgres`) but never invokes the second.
Root cause unknown. Workaround: use a URL-based streamable HTTP server for the second.

### Old SSE Transport Not Supported in Claude Code 2.x
**Confirmed 2026-03-29.** Claude Code 2.x uses the MCP 2025 streamable HTTP transport
for URL-based servers. The old HTTP+SSE protocol (separate SSE stream + POST endpoint)
is no longer connected, even if the endpoint responds correctly. `crystaldba/postgres-mcp`
v0.3.0 only supports the old SSE transport — a PR to add streamable HTTP exists but is
unmerged. Use `bytebase/dbhub` instead for URL-based connections.

---

## Supporting Files

- `postgres` wrapper: `/home/ericbell/.local/bin/postgres-mcp`
- `postgres_grail` script: `/home/ericbell/.local/bin/postgres-mcp-grail`
- DB credentials: `~/.config/postgres/default.toml`
- MCP server config: `~/.claude/.claude.json` → `mcpServers`
- Docker images: `crystaldba/postgres-mcp` (postgres), `bytebase/dbhub` (postgres_grail)

---

## Setup on a New Machine

1. Copy `~/.config/postgres/default.toml` (machine-specific credentials)
2. Copy `/home/ericbell/.local/bin/postgres-mcp` and `postgres-mcp-grail`
3. `chmod 750 ~/.local/bin/postgres-mcp ~/.local/bin/postgres-mcp-grail`
4. Edit `~/.claude/settings.json` to add both `mcpServers` entries (see above)
5. Pull Docker images:
   ```bash
   docker pull crystaldba/postgres-mcp
   docker pull bytebase/dbhub
   ```
6. Start the grail container before launching Claude Code: `postgres-mcp-grail`
