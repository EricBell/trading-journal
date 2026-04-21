# PostgreSQL MCP Servers — Setup & Troubleshooting

## Current Architecture (as of 2026-03-29)

Two postgres MCP servers are configured. Both use `bytebase/dbhub` with streamable HTTP
transport and must be **pre-started** before launching Claude Code.

| Server | Database | Port | How it starts |
|--------|----------|------|---------------|
| `postgres` | `trading_journal` | 8002 | Run `postgres-mcp` before launching Claude Code |
| `postgres_grail` | `grail_files` | 8001 | Run `postgres-mcp-grail` before launching Claude Code |

**Why both use bytebase/dbhub?** Claude Code 2.x requires streamable HTTP transport (MCP
2025 spec). `crystaldba/postgres-mcp` only supports the old SSE protocol and has been
removed. `bytebase/dbhub` supports streamable HTTP and has a fully working `execute_sql`.

---

## MCP Server Config (`~/.claude/settings.json`)

```json
"mcpServers": {
  "postgres": {
    "url": "http://localhost:8002/mcp"
  },
  "postgres_grail": {
    "url": "http://localhost:8001/mcp"
  }
}
```

Both servers use streamable HTTP URL — no command-based entries. Claude Code connects to
pre-running containers on startup.

**Important:** Omit the `"type"` field entirely — just use `"url"`.
Using `"type": "sse"` targets the old SSE protocol which Claude Code 2.x no longer supports.

---

## Starting Both MCP Servers

Run both **before launching Claude Code**:

```bash
postgres-mcp          # trading_journal on port 8002
postgres-mcp-grail    # grail_files on port 8001
```

To stop them:
```bash
docker rm -f postgres-mcp postgres-mcp-grail
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
2. Stops any existing `postgres-mcp` container
3. Starts a detached `bytebase/dbhub` container with `-p 8002:8080` and `--transport=http`
4. Exits immediately — container runs in background until you stop it
5. Supports `POSTGRES_MCP_DB` env var to target a different database (default: `trading_journal`)
6. Supports `POSTGRES_MCP_CONTAINER` env var to override the container name

**Tools exposed by dbhub:**
- `execute_sql` — run arbitrary SQL queries
- `search_objects` — explore schemas, tables, columns, indexes

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
- Docker image: `bytebase/dbhub` (both servers)

---

## Setup on a New Machine

1. Copy `~/.config/postgres/default.toml` (machine-specific credentials)
2. Copy `/home/ericbell/.local/bin/postgres-mcp` and `postgres-mcp-grail`
3. `chmod 750 ~/.local/bin/postgres-mcp ~/.local/bin/postgres-mcp-grail`
4. Edit `~/.claude/settings.json` to add both `mcpServers` entries (see above)
5. Pull Docker image:
   ```bash
   docker pull bytebase/dbhub
   ```
6. Start both containers before launching Claude Code: `postgres-mcp && postgres-mcp-grail`
