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
                   