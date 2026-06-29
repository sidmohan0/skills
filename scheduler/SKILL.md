---
name: scheduler
description: Find, rank, validate, create, and update calendar meeting times with deterministic availability planning and guarded calendar writes. Use when the user asks to schedule, book, arrange, reschedule, move, or update a meeting; compare availability across people; find mutual free time next week or in a date range; turn proposed availabilities into candidate slots; or create/update calendar events after explicit confirmation.
---

# Scheduler

## Core Route

Use calendar connectors for profile/calendar discovery, event fetching, and final writes. Use the bundled script for deterministic date-range bounds, mutual availability, slot ranking, slot validation, and reviewed create/update action plans:

```bash
SKILL_DIR="${CODEX_SKILL_DIR:-$HOME/.codex/skills/scheduler}"
python3 "$SKILL_DIR/scripts/scheduler.py" window --start-date 2026-07-06 --end-date 2026-07-11 --timezone America/Los_Angeles
python3 "$SKILL_DIR/scripts/scheduler.py" rank-slots --input /tmp/scheduler-input.json
python3 "$SKILL_DIR/scripts/scheduler.py" validate-slot --input /tmp/scheduler-input.json --start 2026-07-06T10:30:00-07:00 --end 2026-07-06T11:00:00-07:00
python3 "$SKILL_DIR/scripts/scheduler.py" action-plan --input /tmp/scheduler-input.json --action create --slot-id slot-002
```

The script does not call calendar providers and does not mutate calendars. Build a JSON envelope from connector results and user-provided availability, pass it to the script, and use the script output to drive the scheduling conversation.

## Scheduling Workflow

1. Resolve the requested date range and timezone to exact bounds. Convert relative dates such as `next week` before querying connectors.
2. Discover the relevant calendars and source account labels with connector tools. Use connector returned labels; do not hard-code personal account names.
3. Fetch busy events for every selected required participant/calendar over the exact range. Include user-provided availability windows when the user gives them.
4. Build the scheduler JSON envelope.
5. Run `rank-slots` to compute deterministic candidate slots.
6. Present candidate slots to the user. Do not create or update anything yet.
7. After the user chooses a slot, run `validate-slot` against the latest envelope. If the slot is no longer available, show the conflict and ask for another slot.
8. Run `action-plan` for `create` or `update`.
9. Use calendar write tools only after explicit confirmation of the action plan.

## Envelope Shape

```json
{
  "request": {
    "title": "Raju sync",
    "duration_minutes": 30,
    "timezone": "America/Los_Angeles",
    "range": { "start": "2026-07-06", "end": "2026-07-11" },
    "workday": ["09:00", "17:00"],
    "step_minutes": 15,
    "max_results": 10,
    "target_calendar": {
      "source": "google",
      "calendar_label": "primary",
      "calendar_id": "primary"
    }
  },
  "participants": [
    {
      "id": "sid",
      "label": "Sid",
      "email": "sid@example.com",
      "required": true,
      "availability": [
        { "start": "2026-07-06T09:00:00-07:00", "end": "2026-07-06T12:00:00-07:00" }
      ],
      "events": [
        { "title": "Standup", "start": "2026-07-06T09:00:00-07:00", "end": "2026-07-06T09:30:00-07:00" }
      ]
    }
  ]
}
```

If a participant has no explicit `availability`, the script treats the request workday as their availability and subtracts busy events. Transparent/free, declined, canceled, and deleted events are ignored as busy blocks. Required participants must all be free; optional participants are reported as available or conflicting.

## Guarded Writes

Before any create or update tool call, the answer must include:

- Operation: create or update.
- Target calendar source and label/id.
- Title.
- Exact start, end, and timezone.
- Attendees.
- Location or conferencing expectation when provided.

Do not create or update an event until the user explicitly confirms the exact action plan. If the user asks to update a recurring event, read the event first and ask whether the change applies to one instance, the whole series, or this-and-following before writing.

For cancellations or deletes, read the target event first, identify whether the signed-in user is organizer or attendee, and ask for explicit confirmation. The planner script does not perform cancellation planning.

## Deterministic Boundaries

The script owns:

- date-range bounds
- busy/free interval normalization
- buffers before and after busy events
- mutual availability intersection
- candidate slot ranking
- proposed slot validation
- create/update action-plan formatting

The agent owns:

- resolving ambiguous people, calendars, and relative dates
- calling Google/Outlook calendar connectors
- asking clarification when duration, attendees, target calendar, or write intent is ambiguous
- performing confirmed writes through connector tools
- explaining tradeoffs beyond the deterministic slot table

If the script fails, report the failure and do not silently switch to hand-computed scheduling math.
