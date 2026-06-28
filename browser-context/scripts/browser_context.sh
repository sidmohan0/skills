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

profile_info="$(
python3 - "$chrome_base" "$profile_name" "$profile_dir_override" <<'PY'
import json, os, sys
base, wanted, override = sys.argv[1], sys.argv[2], sys.argv[3]
def emit(path="", dirname="", name="", match="unavailable"):
    print(path)
    print(dirname)
    print(name)
    print(match)
if override:
    path = os.path.abspath(os.path.expanduser(override))
    emit(path, os.path.basename(path), "", "override")
    raise SystemExit
local_state = os.path.join(base, "Local State")
try:
    data = json.load(open(local_state))
    profiles = data.get("profile", {}).get("info_cache", {})
    for dirname, info in profiles.items():
        display_name = info.get("name", "")
        if display_name == wanted or dirname == wanted:
            emit(os.path.join(base, dirname), dirname, display_name, "exact")
            raise SystemExit
    if len(profiles) == 1:
        dirname, info = next(iter(profiles.items()))
        emit(os.path.join(base, dirname), dirname, info.get("name", ""), "fallback-single-profile")
        raise SystemExit
    if "Default" in profiles:
        info = profiles["Default"]
        emit(os.path.join(base, "Default"), "Default", info.get("name", ""), "fallback-default")
        raise SystemExit
except Exception:
    pass
emit()
PY
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
echo "## Pinned Tabs"
if [[ -z "$profile_dir" || ! -d "$profile_dir/Sessions" ]]; then
  echo "Pinned tabs unavailable: Chrome profile session directory is not readable."
else
  python3 - "$profile_dir" "$limit" <<'PY'
import datetime as dt
import glob
import os
import struct
import sys

profile_dir, limit = sys.argv[1], int(sys.argv[2])

def esc(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")

def group_key(payload):
    if len(payload) < 25 or payload[24] == 0:
        return ""
    high = struct.unpack_from("<Q", payload, 8)[0]
    low = struct.unpack_from("<Q", payload, 16)[0]
    if high == 0 and low == 0:
        return ""
    return f"{high:016x}:{low:016x}"

def latest_session_file(root):
    files = glob.glob(os.path.join(root, "Sessions", "Session_*"))
    return max(files, key=os.path.getmtime) if files else ""

def iter_records(path):
    data = open(path, "rb").read()
    if len(data) < 8 or data[:4] != b"SNSS":
        return
    offset = 8
    while offset + 2 <= len(data):
        size = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        record = data[offset:offset + size]
        offset += size
        if record:
            yield record[0], record[1:]

path = latest_session_file(profile_dir)
if not path:
    print("Pinned tabs unavailable: no Chrome Session_* files found.")
    raise SystemExit

pinned = {}
groups = {}
for command_id, payload in iter_records(path):
    if command_id == 12 and len(payload) >= 5:
        tab_id = struct.unpack_from("<i", payload, 0)[0]
        pinned[tab_id] = payload[4] != 0
    elif command_id == 25 and len(payload) >= 25:
        tab_id = struct.unpack_from("<i", payload, 0)[0]
        key = group_key(payload)
        if key:
            groups[tab_id] = key
        else:
            groups.pop(tab_id, None)

modified = dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
print(f"- Source: `{esc(os.path.relpath(path, profile_dir))}`")
print(f"- Source modified: {modified}")
active = [tab_id for tab_id, value in pinned.items() if value]
if not active:
    print("No pinned tabs recorded in latest Chrome session metadata.")
else:
    print("| Tab ID | Group ID |")
    print("|---:|---|")
    for tab_id in active[:limit]:
        print(f"| {tab_id} | {esc(groups.get(tab_id, ''))} |")
PY
fi

echo
echo "## Tab Groups"
if [[ -z "$profile_dir" || ! -d "$profile_dir/Sessions" ]]; then
  echo "Tab groups unavailable: Chrome profile session directory is not readable."
else
  python3 - "$profile_dir" "$limit" <<'PY'
import datetime as dt
import glob
import os
import struct
import sys

profile_dir, limit = sys.argv[1], int(sys.argv[2])

def esc(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")

def group_key(payload):
    if len(payload) < 25 or payload[24] == 0:
        return ""
    high = struct.unpack_from("<Q", payload, 8)[0]
    low = struct.unpack_from("<Q", payload, 16)[0]
    if high == 0 and low == 0:
        return ""
    return f"{high:016x}:{low:016x}"

def align4(pos):
    return (pos + 3) & ~3

def read_group_metadata(payload):
    if len(payload) < 24:
        return None
    pos = 4
    high = struct.unpack_from("<Q", payload, pos)[0]
    pos += 8
    low = struct.unpack_from("<Q", payload, pos)[0]
    pos += 8
    key = f"{high:016x}:{low:016x}"
    if len(payload) < pos + 4:
        return key, "", "", "", ""
    title_len = struct.unpack_from("<i", payload, pos)[0]
    pos += 4
    title = ""
    if 0 <= title_len <= 4096 and len(payload) >= pos + title_len * 2:
        raw = payload[pos:pos + title_len * 2]
        title = raw.decode("utf-16-le", "replace")
        pos = align4(pos + title_len * 2)
    color = ""
    collapsed = ""
    saved_guid = ""
    if len(payload) >= pos + 4:
        color = str(struct.unpack_from("<I", payload, pos)[0])
        pos += 4
    if len(payload) >= pos + 4:
        collapsed = str(payload[pos] != 0).lower()
        pos += 4
    if len(payload) >= pos + 4:
        is_saved = payload[pos] != 0
        pos += 4
        if is_saved and len(payload) >= pos + 4:
            saved_len = struct.unpack_from("<i", payload, pos)[0]
            pos += 4
            if 0 <= saved_len <= 4096 and len(payload) >= pos + saved_len:
                saved_guid = payload[pos:pos + saved_len].decode("utf-8", "replace")
    return key, title, color, collapsed, saved_guid

def latest_session_file(root):
    files = glob.glob(os.path.join(root, "Sessions", "Session_*"))
    return max(files, key=os.path.getmtime) if files else ""

def iter_records(path):
    data = open(path, "rb").read()
    if len(data) < 8 or data[:4] != b"SNSS":
        return
    offset = 8
    while offset + 2 <= len(data):
        size = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        record = data[offset:offset + size]
        offset += size
        if record:
            yield record[0], record[1:]

path = latest_session_file(profile_dir)
if not path:
    print("Tab groups unavailable: no Chrome Session_* files found.")
    raise SystemExit

tab_groups = {}
metadata = {}
for command_id, payload in iter_records(path):
    if command_id == 25 and len(payload) >= 25:
        tab_id = struct.unpack_from("<i", payload, 0)[0]
        key = group_key(payload)
        if key:
            tab_groups[tab_id] = key
        else:
            tab_groups.pop(tab_id, None)
    elif command_id == 27:
        parsed = read_group_metadata(payload)
        if parsed:
            key, title, color, collapsed, saved_guid = parsed
            metadata[key] = {
                "title": title,
                "color": color,
                "collapsed": collapsed,
                "saved_guid": saved_guid,
            }

modified = dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
print(f"- Source: `{esc(os.path.relpath(path, profile_dir))}`")
print(f"- Source modified: {modified}")
groups_to_tabs = {}
for tab_id, key in tab_groups.items():
    groups_to_tabs.setdefault(key, []).append(tab_id)
if not groups_to_tabs:
    print("No tab groups recorded in latest Chrome session metadata.")
else:
    print("| Group ID | Tab IDs | Title | Color | Collapsed | Saved GUID |")
    print("|---|---|---|---:|---|---|")
    for key in sorted(groups_to_tabs, key=lambda item: (metadata.get(item, {}).get("title", ""), item))[:limit]:
        meta = metadata.get(key, {})
        tabs = ", ".join(str(tab_id) for tab_id in sorted(groups_to_tabs[key]))
        print(
            f"| {esc(key)} | {esc(tabs)} | {esc(meta.get('title', ''))} | "
            f"{esc(meta.get('color', ''))} | {esc(meta.get('collapsed', ''))} | "
            f"{esc(meta.get('saved_guid', ''))} |"
        )
PY
fi

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
