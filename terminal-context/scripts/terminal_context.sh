#!/usr/bin/env bash
set -euo pipefail

target_path="$PWD"
history_limit=15

usage() {
  cat <<'USAGE'
Usage: terminal_context.sh [--path PATH] [--history-limit N]

Read-only terminal/project context: pwd, git branch/status, recent commands,
running developer processes, virtualenv/conda, and tmux sessions.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --path)
      [[ $# -ge 2 ]] || { echo "Missing value for --path" >&2; exit 2; }
      target_path="$2"
      shift 2
      ;;
    --path=*)
      target_path="${1#--path=}"
      shift
      ;;
    --history-limit)
      [[ $# -ge 2 ]] || { echo "Missing value for --history-limit" >&2; exit 2; }
      history_limit="$2"
      shift 2
      ;;
    --history-limit=*)
      history_limit="${1#--history-limit=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "$history_limit" =~ ^[0-9]+$ ]] || { echo "--history-limit must be numeric" >&2; exit 2; }

md_cell() {
  printf '%s' "${1:-}" | tr '\n' ' ' | sed 's/|/\\|/g'
}

echo "# Terminal Context"
echo
echo "- Script cwd: $PWD"
echo "- Target path: $target_path"
echo "- Shell: ${SHELL:-unknown}"
echo "- Virtualenv: ${VIRTUAL_ENV:-none}"
echo "- Conda env: ${CONDA_DEFAULT_ENV:-none}"
echo

echo "## Git"
if git -C "$target_path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  repo_root="$(git -C "$target_path" rev-parse --show-toplevel 2>/dev/null || true)"
  branch="$(git -C "$target_path" branch --show-current 2>/dev/null || true)"
  head="$(git -C "$target_path" rev-parse --short HEAD 2>/dev/null || true)"
  echo "- Repo root: ${repo_root:-unknown}"
  echo "- Branch: ${branch:-detached}"
  echo "- HEAD: ${head:-unknown}"
  echo
  echo "### Status"
  status="$(git -C "$target_path" status --short 2>/dev/null || true)"
  if [[ -n "$status" ]]; then
    printf '```text\n%s\n```\n' "$status"
  else
    echo "Working tree clean."
  fi
else
  echo "Not inside a git worktree."
fi

echo
echo "## Recent Shell Commands"
histfile="${HISTFILE:-$HOME/.zsh_history}"
if [[ -r "$histfile" ]]; then
  tail -n $((history_limit * 3)) "$histfile" 2>/dev/null | sed -E 's/^: [0-9]+:[0-9]+;//' | tail -n "$history_limit" | nl -ba | sed 's/^/    /'
else
  echo "History unavailable: ${histfile} is not readable."
fi

echo
echo "## Running Developer Processes"
echo '| PID | State | Command |'
echo '|---:|---|---|'
ps -axo pid=,stat=,command= 2>/dev/null \
  | python3 -c '
import os, shlex, sys
names = {"npm", "pnpm", "yarn", "bun", "node", "python", "python3", "ruby", "cargo", "tmux", "ssh", "vite", "next"}
phrases = ("go run",)
self_pid = str(os.getpid())
for line in sys.stdin:
    parts = line.strip().split(None, 2)
    if len(parts) < 3:
        continue
    if parts[0] == self_pid:
        continue
    command = parts[2]
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    bases = {os.path.basename(token).lower().rstrip(":") for token in tokens if token}
    if bases & names or any(phrase in command.lower() for phrase in phrases):
        sys.stdout.write(line)
' \
  | head -n 30 \
  | while read -r pid stat command; do
      printf '| %s | %s | %s |\n' "$(md_cell "$pid")" "$(md_cell "$stat")" "$(md_cell "$command")"
    done

echo
echo "## tmux"
if command -v tmux >/dev/null 2>&1; then
  echo "- TMUX env: ${TMUX:-none}"
  sessions="$(tmux list-sessions 2>/dev/null || true)"
  if [[ -n "$sessions" ]]; then
    printf '```text\n%s\n```\n' "$sessions"
  else
    echo "No tmux sessions reported."
  fi
else
  echo "tmux is not installed or not on PATH."
fi
