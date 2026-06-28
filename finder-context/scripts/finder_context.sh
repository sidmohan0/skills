#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: finder_context.sh [--folder PATH] [--recent-limit N]

Read-only Finder context: selected files, front Finder folder, recent files,
Finder tags, and file metadata.
USAGE
}

folder_override=""
recent_limit=12

while [[ $# -gt 0 ]]; do
  case "$1" in
    --folder)
      [[ $# -ge 2 ]] || { echo "Missing value for --folder" >&2; exit 2; }
      folder_override="$2"
      shift 2
      ;;
    --folder=*)
      folder_override="${1#--folder=}"
      shift
      ;;
    --recent-limit)
      [[ $# -ge 2 ]] || { echo "Missing value for --recent-limit" >&2; exit 2; }
      recent_limit="$2"
      shift 2
      ;;
    --recent-limit=*)
      recent_limit="${1#--recent-limit=}"
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

[[ "$recent_limit" =~ ^[0-9]+$ ]] || { echo "--recent-limit must be numeric" >&2; exit 2; }

md_cell() {
  printf '%s' "${1:-}" | tr '\n' ' ' | sed 's/|/\\|/g'
}

md_raw() {
  local key="$1"
  local path="$2"
  mdls -raw -name "$key" "$path" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true
}

clean_mdls() {
  local value="${1:-}"
  case "$value" in
    ""|"(null)"|"null") printf '' ;;
    *) printf '%s' "$value" | sed 's/^(\(.*\))$/\1/' | sed 's/"//g' ;;
  esac
}

file_row() {
  local path="$1"
  local kind size modified last_used tags
  kind="$(clean_mdls "$(md_raw kMDItemKind "$path")")"
  [[ -n "$kind" ]] || kind="$(test -d "$path" && echo Folder || echo File)"
  size="$(stat -f "%z" "$path" 2>/dev/null || true)"
  modified="$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$path" 2>/dev/null || true)"
  last_used="$(clean_mdls "$(md_raw kMDItemLastUsedDate "$path")")"
  tags="$(clean_mdls "$(md_raw kMDItemUserTags "$path")")"
  printf '| `%s` | %s | %s | %s | %s | %s |\n' \
    "$(md_cell "$path")" "$(md_cell "$kind")" "$(md_cell "$size")" \
    "$(md_cell "$modified")" "$(md_cell "$last_used")" "$(md_cell "$tags")"
}

finder_output="$(
osascript <<'APPLESCRIPT' 2>/dev/null || true
set outputLines to {}
set selectedPaths to {}
set currentFolder to ""
tell application "System Events"
	set finderRunning to exists application process "Finder"
end tell
if finderRunning then
	tell application "Finder"
		try
			set currentFolder to POSIX path of ((target of front Finder window) as alias)
		on error
			set currentFolder to POSIX path of (path to desktop folder)
		end try
		try
			repeat with itemRef in selection
				set end of selectedPaths to POSIX path of (itemRef as alias)
			end repeat
		end try
	end tell
	set end of outputLines to "finder=running"
else
	set end of outputLines to "finder=not_running"
end if
set end of outputLines to "current_folder=" & currentFolder
repeat with selectedPath in selectedPaths
	set end of outputLines to "selected=" & (contents of selectedPath)
end repeat
set text item delimiters of AppleScript to linefeed
return outputLines as text
APPLESCRIPT
)"

finder_state="$(printf '%s\n' "$finder_output" | awk -F= '/^finder=/{print $2; exit}')"
current_folder="$(printf '%s\n' "$finder_output" | sed -n 's/^current_folder=//p' | head -n 1)"
if [[ -n "$folder_override" ]]; then
  current_folder="$folder_override"
fi

echo "# Finder Context"
echo
echo "- Finder: ${finder_state:-unknown}"
echo "- Current folder: ${current_folder:-unavailable}"
echo

echo "## Selected Files"
selected_tmp="$(mktemp "${TMPDIR:-/tmp}/finder-selected.XXXXXX")"
printf '%s\n' "$finder_output" | sed -n 's/^selected=//p' > "$selected_tmp"
if [[ ! -s "$selected_tmp" ]]; then
  echo "No selected Finder files reported."
else
  echo '| Path | Kind | Size | Modified | Last Used | Finder Tags |'
  echo '|---|---:|---:|---|---|---|'
  while IFS= read -r path; do
    [[ -e "$path" ]] && file_row "$path" || printf '| `%s` | missing |  |  |  |  |\n' "$(md_cell "$path")"
  done < "$selected_tmp"
fi
rm -f "$selected_tmp"

echo
echo "## Recent Files"
if [[ -z "$current_folder" || ! -d "$current_folder" ]]; then
  echo "Recent files unavailable: current folder is not available."
elif ! command -v mdfind >/dev/null 2>&1; then
  echo "Recent files unavailable: mdfind is not available."
else
  recent_tmp="$(mktemp "${TMPDIR:-/tmp}/finder-recent.XXXXXX")"
  mdfind -onlyin "$current_folder" 'kMDItemFSContentChangeDate >= $time.today(-14)' 2>/dev/null | head -n "$recent_limit" > "$recent_tmp" || true
  if [[ ! -s "$recent_tmp" ]]; then
    echo "No recent Spotlight results for this folder."
  else
    echo '| Path | Kind | Size | Modified | Last Used | Finder Tags |'
    echo '|---|---:|---:|---|---|---|'
    while IFS= read -r path; do
      [[ -e "$path" ]] && file_row "$path"
    done < "$recent_tmp"
  fi
  rm -f "$recent_tmp"
fi
