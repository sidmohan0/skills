#!/usr/bin/env python3
"""Render running editor-window rows with active file/project inference."""

import re
import sys


EDITOR_SUFFIXES = [
    "Cursor",
    "Visual Studio Code",
    "VS Code",
    "Code",
    "Code - Insiders",
    "VSCodium",
]


def md_cell(value):
    return str(value or "").replace("\n", " ").replace("|", "\\|")


def split_title(title):
    return [part.strip() for part in re.split(r"\s+(?:-|\u2014)\s+", title or "") if part.strip()]


def normalized(value):
    return " ".join(str(value or "").lower().replace("\u2014", "-").split())


def suffix_candidates(app_name):
    values = [app_name] if app_name else []
    values.extend(EDITOR_SUFFIXES)
    seen = set()
    for value in values:
        key = normalized(value)
        if key and key not in seen:
            seen.add(key)
            yield split_title(value)


def strip_editor_suffix(parts, app_name):
    for suffix in sorted(suffix_candidates(app_name), key=len, reverse=True):
        if suffix and len(parts) >= len(suffix):
            if [normalized(part) for part in parts[-len(suffix) :]] == [normalized(part) for part in suffix]:
                return parts[: -len(suffix)], True
    return parts, False


def looks_like_file(value):
    text = str(value or "").strip()
    if not text:
        return False
    last = text.rsplit("/", 1)[-1]
    return "." in last or last.lower().startswith("untitled")


def infer_title(title, app_name=""):
    parts = split_title(title)
    if not parts:
        return {"active_file": "", "project": ""}

    parts, removed_editor_suffix = strip_editor_suffix(parts, app_name)
    if not parts:
        return {"active_file": "", "project": ""}

    if len(parts) >= 2:
        return {"active_file": parts[0], "project": parts[-1]}

    only = parts[0]
    if removed_editor_suffix and not looks_like_file(only):
        return {"active_file": "", "project": only}
    return {"active_file": only, "project": ""}


def markdown_row(app, window, title):
    inferred = infer_title(title, app)
    return (
        f"| {md_cell(app)} | {md_cell(window)} | {md_cell(title)} | "
        f"{md_cell(inferred['active_file'])} | {md_cell(inferred['project'])} |"
    )


def iter_rows(lines):
    for line in lines:
        parts = line.rstrip("\n").split("\t", 2)
        if len(parts) < 3:
            continue
        yield markdown_row(parts[0], parts[1], parts[2])


def main():
    for row in iter_rows(sys.stdin):
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
