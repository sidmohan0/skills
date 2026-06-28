#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: mac_context.sh [mode] [options]

Read-only "eyes" for the local macOS session. Observes ambient context
through deterministic AppleScript and shell. Does not act on apps or send
keystrokes unless a mode explicitly says so.

Modes:
  --frontmost            Frontmost app name and front window title. (default)
  --browser              Active tab URL + title of the frontmost/running browser.
  --browser-tabs         All tab URLs + titles across windows of a browser.
  --clipboard            Print the current text clipboard (pbpaste).
  --selection            Copy the current text selection and print it.
                         NOTE: sends Cmd+C and temporarily overwrites text clipboard.
  --screenshot [PATH]    Capture the screen silently to PATH (PNG).
  --snapshot             Combined read-only context: frontmost + browser + clipboard.
  --list                 Describe capabilities and required macOS permissions.

Screenshot options:
  --interactive          Let the user select a region (screencapture -i).
  --window               Capture a clicked window (screencapture -w).
                         Screenshot PATH may come before or after these options.

General:
  -h, --help             Show this help.

Permissions: window titles and selection use Accessibility; browser modes use
Automation; screenshots use Screen Recording. The script never sends, posts,
edits, or deletes anything. The only side effects are --selection's text
clipboard overwrite and --screenshot's image file, both explicit.
USAGE
}

mode="frontmost"
shot_path=""
shot_flag="-x"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --frontmost) mode="frontmost"; shift ;;
    --browser) mode="browser"; shift ;;
    --browser-tabs) mode="browser-tabs"; shift ;;
    --clipboard) mode="clipboard"; shift ;;
    --selection) mode="selection"; shift ;;
    --snapshot) mode="snapshot"; shift ;;
    --list) mode="list"; shift ;;
    --screenshot)
      mode="screenshot"
      shift
      if [[ $# -ge 1 && "$1" != --* ]]; then
        shot_path="$1"
        shift
      fi
      ;;
    --interactive) shot_flag="-i"; shift ;;
    --window) shot_flag="-w"; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      if [[ "$mode" == "screenshot" && "$1" != --* && -z "$shot_path" ]]; then
        shot_path="$1"
        shift
      else
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
done

frontmost_app() {
  osascript <<'APPLESCRIPT'
tell application "System Events"
	set procName to name of first application process whose frontmost is true
end tell
return procName
APPLESCRIPT
}

print_frontmost() {
  osascript <<'APPLESCRIPT'
tell application "System Events"
	set proc to first application process whose frontmost is true
	set procName to name of proc
	set winTitle to ""
	try
		set winTitle to name of front window of proc
	end try
end tell
return "app=" & procName & linefeed & "window=" & winTitle
APPLESCRIPT
}

# Reads the active tab (or all tabs) of a known browser.
# $1 = "active" | "all"
print_browser() {
  local scope="$1"
  local front
  front="$(frontmost_app || true)"

  osascript - "$scope" "$front" <<'APPLESCRIPT'
on run argv
	set scopeMode to item 1 of argv
	set frontApp to item 2 of argv

	set chromeNames to {"Google Chrome", "Google Chrome Canary", "Brave Browser", "Microsoft Edge", "Arc", "Vivaldi"}
	set safariNames to {"Safari", "Safari Technology Preview"}

	set targetApp to ""
	-- Prefer the frontmost app if it is a browser, else the first running one.
	if frontApp is in chromeNames or frontApp is in safariNames then
		set targetApp to frontApp
	else
		tell application "System Events"
			repeat with candidate in (chromeNames & safariNames)
				if (exists application process (contents of candidate)) then
					set targetApp to (contents of candidate)
					exit repeat
				end if
			end repeat
		end tell
	end if

	if targetApp is "" then return "browser=none_running"

	set out to {"browser=" & targetApp}
	if targetApp is in safariNames then
		tell application targetApp
			if scopeMode is "active" then
				set end of out to "url=" & (URL of current tab of front window)
				set end of out to "title=" & (name of current tab of front window)
			else
				set i to 0
				repeat with w in windows
					repeat with t in (tabs of w)
						set i to i + 1
						set end of out to "tab" & i & "_url=" & (URL of t)
						set end of out to "tab" & i & "_title=" & (name of t)
					end repeat
				end repeat
			end if
		end tell
	else
		tell application targetApp
			if scopeMode is "active" then
				set end of out to "url=" & (URL of active tab of front window)
				set end of out to "title=" & (title of active tab of front window)
			else
				set i to 0
				repeat with w in windows
					repeat with t in (tabs of w)
						set i to i + 1
						set end of out to "tab" & i & "_url=" & (URL of t)
						set end of out to "tab" & i & "_title=" & (title of t)
					end repeat
				end repeat
			end if
		end tell
	end if

	set AppleScript's text item delimiters to linefeed
	return out as text
end run
APPLESCRIPT
}

print_selection() {
  # Save text clipboard, copy selection, read it, restore text clipboard.
  # Refuse non-text clipboards rather than silently destroying richer pasteboard data.
  local info
  info="$(osascript -e 'clipboard info' 2>/dev/null || true)"
  local ascii_info
  ascii_info="$(printf '%s' "$info" | LC_ALL=C tr -cd '\11\12\15\40-\176')"
  local non_text
  non_text="$(printf '%s' "$ascii_info" | sed -E 's/class utf8|class ut16|string|Unicode text|text|[0-9]|,|[[:space:]]//g')"
  if [[ -n "$non_text" ]]; then
    echo "selection=unavailable" >&2
    echo "reason=clipboard_contains_non_text_formats" >&2
    echo "Refusing --selection because restoring this clipboard with pbcopy would drop non-text data." >&2
    return 3
  fi

  local saved
  saved="$(pbpaste 2>/dev/null || true)"
  local sentinel
  sentinel="__MAC_CONTEXT_SELECTION_SENTINEL_$$_$(date +%s%N)__"
  printf '%s' "$sentinel" | pbcopy 2>/dev/null || true
  osascript <<'APPLESCRIPT' >/dev/null
tell application "System Events" to keystroke "c" using {command down}
delay 0.15
APPLESCRIPT
  local selection
  selection="$(pbpaste 2>/dev/null || true)"
  printf '%s' "$saved" | pbcopy 2>/dev/null || true
  if [[ "$selection" == "$sentinel" ]]; then
    echo "selection=unavailable" >&2
    echo "reason=clipboard_did_not_change_after_copy" >&2
    return 1
  fi
  printf 'selection<<EOF\n%s\nEOF\n' "$selection"
}

case "$mode" in
  frontmost)
    print_frontmost
    ;;
  browser)
    print_browser active
    ;;
  browser-tabs)
    print_browser all
    ;;
  clipboard)
    printf 'clipboard<<EOF\n%s\nEOF\n' "$(pbpaste 2>/dev/null || true)"
    ;;
  selection)
    print_selection
    ;;
  screenshot)
    if [[ -z "$shot_path" ]]; then
      dir="${TMPDIR:-/tmp}"
      shot_path="${dir%/}/mac-context-$(date +%Y%m%d-%H%M%S).png"
    fi
    screencapture "$shot_flag" "$shot_path"
    echo "screenshot=$shot_path"
    ;;
  snapshot)
    echo "# Mac Context Snapshot"
    echo
    echo "## Frontmost"
    print_frontmost || echo "frontmost=unavailable"
    echo
    echo "## Browser"
    print_browser active 2>/dev/null || echo "browser=unavailable"
    echo
    echo "## Clipboard"
    printf 'clipboard<<EOF\n%s\nEOF\n' "$(pbpaste 2>/dev/null || true)"
    ;;
  list)
    cat <<'INFO'
mac-context capabilities (all read-only):

  frontmost     Frontmost app + front window title.   Needs: Accessibility
  browser       Active tab URL/title.                 Needs: Automation
  browser-tabs  All tabs across browser windows.      Needs: Automation
  clipboard     Current text clipboard.               Needs: none
  selection     Selected text (issues Cmd+C).         Needs: Accessibility *
  screenshot    Silent PNG to a path.                 Needs: Screen Recording
  snapshot      frontmost + browser + clipboard.      Needs: above as used

  * --selection temporarily overwrites a text-only clipboard, then restores it.
    It refuses to run when the clipboard currently contains non-text formats.

Supported browsers: Safari, Safari Technology Preview, Google Chrome,
Chrome Canary, Brave, Microsoft Edge, Arc, Vivaldi.

If macOS prompts for a permission the first time a mode runs, pause and tell
the user which permission is needed (Accessibility / Automation / Screen
Recording) under System Settings > Privacy & Security.
INFO
    ;;
  *)
    echo "Unsupported mode: $mode" >&2
    exit 2
    ;;
esac
