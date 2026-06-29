#!/usr/bin/env bash
set -euo pipefail

target_path="$PWD"
include_selection="false"
state_root=""

usage() {
  cat <<'USAGE'
Usage: editor_context.sh [--path PATH] [--state-root PATH] [--include-selection]

Read-only VS Code/Cursor context: running apps, front window title, inferred
active file/project, persisted editor hints, optional selected text, and git
context for a project path.
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
    --include-selection)
      include_selection="true"
      shift
      ;;
    --state-root)
      [[ $# -ge 2 ]] || { echo "Missing value for --state-root" >&2; exit 2; }
      state_root="$2"
      shift 2
      ;;
    --state-root=*)
      state_root="${1#--state-root=}"
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

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_osascript_file() {
  local timeout_seconds="$1"
  local script_file="$2"
  local output_file pid killer
  output_file="$(mktemp "${TMPDIR:-/tmp}/editor-osascript.XXXXXX")"
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

echo "# Editor Context"
echo
echo "- Target path for git context: $target_path"
echo

echo "## Running Editor Windows"
window_script="$(mktemp "${TMPDIR:-/tmp}/editor-windows.XXXXXX")"
cat > "$window_script" <<'APPLESCRIPT'
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
window_output="$(run_osascript_file 4 "$window_script")"
rm -f "$window_script"

if [[ -z "$window_output" ]]; then
  echo "No Cursor or VS Code windows reported."
else
  echo '| App | Window | Title | Inferred Active File | Inferred Project |'
  echo '|---|---:|---|---|---|'
  printf '%s\n' "$window_output" | python3 "$script_dir/editor_window_context.py"
fi

echo
echo "## Persisted Editor State"
if [[ -n "$state_root" ]]; then
  python3 "$script_dir/editor_state_context.py" "$target_path" "$state_root"
else
  python3 "$script_dir/editor_state_context.py" "$target_path"
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
ax_script="$(mktemp "${TMPDIR:-/tmp}/editor-ax.XXXXXX")"
cat > "$ax_script" <<'APPLESCRIPT'
set outputLines to {}
tell application "System Events"
	try
		set frontProc to first application process whose frontmost is true
		set end of outputLines to "app=" & (name of frontProc)
		set focusedElement to value of attribute "AXFocusedUIElement" of frontProc
		try
			set end of outputLines to "role=" & (value of attribute "AXRole" of focusedElement)
		end try
		try
			set end of outputLines to "selected_range=" & (value of attribute "AXSelectedTextRange" of focusedElement as text)
		end try
		try
			set end of outputLines to "insertion_line=" & (value of attribute "AXInsertionPointLineNumber" of focusedElement as text)
		end try
	on error errMsg
		set end of outputLines to "error=" & errMsg
	end try
end tell
set text item delimiters of AppleScript to linefeed
return outputLines as text
APPLESCRIPT
ax_output="$(run_osascript_file 4 "$ax_script")"
rm -f "$ax_script"
if printf '%s\n' "$ax_output" | grep -q '^selected_range='; then
  printf '%s\n' "$ax_output" | sed -n 's/^app=/- Focused app: /p; s/^role=/- Focused role: /p; s/^selected_range=/- Selected text range: /p; s/^insertion_line=/- Insertion line: /p'
else
  echo "unavailable: no focused editor text range exposed through Accessibility."
  printf '%s\n' "$ax_output" | sed -n 's/^app=/- Focused app: /p; s/^role=/- Focused role: /p; s/^error=/- Accessibility error: /p'
fi

echo
echo "## Diagnostics"
echo "### Persisted Diagnostics"
echo "See persisted editor hints above for any stored marker or diagnostic keys."
echo
echo "### Git Diff Check"
if git -C "$target_path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  diff_check="$(git -C "$target_path" diff --check 2>&1 || true)"
  if [[ -n "$diff_check" ]]; then
    printf '```text\n%s\n```\n' "$diff_check"
  else
    echo "No whitespace diagnostics from git diff --check."
  fi
else
  echo "Not inside a git worktree."
fi

echo
echo "## Selection"
if [[ "$include_selection" != "true" ]]; then
  echo "Not captured by default. Re-run with --include-selection to print AXSelectedText when the focused editor exposes it."
else
  selection_script="$(mktemp "${TMPDIR:-/tmp}/editor-selection.XXXXXX")"
  cat > "$selection_script" <<'APPLESCRIPT'
set outputLines to {}
tell application "System Events"
	try
		set frontProc to first application process whose frontmost is true
		set focusedElement to value of attribute "AXFocusedUIElement" of frontProc
		try
			set selectedText to value of attribute "AXSelectedText" of focusedElement
			set end of outputLines to "selected_text=" & selectedText
		on error
			set end of outputLines to "selected_text="
		end try
	on error errMsg
		set end of outputLines to "error=" & errMsg
	end try
end tell
set text item delimiters of AppleScript to linefeed
return outputLines as text
APPLESCRIPT
  selection_output="$(run_osascript_file 4 "$selection_script")"
  rm -f "$selection_script"
  selected_text="$(printf '%s\n' "$selection_output" | sed -n 's/^selected_text=//p')"
  if [[ -n "$selected_text" ]]; then
    printf '```text\n%s\n```\n' "$selected_text"
  else
    echo "No selected text exposed through Accessibility."
    printf '%s\n' "$selection_output" | sed -n 's/^error=/- Accessibility error: /p'
  fi
fi
