#!/usr/bin/env bash
set -euo pipefail

profile_name="Work"
profile_dir_override=""
limit=30

usage() {
  cat <<'USAGE'
Usage: browser_context.sh [--profile NAME] [--profile-dir PATH] [--limit N]

Read-only browser workspace context for Google Chrome on macOS.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      [[ $# -ge 2 ]] || { echo "Missing value for --profile" >&2; exit 2; }
      profile_name="$2"
      shift 2
      ;;
    --profile=*)
      profile_name="${1#--profile=}"
      shift
      ;;
    --profile-dir)
      [[ $# -ge 2 ]] || { echo "Missing value for --profile-dir" >&2; exit 2; }
      profile_dir_override="$2"
      shift 2
      ;;
    --profile-dir=*)
      profile_dir_override="${1#--profile-dir=}"
      shift
      ;;
    --limit)
      [[ $# -ge 2 ]] || { echo "Missing value for --limit" >&2; exit 2; }
      limit="$2"
      shift 2
      ;;
    --limit=*)
      limit="${1#--limit=}"
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

[[ "$limit" =~ ^[0-9]+$ ]] || { echo "--limit must be numeric" >&2; exit 2; }

md_cell() {
  printf '%s' "${1:-}" | tr '\n' ' ' | sed 's/|/\\|/g'
}

chrome_base="${HOME}/Library/Application Support/Google/Chrome"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

profile_info="$(
python3 "$script_dir/chrome_profile_context.py" profile "$chrome_base" "$profile_name" "$profile_dir_override"
)"
profile_dir="$(printf '%s\n' "$profile_info" | sed -n '1p')"
profile_dir_name="$(printf '%s\n' "$profile_info" | sed -n '2p')"
profile_display_name="$(printf '%s\n' "$profile_info" | sed -n '3p')"
profile_match="$(printf '%s\n' "$profile_info" | sed -n '4p')"

echo "# Browser Context"
echo
echo "- Browser: Google Chrome"
echo "- Requested profile: ${profile_name}"
echo "- Resolved profile directory: ${profile_dir:-unavailable}"
echo "- Resolved profile name: ${profile_display_name:-unknown}"
echo "- Profile match: ${profile_match:-unavailable}"
echo

echo "## Open Tabs"
tabs_output="$(
osascript <<'APPLESCRIPT' 2>/dev/null || true
tell application "System Events"
	set chromeRunning to exists application process "Google Chrome"
end tell
if not chromeRunning then return "chrome=not_running"
set outputLines to {"chrome=running"}
tell application "Google Chrome"
	set windowIndex to 0
	repeat with w in windows
		set windowIndex to windowIndex + 1
		set activeIndex to active tab index of w
		set tabIndex to 0
		repeat with t in tabs of w
			set tabIndex to tabIndex + 1
			set activeText to "false"
			if tabIndex is activeIndex then set activeText to "true"
			set end of outputLines to "tab" & tab & windowIndex & tab & tabIndex & tab & activeText & tab & (title of t) & tab & (URL of t)
		end repeat
	end repeat
end tell
set text item delimiters of AppleScript to linefeed
return outputLines as text
APPLESCRIPT
)"

chrome_state="$(printf '%s\n' "$tabs_output" | awk -F= '/^chrome=/{print $2; exit}')"
if [[ "$chrome_state" != "running" ]]; then
  echo "Chrome is not running or is not scriptable."
else
  echo '| Window | Tab | Active | Title | URL |'
  echo '|---:|---:|---|---|---|'
  printf '%s\n' "$tabs_output" | awk -F'\t' '/^tab\t/ {print $2 "\t" $3 "\t" $4 "\t" $5 "\t" $6}' | head -n "$limit" | while IFS=$'\t' read -r win tab active title url; do
    printf '| %s | %s | %s | %s | %s |\n' "$(md_cell "$win")" "$(md_cell "$tab")" "$(md_cell "$active")" "$(md_cell "$title")" "$(md_cell "$url")"
  done
fi

echo
if [[ -z "$profile_dir" || ! -d "$profile_dir/Sessions" ]]; then
  echo "## Pinned Tabs"
  echo "Pinned tabs unavailable: Chrome profile session directory is not readable."
  echo
  echo "## Tab Groups"
  echo "Tab groups unavailable: Chrome profile session directory is not readable."
else
  python3 "$script_dir/chrome_session_context.py" "$profile_dir" "$limit"
fi

echo
echo "## Downloads"
if [[ -z "$profile_dir" || ! -r "$profile_dir/History" ]]; then
  echo "Downloads unavailable: Chrome profile History database is not readable."
else
  tmpdb="$(mktemp "${TMPDIR:-/tmp}/chrome-history.XXXXXX")"
  cp "$profile_dir/History" "$tmpdb" 2>/dev/null || true
  python3 "$script_dir/chrome_profile_context.py" downloads "$tmpdb" "$limit"
  rm -f "$tmpdb"
fi

echo
echo "## Reading List"
if [[ -z "$profile_dir" || ! -r "$profile_dir/Bookmarks" ]]; then
  echo "Reading list unavailable: Chrome profile Bookmarks file is not readable."
else
  python3 "$script_dir/chrome_profile_context.py" reading-list "$profile_dir/Bookmarks" "$limit"
fi
