# PostgreSQL MCP Servers — Setup & Troubleshooting

## Current State (as of 2026-03-28)

Two postgres MCP servers are configured and working. Both use the same wrapper
script (`/home/ericbell/.local/bin/postgres-mcp`) but point to different
databases via environment variables.

### MCP Server Config (`~/.claude/settings.json`)

```json
"mcpServers": {
  "postgres": {
    "command": "/home/ericbell/.local/bin/postgres-mcp",
    "args": [],
    "env": {}
  },
  "postgres_grail": {
    "command": "/home/ericbell/.local/bin/postgres-mcp-grail",
    "args": [],
    "env": {}
  }
}
```

**Note:** Each server uses a dedicated wrapper script. Claude Code does NOT pass
`env` vars from `mcpServers` config to the subprocess (confirmed 2026-03-28).
The grail-specific DB name and container name are hardcoded in `postgres-mcp-grail`.

- `postgres` → `trading_journal` database, Docker container `postgres-mcp`
- `postgres_grail` → `grail_files` database, Docker container `postgres-mcp-grail`

The total MCP server count in Claude Code's /mcp dialog should be **4**:
postgres, postgres_grail, telegram, skill-creator.

---

## How the Wrapper Works

`/home/ericbell/.local/bin/postgres-mcp`:

1. Reads credentials from `~/.config/postgres/default.toml` (never hardcoded)
2. Reads `POSTGRES_MCP_DB` env var (default: `trading_journal`)
3. Reads `POSTGRES_MCP_CONTAINER` env var (default: `postgres-mcp`)
4. **If stdin is a terminal** (interactive run): prints config info and exits —
   does NOT touch any running container
5. If stdin is a pipe (invoked by Claude Code): runs `docker rm -f <name>` to
   clear any stale container, then `exec docker run -i --rm --name <name>`

The `exec docker run -i` keeps the process alive; Claude Code communicates with
the MCP server over stdin/stdout of that process.

---

## Root Cause: Claude Code Does Not Pass `env` Vars to MCP Subprocesses

**Confirmed 2026-03-28.** The `env` block in `mcpServers` config is silently ignored —
subprocesses receive no extra environment variables from it.

**Evidence:** Added debug logging to wrapper; after Claude Code restart both invocations
showed `DB=<unset> CONTAINER=<unset>`, causing both servers to default to the same
`trading_journal`/`postgres-mcp` container name. The second `docker run --name postgres-mcp`
failed silently, so `postgres_grail` never connected.

**Fix applied 2026-03-28:** Created `/home/ericbell/.local/bin/postgres-mcp-grail` — a
dedicated wrapper with `DB=grail_files` and `CONTAINER=postgres-mcp-grail` hardcoded.
Updated `~/.claude/settings.json` to point `postgres_grail` at this new script.

---

## Known Issue: Orphaned Containers

**Symptom:** `/mcp` dialog shows only 1 postgres server instead of 2.

**Root cause:** The `postgres_grail` MCP server's `docker run` client process
died (for unknown reasons — possibly a startup race condition), but the Docker
container kept running because `--rm` only removes the container when the
*container itself* exits, not when the client disconnects.

**Evidence:**
- `docker ps` shows both `postgres-mcp` and `postgres-mcp-grail` containers
- `ps aux | grep "docker run"` shows NO ericbell-owned `docker run` for
  `postgres-mcp-grail`
- `mcp__postgres_grail__*` tools never appear in Claude's tool list

**Fix:** Restart Claude Code. Before restarting, clear orphaned containers:
```bash
docker rm -f postgres-mcp postgres-mcp-grail
```
Then reopen Claude Code — both MCP servers will reinitialize cleanly.

---

## Known Issue: Test Commands Kill Live MCP Containers

**Symptom:** `mcp__postgres__*` tools disconnect mid-session.

**Root cause (now fixed):** Running `postgres-mcp` from a terminal (e.g. to
test it) used to run `docker rm -f postgres-mcp`, killing the live container
that Claude Code was using for its MCP connection. This triggered
mid-conversation tool disconnection.

**Fix applied 2026-03-28:** The wrapper script now checks `[ -t 0 ]`. If stdin
is a terminal, it prints config info and exits without touching any container.

---

## Verifying Both Servers Are Connected

At the start of a Claude Code session, the deferred tools list should include
both `mcp__postgres__*` AND `mcp__postgres_grail__*` tool families. If only
`mcp__postgres__*` is present, `postgres_grail` failed to connect.

Quick checks:
```bash
# Both containers should be running
docker ps | grep postgres-mcp

# Two ericbell-owned docker run processes should exist (one per server)
ps aux | grep "docker run" | grep -v grep
```

---

## Supporting Files

- Wrapper scripts: `/home/ericbell/.local/bin/postgres-mcp` and `postgres-mcp-grail`
- DB credentials: `~/.config/postgres/default.toml`
- MCP server config: `~/.claude/settings.json` → `mcpServers`
- Docker image: `crystaldba/postgres-mcp` (must be locally pulled)

---

## Setup on a New Machine

1. Copy `~/.config/postgres/default.toml` (machine-specific credentials)
2. Copy `/home/ericbell/.local/bin/postgres-mcp` and `/home/ericbell/.local/bin/postgres-mcp-grail`
3. `chmod 750 ~/.local/bin/postgres-mcp ~/.local/bin/postgres-mcp-grail`
4. Edit `~/.claude/settings.json` to add both `mcpServers` entries (see above)
5. Pull the Docker image: `docker pull crystaldba/postgres-mcp`
