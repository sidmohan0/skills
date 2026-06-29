#!/usr/bin/env bash
set -euo pipefail

target_path="$PWD"
history_limit=15
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

run_osascript_file() {
  local timeout_seconds="$1"
  local script_file="$2"
  local output_file pid killer
  output_file="$(mktemp "${TMPDIR:-/tmp}/terminal-osascript.XXXXXX")"
  osascript "$script_file" > "$output_file" 2>/dev/null &
  pid="$!"
  (
    sleep "$timeout_seconds"
    kill "$pid" 2>/dev/null || true
  ) &
  killer="$!"
  wait "$pid" 2>/dev/null || true
  kill "$killer" 2>/dev/null || true
  cat "$output_file"
  rm -f "$output_file"
}

echo "# Terminal Context"
echo
echo "- Script cwd: $PWD"
echo "- Target path: $target_path"
echo "- Shell: ${SHELL:-unknown}"
echo "- Virtualenv: ${VIRTUAL_ENV:-none}"
echo "- Conda env: ${CONDA_DEFAULT_ENV:-none}"
echo

echo "## Terminal App Windows"
terminal_script="$(mktemp "${TMPDIR:-/tmp}/terminal-windows.XXXXXX")"
cat > "$terminal_script" <<'APPLESCRIPT'
set outputLines to {}
tell application "System Events"
	set terminalRunning to exists application process "Terminal"
	set itermRunning to exists application process "iTerm2"
end tell
if terminalRunning then
	tell application "Terminal"
		set windowIndex to 0
		repeat with w in windows
			set windowIndex to windowIndex + 1
			set tabIndex to 0
			repeat with t in tabs of w
				set tabIndex to tabIndex + 1
				set tabTitle to ""
				set tabTTY to ""
				try
					set tabTitle to custom title of t
				end try
				try
					set tabTTY to tty of t
				end try
				set end of outputLines to "Terminal" & tab & windowIndex & tab & tabIndex & tab & tabTTY & tab & tabTitle
			end repeat
		end repeat
	end tell
end if
if itermRunning then
	tell application "iTerm2"
		set windowIndex to 0
		repeat with w in windows
			set windowIndex to windowIndex + 1
			set tabIndex to 0
			repeat with t in tabs of w
				set tabIndex to tabIndex + 1
				set sessionIndex to 0
				repeat with s in sessions of t
					set sessionIndex to sessionIndex + 1
					set sessionName to ""
					set sessionTTY to ""
					try
						set sessionName to name of s
					end try
					try
						set sessionTTY to tty of s
					end try
					set end of outputLines to "iTerm2" & tab & windowIndex & tab & tabIndex & "." & sessionIndex & tab & sessionTTY & tab & sessionName
				end repeat
			end repeat
		end repeat
	end tell
end if
set text item delimiters of AppleScript to linefeed
return outputLines as text
APPLESCRIPT
terminal_windows="$(run_osascript_file 4 "$terminal_script")"
rm -f "$terminal_script"
if [[ -z "$terminal_windows" ]]; then
  echo "No Terminal or iTerm2 windows reported."
else
  echo '| App | Window | Tab/Session | TTY | Title |'
  echo '|---|---:|---:|---|---|'
  printf '%s\n' "$terminal_windows" | while IFS=$'\t' read -r app win tab tty title; do
    printf '| %s | %s | %s | %s | %s |\n' "$(md_cell "$app")" "$(md_cell "$win")" "$(md_cell "$tab")" "$(md_cell "$tty")" "$(md_cell "$title")"
  done
fi

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
echo '| PID | PPID | PGID | TTY | State | Elapsed | Command |'
echo '|---:|---:|---:|---|---|---:|---|'
ps -axo pid=,ppid=,pgid=,stat=,tty=,etime=,command= 2>/dev/null \
  | TERMINAL_CONTEXT_SCRIPT_PID="$$" python3 "$script_dir/terminal_process_context.py" --limit 30

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
