#!/usr/bin/env python3
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "daily_calendar_view.py"
FIXTURE = ROOT / "fixtures" / "mixed_day.json"


def run_script(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=True,
        capture_output=True,
        input=input_text,
        text=True,
    )
    return result.stdout


class DailyCalendarViewTests(unittest.TestCase):
    def test_window_uses_exact_local_day_bounds(self) -> None:
        output = run_script("window", "--date", "2026-06-29", "--timezone", "America/Los_Angeles")
        payload = json.loads(output)
        self.assertEqual(payload["date"], "2026-06-29")
        self.assertEqual(payload["timezone"], "America/Los_Angeles")
        self.assertEqual(payload["start"], "2026-06-29T00:00:00-07:00")
        self.assertEqual(payload["end"], "2026-06-30T00:00:00-07:00")

    def test_render_json_applies_calendar_rules(self) -> None:
        output = run_script("render", "--input", str(FIXTURE), "--format", "json")
        payload = json.loads(output)
        titles = [event["title"] for event in payload["events"]]

        self.assertEqual(payload["resolved_date"], "2026-06-29")
        self.assertEqual(payload["window_start"], "2026-06-29T00:00:00-07:00")
        self.assertEqual(payload["window_end"], "2026-06-30T00:00:00-07:00")
        self.assertNotIn("Canceled Event", titles)
        self.assertIn("Canceled Event", [event["title"] for event in payload["excluded_events"]])
        self.assertEqual(titles[0], "Company Holiday")

        team_sync = next(event for event in payload["events"] if event["title"] == "Team Sync")
        self.assertEqual(team_sync["source_labels"], ["Google", "Outlook"])
        self.assertIn("Team Sync overlaps Deep Work", "\n".join(payload["conflicts"]))
        self.assertTrue(any("One-on-one" in item for item in payload["possible_duplicates"]))
        self.assertEqual(payload["free_windows"], ["10:50 AM-2:00 PM", "2:30 PM-5:00 PM"])
        self.assertTrue(any("Client Review: agenda, doc links, action words." == item for item in payload["prep_hints"]))

    def test_render_markdown_is_stable_and_user_facing(self) -> None:
        markdown = run_script("render", "--input", str(FIXTURE))
        self.assertIn("**Daily Calendar View", markdown)
        self.assertIn("Sources: Google `personal@example.com` checked; Outlook `work@example.com` checked.", markdown)
        self.assertIn("| 9:00 AM-9:30 AM | Google + Outlook | Team Sync |", markdown)
        self.assertIn("- Conflict: Team Sync overlaps Deep Work by 10 min.", markdown)
        self.assertIn("- Free window: 10:50 AM-2:00 PM.", markdown)
        self.assertNotIn("| 3:00 PM-3:30 PM | Google | Canceled Event |", markdown)

    def test_details_needed_identifies_partial_records(self) -> None:
        output = run_script("details-needed", "--input", str(FIXTURE))
        payload = json.loads(output)
        ids = {item["event_id"] for item in payload["details_needed"]}
        self.assertIn("g-focus", ids)
        self.assertNotIn("g-canceled", ids)

    def test_render_without_timezone_uses_runtime_fallback(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        del payload["request"]["timezone"]
        output = run_script("render", "--format", "json", input_text=json.dumps(payload))
        rendered = json.loads(output)
        self.assertEqual(rendered["resolved_date"], "2026-06-29")
        self.assertTrue(rendered["timezone"])
        self.assertTrue(rendered["events"])


if __name__ == "__main__":
    unittest.main()
