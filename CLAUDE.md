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

**Every change — new feature, enhancement, or bug fix, no matter how small — requires a GitHub issue created first, before any implementation.**

- As soon as the work is understood well enough to describe (a bug is diagnosed, or a feature/change request is clear), create the GitHub issue documenting it.
- Then stop and wait for explicit approval ("go ahead", "fix it", etc.) before writing any code.
- Do not implement first and file the issue retroactively.

This ensures every change has a record — both the issue and its resolution — regardless of whether planning mode was used.

## Planning Mode

When in plan mode, plans must NOT include code. Present strategy, approach, trade-offs, and discussion only. Code should appear only during implementation.

