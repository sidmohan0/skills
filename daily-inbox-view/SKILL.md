---
name: daily-inbox-view
description: Inspect Apple Mail accounts and produce daily inbox triage previews across configured Mail accounts. Use when the user asks to check Apple Mail accounts, list which accounts can be acted on, preview today's inbox, print message subject tables, recommend inbox actions, open reply drafts, or open/inspect exact sent-mail matches such as emails sent yesterday.
---

# Daily Inbox View

## Core Route

Use Mail's scriptability for exact account and message selection. Do not rely on manual Mail UI search for date matching or mailbox scoping; Mail search and sidebar selection are easy to mis-scope from automation.

Run the bundled script:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-inbox-view}"
bash "$SKILL_DIR/scripts/daily_inbox_view.sh"
```

Default behavior:

- Compute today in the machine's local timezone.
- Search every Apple Mail account for inbox mailboxes named `Inbox` or `INBOX`.
- Print a Markdown table of messages whose `date received` is within that local calendar day.
- Include account, stable Mail message id, received time, sender, subject, and a first-pass recommended action.
- Do not open or modify messages.

## Common Tasks

List the Apple Mail accounts and mailboxes exposed to automation:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-inbox-view}"
bash "$SKILL_DIR/scripts/daily_inbox_view.sh" --list-accounts
```

Preview inbox counts for a specific date:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-inbox-view}"
bash "$SKILL_DIR/scripts/daily_inbox_view.sh" --date 2026-06-28 --count
```

Print the Markdown triage table for a specific date:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-inbox-view}"
bash "$SKILL_DIR/scripts/daily_inbox_view.sh" --date 2026-06-28 --markdown
```

The recommended action is heuristic. Use the table as a first-pass triage surface, then let the agent revise recommendations from sender/subject context when appropriate.

Open messages sent yesterday, preserving the original workflow:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-inbox-view}"
bash "$SKILL_DIR/scripts/daily_inbox_view.sh" --open-yesterday-sent
```

Dry-run sent-mail matches before opening:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-inbox-view}"
bash "$SKILL_DIR/scripts/daily_inbox_view.sh" --sent --date 2026-06-27
```

Generate a reviewable AppleScript that opens exact matched sent-message ids:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-inbox-view}"
bash "$SKILL_DIR/scripts/daily_inbox_view.sh" --sent --date 2026-06-27 --emit-open-script > /tmp/open-sent-mail.applescript
osascript /tmp/open-sent-mail.applescript
```

Use `--emit-open-script` when the agent should identify messages deterministically, inspect or log the generated open command, then execute the open step separately.

Generate an AppleScript for inbox actions by exact message id:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-inbox-view}"
bash "$SKILL_DIR/scripts/daily_inbox_view.sh" --emit-action-script reply --ids 271644,271645 > /tmp/mail-action.applescript
osascript /tmp/mail-action.applescript
```

Generate an action script for all inbox messages from one account on a date:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-inbox-view}"
bash "$SKILL_DIR/scripts/daily_inbox_view.sh" --emit-action-script reply --account "Account Name" --date 2026-06-28 > /tmp/mail-action.applescript
```

Supported action names:

- `reply`: open Mail reply compose windows only. Do not send.
- `archive`: move matching inbox messages to `Archive` or `All Mail` for that account.
- `delete`: delete matching inbox messages, moving them through Mail's normal delete behavior.
- `snooze`: move matching inbox messages to `Later` or `Snoozed` if that mailbox exists. Apple Mail's Remind Me/Snooze UI is not reliably exposed through AppleScript.

## Account Scope

Apple Mail automation can act on accounts returned by `--list-accounts`. It works through the local Mail app, so it can only see accounts and mailboxes configured in Apple Mail for the current macOS user.

Do not hard-code personal email addresses in this skill. Discover account names with `--list-accounts`, then use the exact account name returned by Mail when the user requests account-scoped actions.

The script is intentionally read-mostly:

- Account and inbox view modes only list/count/print subject tables.
- Sent-message mode only opens matching messages unless the user explicitly requests a different action.
- Reply action opens draft compose windows only and never sends.
- Archive, delete, and snooze are state-changing. Generate the script first; run it only after an explicit user instruction that names the action and target set.
- Do not send, reply, archive, delete, snooze, mark, or otherwise modify messages without an explicit user request.

## Optional UI Verification

If `cua-driver` is available, use it for launching Mail and verifying windows, not for finding messages:

1. Start a session, e.g. `start_session({"session":"daily-inbox-view"})`.
2. Launch Mail with bundle id `com.apple.mail`.
3. Run the bundled script to identify exact matches or counts.
4. Use `list_windows` for Mail's pid when verifying opened messages.
5. End the session.

If the script reports `0`, do not keep clicking around Mail. Tell the user no matching messages were found for the resolved date and mention the exact date.

## Guardrails

- State the resolved local date in the final answer.
- Avoid quoting email bodies unless the user explicitly asks for content.
- If Mail automation prompts for permission, pause and tell the user which permission is needed.
