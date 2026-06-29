#!/usr/bin/env python3
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scheduler.py"
FIXTURE = ROOT / "fixtures" / "raju_next_week.json"


def run_script(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


class SchedulerTests(unittest.TestCase):
    def test_window_outputs_exact_range_bounds(self) -> None:
        output = run_script(
            "window",
            "--start-date",
            "2026-07-06",
            "--end-date",
            "2026-07-11",
            "--timezone",
            "America/Los_Angeles",
        )
        payload = json.loads(output)
        self.assertEqual(payload["start"], "2026-07-06T00:00:00-07:00")
        self.assertEqual(payload["end"], "2026-07-11T00:00:00-07:00")
        self.assertEqual(payload["timezone"], "America/Los_Angeles")

    def test_rank_slots_finds_required_overlap_and_optional_conflicts(self) -> None:
        output = run_script("rank-slots", "--input", str(FIXTURE), "--format", "json")
        payload = json.loads(output)
        slots = payload["slots"]

        self.assertEqual(slots[0]["id"], "slot-001")
        self.assertEqual(slots[0]["start"], "2026-07-06T09:30:00-07:00")
        self.assertEqual(slots[0]["end"], "2026-07-06T10:00:00-07:00")
        self.assertEqual(slots[0]["required_participants"], ["Sid", "Raju"])
        self.assertIn("Priya", slots[0]["optional_conflicts"])
        self.assertEqual(slots[1]["start"], "2026-07-06T10:30:00-07:00")
        self.assertEqual(slots[1]["optional_available"], ["Priya"])

    def test_validate_slot_reports_required_conflict(self) -> None:
        output = run_script(
            "validate-slot",
            "--input",
            str(FIXTURE),
            "--start",
            "2026-07-06T10:00:00-07:00",
            "--end",
            "2026-07-06T10:30:00-07:00",
            "--format",
            "json",
        )
        payload = json.loads(output)
        self.assertFalse(payload["available"])
        raju = next(participant for participant in payload["participants"] if participant["label"] == "Raju")
        self.assertFalse(raju["available"])
        self.assertTrue(any("Customer call" in conflict for conflict in raju["conflicts"]))

    def test_action_plan_requires_confirmation_and_does_not_write(self) -> None:
        output = run_script(
            "action-plan",
            "--input",
            str(FIXTURE),
            "--action",
            "create",
            "--slot-id",
            "slot-002",
            "--format",
            "json",
        )
        payload = json.loads(output)
        self.assertEqual(payload["action"], "create")
        self.assertTrue(payload["requires_confirmation"])
        self.assertEqual(payload["event"]["title"], "Raju sync")
        self.assertEqual(payload["event"]["start"], "2026-07-06T10:30:00-07:00")
        self.assertEqual(payload["target_calendar"]["source"], "google")

    def test_markdown_mentions_guardrail(self) -> None:
        markdown = run_script("rank-slots", "--input", str(FIXTURE))
        self.assertIn("**Scheduler Candidates**", markdown)
        self.assertIn("No calendar event has been created or updated.", markdown)
        self.assertIn("| 1 | Mon Jul 6, 9:30 AM-10:00 AM | Sid, Raju | conflicts: Priya |", markdown)


if __name__ == "__main__":
    unittest.main()
