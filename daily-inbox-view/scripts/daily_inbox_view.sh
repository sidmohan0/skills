#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: daily_inbox_view.sh [--date YYYY-MM-DD] [--markdown|--count] [--list-accounts]
       daily_inbox_view.sh --sent [--date YYYY-MM-DD] [--open] [--dry-run] [--emit-open-script] [--quiet]
       daily_inbox_view.sh --emit-action-script ACTION [--ids ID[,ID...]] [--account ACCOUNT] [--date YYYY-MM-DD]
       daily_inbox_view.sh --open-yesterday-sent

Apple Mail account checks and daily inbox views.

Default:
  Print a Markdown table of messages received today in each account's Inbox/INBOX mailbox.

Options:
  --date YYYY-MM-DD       Use an explicit local date.
  --list-accounts         List Apple Mail accounts and their mailboxes.
  --markdown              Print an inbox Markdown table. Default for inbox mode.
  --count                 Print inbox counts only.
  --sent                  Count sent-mail messages for the target date.
  --open                  Open matched sent-mail messages. Use only with --sent.
  --open-yesterday-sent   Shortcut for --sent --open with yesterday's date.
  --dry-run               Count matches without opening messages.
  --emit-open-script      Emit AppleScript that opens exact matched sent-message ids.
  --emit-action-script    Emit AppleScript for inbox actions: reply, archive, delete, snooze.
  --ids ID[,ID...]        Message ids for --emit-action-script.
  --account ACCOUNT       Account filter for --emit-action-script when --ids is omitted.
  --quiet                 Print only target date and totals where supported.
  -h, --help              Show this help.
USAGE
}

mode="inbox"
inbox_format="markdown"
target_date=""
open_matches=0
dry_run=0
quiet=0
emit_open_script=0
emit_action_script=""
ids_csv=""
account_filter=""
yesterday_shortcut=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      [[ $# -ge 2 ]] || { echo "Missing value for --date" >&2; exit 2; }
      target_date="$2"
      shift 2
      ;;
    --date=*)
      target_date="${1#--date=}"
      shift
      ;;
    --list-accounts)
      mode="accounts"
      shift
      ;;
    --markdown)
      inbox_format="markdown"
      shift
      ;;
    --count)
      inbox_format="count"
      shift
      ;;
    --sent)
      mode="sent"
      shift
      ;;
    --open)
      open_matches=1
      shift
      ;;
    --open-yesterday-sent)
      mode="sent"
      open_matches=1
      yesterday_shortcut=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    --emit-open-script)
      mode="sent"
      emit_open_script=1
      dry_run=1
      shift
      ;;
    --emit-action-script)
      [[ $# -ge 2 ]] || { echo "Missing action for --emit-action-script" >&2; exit 2; }
      mode="action-script"
      emit_action_script="$2"
      shift 2
      ;;
    --emit-action-script=*)
      mode="action-script"
      emit_action_script="${1#--emit-action-script=}"
      shift
      ;;
    --ids)
      [[ $# -ge 2 ]] || { echo "Missing value for --ids" >&2; exit 2; }
      ids_csv="$2"
      shift 2
      ;;
    --ids=*)
      ids_csv="${1#--ids=}"
      shift
      ;;
    --account)
      [[ $# -ge 2 ]] || { echo "Missing value for --account" >&2; exit 2; }
      account_filter="$2"
      shift 2
      ;;
    --account=*)
      account_filter="${1#--account=}"
      shift
      ;;
    --quiet)
      quiet=1
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

if [[ "$mode" == "accounts" ]]; then
  osascript <<'APPLESCRIPT'
tell application "Mail"
	set reportLines to {"mode=accounts", "account_count=" & ((count of accounts) as text)}
	repeat with acct in accounts
		set acctName to name of acct
		set acctId to id of acct
		set mailboxNames to {}
		try
			repeat with mb in mailboxes of acct
				set end of mailboxNames to name of mb
			end repeat
		end try
		set AppleScript's text item delimiters to ", "
		set mailboxText to mailboxNames as text
		set AppleScript's text item delimiters to ""
		set end of reportLines to acctName & " | id=" & acctId & " | mailboxes=" & mailboxText
	end repeat
	set AppleScript's text item delimiters to linefeed
	return reportLines as text
end tell
APPLESCRIPT
  exit 0
fi

if [[ -z "$target_date" ]]; then
  if [[ "$yesterday_shortcut" -eq 1 || "$mode" == "sent" ]]; then
    target_date="$(date -v-1d +%Y-%m-%d)"
  else
    target_date="$(date +%Y-%m-%d)"
  fi
fi

if [[ ! "$target_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Date must be YYYY-MM-DD: $target_date" >&2
  exit 2
fi

year="${target_date%%-*}"
month_day="${target_date#*-}"
month="${month_day%%-*}"
day="${month_day##*-}"
month="$((10#$month))"
day="$((10#$day))"

applescript_escape() {
  sed 's/\\/\\\\/g; s/"/\\"/g' <<<"$1"
}

ids_source="{}"
if [[ -n "$ids_csv" ]]; then
  IFS=',' read -ra raw_ids <<<"$ids_csv"
  normalized_ids=()
  for raw_id in "${raw_ids[@]}"; do
    id="${raw_id//[[:space:]]/}"
    [[ "$id" =~ ^[0-9]+$ ]] || { echo "Message ids must be numeric: $raw_id" >&2; exit 2; }
    normalized_ids+=("$id")
  done
  joined_ids="$(IFS=', '; echo "${normalized_ids[*]}")"
  ids_source="{${joined_ids}}"
fi

account_filter_escaped="$(applescript_escape "$account_filter")"

if [[ "$mode" == "action-script" ]]; then
  case "$emit_action_script" in
    reply|archive|delete|snooze) ;;
    *) echo "--emit-action-script must be one of: reply, archive, delete, snooze" >&2; exit 2 ;;
  esac

  osascript <<APPLESCRIPT
set targetYear to ${year}
set targetMonthNumber to ${month}
set targetDay to ${day}
set accountFilter to "${account_filter_escaped}"
set requestedAction to "${emit_action_script}"
set targetMessageIds to ${ids_source}

set monthNames to {January, February, March, April, May, June, July, August, September, October, November, December}
set startDate to (current date)
set year of startDate to targetYear
set month of startDate to item targetMonthNumber of monthNames
set day of startDate to targetDay
set time of startDate to 0
set endDate to startDate + days
set targetDateText to "${target_date}"

if (count of targetMessageIds) is 0 then
	tell application "Mail"
		repeat with acct in accounts
			set acctName to name of acct
			if accountFilter is "" or acctName is accountFilter then
				try
					repeat with mb in mailboxes of acct
						set mbName to name of mb
						if mbName is "Inbox" or mbName is "INBOX" then
							set matchingMessages to (messages of mb whose date received is greater than or equal to startDate and date received is less than endDate)
							repeat with msg in matchingMessages
								set end of targetMessageIds to id of msg
							end repeat
						end if
					end repeat
				end try
			end if
		end repeat
	end tell
end if

set AppleScript's text item delimiters to ", "
if (count of targetMessageIds) is 0 then
	set targetIdsSource to "{}"
else
	set targetIdsSource to "{" & (targetMessageIds as text) & "}"
end if
set AppleScript's text item delimiters to ""
set q to quote
set generatedLines to {"-- Generated by daily-inbox-view for " & targetDateText, "-- action=" & requestedAction, "-- target_count=" & ((count of targetMessageIds) as text), "set requestedAction to " & q & requestedAction & q, "set targetMessageIds to " & targetIdsSource, "set actedCount to 0", "set skippedCount to 0", "", "on containsId(xs, candidateId)", tab & "repeat with x in xs", tab & tab & "if (contents of x) is candidateId then return true", tab & "end repeat", tab & "return false", "end containsId", "", "on firstMailboxNamed(acct, namesToFind)", tab & "tell application " & q & "Mail" & q, tab & tab & "repeat with mb in mailboxes of acct", tab & tab & tab & "set mbName to name of mb", tab & tab & tab & "repeat with wantedName in namesToFind", tab & tab & tab & tab & "if mbName is (contents of wantedName) then return mb", tab & tab & tab & "end repeat", tab & tab & "end repeat", tab & "end tell", tab & "return missing value", "end firstMailboxNamed", "", "tell application " & q & "Mail" & q, tab & "activate", tab & "repeat with acct in accounts", tab & tab & "try", tab & tab & tab & "repeat with mb in mailboxes of acct", tab & tab & tab & tab & "set mbName to name of mb", tab & tab & tab & tab & "if mbName is " & q & "Inbox" & q & " or mbName is " & q & "INBOX" & q & " then", tab & tab & tab & tab & tab & "repeat with msg in messages of mb", tab & tab & tab & tab & tab & tab & "set msgId to id of msg", tab & tab & tab & tab & tab & tab & "if my containsId(targetMessageIds, msgId) then", tab & tab & tab & tab & tab & tab & tab & "if requestedAction is " & q & "reply" & q & " then", tab & tab & tab & tab & tab & tab & tab & tab & "reply msg opening window yes", tab & tab & tab & tab & tab & tab & tab & tab & "set actedCount to actedCount + 1", tab & tab & tab & tab & tab & tab & tab & "else if requestedAction is " & q & "archive" & q & " then", tab & tab & tab & tab & tab & tab & tab & tab & "set destinationMailbox to my firstMailboxNamed(acct, {" & q & "Archive" & q & ", " & q & "All Mail" & q & "})", tab & tab & tab & tab & tab & tab & tab & tab & "if destinationMailbox is missing value then", tab & tab & tab & tab & tab & tab & tab & tab & tab & "set skippedCount to skippedCount + 1", tab & tab & tab & tab & tab & tab & tab & tab & "else", tab & tab & tab & tab & tab & tab & tab & tab & tab & "move msg to destinationMailbox", tab & tab & tab & tab & tab & tab & tab & tab & tab & "set actedCount to actedCount + 1", tab & tab & tab & tab & tab & tab & tab & tab & "end if", tab & tab & tab & tab & tab & tab & tab & "else if requestedAction is " & q & "snooze" & q & " then", tab & tab & tab & tab & tab & tab & tab & tab & "set destinationMailbox to my firstMailboxNamed(acct, {" & q & "Later" & q & ", " & q & "Snoozed" & q & "})", tab & tab & tab & tab & tab & tab & tab & tab & "if destinationMailbox is missing value then", tab & tab & tab & tab & tab & tab & tab & tab & tab & "set skippedCount to skippedCount + 1", tab & tab & tab & tab & tab & tab & tab & tab & "else", tab & tab & tab & tab & tab & tab & tab & tab & tab & "move msg to destinationMailbox", tab & tab & tab & tab & tab & tab & tab & tab & tab & "set actedCount to actedCount + 1", tab & tab & tab & tab & tab & tab & tab & tab & "end if", tab & tab & tab & tab & tab & tab & tab & "else if requestedAction is " & q & "delete" & q & " then", tab & tab & tab & tab & tab & tab & tab & tab & "delete msg", tab & tab & tab & tab & tab & tab & tab & tab & "set actedCount to actedCount + 1", tab & tab & tab & tab & tab & tab & tab & "end if", tab & tab & tab & tab & tab & tab & "end if", tab & tab & tab & tab & tab & "end repeat", tab & tab & tab & tab & "end if", tab & tab & tab & "end repeat", tab & tab & "end try", tab & "end repeat", "end tell", "return " & q & "action=" & q & " & requestedAction & " & q & " acted_total=" & q & " & (actedCount as text) & " & q & " skipped_total=" & q & " & (skippedCount as text)"}
set AppleScript's text item delimiters to linefeed
return generatedLines as text
APPLESCRIPT
  exit 0
fi

if [[ "$mode" == "inbox" ]]; then
  if [[ "$inbox_format" == "markdown" ]]; then
    osascript <<APPLESCRIPT
set targetYear to ${year}
set targetMonthNumber to ${month}
set targetDay to ${day}

on replaceText(findText, replaceText, sourceText)
	set oldDelimiters to AppleScript's text item delimiters
	set AppleScript's text item delimiters to findText
	set textItems to text items of sourceText
	set AppleScript's text item delimiters to replaceText
	set newText to textItems as text
	set AppleScript's text item delimiters to oldDelimiters
	return newText
end replaceText

on mdEscape(valueText)
	set cleanText to valueText as text
	set cleanText to my replaceText(return, " ", cleanText)
	set cleanText to my replaceText(linefeed, " ", cleanText)
	set cleanText to my replaceText("|", "/", cleanText)
	return cleanText
end mdEscape

on lowerText(valueText)
	return do shell script "printf %s " & quoted form of (valueText as text) & " | /usr/bin/tr '[:upper:]' '[:lower:]'"
end lowerText

on recommendedAction(senderText, subjectText)
	set haystack to my lowerText((senderText as text) & " " & (subjectText as text))
	if haystack contains "unsubscribe" or haystack contains "sale" or haystack contains "promo" or haystack contains "discount" or haystack contains "webinar" or haystack contains "newsletter" or haystack contains "digest" then return "Delete"
	if haystack contains "due" or haystack contains "deadline" or haystack contains "reminder" or haystack contains "expires" or haystack contains "renew" or haystack contains "rsvp" or haystack contains "event" then return "Snooze"
	if haystack contains "re:" or haystack contains "follow up" or haystack contains "intro" or haystack contains "meeting" or haystack contains "request" or haystack contains "?" then return "Reply Now"
	if haystack contains "noreply" or haystack contains "no-reply" or haystack contains "invoice" or haystack contains "receipt" or haystack contains "statement" or haystack contains "alert" or haystack contains "notification" then return "Archive"
	return "Archive"
end recommendedAction

set monthNames to {January, February, March, April, May, June, July, August, September, October, November, December}
set startDate to (current date)
set year of startDate to targetYear
set month of startDate to item targetMonthNumber of monthNames
set day of startDate to targetDay
set time of startDate to 0
set endDate to startDate + days

set targetDateText to "${target_date}"
set reportLines to {"mode=inbox-markdown", "target_date=" & targetDateText, "", "| Account | ID | Received | Sender | Subject | Recommended Action |", "|---|---:|---|---|---|---|"}
set matchedTotal to 0

tell application "Mail"
	repeat with acct in accounts
		set acctName to name of acct
		try
			repeat with mb in mailboxes of acct
				set mbName to name of mb
				if mbName is "Inbox" or mbName is "INBOX" then
					set matchingMessages to (messages of mb whose date received is greater than or equal to startDate and date received is less than endDate)
					repeat with msg in matchingMessages
						set msgId to id of msg
						set msgSender to sender of msg
						set msgSubject to subject of msg
						set msgDate to date received of msg
						set actionName to my recommendedAction(msgSender, msgSubject)
						set end of reportLines to "| " & my mdEscape(acctName) & " | " & (msgId as text) & " | " & my mdEscape(msgDate as text) & " | " & my mdEscape(msgSender) & " | " & my mdEscape(msgSubject) & " | " & actionName & " |"
						set matchedTotal to matchedTotal + 1
					end repeat
				end if
			end repeat
		on error errMsg number errNum
			set end of reportLines to "| " & my mdEscape(acctName) & " |  |  | error | " & my mdEscape(errMsg) & " |  |"
		end try
	end repeat
end tell

set end of reportLines to ""
set end of reportLines to "matched_total=" & (matchedTotal as text)
set AppleScript's text item delimiters to linefeed
return reportLines as text
APPLESCRIPT
    exit 0
  fi

  osascript <<APPLESCRIPT
set targetYear to ${year}
set targetMonthNumber to ${month}
set targetDay to ${day}

set monthNames to {January, February, March, April, May, June, July, August, September, October, November, December}
set startDate to (current date)
set year of startDate to targetYear
set month of startDate to item targetMonthNumber of monthNames
set day of startDate to targetDay
set time of startDate to 0
set endDate to startDate + days

set targetDateText to "${target_date}"
set reportLines to {"mode=inbox-preview", "target_date=" & targetDateText}
set matchedTotal to 0

tell application "Mail"
	repeat with acct in accounts
		set acctName to name of acct
		set accountTotal to 0
		try
			repeat with mb in mailboxes of acct
				set mbName to name of mb
				if mbName is "Inbox" or mbName is "INBOX" then
					set n to count of (messages of mb whose date received is greater than or equal to startDate and date received is less than endDate)
					set accountTotal to accountTotal + n
				end if
			end repeat
			set matchedTotal to matchedTotal + accountTotal
			set end of reportLines to acctName & " | inbox_received=" & (accountTotal as text)
		on error errMsg number errNum
			set end of reportLines to acctName & " | error | " & errMsg
		end try
	end repeat
end tell

set end of reportLines to "matched_total=" & (matchedTotal as text)
set AppleScript's text item delimiters to linefeed
return reportLines as text
APPLESCRIPT
  exit 0
fi

if [[ "$mode" != "sent" ]]; then
  echo "Unsupported mode: $mode" >&2
  exit 2
fi

osascript <<APPLESCRIPT
set targetYear to ${year}
set targetMonthNumber to ${month}
set targetDay to ${day}
set openMatches to ${open_matches}
set dryRun to ${dry_run}
set quietMode to ${quiet}
set emitOpenScript to ${emit_open_script}

set monthNames to {January, February, March, April, May, June, July, August, September, October, November, December}
set startDate to (current date)
set year of startDate to targetYear
set month of startDate to item targetMonthNumber of monthNames
set day of startDate to targetDay
set time of startDate to 0
set endDate to startDate + days

set targetDateText to "${target_date}"
set reportLines to {"mode=sent", "target_date=" & targetDateText}
set openedCount to 0
set matchedCount to 0
set matchedIds to {}

tell application "Mail"
	if openMatches is 1 and dryRun is 0 then activate
	repeat with acct in accounts
		set acctName to name of acct
		try
			set acctMailboxes to mailboxes of acct
			repeat with mb in acctMailboxes
				set mbName to name of mb
				if mbName contains "Sent" or mbName contains "sent" then
					set matchingMessages to (messages of mb whose date sent is greater than or equal to startDate and date sent is less than endDate)
					set n to count of matchingMessages
					set matchedCount to matchedCount + n
					if quietMode is 0 then set end of reportLines to acctName & " | " & mbName & " | sent_matches=" & (n as text)
					repeat with msg in matchingMessages
						set end of matchedIds to ((id of msg) as text)
						if openMatches is 1 and dryRun is 0 then
							open msg
							set openedCount to openedCount + 1
						end if
					end repeat
				end if
			end repeat
		on error errMsg number errNum
			if quietMode is 0 then set end of reportLines to acctName & " | error | " & errMsg
		end try
	end repeat
end tell

if emitOpenScript is 1 then
	set AppleScript's text item delimiters to ", "
	if (count of matchedIds) is 0 then
		set targetIdsSource to "{}"
	else
		set targetIdsSource to "{" & (matchedIds as text) & "}"
	end if
	set AppleScript's text item delimiters to ""
	set q to quote
	set generatedLines to {"-- Generated by daily-inbox-view for " & targetDateText, "-- matched_total=" & (matchedCount as text), "set targetMessageIds to " & targetIdsSource, "set openedCount to 0", "tell application " & q & "Mail" & q, tab & "activate", tab & "repeat with targetMessageId in targetMessageIds", tab & tab & "set targetId to contents of targetMessageId", tab & tab & "repeat with acct in accounts", tab & tab & tab & "try", tab & tab & tab & tab & "repeat with mb in mailboxes of acct", tab & tab & tab & tab & tab & "set mbName to name of mb", tab & tab & tab & tab & tab & "if mbName contains " & q & "Sent" & q & " or mbName contains " & q & "sent" & q & " then", tab & tab & tab & tab & tab & tab & "set matches to (messages of mb whose id is targetId)", tab & tab & tab & tab & tab & tab & "repeat with msg in matches", tab & tab & tab & tab & tab & tab & tab & "open msg", tab & tab & tab & tab & tab & tab & tab & "set openedCount to openedCount + 1", tab & tab & tab & tab & tab & tab & "end repeat", tab & tab & tab & tab & tab & "end if", tab & tab & tab & tab & "end repeat", tab & tab & tab & "end try", tab & tab & "end repeat", tab & "end repeat", "end tell", "return " & q & "opened_total=" & q & " & (openedCount as text)"}
	set AppleScript's text item delimiters to linefeed
	return generatedLines as text
end if

set end of reportLines to "matched_total=" & (matchedCount as text)
set end of reportLines to "opened_total=" & (openedCount as text)
set AppleScript's text item delimiters to linefeed
return reportLines as text
APPLESCRIPT
