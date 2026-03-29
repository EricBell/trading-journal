The live .claude.json doesn't exist─right─now─—─Claude─Code─manages─it─and─backs─it─up─each───
  session. The cleanest path is to update the MCP entry via the /mcp dialog in Claude Code      
  rather than editing a backup.                                                                 
                                                                                                
  Here's what to configure when you open /mcp → edit the postgres server:                       
                                                                                                
  - Command: /home/ericbell/.local/bin/postgres-mcp                                             
  - Args: (empty)                                                                             
  - Env: (empty)                                                                                
                                                                                                
  That replaces the current docker run ... DATABASE_URI=postgresql://postgres:f96CW7u!... entry 
  with the wrapper script.                                                                    
                                                                                                
  ---                                                                                         
  For the other workstation, the setup is:
                                                                                                
  1. Copy ~/.config/postgres/default.toml (with that machine's credentials)
  2. Copy /home/ericbell/.local/bin/postgres-mcp (the script is identical — no machine-specific 
  values)                                                                                       
  3. chmod 750 ~/.local/bin/postgres-mcp                                                        
  4. In Claude Code's /mcp, add a new postgres server with command ~/.local/bin/postgres-mcp, no
   args, no env                                                                                 
                                                                                                
  The script auto-reads from default.toml so each machine just needs its own toml with the right
   credentials.                                                                               
                   
##default.toml

[server]
host = "192.168..."
port = 32...
user = "post..."
password = "f96CW..."

[metadata]
created_at = "2025-12-12T19:42:09.502900"
description = "Main PostgreSQL server"

##postgres-mcp

#!/bin/bash
# Wrapper for crystaldba/postgres-mcp that reads credentials from
# ~/.config/postgres/default.toml so the password is never stored in
# ~/.claude/.claude.json.
#
# Override the target database with:
#   POSTGRES_MCP_DB=trading_journal_dev postgres-mcp
set -euo pipefail

read -r HOST PORT USER PW <<< "$(python3 - <<'EOF'
import tomllib, os
path = os.path.expanduser("~/.config/postgres/default.toml")
with open(path, "rb") as f:
    d = tomllib.load(f)
s = d["server"]
print(s["host"], s["port"], s["user"], s["password"])
EOF
)"

DB="${POSTGRES_MCP_DB:-trading_journal}"
URI="postgresql://${USER}:${PW}@${HOST}:${PORT}/${DB}"

exec docker run -i --rm \
    -e "DATABASE_URI=${URI}" \
    crystaldba/postgres-mcp \
    --access-mode=restricted

## new postgres mcp.md 

#!/bin/bash
# Wrapper for crystaldba/postgres-mcp that reads credentials from
# ~/.config/postgres/default.toml so the password is never stored in
# ~/.claude/.claude.json.
#
# Uses a fixed container name so only one instance ever runs at a time.
# Any stale container from a prior session is removed before starting.
#
# Override the target database with:
#   POSTGRES_MCP_DB=trading_journal_dev postgres-mcp
set -euo pipefail

read -r HOST PORT USER PW <<< "$(python3 - <<'EOF'
import tomllib, os
path = os.path.expanduser("~/.config/postgres/default.toml")
with open(path, "rb") as f:
    d = tomllib.load(f)
s = d["server"]
print(s["host"], s["port"], s["user"], s["password"])
EOF
)"

DB="${POSTGRES_MCP_DB:-trading_journal}"
URI="postgresql://${USER}:${PW}@${HOST}:${PORT}/${DB}"
CONTAINER_NAME="postgres-mcp"

# Remove any stale container from a previous session
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

exec docker run -i --rm --name "$CONTAINER_NAME" \
    -e "DATABASE_URI=${URI}" \
    crystaldba/postgres-mcp \
    --access-mode=restricted
