---
name: daily-calendar-view
description: Produce a read-only daily agenda from connected calendar sources. Use when the user asks to see today's schedule, list calendar events for a day, build a daily calendar view, summarize meetings, identify conflicts/free windows, or gather important context for scheduled events across Google Calendar, Outlook Calendar, and optionally local macOS Calendar.
---

# Daily Calendar View

## Core Route

Build a read-only agenda first. Do not create, update, delete, cancel, or respond to events unless the user explicitly asks for that action later.

Use exact local-day bounds in the user's local timezone unless the user specifies a different timezone. Detect the local timezone from the runtime, connector profile, or user-provided context before querying:

- Start: `YYYY-MM-DDT00:00:00` with the correct local offset.
- End: next day at `00:00:00` with the correct local offset.
- State the resolved date in the final answer.

## Source Discovery

Use connected calendar sources discovered at runtime:

- Google Calendar: query the authenticated profile's `primary` calendar, then any explicitly requested calendar ids.
- Outlook Calendar: query the authenticated profile's default `Calendar`, then any explicitly requested shared/delegated/read-only calendars.
- Local macOS Calendar: use only as a fallback, and only with tight scoping to specific calendars.

Do not hard-code personal email addresses, domains, or calendar account names in this skill. State the source account labels returned by the connectors during the current run. If a requested account is not returned by profile or calendar-listing tools, report it as unavailable rather than silently omitting it.

## Fetch Workflow

1. Determine the target date and timezone.
2. Query Google Calendar with `search_events` over the exact day window when that connector is available.
3. Query Outlook mailbox settings for timezone if needed, then list Outlook events over the same exact day window when that connector is available.
4. If event records are partial and the answer needs attendees, conferencing, descriptions, response state, or organizer details, read/fetch specific events by id.
5. Merge events by time. Preserve source/account labels.
6. Highlight overlaps, travel/location changes, all-day events, tentative/declined status, missing conferencing links, and prep cues from descriptions.

## Output Shape

Prefer this structure:

```markdown
**Daily Calendar View — Month D, YYYY**

Sources checked: Google `<profile email>`; Outlook `<profile email>`.

| Time | Source | Event | Important Info |
|---|---|---|---|
| 9:00-9:30 AM | Google | Team sync | Google Meet; 4 attendees; accepted |

**Things To Know**
- Conflict: ...
- Free window: ...
- Prep: ...
```

Keep descriptions summarized. Do not dump full event descriptions unless the user asks.

## Important Info Heuristics

Surface:

- Meeting link or location when present.
- Organizer, attendee count, and user's response status when available.
- Whether the event is all-day, tentative, declined, private, transparent/free, or out-of-office.
- Conflicts or tight transitions between events.
- Free windows of 30+ minutes during the workday.
- Prep hints: agenda, doc links, call notes, customer/company names, or explicit action words in descriptions.

## Guardrails

- Default to read-only.
- For write actions, ask for explicit target event(s) and desired operation before using create/update/delete/respond tools.
- For recurring events, read the event first and be explicit about whether an action applies to one instance, the whole series, or this-and-following.
- If a source returns an auth or not-found error, report that source as unavailable instead of silently omitting it.
