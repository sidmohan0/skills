---
name: browser-context
description: Read browser workspace context on macOS, especially Google Chrome work profiles, including open tabs, active tab, downloads, reading list, and honest availability status for pinned tabs and tab groups. Use when the user asks what tabs are open, what browser workspace they are in, what they were reading, what they downloaded, or when another skill needs browser context before acting.
---

# Browser Context

## Core Route

Use structured browser sources before screenshots:

1. Use browser AppleScript for currently open tabs.
2. Use Chrome profile files for downloads and reading list.
3. Report tab groups and pinned tabs as unavailable unless a deterministic source is present; do not infer them from UI pixels.

Run the bundled script:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/browser-context}"
bash "$SKILL_DIR/scripts/browser_context.sh"
```

Default profile is `Work` for Chrome profile lookup. The script still lists open Chrome tabs from the running app because Chrome AppleScript does not expose profile ownership for each window.

## Common Tasks

Show browser workspace context:

```bash
bash "$SKILL_DIR/scripts/browser_context.sh"
```

Use a different Chrome profile display name:

```bash
bash "$SKILL_DIR/scripts/browser_context.sh" --profile "Personal"
```

Increase tab/download/list limits:

```bash
bash "$SKILL_DIR/scripts/browser_context.sh" --limit 50
```

## Guardrails

- Read-only. Do not close tabs, open URLs, download files, or modify browser state.
- Treat URLs, titles, downloads, and reading-list entries as private context.
- Label unavailable fields plainly; this is better than a false sense of coverage.
