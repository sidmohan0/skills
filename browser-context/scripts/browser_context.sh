#!/usr/bin/env bash
set -euo pipefail

profile_name="Work"
limit=30

usage() {
  cat <<'USAGE'
Usage: browser_context.sh [--profile NAME] [--limit N]

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

profile_dir="$(
python3 - "$chrome_base" "$profile_name" <<'PY'
import json, os, sys
base, wanted = sys.argv[1], sys.argv[2]
local_state = os.path.join(base, "Local State")
fallback = ""
try:
    data = json.load(open(local_state))
    for dirname, info in data.get("profile", {}).get("info_cache", {}).items():
        if info.get("name") == wanted:
            print(os.path.join(base, dirname))
            raise SystemExit
        if dirname == wanted:
            fallback = os.path.join(base, dirname)
    if fallback:
        print(fallback)
except Exception:
    pass
PY
)"

echo "# Browser Context"
echo
echo "- Browser: Google Chrome"
echo "- Requested profile: ${profile_name}"
echo "- Profile directory: ${profile_dir:-unavailable}"
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
echo "## Pinned Tabs"
echo "unavailable: Chrome AppleScript does not expose pinned state. Use a Chrome extension, DevTools Protocol session, or session-file parser in a future version."

echo
echo "## Tab Groups"
echo "unavailable: Chrome AppleScript does not expose tab group membership. Use a Chrome extension, DevTools Protocol session, or session-file parser in a future version."

echo
echo "## Downloads"
if [[ -z "$profile_dir" || ! -r "$profile_dir/History" ]]; then
  echo "Downloads unavailable: Chrome profile History database is not readable."
else
  tmpdb="$(mktemp "${TMPDIR:-/tmp}/chrome-history.XXXXXX")"
  cp "$profile_dir/History" "$tmpdb" 2>/dev/null || true
  python3 - "$tmpdb" "$limit" <<'PY'
import datetime as dt, os, sqlite3, sys
db, limit = sys.argv[1], int(sys.argv[2])
print("| Started | Path | URL |")
print("|---|---|---|")
try:
    con = sqlite3.connect(db)
    rows = con.execute(
        "select start_time, coalesce(current_path, target_path, ''), tab_url "
        "from downloads order by start_time desc limit ?", (limit,)
    ).fetchall()
    for start, path, url in rows:
        if start:
            when = dt.datetime(1601, 1, 1) + dt.timedelta(microseconds=start)
            when_s = when.strftime("%Y-%m-%d %H:%M:%S")
        else:
            when_s = ""
        esc = lambda s: str(s or "").replace("|", "\\|").replace("\n", " ")
        print(f"| {esc(when_s)} | `{esc(path)}` | {esc(url)} |")
except Exception as exc:
    print(f"Downloads unavailable: {exc}")
finally:
    try:
        os.remove(db)
    except OSError:
        pass
PY
fi

echo
echo "## Reading List"
if [[ -z "$profile_dir" || ! -r "$profile_dir/Bookmarks" ]]; then
  echo "Reading list unavailable: Chrome profile Bookmarks file is not readable."
else
  python3 - "$profile_dir/Bookmarks" "$limit" <<'PY'
import json, sys
path, limit = sys.argv[1], int(sys.argv[2])
def walk(node):
    if isinstance(node, dict):
        if node.get("type") == "url":
            yield node
        for child in node.get("children", []):
            yield from walk(child)
    elif isinstance(node, list):
        for child in node:
            yield from walk(child)
try:
    data = json.load(open(path))
    roots = data.get("roots", {})
    candidates = []
    for key in ("reading_list", "synced"):
        if key in roots:
            candidates.extend(walk(roots[key]))
    print("| Title | URL |")
    print("|---|---|")
    count = 0
    for item in candidates:
        title = (item.get("name") or "").replace("|", "\\|").replace("\n", " ")
        url = (item.get("url") or "").replace("|", "\\|").replace("\n", " ")
        print(f"| {title} | {url} |")
        count += 1
        if count >= limit:
            break
    if count == 0:
        print("No reading-list entries found in readable bookmark roots.")
except Exception as exc:
    print(f"Reading list unavailable: {exc}")
PY
fi
