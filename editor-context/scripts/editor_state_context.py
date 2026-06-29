#!/usr/bin/env python3
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import sys
from urllib.parse import unquote, urlparse


APP_DIRS = [
    ("Cursor", "Cursor"),
    ("VS Code", "Code"),
    ("VS Code Insiders", "Code - Insiders"),
    ("VSCodium", "VSCodium"),
]


def md_cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def from_file_uri(value):
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return unquote(parsed.path)
    return value


def short_path(path, home):
    path = from_file_uri(path)
    if path.startswith(home + os.sep):
        return "~/" + os.path.relpath(path, home)
    return path


def load_jsonish(value):
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not value:
        return value
    if value[0] not in "[{\"":
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def extract_paths(value):
    text = "\n".join(iter_strings(value))
    found = []
    for match in re.finditer(r"file://[^\s\"'<>]+", text):
        found.append(from_file_uri(match.group(0)))
    for match in re.finditer(r"(?:~|/Users/|/Volumes/|/private/|/tmp/)[^\s\"'<>]+", text):
        found.append(os.path.expanduser(match.group(0)))
    deduped = []
    seen = set()
    for path in found:
        if path not in seen:
            deduped.append(path)
            seen.add(path)
    return deduped


def snippet(value, limit=260):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True, sort_keys=True)
    text = " ".join(text.split())
    return text[:limit]


def classify(key, value):
    probe = (str(key) + " " + snippet(value, 1000)).lower()
    categories = []
    if any(term in probe for term in ("activeeditor", "active editor", "activefile", "active file")):
        categories.append("active")
    if any(term in probe for term in ("history", "recent", "editor.memento", "opened editors", "entries")):
        categories.append("recent")
    if any(term in probe for term in ("selection", "cursor", "position", "viewstate", "visible range")):
        categories.append("cursor-selection")
    if any(term in probe for term in ("diagnostic", "marker", "problem", "problems")):
        categories.append("diagnostics")
    if any(term in probe for term in ("workspace", "folder", "file", "editor")):
        categories.append("editor-state")
    return categories


def app_roots(app_support_root):
    for display_name, dirname in APP_DIRS:
        yield display_name, os.path.join(app_support_root, dirname)


def collect_global_storage(app_name, root, home):
    storage = os.path.join(root, "User", "globalStorage", "storage.json")
    rows = []
    if not os.path.exists(storage):
        return rows
    try:
        data = json.load(open(storage))
    except Exception:
        return rows
    for key, value in data.items():
        parsed = load_jsonish(value)
        categories = classify(key, parsed)
        if not categories:
            continue
        paths = extract_paths(parsed)
        rows.append(
            {
                "app": app_name,
                "source": "globalStorage",
                "key": key,
                "categories": ", ".join(categories),
                "paths": ", ".join(short_path(path, home) for path in paths[:4]),
                "snippet": snippet(parsed),
            }
        )
    return rows


def collect_workspace_state(app_name, root, home):
    workspace_root = os.path.join(root, "User", "workspaceStorage")
    workspace_rows = []
    hint_rows = []
    if not os.path.isdir(workspace_root):
        return workspace_rows, hint_rows
    workspace_dirs = sorted(glob.glob(os.path.join(workspace_root, "*")), key=os.path.getmtime, reverse=True)
    for workspace_dir in workspace_dirs[:20]:
        workspace_id = os.path.basename(workspace_dir)
        workspace_json = os.path.join(workspace_dir, "workspace.json")
        folder = ""
        workspace = ""
        if os.path.exists(workspace_json):
            try:
                data = json.load(open(workspace_json))
                folder = from_file_uri(data.get("folder", ""))
                workspace = from_file_uri(data.get("workspace", ""))
            except Exception:
                pass
        if folder or workspace:
            modified = dt.datetime.fromtimestamp(os.path.getmtime(workspace_dir)).strftime("%Y-%m-%d %H:%M:%S")
            workspace_rows.append(
                {
                    "app": app_name,
                    "folder": short_path(folder, home),
                    "workspace": short_path(workspace, home),
                    "modified": modified,
                    "state_path": short_path(workspace_dir, home),
                }
            )
        db = os.path.join(workspace_dir, "state.vscdb")
        if not os.path.exists(db):
            continue
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            items = list(con.execute("select key, value from ItemTable"))
        except Exception:
            continue
        for key, value in items:
            parsed = load_jsonish(value)
            categories = classify(key, parsed)
            paths = extract_paths(parsed)
            if not categories and not paths:
                continue
            hint_rows.append(
                {
                    "app": app_name,
                    "source": workspace_id,
                    "key": str(key),
                    "categories": ", ".join(categories or ["path"]),
                    "paths": ", ".join(short_path(path, home) for path in paths[:4]),
                    "snippet": snippet(parsed),
                }
            )
    return workspace_rows, hint_rows


def print_table(title, headers, rows, values):
    print(f"### {title}")
    if not rows:
        print(f"No {title.lower()} found.")
        print()
        return
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        print("| " + " | ".join(md_cell(row.get(value, "")) for value in values) + " |")
    print()


def main():
    if len(sys.argv) not in (2, 3):
        print("Usage: editor_state_context.py TARGET_PATH [APP_SUPPORT_ROOT]", file=sys.stderr)
        return 2
    target_path = os.path.abspath(os.path.expanduser(sys.argv[1]))
    app_support_root = (
        os.path.abspath(os.path.expanduser(sys.argv[2]))
        if len(sys.argv) == 3
        else os.path.expanduser("~/Library/Application Support")
    )
    home = os.path.expanduser("~")

    workspace_rows = []
    hint_rows = []
    for app_name, root in app_roots(app_support_root):
        if not os.path.isdir(root):
            continue
        workspace_part, hints_part = collect_workspace_state(app_name, root, home)
        workspace_rows.extend(workspace_part)
        hint_rows.extend(hints_part)
        hint_rows.extend(collect_global_storage(app_name, root, home))

    target_rows = [
        row for row in workspace_rows
        if row.get("folder") and os.path.abspath(os.path.expanduser(row["folder"].replace("~/", home + os.sep))).startswith(target_path)
    ]
    if target_rows:
        workspace_rows = target_rows + [row for row in workspace_rows if row not in target_rows]

    active_rows = [row for row in hint_rows if "active" in row.get("categories", "")]
    recent_rows = [row for row in hint_rows if "recent" in row.get("categories", "") and row not in active_rows]
    cursor_rows = [row for row in hint_rows if "cursor-selection" in row.get("categories", "")]
    diagnostic_rows = [row for row in hint_rows if "diagnostics" in row.get("categories", "")]
    other_rows = [
        row for row in hint_rows
        if row not in active_rows and row not in recent_rows and row not in cursor_rows and row not in diagnostic_rows
    ]

    print(f"- App support root: {md_cell(short_path(app_support_root, home))}")
    print()
    print_table(
        "Persisted Workspaces",
        ["App", "Folder", "Workspace", "Modified", "State Path"],
        workspace_rows[:12],
        ["app", "folder", "workspace", "modified", "state_path"],
    )
    print_table(
        "Active Editor Candidates",
        ["App", "Source", "Key", "Paths", "Value Snippet"],
        active_rows[:12],
        ["app", "source", "key", "paths", "snippet"],
    )
    print_table(
        "Recent Editor Candidates",
        ["App", "Source", "Key", "Paths", "Value Snippet"],
        recent_rows[:12],
        ["app", "source", "key", "paths", "snippet"],
    )
    print_table(
        "Cursor And Selection Hints",
        ["App", "Source", "Key", "Paths", "Value Snippet"],
        cursor_rows[:12],
        ["app", "source", "key", "paths", "snippet"],
    )
    print_table(
        "Diagnostics Hints",
        ["App", "Source", "Key", "Paths", "Value Snippet"],
        diagnostic_rows[:12],
        ["app", "source", "key", "paths", "snippet"],
    )
    print_table(
        "Other Editor State Hints",
        ["App", "Source", "Key", "Categories", "Paths", "Value Snippet"],
        other_rows[:12],
        ["app", "source", "key", "categories", "paths", "snippet"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
