#!/usr/bin/env python3
"""Deterministic scheduling planner.

The script does not call calendar providers or mutate calendars. Agents provide
availability/event JSON, and the script computes candidate slots and action
plans that can be reviewed before connector write tools are used.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


WINDOWS_TZ_MAP = {
    "Pacific Standard Time": "America/Los_Angeles",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "UTC": "UTC",
}


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class BusyBlock:
    participant_id: str
    title: str
    interval: Interval
    source: str = ""


@dataclass
class Participant:
    id: str
    label: str
    email: str = ""
    required: bool = True
    availability: list[Interval] = field(default_factory=list)
    busy: list[BusyBlock] = field(default_factory=list)
    free: list[Interval] = field(default_factory=list)


@dataclass
class Slot:
    id: str
    start: datetime
    end: datetime
    required_participants: list[str]
    optional_available: list[str] = field(default_factory=list)
    optional_conflicts: dict[str, list[str]] = field(default_factory=dict)

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def read_json(path: str | None) -> dict[str, Any]:
    if path and path != "-":
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return json.load(sys.stdin)


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("|", "/")


def normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def tz_from_name(name: str | None) -> ZoneInfo | timezone:
    if not name:
        return datetime.now().astimezone().tzinfo or timezone.utc
    mapped = WINDOWS_TZ_MAP.get(name, name)
    if mapped.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(mapped)
    except ZoneInfoNotFoundError as exc:
        raise SystemExit(f"Unknown timezone: {name}") from exc


def tz_label(name: str | None) -> str:
    if name:
        return WINDOWS_TZ_MAP.get(name, name)
    env_tz = os.environ.get("TZ")
    if env_tz:
        return WINDOWS_TZ_MAP.get(env_tz, env_tz)
    return datetime.now().astimezone().tzname() or "local"


def resolve_timezone(name: str | None) -> tuple[ZoneInfo | timezone, str]:
    if name:
        label = tz_label(name)
        return tz_from_name(label), label
    return tz_from_name(None), tz_label(None)


def parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"{field_name} must be YYYY-MM-DD: {value}") from exc


def parse_time_of_day(value: str, field_name: str) -> time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except Exception as exc:  # noqa: BLE001 - turn any parse issue into a CLI error.
        raise SystemExit(f"{field_name} must be HH:MM: {value}") from exc


def parse_dt(value: Any, fallback_tz: ZoneInfo | timezone) -> datetime:
    if isinstance(value, dict):
        if value.get("date"):
            return datetime.combine(parse_date(str(value["date"]), "date"), time.min, tzinfo=fallback_tz)
        event_tz = tz_from_name(value.get("timeZone") or value.get("timezone")) if (
            value.get("timeZone") or value.get("timezone")
        ) else fallback_tz
        dt_value = value.get("dateTime") or value.get("datetime")
        return parse_dt(dt_value, event_tz).astimezone(fallback_tz)
    if not value:
        raise ValueError("missing datetime")
    text = str(value).strip().replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return datetime.combine(parse_date(text, "date"), time.min, tzinfo=fallback_tz)
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=fallback_tz)
    return parsed.astimezone(fallback_tz)


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def format_time(value: datetime) -> str:
    suffix = "AM" if value.hour < 12 else "PM"
    hour = value.hour % 12 or 12
    return f"{hour}:{value.minute:02d} {suffix}"


def format_datetime_range(start: datetime, end: datetime) -> str:
    if start.date() == end.date():
        return f"{start.strftime('%a %b')} {start.day}, {format_time(start)}-{format_time(end)}"
    return f"{iso(start)} to {iso(end)}"


def request_obj(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("request") if isinstance(payload.get("request"), dict) else {}


def requested_timezone(payload: dict[str, Any]) -> tuple[ZoneInfo | timezone, str]:
    request = request_obj(payload)
    value = request.get("timezone") or payload.get("timezone")
    return resolve_timezone(str(value) if value else None)


def date_range_from_payload(payload: dict[str, Any]) -> tuple[datetime, datetime, ZoneInfo | timezone, str]:
    request = request_obj(payload)
    tzinfo, label = requested_timezone(payload)
    range_obj = request.get("range") if isinstance(request.get("range"), dict) else {}
    start_value = range_obj.get("start") or request.get("start_date") or payload.get("start_date")
    end_value = range_obj.get("end") or request.get("end_date") or payload.get("end_date")
    if not start_value or not end_value:
        raise SystemExit("request.range.start and request.range.end are required")
    start = parse_range_boundary(str(start_value), tzinfo, "range.start")
    end = parse_range_boundary(str(end_value), tzinfo, "range.end")
    if end <= start:
        raise SystemExit("range.end must be after range.start")
    return start, end, tzinfo, label


def parse_range_boundary(value: str, tzinfo: ZoneInfo | timezone, field_name: str) -> datetime:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return datetime.combine(parse_date(value, field_name), time.min, tzinfo=tzinfo)
    return parse_dt(value, tzinfo)


def request_duration(payload: dict[str, Any]) -> int:
    request = request_obj(payload)
    duration = int(request.get("duration_minutes") or payload.get("duration_minutes") or 30)
    if duration <= 0:
        raise SystemExit("duration_minutes must be positive")
    return duration


def request_step(payload: dict[str, Any]) -> int:
    request = request_obj(payload)
    step = int(request.get("step_minutes") or payload.get("step_minutes") or 15)
    if step <= 0:
        raise SystemExit("step_minutes must be positive")
    return step


def request_workday(payload: dict[str, Any]) -> tuple[time, time]:
    request = request_obj(payload)
    workday = request.get("workday") if isinstance(request.get("workday"), list) else []
    start_text = str(request.get("workday_start") or (workday[0] if workday else "09:00"))
    end_text = str(request.get("workday_end") or (workday[1] if len(workday) > 1 else "17:00"))
    start = parse_time_of_day(start_text, "workday_start")
    end = parse_time_of_day(end_text, "workday_end")
    if datetime.combine(date.today(), end) <= datetime.combine(date.today(), start):
        raise SystemExit("workday end must be after workday start")
    return start, end


def request_buffers(payload: dict[str, Any]) -> tuple[int, int]:
    request = request_obj(payload)
    before = int(request.get("buffer_before_minutes") or 0)
    after = int(request.get("buffer_after_minutes") or 0)
    if before < 0 or after < 0:
        raise SystemExit("buffers must be non-negative")
    return before, after


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    valid = sorted([item for item in intervals if item.end > item.start], key=lambda item: (item.start, item.end))
    merged: list[Interval] = []
    for interval in valid:
        if not merged or interval.start > merged[-1].end:
            merged.append(interval)
        else:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, interval.end))
    return merged


def clip_interval(interval: Interval, start: datetime, end: datetime) -> Interval | None:
    clipped = Interval(max(interval.start, start), min(interval.end, end))
    return clipped if clipped.end > clipped.start else None


def subtract_intervals(allowed: list[Interval], busy: list[Interval]) -> list[Interval]:
    free = merge_intervals(allowed)
    for block in merge_intervals(busy):
        next_free: list[Interval] = []
        for interval in free:
            if block.end <= interval.start or block.start >= interval.end:
                next_free.append(interval)
                continue
            if block.start > interval.start:
                next_free.append(Interval(interval.start, min(block.start, interval.end)))
            if block.end < interval.end:
                next_free.append(Interval(max(block.end, interval.start), interval.end))
        free = next_free
    return merge_intervals(free)


def intersect_two(left: list[Interval], right: list[Interval]) -> list[Interval]:
    intersections: list[Interval] = []
    i = 0
    j = 0
    left_sorted = merge_intervals(left)
    right_sorted = merge_intervals(right)
    while i < len(left_sorted) and j < len(right_sorted):
        start = max(left_sorted[i].start, right_sorted[j].start)
        end = min(left_sorted[i].end, right_sorted[j].end)
        if end > start:
            intersections.append(Interval(start, end))
        if left_sorted[i].end < right_sorted[j].end:
            i += 1
        else:
            j += 1
    return merge_intervals(intersections)


def intersect_many(interval_sets: list[list[Interval]]) -> list[Interval]:
    if not interval_sets:
        return []
    current = merge_intervals(interval_sets[0])
    for intervals in interval_sets[1:]:
        current = intersect_two(current, intervals)
    return current


def build_workday_intervals(
    start: datetime,
    end: datetime,
    tzinfo: ZoneInfo | timezone,
    workday_start: time,
    workday_end: time,
) -> list[Interval]:
    intervals = []
    cursor = start.date()
    while datetime.combine(cursor, time.min, tzinfo=tzinfo) < end:
        interval = Interval(
            datetime.combine(cursor, workday_start, tzinfo=tzinfo),
            datetime.combine(cursor, workday_end, tzinfo=tzinfo),
        )
        clipped = clip_interval(interval, start, end)
        if clipped:
            intervals.append(clipped)
        cursor += timedelta(days=1)
    return intervals


def is_canceled(raw: dict[str, Any]) -> bool:
    return str(raw.get("status") or "").lower() in {"cancelled", "canceled", "deleted"} or bool(
        raw.get("isCancelled") or raw.get("is_canceled")
    )


def is_declined(raw: dict[str, Any]) -> bool:
    direct = raw.get("self_response") or raw.get("my_response_status") or raw.get("responseStatus")
    if isinstance(direct, dict):
        direct = direct.get("response") or direct.get("status")
    if str(direct or "").lower() == "declined":
        return True
    attendees = raw.get("attendees") if isinstance(raw.get("attendees"), list) else []
    for attendee in attendees:
        if attendee.get("is_self") or attendee.get("isSelf"):
            response = attendee.get("response_status") or get_nested(attendee, "status", "response")
            if str(response or "").lower() == "declined":
                return True
    return False


def is_free(raw: dict[str, Any]) -> bool:
    transparency = str(raw.get("transparency") or "").lower()
    show_as = str(raw.get("showAs") or raw.get("show_as") or "").lower()
    return transparency in {"transparent", "free"} or show_as == "free"


def get_nested(raw: dict[str, Any], *keys: str) -> Any:
    current: Any = raw
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def event_title(raw: dict[str, Any]) -> str:
    return str(raw.get("summary") or raw.get("subject") or raw.get("title") or "(busy)")


def event_interval(raw: dict[str, Any], tzinfo: ZoneInfo | timezone) -> Interval | None:
    start_value = raw.get("start") or raw.get("start_datetime") or raw.get("startDateTime")
    end_value = raw.get("end") or raw.get("end_datetime") or raw.get("endDateTime")
    if not start_value or not end_value:
        return None
    start = parse_dt(start_value, tzinfo)
    end = parse_dt(end_value, tzinfo)
    return Interval(start, end) if end > start else None


def parse_interval(raw: dict[str, Any], tzinfo: ZoneInfo | timezone) -> Interval:
    return Interval(parse_dt(raw.get("start"), tzinfo), parse_dt(raw.get("end"), tzinfo))


def participant_id(item: dict[str, Any], index: int) -> str:
    return str(item.get("id") or item.get("email") or item.get("label") or f"participant-{index}")


def participant_label(item: dict[str, Any], pid: str) -> str:
    return str(item.get("label") or item.get("name") or item.get("email") or pid)


def parse_participants(payload: dict[str, Any]) -> list[Participant]:
    start, end, tzinfo, _label = date_range_from_payload(payload)
    workday_start, workday_end = request_workday(payload)
    buffer_before, buffer_after = request_buffers(payload)
    participants_raw = payload.get("participants") if isinstance(payload.get("participants"), list) else []
    top_level_events = payload.get("events") if isinstance(payload.get("events"), list) else []
    participants: list[Participant] = []

    for index, item in enumerate(participants_raw, start=1):
        if not isinstance(item, dict):
            continue
        pid = participant_id(item, index)
        availability_raw = item.get("availability") if isinstance(item.get("availability"), list) else []
        if availability_raw:
            allowed = [
                clipped
                for interval_item in availability_raw
                if isinstance(interval_item, dict)
                for clipped in [clip_interval(parse_interval(interval_item, tzinfo), start, end)]
                if clipped is not None
            ]
        else:
            allowed = build_workday_intervals(start, end, tzinfo, workday_start, workday_end)

        participant_events = item.get("events") if isinstance(item.get("events"), list) else []
        event_items = participant_events + [
            event for event in top_level_events if isinstance(event, dict) and str(event.get("participant_id") or "") == pid
        ]
        busy_blocks: list[BusyBlock] = []
        for event_item in event_items:
            if not isinstance(event_item, dict):
                continue
            raw = event_item.get("raw") if isinstance(event_item.get("raw"), dict) else event_item
            if is_canceled(raw) or is_declined(raw) or is_free(raw):
                continue
            interval = event_interval(raw, tzinfo)
            if not interval:
                continue
            buffered = Interval(
                interval.start - timedelta(minutes=buffer_before),
                interval.end + timedelta(minutes=buffer_after),
            )
            clipped = clip_interval(buffered, start, end)
            if clipped:
                busy_blocks.append(
                    BusyBlock(
                        participant_id=pid,
                        title=event_title(raw),
                        interval=clipped,
                        source=str(event_item.get("source") or raw.get("source") or ""),
                    )
                )

        busy_intervals = [block.interval for block in busy_blocks]
        free = subtract_intervals(allowed, busy_intervals)
        participants.append(
            Participant(
                id=pid,
                label=participant_label(item, pid),
                email=str(item.get("email") or ""),
                required=bool(item.get("required", True)),
                availability=merge_intervals(allowed),
                busy=busy_blocks,
                free=free,
            )
        )

    return participants


def round_up_to_step(value: datetime, step_minutes: int) -> datetime:
    midnight = datetime.combine(value.date(), time.min, tzinfo=value.tzinfo)
    minutes = int((value - midnight).total_seconds() // 60)
    remainder = minutes % step_minutes
    if remainder == 0 and value.second == 0 and value.microsecond == 0:
        return value.replace(second=0, microsecond=0)
    rounded_minutes = minutes + (step_minutes - remainder)
    return midnight + timedelta(minutes=rounded_minutes)


def build_slots(payload: dict[str, Any]) -> tuple[list[Slot], list[Participant], dict[str, Any]]:
    range_start, range_end, _tzinfo, timezone_name = date_range_from_payload(payload)
    duration = request_duration(payload)
    step = request_step(payload)
    request = request_obj(payload)
    max_results = int(request.get("max_results") or payload.get("max_results") or 10)
    if max_results <= 0:
        raise SystemExit("max_results must be positive")

    participants = parse_participants(payload)
    required = [participant for participant in participants if participant.required]
    optional = [participant for participant in participants if not participant.required]
    if not required:
        raise SystemExit("at least one required participant is needed")

    common = intersect_many([participant.free for participant in required])
    slots: list[Slot] = []
    slot_index = 1
    for interval in common:
        cursor = round_up_to_step(interval.start, step)
        while cursor + timedelta(minutes=duration) <= interval.end:
            slot_end = cursor + timedelta(minutes=duration)
            optional_available = []
            optional_conflicts: dict[str, list[str]] = {}
            for participant in optional:
                slot_interval = Interval(cursor, slot_end)
                if any(contains_interval(free_interval, slot_interval) for free_interval in participant.free):
                    optional_available.append(participant.label)
                else:
                    optional_conflicts[participant.label] = conflicts_for_interval(participant, slot_interval)
            slots.append(
                Slot(
                    id=f"slot-{slot_index:03d}",
                    start=cursor,
                    end=slot_end,
                    required_participants=[participant.label for participant in required],
                    optional_available=optional_available,
                    optional_conflicts=optional_conflicts,
                )
            )
            slot_index += 1
            if len(slots) >= max_results:
                metadata = {
                    "range_start": iso(range_start),
                    "range_end": iso(range_end),
                    "timezone": timezone_name,
                    "duration_minutes": duration,
                    "step_minutes": step,
                    "max_results": max_results,
                }
                return slots, participants, metadata
            cursor += timedelta(minutes=step)

    metadata = {
        "range_start": iso(range_start),
        "range_end": iso(range_end),
        "timezone": timezone_name,
        "duration_minutes": duration,
        "step_minutes": step,
        "max_results": max_results,
    }
    return slots, participants, metadata


def contains_interval(container: Interval, candidate: Interval) -> bool:
    return container.start <= candidate.start and container.end >= candidate.end


def intervals_overlap(left: Interval, right: Interval) -> bool:
    return left.start < right.end and right.start < left.end


def conflicts_for_interval(participant: Participant, interval: Interval) -> list[str]:
    return [
        f"{block.title} {format_datetime_range(block.interval.start, block.interval.end)}"
        for block in participant.busy
        if intervals_overlap(block.interval, interval)
    ]


def validate_slot(payload: dict[str, Any], start: datetime, end: datetime) -> dict[str, Any]:
    if end <= start:
        raise SystemExit("slot end must be after slot start")
    interval = Interval(start, end)
    participants = parse_participants(payload)
    participant_results = []
    all_required_available = True
    for participant in participants:
        available = any(contains_interval(free_interval, interval) for free_interval in participant.free)
        conflicts = [] if available else conflicts_for_interval(participant, interval)
        if participant.required and not available:
            all_required_available = False
        participant_results.append(
            {
                "id": participant.id,
                "label": participant.label,
                "required": participant.required,
                "available": available,
                "conflicts": conflicts,
            }
        )
    return {
        "available": all_required_available,
        "slot": {"start": iso(start), "end": iso(end), "minutes": int((end - start).total_seconds() // 60)},
        "participants": participant_results,
    }


def slots_to_json(slots: list[Slot], participants: list[Participant], metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "metadata": metadata,
        "participants": [
            {
                "id": participant.id,
                "label": participant.label,
                "email": participant.email,
                "required": participant.required,
                "free": [{"start": iso(interval.start), "end": iso(interval.end)} for interval in participant.free],
            }
            for participant in participants
        ],
        "slots": [
            {
                "id": slot.id,
                "start": iso(slot.start),
                "end": iso(slot.end),
                "minutes": slot.minutes,
                "required_participants": slot.required_participants,
                "optional_available": slot.optional_available,
                "optional_conflicts": slot.optional_conflicts,
            }
            for slot in slots
        ],
    }


def render_slots_markdown(slots: list[Slot], participants: list[Participant], metadata: dict[str, Any]) -> str:
    lines = [
        "**Scheduler Candidates**",
        "",
        f"Resolved window: `{metadata['range_start']}` to `{metadata['range_end']}`",
        f"Timezone: `{metadata['timezone']}`",
        f"Duration: {metadata['duration_minutes']} min",
        "Participants: "
        + "; ".join(
            f"{participant.label} ({'required' if participant.required else 'optional'})" for participant in participants
        ),
        "",
    ]
    if slots:
        lines.extend(["| Rank | Slot | Required | Optional |", "|---:|---|---|---|"])
        for rank, slot in enumerate(slots, start=1):
            optional = ", ".join(slot.optional_available) if slot.optional_available else "-"
            if slot.optional_conflicts:
                conflict_text = "conflicts: " + ", ".join(sorted(slot.optional_conflicts))
                optional = f"{optional}; {conflict_text}" if optional != "-" else conflict_text
            lines.append(
                f"| {rank} | {md_escape(format_datetime_range(slot.start, slot.end))} | "
                f"{md_escape(', '.join(slot.required_participants))} | {md_escape(optional)} |"
            )
    else:
        lines.append("No mutual slots found for the required participants.")
    lines.extend(
        [
            "",
            "**Guardrail**",
            "- No calendar event has been created or updated.",
            "- Use `action-plan` after the user confirms a specific slot and operation.",
        ]
    )
    return "\n".join(lines)


def render_validate_markdown(result: dict[str, Any]) -> str:
    lines = [
        "**Scheduler Slot Validation**",
        "",
        f"Slot: `{result['slot']['start']}` to `{result['slot']['end']}`",
        f"Available for required participants: {'yes' if result['available'] else 'no'}",
        "",
        "| Participant | Required | Available | Conflicts |",
        "|---|---|---|---|",
    ]
    for participant in result["participants"]:
        conflicts = "; ".join(participant["conflicts"]) if participant["conflicts"] else "-"
        lines.append(
            f"| {md_escape(participant['label'])} | {'yes' if participant['required'] else 'no'} | "
            f"{'yes' if participant['available'] else 'no'} | {md_escape(conflicts)} |"
        )
    lines.extend(["", "No calendar event has been created or updated."])
    return "\n".join(lines)


def find_slot(slots: list[Slot], slot_id: str) -> Slot:
    for slot in slots:
        if slot.id == slot_id:
            return slot
    raise SystemExit(f"slot_id not found: {slot_id}")


def action_plan(payload: dict[str, Any], action: str, slot_id: str | None, event_id: str | None) -> dict[str, Any]:
    if action not in {"create", "update"}:
        raise SystemExit("action must be create or update")
    slots, participants, metadata = build_slots(payload)
    if not slots:
        raise SystemExit("no candidate slots available for action plan")
    slot = find_slot(slots, slot_id or slots[0].id)
    request = request_obj(payload)
    target = request.get("target_calendar") if isinstance(request.get("target_calendar"), dict) else {}
    title = str(request.get("title") or "Meeting")
    timezone_name = metadata["timezone"]
    attendees = [
        {"email": participant.email, "name": participant.label, "required": participant.required}
        for participant in participants
        if participant.email
    ]
    plan = {
        "action": action,
        "requires_confirmation": True,
        "confirmation_text": (
            f"Create `{title}` on {format_datetime_range(slot.start, slot.end)}?"
            if action == "create"
            else f"Update `{title}` to {format_datetime_range(slot.start, slot.end)}?"
        ),
        "target_calendar": {
            "source": target.get("source") or request.get("source") or "unspecified",
            "calendar_id": target.get("calendar_id") or request.get("calendar_id") or "",
            "calendar_label": target.get("calendar_label") or request.get("calendar_label") or "",
        },
        "event": {
            "event_id": event_id or request.get("event_id") or "",
            "title": title,
            "start": iso(slot.start),
            "end": iso(slot.end),
            "timezone": timezone_name,
            "duration_minutes": slot.minutes,
            "attendees": attendees,
            "location": request.get("location") or "",
            "conference_requested": bool(request.get("conference_requested", True)),
            "description": request.get("description") or "",
        },
    }
    return plan


def render_action_plan_markdown(plan: dict[str, Any]) -> str:
    event = plan["event"]
    target = plan["target_calendar"]
    attendee_text = ", ".join(
        attendee.get("name") or attendee.get("email") for attendee in event["attendees"]
    ) or "-"
    lines = [
        f"**Scheduler Action Plan - {plan['action'].title()} Event**",
        "",
        "No calendar event has been created or updated.",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Title | {md_escape(event['title'])} |",
        f"| Time | `{event['start']}` to `{event['end']}` |",
        f"| Timezone | `{event['timezone']}` |",
        f"| Attendees | {md_escape(attendee_text)} |",
        f"| Target calendar | {md_escape(target['source'])} {md_escape(target['calendar_label'] or target['calendar_id'])} |",
        f"| Confirmation required | {'yes' if plan['requires_confirmation'] else 'no'} |",
        "",
        f"Confirmation prompt: {plan['confirmation_text']}",
    ]
    return "\n".join(lines)


def cmd_window(args: argparse.Namespace) -> int:
    tzinfo, timezone_name = resolve_timezone(args.timezone)
    start = datetime.combine(parse_date(args.start_date, "start-date"), time.min, tzinfo=tzinfo)
    end = datetime.combine(parse_date(args.end_date, "end-date"), time.min, tzinfo=tzinfo)
    if end <= start:
        raise SystemExit("end-date must be after start-date")
    print(
        json.dumps(
            {
                "start": iso(start),
                "end": iso(end),
                "timezone": timezone_name,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_rank_slots(args: argparse.Namespace) -> int:
    payload = read_json(args.input)
    slots, participants, metadata = build_slots(payload)
    if args.format == "json":
        print(json.dumps(slots_to_json(slots, participants, metadata), indent=2, sort_keys=True))
    else:
        print(render_slots_markdown(slots, participants, metadata))
    return 0


def cmd_validate_slot(args: argparse.Namespace) -> int:
    payload = read_json(args.input)
    _range_start, _range_end, tzinfo, _timezone_name = date_range_from_payload(payload)
    result = validate_slot(payload, parse_dt(args.start, tzinfo), parse_dt(args.end, tzinfo))
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_validate_markdown(result))
    return 0


def cmd_action_plan(args: argparse.Namespace) -> int:
    payload = read_json(args.input)
    plan = action_plan(payload, args.action, args.slot_id, args.event_id)
    if args.format == "json":
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(render_action_plan_markdown(plan))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic meeting scheduler.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    window = subparsers.add_parser("window", help="Print exact date-range query bounds.")
    window.add_argument("--start-date", required=True, help="Inclusive start date as YYYY-MM-DD.")
    window.add_argument("--end-date", required=True, help="Exclusive end date as YYYY-MM-DD.")
    window.add_argument("--timezone", help="IANA or supported Windows timezone. Defaults to local timezone.")
    window.set_defaults(func=cmd_window)

    rank = subparsers.add_parser("rank-slots", help="Rank candidate meeting slots from JSON availability.")
    rank.add_argument("--input", "-i", help="Input JSON file. Defaults to stdin.")
    rank.add_argument("--format", choices=("markdown", "json"), default="markdown")
    rank.set_defaults(func=cmd_rank_slots)

    validate = subparsers.add_parser("validate-slot", help="Validate one proposed slot against availability.")
    validate.add_argument("--input", "-i", help="Input JSON file. Defaults to stdin.")
    validate.add_argument("--start", required=True, help="Slot start ISO timestamp.")
    validate.add_argument("--end", required=True, help="Slot end ISO timestamp.")
    validate.add_argument("--format", choices=("markdown", "json"), default="markdown")
    validate.set_defaults(func=cmd_validate_slot)

    action = subparsers.add_parser("action-plan", help="Build a reviewed create/update plan for a chosen slot.")
    action.add_argument("--input", "-i", help="Input JSON file. Defaults to stdin.")
    action.add_argument("--action", choices=("create", "update"), required=True)
    action.add_argument("--slot-id", help="Candidate slot id. Defaults to first ranked slot.")
    action.add_argument("--event-id", help="Existing event id for update plans.")
    action.add_argument("--format", choices=("markdown", "json"), default="markdown")
    action.set_defaults(func=cmd_action_plan)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
