---
name: terminal-context
description: Read terminal and shell project context, including current directory, git branch and status, recent shell commands, Terminal/iTerm window TTYs, likely running developer jobs with PID/PPID/PGID/TTY, active virtualenv or conda environment, and tmux sessions. Use when the user asks what they are coding, what terminal project is active, what commands were run, what jobs are running, or when another skill needs coding context before acting.
---

# Terminal Context

## Core Route

Use shell, git, process, Terminal/iTerm, history, and tmux state as the source of truth. This skill is read-only and should not start, stop, or attach to jobs.

Run the bundled script:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/terminal-context}"
bash "$SKILL_DIR/scripts/terminal_context.sh"
```

Default behavior reports context for the process current directory, Terminal/iTerm windows when visible to AppleScript, and likely developer jobs grouped by PID/PPID/PGID/TTY.

## Common Tasks

What am I coding:

```bash
bash "$SKILL_DIR/scripts/terminal_context.sh"
```

Inspect another project path:

```bash
bash "$SKILL_DIR/scripts/terminal_context.sh" --path /path/to/project
```

Show more recent shell commands:

```bash
bash "$SKILL_DIR/scripts/terminal_context.sh" --history-limit 30
```

## Guardrails

- Read-only. Do not kill processes, attach tmux sessions, run package scripts, or mutate git state.
- Shell history and process lists can contain private tokens or paths. Quote only what the task needs.
- A non-interactive script cannot read live shell builtins like `jobs` from another terminal; report Terminal/iTerm TTYs, process groups, process candidates, and tmux state instead.
