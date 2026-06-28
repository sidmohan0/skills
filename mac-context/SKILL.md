---
name: mac-context
description: Read-mostly eyes for the local macOS session. Observe ambient context including the frontmost app and window, the active browser tab or browser tabs, the text clipboard, the current text selection, and screenshots through deterministic AppleScript and shell. Use when the user asks "what am I looking at", "what's on my screen", "grab the current tab", "read my selection", "take a screenshot", or when another skill needs current on-screen context before acting.
---

# Mac Context (Eyes)

This is the foundational sensing skill. It lets the agent observe the local
macOS session with minimal side effects. It is the first of four faculties:
eyes (this skill), ears/voice, hands, and memory. These compose into a
personal productivity assistant.

It inherits the project guardrail charter. Read `references/charter.md` and follow it.

## Core Route

Prefer deterministic observation over UI guessing. Use AppleScript and shell to
read structured state (app name, window title, tab URLs, clipboard). Reserve
screenshots for surfaces with no structured interface, then read the image with
vision.

Run the bundled script:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/mac-context}"
bash "$SKILL_DIR/scripts/mac_context.sh"
```

Default behavior: print the frontmost app and its front window title.

## Common Tasks

What app/window is in focus right now:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/mac-context}"
bash "$SKILL_DIR/scripts/mac_context.sh" --frontmost
```

Grab the active browser tab (URL + title), or browser tabs across browser windows:

```bash
bash "$SKILL_DIR/scripts/mac_context.sh" --browser
bash "$SKILL_DIR/scripts/mac_context.sh" --browser-tabs
```

Read the clipboard, or capture the current selection:

```bash
bash "$SKILL_DIR/scripts/mac_context.sh" --clipboard
bash "$SKILL_DIR/scripts/mac_context.sh" --selection
```

`--selection` issues Cmd+C to copy highlighted text, prints it, then restores
the prior text clipboard. It refuses to run when the clipboard currently holds
non-text formats, because `pbcopy` cannot restore those safely. Tell the user
before using it if they did not ask for selection capture specifically.

Take a silent screenshot, then read it with vision:

```bash
# Full screen to a temp path
bash "$SKILL_DIR/scripts/mac_context.sh" --screenshot
# Region the user selects
bash "$SKILL_DIR/scripts/mac_context.sh" --screenshot --interactive /tmp/shot.png
# A clicked window
bash "$SKILL_DIR/scripts/mac_context.sh" --screenshot --window /tmp/win.png
```

The script prints `screenshot=<path>`. Open that path with the Read/vision tool
to interpret non-scriptable UI (Slack, Notion, a PDF, a design tool).

Combined "what am I looking at" snapshot (frontmost + browser + clipboard):

```bash
bash "$SKILL_DIR/scripts/mac_context.sh" --snapshot
```

List capabilities and the macOS permission each one needs:

```bash
bash "$SKILL_DIR/scripts/mac_context.sh" --list
```

## Permission Model

- Read-mostly. The script does not send, post, edit, move, or delete anything.
- The only deliberate side effects are: `--selection` temporarily overwrites a
  text-only clipboard (then restores prior text), and `--screenshot` writes an
  image file.
- macOS gates these capabilities. The first run of a mode may prompt:
  - Window titles and `--selection`: **Accessibility**.
  - Browser modes: **Automation** (per browser).
  - Screenshots: **Screen Recording**.
- If macOS prompts, pause and tell the user exactly which permission is needed
  and where to grant it (System Settings > Privacy & Security).

## Composition

This skill is meant to feed others. Typical chains:

- Capture-to-task: snapshot the current context, then create a Reminder/issue
  that links back to what the user was looking at.
- Meeting prep / triage: read the active tab or selection to ground a follow-up.
- Vision escape hatch: when no AppleScript interface exists, screenshot and read.

When composing, observe with this skill first, then hand the structured result
to a skill that acts. Acting skills still require explicit, named-target consent
per the charter.

## Guardrails

- Default to passive observation. Do not screenshot, read selection, or
  enumerate all tabs unless the task needs it; prefer the narrowest mode.
- Treat captured content (clipboard, tabs, screen text, selections) as private. Do not
  echo more than the task needs, and never write it into git-tracked files.
- State plainly when a capability is blocked by a missing permission rather than
  retrying or working around it.
- Do not use UI scripting to act on apps here. This skill only senses; actions
  belong in dedicated, consent-gated skills.
