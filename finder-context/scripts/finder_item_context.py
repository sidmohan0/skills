#!/usr/bin/env python3
"""Render Finder item metadata rows from local paths."""

import argparse
import datetime as dt
import os
import subprocess
import sys


def md_cell(value):
    return str(value or "").replace("\n", " ").replace("|", "\\|")


def clean_mdls(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"", "(null)", "null"}:
        return ""
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    pieces = []
    for piece in text.replace("\n", " ").split(","):
        cleaned = piece.strip().strip('"')
        if cleaned and cleaned not in {"(null)", "null"}:
            pieces.append(cleaned)
    return ", ".join(pieces) if pieces else text.strip().strip('"')


def mdls_raw(key, path):
    try:
        result = subprocess.run(
            ["mdls", "-raw", "-name", key, path],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return ""
    return result.stdout.strip()


def stat_metadata(path):
    try:
        info = os.stat(path)
    except OSError:
        return "", ""
    modified = dt.datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return str(info.st_size), modified


def item_metadata(path):
    if not os.path.exists(path):
        return {
            "path": path,
            "kind": "missing",
            "size": "",
            "modified": "",
            "last_used": "",
            "tags": "",
        }

    kind = clean_mdls(mdls_raw("kMDItemKind", path))
    if not kind:
        kind = "Folder" if os.path.isdir(path) else "File"
    size, modified = stat_metadata(path)
    return {
        "path": path,
        "kind": kind,
        "size": size,
        "modified": modified,
        "last_used": clean_mdls(mdls_raw("kMDItemLastUsedDate", path)),
        "tags": clean_mdls(mdls_raw("kMDItemUserTags", path)),
    }


def markdown_row(metadata):
    return (
        f"| `{md_cell(metadata.get('path'))}` | {md_cell(metadata.get('kind'))} | "
        f"{md_cell(metadata.get('size'))} | {md_cell(metadata.get('modified'))} | "
        f"{md_cell(metadata.get('last_used'))} | {md_cell(metadata.get('tags'))} |"
    )


def iter_input_paths(argv_paths):
    if argv_paths:
        for path in argv_paths:
            yield path
        return
    for line in sys.stdin:
        path = line.rstrip("\n")
        if path:
            yield path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print Finder metadata Markdown rows for paths.")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)

    for path in iter_input_paths(args.paths):
        print(markdown_row(item_metadata(path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
