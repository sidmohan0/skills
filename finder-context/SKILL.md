---
name: finder-context
description: Read Finder workspace context on macOS, including selected files, current Finder folder, recent nearby files, Finder tags, and file metadata. Use when the user asks what files they are working on, what is selected in Finder, what folder is open, which files are recent, or when another skill needs file context before acting.
---

# Finder Context

## Core Route

Use Finder and Spotlight metadata as the source of truth for local file context. Do not infer file context from screenshots when Finder can provide structured state.

Run the bundled script:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/finder-context}"
bash "$SKILL_DIR/scripts/finder_context.sh"
```

Default behavior prints a Markdown snapshot with:

- Current front Finder folder.
- Selected Finder items.
- File kind, size, modified date, last-used date, and Finder tags, rendered through `scripts/finder_item_context.py`.
- Recent files in the current Finder folder when Spotlight can provide them.

## Common Tasks

What files am I working on:

```bash
bash "$SKILL_DIR/scripts/finder_context.sh"
```

Limit recent files:

```bash
bash "$SKILL_DIR/scripts/finder_context.sh" --recent-limit 20
```

Focus on a specific folder when Finder is not the right source:

```bash
bash "$SKILL_DIR/scripts/finder_context.sh" --folder "$PWD"
```

## Guardrails

- Read-only. Do not move, rename, tag, delete, or open files from this skill.
- Treat paths and metadata as private context. Echo only what the task needs.
- If Finder or Spotlight is unavailable, report the missing source instead of guessing.
