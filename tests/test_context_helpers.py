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
terminal_process = load_module(
    "terminal_process_context",
    REPO_ROOT / "terminal-context" / "scripts" / "terminal_process_context.py",
)
finder_item = load_module(
    "finder_item_context",
    REPO_ROOT / "finder-context" / "scripts" / "finder_item_context.py",
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


class FinderItemContextTests(unittest.TestCase):
    def test_clean_mdls_and_markdown_rendering(self):
        self.assertEqual(finder_item.clean_mdls("(null)"), "")
        self.assertEqual(finder_item.clean_mdls('("Red", "Needs|Review")'), "Red, Needs|Review")
        self.assertEqual(finder_item.clean_mdls("public.python-script"), "public.python-script")

        row = finder_item.markdown_row(
            {
                "path": "/tmp/project/notes|draft.md",
                "kind": "Markdown Document",
                "size": "42",
                "modified": "2026-06-29 09:30:00",
                "last_used": "2026-06-29 10:00:00",
                "tags": "Red, Needs|Review",
            }
        )
        self.assertIn("notes\\|draft.md", row)
        self.assertIn("Needs\\|Review", row)

    def test_item_metadata_for_existing_and_missing_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "example.txt"
            path.write_text("hello", encoding="utf-8")
            metadata = finder_item.item_metadata(str(path))
            self.assertEqual(metadata["path"], str(path))
            self.assertEqual(metadata["size"], "5")
            self.assertTrue(metadata["modified"])
            self.assertIn(metadata["kind"], {"File", "Plain Text Document", "TextEdit Document"})

        missing = finder_item.item_metadata("/tmp/definitely-missing-finder-context-file")
        self.assertEqual(missing["kind"], "missing")
        self.assertEqual(missing["tags"], "")


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


class TerminalProcessContextTests(unittest.TestCase):
    def test_process_filter_includes_dev_jobs_and_excludes_false_positives(self):
        rows = [
            "100 1 100 S ttys001 00:10 npm run dev",
            "101 1 101 S ttys001 00:11 /bin/bash -lc 'node server.js'",
            "102 1 102 S ttys001 00:12 go run ./cmd/api",
            "103 1 103 S ttys001 00:13 tmux new-session -s work",
            "104 1 104 S ?? 00:14 ssh: user@host [mux]",
            "105 1 105 S ttys001 00:15 /bin/bash -lc \"sed -n '/## tmux/p' terminal-context/scripts/terminal_context.sh\"",
            "106 1 106 S ttys001 00:16 python3 terminal-context/scripts/terminal_process_context.py",
            "107 1 107 S ttys001 00:17 sed -n /node/p README.md",
            "108 1 108 S ttys001 00:18 python3 manage.py runserver",
        ]

        candidates = list(terminal_process.iter_candidates(rows))
        commands = [row.command for row in candidates]

        self.assertEqual(
            commands,
            [
                "npm run dev",
                "/bin/bash -lc 'node server.js'",
                "go run ./cmd/api",
                "tmux new-session -s work",
                "ssh: user@host [mux]",
                "python3 manage.py runserver",
            ],
        )
        self.assertIn("\\|", terminal_process.md_cell("left|right"))
        self.assertIn("python3 manage.py runserver", terminal_process.markdown_row(candidates[-1]))


if __name__ == "__main__":
    unittest.main()
