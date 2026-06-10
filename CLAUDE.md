# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Custom Commands

**`prime app`** — Read `CLAUDE.md` and `docs/OVERVIEW.md` to build full context on this application. OVERVIEW.md is the authoritative description of architecture, design decisions, feature inventory, and file map. Read individual source files on demand when a task requires it — use §11 of OVERVIEW.md to locate the right file.

## Version Management

Version is stored **only in `pyproject.toml`** under `[project] version`. Format is `x.y.z`:

- **x** — major: breaking changes or major releases
- **y** — minor: increment by 1 when one or more new features are delivered in a turn (even if multiple features are implemented together, only increment once)
- **z** — patch: increment by 1 when delivering bug fixes or non-feature changes

Claude must update `pyproject.toml` at the end of every turn where code changes were made.

## Issue Tracking

When the user reports a problem or bug and a diagnosis is reached, ask: **"Would you like me to create a GitHub issue for this before we fix it?"**

- If yes: create the issue, then wait for explicit approval ("go ahead", "fix it", etc.) before implementing anything.
- If no: proceed directly to the fix.

This ensures every diagnosed problem has a record — both the issue and its resolution — regardless of whether planning mode was used.

## Planning Mode

When in plan mode, plans must NOT include code. Present strategy, approach, trade-offs, and discussion only. Code should appear only during implementation.

