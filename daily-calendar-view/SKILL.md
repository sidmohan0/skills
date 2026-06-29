---
name: daily-calendar-view
description: Produce a read-only daily agenda from connected calendar sources. Use when the user asks to see today's schedule, list calendar events for a day, build a daily calendar view, summarize meetings, identify conflicts/free windows, or gather important context for scheduled events across Google Calendar, Outlook Calendar, and optionally local macOS Calendar.
---

# Daily Calendar View

## Deterministic Contract

Build a read-only agenda first. Do not create, update, delete, cancel, or respond to events unless the user explicitly asks for that action later.

Treat connector results as the source of truth. Do not infer that an unavailable source is empty. Report every selected source as `checked`, `unavailable`, or `error`.

## Resolve Date And Window

Resolve the target date and timezone in this order:

1. Use the user's explicit date and timezone when provided.
2. Use connector calendar/profile timezone when the user gives a date but no timezone.
3. Use the machine/runtime local timezone when no connector timezone is available.
4. Default to today in the resolved timezone when the user gives no date.

Query a closed-open local-day window:

- Start: `YYYY-MM-DDT00:00:00` with the resolved local offset.
- End: next day at `00:00:00` with the resolved local offset.

Do not query connectors with vague date text such as `today` or `tomorrow`. Convert relative dates first, then query exact bounds. State the resolved date, timezone, and window in the final answer.

## Source Discovery

Use connected calendar sources discovered at runtime in this order:

1. Google Calendar authenticated profile's `primary` calendar.
2. Google Calendar calendars explicitly requested by id or name.
3. Outlook Calendar authenticated profile's default `Calendar`.
4. Outlook Calendar shared, delegated, or read-only calendars explicitly requested by id or name.
5. Local macOS Calendar only when calendar connectors are unavailable or the user explicitly asks for local calendars.

Do not hard-code personal email addresses, domains, or calendar account names in this skill. State the source account labels returned by the connectors during the current run. If a requested account is not returned by profile or calendar-listing tools, report it as unavailable rather than silently omitting it.

## Fetch Workflow

1. Determine the target date and timezone.
2. Discover available source/account labels and calendar ids only as needed.
3. Query every selected source over the same exact day window.
4. If event records are partial and the answer needs attendees, conferencing, descriptions, response state, organizer details, or recurrence details, fetch specific events by id.
5. Normalize every event before summarizing.
6. Merge, deduplicate, sort, and analyze events using the rules below.

## Normalized Event Record

Build an internal record with these fields when available:

- `source_order`, `source`, `account_label`, `calendar_label`, `event_id`
- `title`, `start`, `end`, `all_day`, `timezone`
- `status`, `self_response`, `transparency`, `privacy`, `recurrence`
- `organizer`, `attendee_count`
- `location`, `conference_summary`
- `description_flags`: agenda/doc links/action words/customer or company names

Treat missing fields as unknown. Do not invent attendees, links, locations, or response state.

## Merge And Sort Rules

Exclude canceled or deleted events from the main agenda. Mention them only if the user asks or if their presence explains a source discrepancy.

Deduplicate across sources only when events have the same normalized title, exact start and end time, and either the same organizer, same conference link, or same location. Combine source labels for deduplicated events. If events share title and time but fail the dedupe rule, keep both and mark `possible duplicate`.

Sort output deterministically:

1. All-day events before timed events.
2. Timed events by start time, then end time.
3. Ties by source order, calendar label, title, then event id.

For all-day event ties, sort by source order, calendar label, title, then event id.

## Conflict And Free-Window Rules

Mark a conflict when two non-declined, non-canceled, busy timed events overlap by at least 1 minute. Do not count transparent/free events as conflicts. Mention tentative events in conflicts as tentative.

Mark a tight transition when two timed events have less than 10 minutes between them and either event has a physical location or a different conferencing/location value.

Compute free windows only across the default workday `9:00 AM-5:00 PM` in the resolved timezone unless the user gives other work hours. Ignore all-day events, declined events, canceled events, and transparent/free events when computing free windows. Report windows of 30 minutes or longer.

## Output Shape

Use this structure:

```markdown
**Daily Calendar View — Month D, YYYY**

Resolved window: `YYYY-MM-DDT00:00:00±HH:MM` to `YYYY-MM-DDT00:00:00±HH:MM`
Sources: Google `<account label>` checked; Outlook `<account label>` unavailable/error/checked.

| Time | Source | Event | Important Info |
|---|---|---|---|
| 9:00-9:30 AM | Google | Team sync | Google Meet; 4 attendees; accepted |

**Things To Know**
- Conflict: ...
- Free window: ...
- Prep: ...
```

When there are no events, still include the resolved window and source statuses, then say there are no events for that date. Keep descriptions summarized. Do not dump full event descriptions unless the user asks.

## Important Info Heuristics

Surface important info in this order when available:

1. Status flags: all-day, tentative, declined, private, transparent/free, out-of-office, recurring.
2. Meeting link summary or physical location.
3. Organizer, attendee count, and user's response status.
4. Conflict, possible duplicate, or tight-transition note.
5. Prep hints: agenda, doc links, call notes, customer/company names, or explicit action words in descriptions.

## Guardrails

- Default to read-only.
- For write actions, ask for explicit target event(s) and desired operation before using create/update/delete/respond tools.
- For recurring events, read the event first and be explicit about whether an action applies to one instance, the whole series, or this-and-following.
- If a source returns an auth or not-found error, report that source as unavailable instead of silently omitting it.
- Do not use local UI automation to infer calendar contents when a connector returned an authoritative result.
