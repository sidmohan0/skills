#!/usr/bin/env python3
"""Deterministic daily calendar normalization and rendering.

This script does not call calendar providers. Agents provide connector payloads
as JSON, and the script owns the repeatable agenda math.
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

ACTION_WORDS_RE = re.compile(
    r"\b(agenda|action|todo|to-do|follow up|follow-up|prep|prepare|review|"
    r"decision|decide|bring|read|draft|send)\b",
    re.IGNORECASE,
)
DOC_LINK_RE = re.compile(
    r"https?://\S+|docs\.google\.com|drive\.google\.com|notion\.so|"
    r"dropbox\.com|sharepoint\.com",
    re.IGNORECASE,
)


@dataclass
class Source:
    source_order: int
    source: str
    status: str
    account_label: str = ""
    calendar_label: str = ""
    calendar_id: str = ""
    error: str = ""

    @property
    def display_source(self) -> str:
        return title_source(self.source)

    @property
    def display_label(self) -> str:
        label = self.account_label or self.calendar_label or self.calendar_id
        return label or "unknown"


@dataclass
class Event:
    source_order: int
    source: str
    account_label: str
    calendar_label: str
    event_id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    timezone_name: str = ""
    status: str = ""
    self_response: str = ""
    transparency: str = ""
    privacy: str = ""
    recurrence: bool = False
    organizer: str = ""
    attendee_count: int | None = None
    location: str = ""
    conference_summary: str = ""
    conference_key: str = ""
    description_flags: list[str] = field(default_factory=list)
    canceled: bool = False
    raw_kind: str = ""
    source_labels: list[str] = field(default_factory=list)
    note_flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.source_labels:
            self.source_labels = [title_source(self.source)]

    @property
    def source_display(self) -> str:
        return " + ".join(dict.fromkeys(self.source_labels))

    @property
    def status_lower(self) -> str:
        return (self.status or "").lower()

    @property
    def response_lower(self) -> str:
        return (self.self_response or "").lower()

    @property
    def transparency_lower(self) -> str:
        return (self.transparency or "").lower()

    @property
    def is_declined(self) -> bool:
        return self.response_lower == "declined" or self.status_lower == "declined"

    @property
    def is_tentative(self) -> bool:
        return self.response_lower == "tentative" or self.status_lower == "tentative"

    @property
    def is_free(self) -> bool:
        return self.transparency_lower in {"transparent", "free"} or self.status_lower == "free"

    @property
    def is_oof(self) -> bool:
        return self.status_lower in {"oof", "outofoffice", "out_of_office", "out-of-office"}

    @property
    def is_busy_for_conflict(self) -> bool:
        return not self.all_day and not self.canceled and not self.is_declined and not self.is_free

    @property
    def has_place_or_conference(self) -> bool:
        return bool(self.location or self.conference_summary or self.conference_key)

    @property
    def place_key(self) -> str:
        value = self.conference_key or self.conference_summary or self.location
        return normalize_key(value)


@dataclass
class RenderResult:
    resolved_date: str
    timezone: str
    window_start: str
    window_end: str
    sources: list[Source]
    events: list[Event]
    excluded_events: list[Event]
    possible_duplicates: list[str]
    conflicts: list[str]
    tight_transitions: list[str]
    free_windows: list[str]
    prep_hints: list[str]
    markdown: str


def title_source(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized == "google":
        return "Google"
    if normalized in {"outlook", "microsoft_outlook", "microsoft-outlook"}:
        return "Outlook"
    if normalized in {"local", "macos", "apple_calendar"}:
        return "Local"
    return (value or "Unknown").strip().title() or "Unknown"


def normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("|", "/")


def read_json(path: str | None) -> dict[str, Any]:
    if path and path != "-":
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return json.load(sys.stdin)


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


def requested_timezone_name(request: dict[str, Any], payload: dict[str, Any]) -> str | None:
    value = request.get("timezone") or payload.get("timezone")
    return str(value) if value else None


def parse_date(value: str | None, tzinfo: ZoneInfo | timezone) -> date:
    if value:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise SystemExit(f"Date must be YYYY-MM-DD: {value}") from exc
    return datetime.now(tzinfo).date()


def day_window(target_date: date, tzinfo: ZoneInfo | timezone) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date, time.min, tzinfo=tzinfo)
    return start, start + timedelta(days=1)


def iso_with_offset(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def parse_time_of_day(value: str, field_name: str) -> time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except Exception as exc:  # noqa: BLE001 - convert any parse error to CLI error.
        raise SystemExit(f"{field_name} must be HH:MM: {value}") from exc


def parse_dt(value: Any, fallback_tz: ZoneInfo | timezone) -> tuple[datetime, bool]:
    if isinstance(value, dict):
        if value.get("date"):
            raw_date = date.fromisoformat(value["date"])
            return datetime.combine(raw_date, time.min, tzinfo=fallback_tz), True
        dt_value = value.get("dateTime") or value.get("datetime")
        event_tz = tz_from_name(value.get("timeZone") or value.get("timezone")) if (
            value.get("timeZone") or value.get("timezone")
        ) else fallback_tz
        return parse_dt(dt_value, event_tz)[0].astimezone(fallback_tz), False
    if not value:
        raise ValueError("missing datetime")
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raw_date = date.fromisoformat(text)
        return datetime.combine(raw_date, time.min, tzinfo=fallback_tz), True
    iso_text = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(iso_text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=fallback_tz)
    return parsed.astimezone(fallback_tz), False


def first_present(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def get_nested(raw: dict[str, Any], *keys: str) -> Any:
    current: Any = raw
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def source_key(source: dict[str, Any]) -> tuple[str, str, str]:
    return (
        normalize_key(str(source.get("source", ""))),
        normalize_key(str(source.get("account_label", ""))),
        normalize_key(str(source.get("calendar_label", "") or source.get("calendar_id", ""))),
    )


def parse_sources(payload: dict[str, Any]) -> list[Source]:
    sources = []
    for index, item in enumerate(payload.get("sources") or [], start=1):
        sources.append(
            Source(
                source_order=int(item.get("source_order") or index),
                source=str(item.get("source") or "unknown"),
                status=str(item.get("status") or "unknown"),
                account_label=str(item.get("account_label") or ""),
                calendar_label=str(item.get("calendar_label") or item.get("calendar_name") or ""),
                calendar_id=str(item.get("calendar_id") or ""),
                error=str(item.get("error") or ""),
            )
        )
    return sources


def source_lookup(sources: list[Source]) -> dict[tuple[str, str, str], Source]:
    lookup = {}
    for source in sources:
        lookup[source_key(asdict(source))] = source
        lookup[(normalize_key(source.source), "", "")] = source
    return lookup


def normalize_event(
    item: dict[str, Any],
    sources: list[Source],
    fallback_tz: ZoneInfo | timezone,
    timezone_name: str,
) -> Event | None:
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else item
    source_name = str(item.get("source") or raw.get("source") or raw.get("provider") or "")
    if not source_name:
        source_name = infer_source(raw)
    account_label = str(item.get("account_label") or raw.get("account_label") or "")
    calendar_label = str(
        item.get("calendar_label")
        or item.get("calendar_name")
        or raw.get("calendar_label")
        or raw.get("calendar_name")
        or raw.get("calendar_id")
        or ""
    )
    event_id = str(item.get("event_id") or raw.get("id") or raw.get("event_id") or "")

    source_map = source_lookup(sources)
    source = (
        source_map.get((normalize_key(source_name), normalize_key(account_label), normalize_key(calendar_label)))
        or source_map.get((normalize_key(source_name), "", ""))
    )
    source_order = int(item.get("source_order") or (source.source_order if source else len(sources) + 1))
    if source:
        account_label = account_label or source.account_label
        calendar_label = calendar_label or source.calendar_label or source.calendar_id

    start_value = first_present(raw, "start", "start_datetime", "startDateTime")
    end_value = first_present(raw, "end", "end_datetime", "endDateTime")
    if start_value is None or end_value is None:
        return None

    start, start_all_day = parse_dt(start_value, fallback_tz)
    end, end_all_day = parse_dt(end_value, fallback_tz)
    all_day = bool(raw.get("all_day") or raw.get("isAllDay") or start_all_day or end_all_day)

    status = normalize_status(raw)
    self_response = normalize_response(raw)
    title = str(first_present(raw, "summary", "display_title", "subject", "title") or "(untitled)")
    organizer = normalize_organizer(raw)
    attendees = raw.get("attendees") if isinstance(raw.get("attendees"), list) else []
    location = normalize_location(raw)
    conference_summary, conference_key = normalize_conference(raw)
    description = normalize_description(raw)
    description_flags = description_flags_from_text(description)
    recurrence = bool(raw.get("recurrence") or raw.get("recurring_event_id") or raw.get("seriesMasterId"))
    canceled = bool(
        str(raw.get("status") or "").lower() in {"cancelled", "canceled", "deleted"}
        or raw.get("isCancelled")
        or raw.get("is_canceled")
    )

    return Event(
        source_order=source_order,
        source=source_name or "unknown",
        account_label=account_label,
        calendar_label=calendar_label,
        event_id=event_id,
        title=title,
        start=start,
        end=end,
        all_day=all_day,
        timezone_name=timezone_name,
        status=status,
        self_response=self_response,
        transparency=normalize_transparency(raw),
        privacy=normalize_privacy(raw),
        recurrence=recurrence,
        organizer=organizer,
        attendee_count=len(attendees) if attendees else None,
        location=location,
        conference_summary=conference_summary,
        conference_key=conference_key,
        description_flags=description_flags,
        canceled=canceled,
        raw_kind=infer_source(raw),
    )


def infer_source(raw: dict[str, Any]) -> str:
    if "summary" in raw or "hangoutLink" in raw or "conferenceData" in raw:
        return "google"
    if "subject" in raw or "showAs" in raw or "onlineMeeting" in raw:
        return "outlook"
    return "unknown"


def normalize_status(raw: dict[str, Any]) -> str:
    show_as = str(raw.get("showAs") or raw.get("show_as") or "").strip()
    event_type = str(raw.get("event_type") or raw.get("type") or "").strip()
    if show_as:
        return show_as
    if event_type.lower() in {"outofoffice", "out_of_office", "out-of-office"}:
        return "out_of_office"
    return str(raw.get("status") or "").strip()


def normalize_response(raw: dict[str, Any]) -> str:
    direct = first_present(raw, "my_response_status", "self_response", "responseStatus")
    if isinstance(direct, dict):
        return str(direct.get("response") or direct.get("status") or "").strip()
    if direct:
        return str(direct).strip()
    attendees = raw.get("attendees") if isinstance(raw.get("attendees"), list) else []
    for attendee in attendees:
        if attendee.get("is_self") or attendee.get("isSelf"):
            return str(attendee.get("response_status") or get_nested(attendee, "status", "response") or "").strip()
    return ""


def normalize_transparency(raw: dict[str, Any]) -> str:
    transparency = str(raw.get("transparency") or "").strip()
    if transparency:
        return transparency
    show_as = str(raw.get("showAs") or raw.get("show_as") or "").strip().lower()
    if show_as == "free":
        return "free"
    return ""


def normalize_privacy(raw: dict[str, Any]) -> str:
    value = str(raw.get("visibility") or raw.get("sensitivity") or raw.get("privacy") or "").strip()
    return value


def normalize_organizer(raw: dict[str, Any]) -> str:
    organizer = raw.get("organizer")
    if isinstance(organizer, str):
        return organizer
    if isinstance(organizer, dict):
        email_address = organizer.get("emailAddress") if isinstance(organizer.get("emailAddress"), dict) else {}
        return str(
            organizer.get("displayName")
            or organizer.get("email")
            or email_address.get("name")
            or email_address.get("address")
            or ""
        ).strip()
    return str(raw.get("creator") or "").strip()


def normalize_location(raw: dict[str, Any]) -> str:
    location = raw.get("location")
    if isinstance(location, str):
        return re.sub(r"\s+", " ", location).strip()
    if isinstance(location, dict):
        return re.sub(
            r"\s+",
            " ",
            str(location.get("displayName") or location.get("address") or location.get("locationUri") or "").strip(),
        )
    locations = raw.get("locations")
    if isinstance(locations, list) and locations:
        names = [normalize_location({"location": item}) for item in locations]
        return "; ".join([name for name in names if name])
    return ""


def normalize_conference(raw: dict[str, Any]) -> tuple[str, str]:
    if raw.get("hangoutLink"):
        return "Google Meet", str(raw.get("hangoutLink"))
    conference_data = raw.get("conferenceData")
    if isinstance(conference_data, dict):
        solution = get_nested(conference_data, "conferenceSolution", "name")
        entry_points = conference_data.get("entryPoints") if isinstance(conference_data.get("entryPoints"), list) else []
        uri = ""
        for entry in entry_points:
            uri = str(entry.get("uri") or entry.get("meetingCode") or "")
            if uri:
                break
        if solution or uri:
            return str(solution or "Conference"), uri
    online = raw.get("onlineMeeting") or raw.get("online_meeting")
    if isinstance(online, dict):
        join_url = str(online.get("joinUrl") or online.get("join_url") or "")
        provider = str(raw.get("onlineMeetingProvider") or raw.get("online_meeting_provider") or "")
        summary = "Microsoft Teams" if "teams" in join_url.lower() or "teams" in provider.lower() else "Online meeting"
        return summary, join_url
    if raw.get("isOnlineMeeting") or raw.get("is_online_meeting"):
        provider = str(raw.get("onlineMeetingProvider") or raw.get("online_meeting_provider") or "")
        return provider or "Online meeting", provider
    return "", ""


def normalize_description(raw: dict[str, Any]) -> str:
    body = raw.get("body")
    if isinstance(body, dict):
        body = body.get("content") or body.get("contentText")
    return str(raw.get("description") or raw.get("bodyPreview") or body or "")


def description_flags_from_text(text: str) -> list[str]:
    flags = []
    if not text:
        return flags
    if re.search(r"\bagenda\b", text, re.IGNORECASE):
        flags.append("agenda")
    if DOC_LINK_RE.search(text):
        flags.append("doc links")
    if ACTION_WORDS_RE.search(text):
        flags.append("action words")
    return list(dict.fromkeys(flags))


def event_sort_key(event: Event) -> tuple[Any, ...]:
    return (
        0 if event.all_day else 1,
        event.start,
        event.end,
        event.source_order,
        normalize_key(event.calendar_label),
        normalize_key(event.title),
        event.event_id,
    )


def dedupe_events(events: list[Event]) -> tuple[list[Event], list[str]]:
    sorted_events = sorted(events, key=event_sort_key)
    consumed: set[int] = set()
    output: list[Event] = []
    possible_duplicates: list[str] = []

    for index, event in enumerate(sorted_events):
        if index in consumed:
            continue
        duplicate_indexes = []
        possible_indexes = []
        for candidate_index in range(index + 1, len(sorted_events)):
            candidate = sorted_events[candidate_index]
            if candidate_index in consumed:
                continue
            same_title_time = (
                normalize_key(event.title) == normalize_key(candidate.title)
                and event.start == candidate.start
                and event.end == candidate.end
            )
            if not same_title_time:
                continue
            same_source = normalize_key(event.source) == normalize_key(candidate.source)
            matching_evidence = bool(
                event.organizer
                and candidate.organizer
                and normalize_key(event.organizer) == normalize_key(candidate.organizer)
            ) or bool(
                event.conference_key
                and candidate.conference_key
                and normalize_key(event.conference_key) == normalize_key(candidate.conference_key)
            ) or bool(
                event.location
                and candidate.location
                and normalize_key(event.location) == normalize_key(candidate.location)
            )
            if not same_source and matching_evidence:
                duplicate_indexes.append(candidate_index)
            elif not same_source:
                possible_indexes.append(candidate_index)

        if duplicate_indexes:
            merged = event
            for duplicate_index in duplicate_indexes:
                duplicate = sorted_events[duplicate_index]
                merged.source_labels.extend(duplicate.source_labels)
                consumed.add(duplicate_index)
                merged.attendee_count = max_count(merged.attendee_count, duplicate.attendee_count)
                merged.description_flags = list(dict.fromkeys(merged.description_flags + duplicate.description_flags))
                merged.note_flags = list(dict.fromkeys(merged.note_flags + duplicate.note_flags))
            merged.source_labels = list(dict.fromkeys(merged.source_labels))
            output.append(merged)
        else:
            output.append(event)

        for possible_index in possible_indexes:
            candidate = sorted_events[possible_index]
            event.note_flags.append("possible duplicate")
            candidate.note_flags.append("possible duplicate")
            possible_duplicates.append(
                f"{event.title} at {format_time_range(event)} appears in {event.source_display} "
                f"and {candidate.source_display} but lacks matching organizer, conference, or location."
            )

    return sorted(output, key=event_sort_key), list(dict.fromkeys(possible_duplicates))


def max_count(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def analyze_events(
    events: list[Event],
    target_date: date,
    tzinfo: ZoneInfo | timezone,
    workday_start: time,
    workday_end: time,
) -> tuple[list[str], list[str], list[str], list[str]]:
    conflicts: list[str] = []
    tight_transitions: list[str] = []
    prep_hints: list[str] = []

    timed = [event for event in events if not event.all_day and not event.canceled and not event.is_declined]
    busy = [event for event in timed if event.is_busy_for_conflict]
    busy_sorted = sorted(busy, key=lambda event: (event.start, event.end, event.title, event.event_id))

    for left_index, left in enumerate(busy_sorted):
        for right in busy_sorted[left_index + 1 :]:
            if right.start >= left.end:
                break
            minutes = int((min(left.end, right.end) - max(left.start, right.start)).total_seconds() // 60)
            if minutes >= 1:
                tentative = " (tentative involved)" if left.is_tentative or right.is_tentative else ""
                conflicts.append(
                    f"{left.title} overlaps {right.title} by {minutes} min{tentative}."
                )
                left.note_flags.append("conflict")
                right.note_flags.append("conflict")

    transition_events = sorted(timed, key=lambda event: (event.start, event.end, event.title, event.event_id))
    for previous, current in zip(transition_events, transition_events[1:]):
        gap_minutes = int((current.start - previous.end).total_seconds() // 60)
        if gap_minutes < 0 or gap_minutes >= 10:
            continue
        different_place = previous.place_key != current.place_key
        has_place = previous.has_place_or_conference or current.has_place_or_conference
        if has_place or different_place:
            tight_transitions.append(
                f"{previous.title} to {current.title} has {gap_minutes} min between events."
            )
            previous.note_flags.append("tight transition")
            current.note_flags.append("tight transition")

    for event in events:
        if event.description_flags:
            prep_hints.append(f"{event.title}: {', '.join(event.description_flags)}.")

    free_windows = compute_free_windows(busy_sorted, target_date, tzinfo, workday_start, workday_end)
    return (
        list(dict.fromkeys(conflicts)),
        list(dict.fromkeys(tight_transitions)),
        free_windows,
        list(dict.fromkeys(prep_hints)),
    )


def compute_free_windows(
    busy_events: list[Event],
    target_date: date,
    tzinfo: ZoneInfo | timezone,
    workday_start: time,
    workday_end: time,
) -> list[str]:
    start = datetime.combine(target_date, workday_start, tzinfo=tzinfo)
    end = datetime.combine(target_date, workday_end, tzinfo=tzinfo)
    intervals: list[tuple[datetime, datetime]] = []
    for event in busy_events:
        clipped_start = max(event.start, start)
        clipped_end = min(event.end, end)
        if clipped_start < clipped_end:
            intervals.append((clipped_start, clipped_end))
    intervals.sort()

    merged: list[tuple[datetime, datetime]] = []
    for interval_start, interval_end in intervals:
        if not merged or interval_start > merged[-1][1]:
            merged.append((interval_start, interval_end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], interval_end))

    cursor = start
    windows = []
    for interval_start, interval_end in merged:
        if interval_start > cursor and (interval_start - cursor) >= timedelta(minutes=30):
            windows.append(f"{format_time(cursor)}-{format_time(interval_start)}")
        cursor = max(cursor, interval_end)
    if end > cursor and (end - cursor) >= timedelta(minutes=30):
        windows.append(f"{format_time(cursor)}-{format_time(end)}")
    return windows


def format_time(value: datetime) -> str:
    hour = value.hour
    minute = value.minute
    suffix = "AM" if hour < 12 else "PM"
    hour_12 = hour % 12 or 12
    return f"{hour_12}:{minute:02d} {suffix}"


def format_time_range(event: Event) -> str:
    if event.all_day:
        return "All day"
    return f"{format_time(event.start)}-{format_time(event.end)}"


def format_month_day(target_date: date) -> str:
    return target_date.strftime("%B ") + str(target_date.day) + target_date.strftime(", %Y")


def source_status_line(sources: list[Source]) -> str:
    if not sources:
        return "Sources: none provided."
    parts = []
    for source in sorted(sources, key=lambda item: (item.source_order, item.display_source, item.display_label)):
        label = f"`{source.display_label}`"
        status = source.status or "unknown"
        detail = f" ({source.error})" if source.error else ""
        parts.append(f"{source.display_source} {label} {status}{detail}")
    return "Sources: " + "; ".join(parts) + "."


def event_important_info(event: Event) -> str:
    parts: list[str] = []
    if event.all_day:
        parts.append("all-day")
    if event.is_tentative:
        parts.append("tentative")
    if event.is_declined:
        parts.append("declined")
    if normalize_key(event.privacy) == "private":
        parts.append("private")
    if event.is_free:
        parts.append("transparent/free")
    if event.is_oof:
        parts.append("out-of-office")
    if event.recurrence:
        parts.append("recurring")
    if event.conference_summary:
        parts.append(event.conference_summary)
    if event.location:
        parts.append(event.location)
    if event.organizer:
        parts.append(f"organizer: {event.organizer}")
    if event.attendee_count is not None:
        noun = "attendee" if event.attendee_count == 1 else "attendees"
        parts.append(f"{event.attendee_count} {noun}")
    if event.self_response and normalize_key(event.self_response) not in {"declined", "tentative"}:
        parts.append(event.self_response)
    for flag in event.note_flags:
        parts.append(flag)
    if event.description_flags:
        parts.append("prep: " + ", ".join(event.description_flags))
    return "; ".join(md_escape(part) for part in parts) or "-"


def render_markdown(result: RenderResult) -> str:
    lines = [
        f"**Daily Calendar View \u2014 {format_month_day(date.fromisoformat(result.resolved_date))}**",
        "",
        f"Resolved window: `{result.window_start}` to `{result.window_end}`",
        f"Timezone: `{result.timezone}`",
        source_status_line(result.sources),
        "",
    ]

    if result.events:
        lines.extend(
            [
                "| Time | Source | Event | Important Info |",
                "|---|---|---|---|",
            ]
        )
        for event in result.events:
            lines.append(
                f"| {md_escape(format_time_range(event))} | {md_escape(event.source_display)} | "
                f"{md_escape(event.title)} | {event_important_info(event)} |"
            )
    else:
        lines.append("No events found for this date.")

    lines.extend(["", "**Things To Know**"])
    if result.conflicts:
        lines.extend(f"- Conflict: {md_escape(conflict)}" for conflict in result.conflicts)
    else:
        lines.append("- Conflict: none found.")
    if result.tight_transitions:
        lines.extend(f"- Tight transition: {md_escape(item)}" for item in result.tight_transitions)
    if result.possible_duplicates:
        lines.extend(f"- Possible duplicate: {md_escape(item)}" for item in result.possible_duplicates)
    if result.free_windows:
        lines.extend(f"- Free window: {window}." for window in result.free_windows)
    else:
        lines.append("- Free window: none 30 minutes or longer during the workday.")
    if result.prep_hints:
        lines.extend(f"- Prep: {md_escape(hint)}" for hint in result.prep_hints)
    else:
        lines.append("- Prep: none found.")

    return "\n".join(lines)


def render_payload(payload: dict[str, Any]) -> RenderResult:
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    tzinfo, timezone_name = resolve_timezone(requested_timezone_name(request, payload))
    target_date = parse_date(str(request.get("date")) if request.get("date") else payload.get("date"), tzinfo)
    start, end = day_window(target_date, tzinfo)
    window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
    window_start = str(window.get("start") or iso_with_offset(start))
    window_end = str(window.get("end") or iso_with_offset(end))
    workday = request.get("workday") if isinstance(request.get("workday"), list) else []
    workday_start = parse_time_of_day(str(request.get("workday_start") or (workday[0] if workday else "09:00")), "workday_start")
    workday_end = parse_time_of_day(str(request.get("workday_end") or (workday[1] if len(workday) > 1 else "17:00")), "workday_end")

    sources = parse_sources(payload)
    normalized = [
        event
        for item in payload.get("events") or []
        if isinstance(item, dict)
        for event in [normalize_event(item, sources, tzinfo, timezone_name)]
        if event is not None
    ]
    excluded = sorted([event for event in normalized if event.canceled], key=event_sort_key)
    active = [event for event in normalized if not event.canceled]
    events, possible_duplicates = dedupe_events(active)
    conflicts, tight_transitions, free_windows, prep_hints = analyze_events(
        events, target_date, tzinfo, workday_start, workday_end
    )
    result = RenderResult(
        resolved_date=target_date.isoformat(),
        timezone=timezone_name,
        window_start=window_start,
        window_end=window_end,
        sources=sources,
        events=events,
        excluded_events=excluded,
        possible_duplicates=possible_duplicates,
        conflicts=conflicts,
        tight_transitions=tight_transitions,
        free_windows=free_windows,
        prep_hints=prep_hints,
        markdown="",
    )
    result.markdown = render_markdown(result)
    return result


def details_needed(payload: dict[str, Any]) -> list[dict[str, str]]:
    needed = []
    sources = parse_sources(payload)
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    tzinfo, timezone_name = resolve_timezone(requested_timezone_name(request, payload))
    for item in payload.get("events") or []:
        if not isinstance(item, dict):
            continue
        event = normalize_event(item, sources, tzinfo, timezone_name)
        if event is None or event.canceled:
            continue
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else item
        missing = []
        if "attendees" not in raw:
            missing.append("attendees")
        if not normalize_organizer(raw):
            missing.append("organizer")
        if not normalize_conference(raw)[0] and not normalize_location(raw):
            missing.append("conference_or_location")
        if "recurrence" not in raw and "recurring_event_id" not in raw and "seriesMasterId" not in raw:
            missing.append("recurrence")
        if missing and event.event_id:
            needed.append(
                {
                    "source": event.source,
                    "calendar_label": event.calendar_label,
                    "event_id": event.event_id,
                    "missing": ",".join(missing),
                }
            )
    return needed


def json_safe_result(result: RenderResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["events"] = [json_safe_event(event) for event in result.events]
    payload["excluded_events"] = [json_safe_event(event) for event in result.excluded_events]
    return payload


def json_safe_event(event: Event) -> dict[str, Any]:
    data = asdict(event)
    data["start"] = iso_with_offset(event.start)
    data["end"] = iso_with_offset(event.end)
    return data


def cmd_window(args: argparse.Namespace) -> int:
    tzinfo, timezone_name = resolve_timezone(args.timezone)
    target_date = parse_date(args.date, tzinfo)
    start, end = day_window(target_date, tzinfo)
    print(
        json.dumps(
            {
                "date": target_date.isoformat(),
                "timezone": timezone_name,
                "start": iso_with_offset(start),
                "end": iso_with_offset(end),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    result = render_payload(read_json(args.input))
    if args.format == "json":
        print(json.dumps(json_safe_result(result), indent=2, sort_keys=True))
    else:
        print(result.markdown)
    return 0


def cmd_details_needed(args: argparse.Namespace) -> int:
    needed = details_needed(read_json(args.input))
    print(json.dumps({"details_needed": needed}, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic daily calendar renderer.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    window = subparsers.add_parser("window", help="Print exact local-day query bounds.")
    window.add_argument("--date", help="Target date as YYYY-MM-DD. Defaults to today in timezone.")
    window.add_argument("--timezone", help="IANA or supported Windows timezone. Defaults to local timezone.")
    window.set_defaults(func=cmd_window)

    render = subparsers.add_parser("render", help="Render an agenda from a connector JSON envelope.")
    render.add_argument("--input", "-i", help="Input JSON file. Defaults to stdin.")
    render.add_argument("--format", choices=("markdown", "json"), default="markdown")
    render.set_defaults(func=cmd_render)

    details = subparsers.add_parser("details-needed", help="List event IDs that need full-detail reads.")
    details.add_argument("--input", "-i", help="Input JSON file. Defaults to stdin.")
    details.set_defaults(func=cmd_details_needed)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
