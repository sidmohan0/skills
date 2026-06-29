# Skills

My current Mac-focused Agent skills, more to come!

- `daily-inbox-view`: reads Apple Mail accounts through the local Mail app and produces a daily inbox triage preview.
- `daily-calendar-view`: builds a read-only daily agenda from connected calendar sources.

I use this as a Codex automation periodically throughout the day to pull my calendar and inbox. I am going to keep building it out from here.

## Current Setup

- Runtime: Codex on macOS.
- OS: macOS 26.4, build 25E246.
- Local apps: Apple Mail 16.0 and Apple Calendar 16.0.
- Calendar sources: Google Calendar and Outlook Calendar through Codex connectors, with local macOS Calendar only as a scoped fallback.
- Mail source: Apple Mail accounts configured for the current macOS user.

## Skills

### `daily-inbox-view`

Produces a read-only inbox snapshot for a local calendar day. It discovers Apple Mail accounts and inboxes, prints message counts or a Markdown triage table, and can generate reviewable AppleScript for exact-message actions when explicitly requested.

Default run:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-inbox-view}"
bash "$SKILL_DIR/scripts/daily_inbox_view.sh"
```

### `daily-calendar-view`

Produces a read-only agenda for a local calendar day. It checks authenticated Google Calendar and Outlook Calendar sources, merges events by time, and highlights conflicts, free windows, locations, meeting links, response state, and prep cues when available.

## Install

```bash
git clone https://github.com/sidmohan0/skills.git
cd skills

mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD/daily-inbox-view" "${CODEX_HOME:-$HOME/.codex}/skills/daily-inbox-view"
ln -s "$PWD/daily-calendar-view" "${CODEX_HOME:-$HOME/.codex}/skills/daily-calendar-view"
```

Restart Codex after installing so it can pick up the new skills.

To install only one skill, link just that directory into `${CODEX_HOME:-$HOME/.codex}/skills`.

## Requirements

- macOS with Apple Mail configured for `daily-inbox-view`.
- Google Calendar and/or Outlook Calendar connectors authenticated in Codex for `daily-calendar-view`.
- Apple Mail Automation permission if macOS prompts the first time the inbox script runs.

## Use

Ask Codex for the skill by name:

- `Use $daily-inbox-view to check my Apple Mail accounts and preview today's inbox.`
- `Use $daily-calendar-view to show my calendar for today with important context.`

You can also smoke-test the inbox script directly:

```bash
bash "${CODEX_HOME:-$HOME/.codex}/skills/daily-inbox-view/scripts/daily_inbox_view.sh" --help
```

## Safety

These skills default to read-only behavior. Mail actions and calendar writes require an explicit user request naming the target and action.
