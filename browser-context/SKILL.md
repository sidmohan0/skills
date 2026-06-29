---
name: browser-context
description: Read browser workspace context on macOS, especially Google Chrome work profiles, including live open tabs, profile session tabs with titles and URLs, active tab, downloads, reading list, pinned tabs, and tab groups. Use when the user asks what tabs are open, what browser workspace they are in, what they were reading, what they downloaded, what is pinned or grouped in Chrome, or when another skill needs browser context before acting.
---

# Browser Context

## Core Route

Use structured browser sources before screenshots:

1. Use browser AppleScript for currently open tabs.
2. Use Chrome `Sessions/Session_*` files for profile session tabs, pinned tabs, tab groups, selected navigation titles, and URLs when readable.
3. Use Chrome profile files for downloads and reading list.

Run the bundled script:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/browser-context}"
bash "$SKILL_DIR/scripts/browser_context.sh"
```

Default profile is `Work` for Chrome profile lookup. If that profile is not present, the script reports the fallback it used. The script still lists open Chrome tabs from the running app because Chrome AppleScript does not expose profile ownership for each window.

## Common Tasks

Show browser workspace context:

```bash
bash "$SKILL_DIR/scripts/browser_context.sh"
```

Use a different Chrome profile display name:

```bash
bash "$SKILL_DIR/scripts/browser_context.sh" --profile "Personal"
```

Use an exact Chrome profile directory:

```bash
bash "$SKILL_DIR/scripts/browser_context.sh" --profile-dir "$HOME/Library/Application Support/Google/Chrome/Default"
```

Increase tab/download/list limits:

```bash
bash "$SKILL_DIR/scripts/browser_context.sh" --limit 50
```

## Guardrails

- Read-only. Do not close tabs, open URLs, download files, or modify browser state.
- Treat URLs, titles, downloads, and reading-list entries as private context.
- Session-derived sections map tab IDs/group IDs to titles and URLs when Chrome navigation entries are present.
- Label unavailable fields plainly; this is better than a false sense of coverage.
