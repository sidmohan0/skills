#!/usr/bin/env bash
set -euo pipefail

target_path="$PWD"

usage() {
  cat <<'USAGE'
Usage: editor_context.sh [--path PATH]

Read-only VS Code/Cursor context: running apps, front window title, inferred
active file/project, and git context for a project path.
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

md_cell() {
  printf '%s' "${1:-}" | tr '\n' ' ' | sed 's/|/\\|/g'
}

echo "# Editor Context"
echo
echo "- Target path for git context: $target_path"
echo

echo "## Running Editor Windows"
window_output="$(
osascript <<'APPLESCRIPT' 2>/dev/null || true
set appNames to {"Cursor", "Visual Studio Code", "Code", "Code - Insiders"}
set outputLines to {}
tell application "System Events"
	repeat with appName in appNames
		if exists application process (contents of appName) then
			set proc to application process (contents of appName)
			set winIndex to 0
			repeat with w in windows of proc
				set winIndex to winIndex + 1
				set winTitle to ""
				try
					set winTitle to name of w
				end try
				set end of outputLines to (contents of appName) & tab & winIndex & tab & winTitle
			end repeat
		end if
	end repeat
end tell
set text item delimiters of AppleScript to linefeed
return outputLines as text
APPLESCRIPT
)"

if [[ -z "$window_output" ]]; then
  echo "No Cursor or VS Code windows reported."
else
  echo '| App | Window | Title | Inferred Active File | Inferred Project |'
  echo '|---|---:|---|---|---|'
  printf '%s\n' "$window_output" | while IFS=$'\t' read -r app win title; do
    inferred="$(
      python3 - "$title" <<'PY'
import re, sys
title = sys.argv[1] if len(sys.argv) > 1 else ""
parts = re.split(r"\s+[-\u2014]\s+", title)
active = parts[0] if parts else ""
project = parts[-1] if len(parts) > 1 else ""
print(active + "\t" + project)
PY
    )"
    active_file="$(printf '%s' "$inferred" | cut -f1)"
    project="$(printf '%s' "$inferred" | cut -f2-)"
    printf '| %s | %s | %s | %s | %s |\n' "$(md_cell "$app")" "$(md_cell "$win")" "$(md_cell "$title")" "$(md_cell "$active_file")" "$(md_cell "$project")"
  done
fi

echo
echo "## Git Context"
if git -C "$target_path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  root="$(git -C "$target_path" rev-parse --show-toplevel 2>/dev/null || true)"
  branch="$(git -C "$target_path" branch --show-current 2>/dev/null || true)"
  echo "- Repo root: ${root:-unknown}"
  echo "- Branch: ${branch:-detached}"
  echo
  echo "### Diff Stat"
  diff_stat="$(git -C "$target_path" diff --stat 2>/dev/null || true)"
  if [[ -n "$diff_stat" ]]; then
    printf '```text\n%s\n```\n' "$diff_stat"
  else
    echo "No unstaged diff."
  fi
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
echo "## Cursor Position"
echo "unavailable: Cursor/VS Code do not expose cursor position to AppleScript. Use an editor extension or explicit user-provided location."

echo
echo "## Diagnostics"
echo "unavailable: diagnostics require an editor extension, language-server query, or project-specific command."

echo
echo "## Selection"
echo "unavailable here: use mac-context --selection when the user explicitly asks to capture selected text."
