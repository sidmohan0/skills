#!/usr/bin/env python3
"""Discover and render recent files for Finder context."""

import argparse
import os
import shutil
import subprocess
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from finder_item_context import item_metadata, markdown_row  # noqa: E402


def inside_folder(path, folder):
    try:
        return os.path.commonpath([os.path.abspath(path), folder]) == folder
    except ValueError:
        return False


def dedupe(paths):
    seen = set()
    for path in paths:
        expanded = os.path.abspath(os.path.expanduser(path))
        if expanded not in seen:
            seen.add(expanded)
            yield expanded


def spotlight_recent_paths(folder, days=14):
    if not shutil.which("mdfind"):
        return []
    query = f"kMDItemFSContentChangeDate >= $time.today(-{int(days)})"
    try:
        result = subprocess.run(
            ["mdfind", "-onlyin", folder, query],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def filesystem_recent_paths(folder, max_entries=2000):
    candidates = []
    scanned = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [name for name in dirs if name not in {".git", "node_modules", "__pycache__"}]
        for name in files:
            path = os.path.join(root, name)
            candidates.append(path)
            scanned += 1
            if scanned >= max_entries:
                return candidates
    return candidates


def stat_sort_key(path):
    try:
        info = os.stat(path)
        return (info.st_mtime, path)
    except OSError:
        return (0, path)


def recent_files(folder, limit, candidate_paths=None):
    folder = os.path.abspath(os.path.expanduser(folder))
    candidates = list(candidate_paths) if candidate_paths is not None else spotlight_recent_paths(folder)
    if not candidates:
        candidates = filesystem_recent_paths(folder)

    filtered = [
        path
        for path in dedupe(candidates)
        if inside_folder(path, folder) and os.path.isfile(path)
    ]
    return sorted(filtered, key=stat_sort_key, reverse=True)[:limit]


def print_recent_files(folder, limit, candidate_paths=None):
    paths = recent_files(folder, limit, candidate_paths=candidate_paths)
    if not paths:
        print("No recent files found in this folder.")
        return 0
    print("| Path | Kind | Size | Modified | Last Used | Finder Tags |")
    print("|---|---:|---:|---|---|---|")
    for path in paths:
        print(markdown_row(item_metadata(path)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print recent Finder file rows for a folder.")
    parser.add_argument("folder")
    parser.add_argument("limit", type=int)
    args = parser.parse_args(argv)
    return print_recent_files(args.folder, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
