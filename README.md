# Skills

My current Mac-focused Agent skills, more to come!

- `daily-inbox-view`: reads Apple Mail accounts through the local Mail app and produces a daily inbox triage preview.
- `daily-calendar-view`: builds a deterministic read-only daily agenda from connected calendar sources.
- `scheduler`: finds, validates, and prepares guarded calendar meeting writes after explicit confirmation.
- `wework`: uses the installed third-party `wework` CLI from `github.com/dvcrn/wework-cli` to inspect and manage WeWork bookings. This is not documented here as an official WeWork CLI.

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

Produces a read-only agenda for a local calendar day. Agents fetch authenticated Google Calendar and Outlook Calendar events, then pass connector JSON to the bundled renderer for deterministic date windows, event normalization, dedupe, sorting, conflict detection, free windows, and Markdown output.

Deterministic renderer:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/daily-calendar-view}"
python3 "$SKILL_DIR/scripts/daily_calendar_view.py" window --date 2026-06-29 --timezone America/Los_Angeles
python3 "$SKILL_DIR/scripts/daily_calendar_view.py" render --input /tmp/daily-calendar-input.json
```

### `scheduler`

Finds and validates meeting times across required and optional participants. It ranks candidate slots from connector events and user-provided availability, validates a selected slot, and generates a reviewed create/update action plan. Calendar writes still happen only through connector tools after explicit user confirmation.

Deterministic planner:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/scheduler}"
python3 "$SKILL_DIR/scripts/scheduler.py" rank-slots --input /tmp/scheduler-input.json
python3 "$SKILL_DIR/scripts/scheduler.py" action-plan --input /tmp/scheduler-input.json --action create --slot-id slot-001
```

### `wework`

Uses an already-installed `wework` command to list WeWork locations, inspect desk availability, manage bookings, quote bookings, and export an `.ics` calendar.

Implementation notes:

- Source/provenance: copied from the `wework` skill bundled in `github.com/dvcrn/wework-cli`.
- CLI dependency: this skill calls the third-party `wework` binary from `github.com/dvcrn/wework-cli`; it does not implement the WeWork API itself.
- Official status: I have not found evidence that `dvcrn/wework-cli` is an official WeWork-maintained CLI, so treat it as unofficial third-party tooling.
- Credentials: the skill does not store credentials. The CLI expects `WEWORK_USERNAME` and `WEWORK_PASSWORD` in the environment, or explicit `--username` and `--password` flags. Prefer environment variables and do not commit credentials.

Basic checks:

```bash
command -v wework
wework --help
```

## Install

```bash
git clone https://github.com/sidmohan0/skills.git
cd skills

mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$PWD/daily-inbox-view" "${CODEX_HOME:-$HOME/.codex}/skills/daily-inbox-view"
ln -s "$PWD/daily-calendar-view" "${CODEX_HOME:-$HOME/.codex}/skills/daily-calendar-view"
ln -s "$PWD/scheduler" "${CODEX_HOME:-$HOME/.codex}/skills/scheduler"
ln -s "$PWD/wework" "${CODEX_HOME:-$HOME/.codex}/skills/wework"
```

Restart Codex after installing so it can pick up the new skills.

To install only one skill, link just that directory into `${CODEX_HOME:-$HOME/.codex}/skills`.

## Requirements

- macOS with Apple Mail configured for `daily-inbox-view`.
- Google Calendar and/or Outlook Calendar connectors authenticated in Codex for `daily-calendar-view` and `scheduler`.
- Python 3 for deterministic calendar and scheduler scripts.
- Apple Mail Automation permission if macOS prompts the first time the inbox script runs.
- Installed `wework` CLI plus `WEWORK_USERNAME` and `WEWORK_PASSWORD` environment variables for `wework`.

## Use

Ask Codex for the skill by name:

- `Use $daily-inbox-view to check my Apple Mail accounts and preview today's inbox.`
- `Use $daily-calendar-view to show my calendar for today with important context.`
- `Use $scheduler to find and book a meeting time with Raju next week.`
- `Use $wework to show my upcoming WeWork bookings.`

You can also smoke-test the inbox script directly:

```bash
bash "${CODEX_HOME:-$HOME/.codex}/skills/daily-inbox-view/scripts/daily_inbox_view.sh" --help
```

And the deterministic calendar/scheduler scripts:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/daily-calendar-view/scripts/daily_calendar_view.py" --help
python3 "${CODEX_HOME:-$HOME/.codex}/skills/scheduler/scripts/scheduler.py" --help
```

## Safety

These skills default to read-only behavior. Mail actions and calendar writes require an explicit user request naming the target and action.
