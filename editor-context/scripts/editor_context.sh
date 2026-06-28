#!/usr/bin/env bash
set -euo pipefail

target_path="$PWD"
include_selection="false"

usage() {
  cat <<'USAGE'
Usage: editor_context.sh [--path PATH] [--include-selection]

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
echo "## Persisted Editor State"
python3 - "$target_path" <<'PY'
import datetime as dt
import glob
import json
import os
import sqlite3
import sys
from urllib.parse import unquote, urlparse

target_path = os.path.abspath(os.path.expanduser(sys.argv[1]))
home = os.path.expanduser("~")
apps = [
    ("Cursor", os.path.join(home, "Library/Application Support/Cursor")),
    ("VS Code", os.path.join(home, "Library/Application Support/Code")),
    ("VS Code Insiders", os.path.join(home, "Library/Application Support/Code - Insiders")),
    ("VSCodium", os.path.join(home, "Library/Application Support/VSCodium")),
]

def esc(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")

def from_file_uri(value):
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return unquote(parsed.path)
    return value

def short_path(path):
    if path.startswith(home + os.sep):
        return "~/" + os.path.relpath(path, home)
    return path

rows = []
hints = []
for app_name, root in apps:
    if not os.path.isdir(root):
        continue
    storage = os.path.join(root, "User", "globalStorage", "storage.json")
    if os.path.exists(storage):
        try:
            data = json.load(open(storage))
        except Exception:
            data = {}
        for key, value in data.items():
            key_l = key.lower()
            if any(term in key_l for term in ("window", "workspace", "folder", "file", "recent", "lastactive")):
                hints.append((app_name, "globalStorage", key, str(value)[:400]))
    workspace_root = os.path.join(root, "User", "workspaceStorage")
    for workspace_dir in sorted(glob.glob(os.path.join(workspace_root, "*")), key=os.path.getmtime, reverse=True)[:12]:
        workspace_json = os.path.join(workspace_dir, "workspace.json")
        folder = ""
        workspace = ""
        if os.path.exists(workspace_json):
            try:
                data = json.load(open(workspace_json))
                folder = from_file_uri(data.get("folder", ""))
                workspace = from_file_uri(data.get("workspace", ""))
            except Exception:
                pass
        if folder or workspace:
            mtime = dt.datetime.fromtimestamp(os.path.getmtime(workspace_dir)).strftime("%Y-%m-%d %H:%M:%S")
            rows.append((app_name, short_path(folder), short_path(workspace), mtime, short_path(workspace_dir)))
        db = os.path.join(workspace_dir, "state.vscdb")
        if os.path.exists(db):
            try:
                con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                for key, value in con.execute("select key, value from ItemTable"):
                    key_l = str(key).lower()
                    value_s = str(value)
                    probe = key_l + " " + value_s[:1000].lower()
                    if any(term in probe for term in ("activeeditor", "active editor", "selected", "selection", "cursor", "position", "diagnostic", "marker", "editor.memento", "history")):
                        hints.append((app_name, os.path.basename(workspace_dir), str(key), value_s[:400]))
            except Exception:
                pass

if rows:
    print("| App | Folder | Workspace | Modified | State Path |")
    print("|---|---|---|---|---|")
    for row in rows:
        print("| " + " | ".join(esc(item) for item in row) + " |")
else:
    print("No Cursor/VS Code workspaceStorage entries found.")

print()
print("### Persisted Hints")
if hints:
    print("| App | Source | Key | Value Snippet |")
    print("|---|---|---|---|")
    for app_name, source, key, value in hints[:20]:
        print(f"| {esc(app_name)} | {esc(source)} | {esc(key)} | {esc(value)} |")
else:
    print("No persisted active-file, cursor, selection, or diagnostic hints found.")
PY

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
