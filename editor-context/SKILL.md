---
name: editor-context
description: Read VS Code and Cursor editor context on macOS, including running editor apps, front window title, inferred active file/project, persisted workspace/editor state, optional selected text, Accessibility cursor range, diagnostics hints, and git diff for a project path. Use when the user asks what file or project is open in Cursor or VS Code, what code they are working on, what editor context exists, what is selected, what diagnostics exist, or when another skill needs editor context before acting.
---

# Editor Context

## Core Route

Use deterministic editor/window metadata first. Prefer running editor windows, Cursor/VS Code persisted state, Accessibility focused-element metadata, and git context. Do not infer code state from screenshots unless the user asks for visual fallback.

Run the bundled script:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/editor-context}"
bash "$SKILL_DIR/scripts/editor_context.sh"
```

Default behavior reports running Cursor/VS Code windows, persisted editor hints, Accessibility cursor/range metadata, diagnostics hints, and git context for the current directory when available. Running-window title inference is handled by `scripts/editor_window_context.py`.

## Common Tasks

What editor project is open:

```bash
bash "$SKILL_DIR/scripts/editor_context.sh"
```

Use a specific project path for git diff/status:

```bash
bash "$SKILL_DIR/scripts/editor_context.sh" --path /path/to/project
```

Use an alternate Cursor/VS Code app-support root for deterministic tests or portable captures:

```bash
bash "$SKILL_DIR/scripts/editor_context.sh" --state-root /path/to/app-support-root
```

Include selected text when the focused editor exposes it through Accessibility:

```bash
bash "$SKILL_DIR/scripts/editor_context.sh" --include-selection
```

## Guardrails

- Read-only. Do not edit files, run formatters, save buffers, or apply code actions.
- Selection capture uses Accessibility only; it does not mutate the clipboard.
- Diagnostics are limited to persisted marker hints and `git diff --check` unless an editor extension or project-specific diagnostic command is added later.
- Persisted state parsing is handled by `scripts/editor_state_context.py` and can be tested with `--state-root`.
- Report cursor position, diagnostics, and selection as unavailable unless a deterministic editor source exists.
