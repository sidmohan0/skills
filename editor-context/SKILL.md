---
name: editor-context
description: Read VS Code and Cursor editor context on macOS, including running editor apps, front window title, inferred active file/project, optional git diff for a project path, and honest availability status for cursor position, diagnostics, and selection. Use when the user asks what file or project is open in Cursor or VS Code, what code they are working on, what editor context exists, or when another skill needs editor context before acting.
---

# Editor Context

## Core Route

Use deterministic editor/window metadata first. Cursor position, diagnostics, and precise selection require an editor extension or explicit user-provided path/selection; do not infer them from screenshots unless the user asks for visual fallback.

Run the bundled script:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/editor-context}"
bash "$SKILL_DIR/scripts/editor_context.sh"
```

Default behavior reports running Cursor/VS Code windows and git context for the current directory when available.

## Common Tasks

What editor project is open:

```bash
bash "$SKILL_DIR/scripts/editor_context.sh"
```

Use a specific project path for git diff/status:

```bash
bash "$SKILL_DIR/scripts/editor_context.sh" --path /path/to/project
```

## Guardrails

- Read-only. Do not edit files, run formatters, save buffers, or apply code actions.
- Report cursor position, diagnostics, and selection as unavailable unless a deterministic editor source exists.
- If the user needs selected editor text, compose with `mac-context --selection`.
