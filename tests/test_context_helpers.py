#!/usr/bin/env python3
import importlib.util
import json
import os
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


chrome_session = load_module(
    "chrome_session_context",
    REPO_ROOT / "browser-context" / "scripts" / "chrome_session_context.py",
)


def pad4(data):
    return data + (b"\x00" * ((4 - len(data) % 4) % 4))


def pickle_string(value):
    raw = value.encode("utf-8")
    return struct.pack("<i", len(raw)) + pad4(raw)


def pickle_string16(value):
    raw = value.encode("utf-16-le")
    return struct.pack("<i", len(value)) + pad4(raw)


def record(command_id, payload):
    body = bytes([command_id]) + payload
    return struct.pack("<H", len(body)) + body


def write_snss(path, records):
    path.write_bytes(b"SNSS\x03\x00\x00\x00" + b"".join(records))


class ChromeSessionContextTests(unittest.TestCase):
    def test_session_parser_maps_tabs_titles_pins_and_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "Sessions"
            session_dir.mkdir()
            session_path = session_dir / "Session_1"

            group_high = 0x1111222233334444
            group_low = 0xAAAABBBBCCCCDDDD
            group_key = f"{group_high:016x}:{group_low:016x}"
            tab_id = 101
            window_id = 501

            nav0 = (
                struct.pack("<iii", 0, tab_id, 0)
                + pickle_string("https://example.test/old")
                + pickle_string16("Old Title")
            )
            nav1 = (
                struct.pack("<iii", 0, tab_id, 1)
                + pickle_string("https://example.test/current")
                + pickle_string16("Current Title")
            )
            group_payload = (
                struct.pack("<i", tab_id)
                + b"\x00\x00\x00\x00"
                + struct.pack("<Q", group_high)
                + struct.pack("<Q", group_low)
                + b"\x01"
            )
            metadata_payload = (
                b"\x00\x00\x00\x00"
                + struct.pack("<Q", group_high)
                + struct.pack("<Q", group_low)
                + pickle_string16("Research")
                + struct.pack("<I", 4)
                + b"\x01\x00\x00\x00"
                + b"\x01\x00\x00\x00"
                + pickle_string("saved-guid-1")
            )

            write_snss(
                session_path,
                [
                    record(0, struct.pack("<ii", window_id, tab_id)),
                    record(2, struct.pack("<ii", tab_id, 3)),
                    record(6, nav0),
                    record(6, nav1),
                    record(7, struct.pack("<ii", tab_id, 1)),
                    record(12, struct.pack("<i", tab_id) + b"\x01"),
                    record(25, group_payload),
                    record(27, metadata_payload),
                ],
            )

            tabs, metadata = chrome_session.parse_session(str(session_path))
            self.assertIn(tab_id, tabs)
            self.assertTrue(tabs[tab_id]["pinned"])
            self.assertEqual(tabs[tab_id]["group"], group_key)
            self.assertEqual(tabs[tab_id]["visual_index"], 3)
            self.assertEqual(tabs[tab_id]["window_id"], window_id)
            self.assertEqual(
                chrome_session.selected_navigation(tabs[tab_id]),
                {"title": "Current Title", "url": "https://example.test/current"},
            )
            self.assertEqual(metadata[group_key]["title"], "Research")
            self.assertEqual(metadata[group_key]["color"], "4")
            self.assertEqual(metadata[group_key]["collapsed"], "true")
            self.assertEqual(metadata[group_key]["saved_guid"], "saved-guid-1")


class EditorStateContextTests(unittest.TestCase):
    def test_editor_state_script_extracts_workspace_active_selection_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "sample-project"
            project.mkdir()
            workspace = root / "Code" / "User" / "workspaceStorage" / "workspace123"
            workspace.mkdir(parents=True)
            (workspace / "workspace.json").write_text(
                json.dumps({"folder": "file://" + str(project)}),
                encoding="utf-8",
            )
            con = sqlite3.connect(workspace / "state.vscdb")
            con.execute("create table ItemTable (key text primary key, value text)")
            con.executemany(
                "insert into ItemTable values (?, ?)",
                [
                    (
                        "workbench.editor.activeEditor",
                        json.dumps(
                            {
                                "resource": "file://" + str(project / "app.py"),
                                "selection": {"startLineNumber": 7, "startColumn": 5},
                            }
                        ),
                    ),
                    (
                        "history.entries",
                        json.dumps({"entries": [{"resource": "file://" + str(project / "README.md")}]}),
                    ),
                    (
                        "workbench.panel.markers",
                        json.dumps(
                            {
                                "diagnostics": [
                                    {
                                        "resource": "file://" + str(project / "app.py"),
                                        "message": "unused import",
                                    }
                                ]
                            }
                        ),
                    ),
                ],
            )
            con.commit()
            con.close()

            script = REPO_ROOT / "editor-context" / "scripts" / "editor_state_context.py"
            result = subprocess.run(
                [sys.executable, str(script), str(project), str(root)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            output = result.stdout
            self.assertIn("### Persisted Workspaces", output)
            self.assertIn("sample-project", output)
            self.assertIn("### Active Editor Candidates", output)
            self.assertIn("app.py", output)
            self.assertIn("startLineNumber", output)
            self.assertIn("### Recent Editor Candidates", output)
            self.assertIn("README.md", output)
            self.assertIn("### Diagnostics Hints", output)
            self.assertIn("unused import", output)


if __name__ == "__main__":
    unittest.main()
