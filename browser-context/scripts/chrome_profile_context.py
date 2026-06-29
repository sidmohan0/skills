#!/usr/bin/env python3
"""Read Chrome profile metadata, downloads, and reading-list entries."""

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys


def md_cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def chrome_time_to_string(value):
    if not value:
        return ""
    try:
        when = dt.datetime(1601, 1, 1) + dt.timedelta(microseconds=int(value))
    except (TypeError, ValueError, OverflowError):
        return ""
    return when.strftime("%Y-%m-%d %H:%M:%S")


def resolve_profile(base, wanted, override=""):
    if override:
        path = os.path.abspath(os.path.expanduser(override))
        return {
            "path": path,
            "dirname": os.path.basename(path),
            "name": "",
            "match": "override",
        }

    local_state = os.path.join(base, "Local State")
    try:
        with open(local_state, encoding="utf-8") as handle:
            data = json.load(handle)
        profiles = data.get("profile", {}).get("info_cache", {})
    except Exception:
        profiles = {}

    for dirname, info in profiles.items():
        display_name = info.get("name", "")
        if display_name == wanted or dirname == wanted:
            return {
                "path": os.path.join(base, dirname),
                "dirname": dirname,
                "name": display_name,
                "match": "exact",
            }

    if len(profiles) == 1:
        dirname, info = next(iter(profiles.items()))
        return {
            "path": os.path.join(base, dirname),
            "dirname": dirname,
            "name": info.get("name", ""),
            "match": "fallback-single-profile",
        }

    if "Default" in profiles:
        info = profiles["Default"]
        return {
            "path": os.path.join(base, "Default"),
            "dirname": "Default",
            "name": info.get("name", ""),
            "match": "fallback-default",
        }

    return {"path": "", "dirname": "", "name": "", "match": "unavailable"}


def iter_downloads(history_db, limit):
    con = sqlite3.connect(history_db)
    try:
        rows = con.execute(
            "select start_time, coalesce(nullif(current_path, ''), nullif(target_path, ''), ''), tab_url "
            "from downloads order by start_time desc limit ?",
            (limit,),
        ).fetchall()
    finally:
        con.close()
    for start, path, url in rows:
        yield {
            "started": chrome_time_to_string(start),
            "path": path or "",
            "url": url or "",
        }


def walk_bookmarks(node):
    if isinstance(node, dict):
        if node.get("type") == "url":
            yield node
        for child in node.get("children", []):
            yield from walk_bookmarks(child)
    elif isinstance(node, list):
        for child in node:
            yield from walk_bookmarks(child)


def iter_reading_list(bookmarks_path, limit):
    with open(bookmarks_path, encoding="utf-8") as handle:
        data = json.load(handle)
    roots = data.get("roots", {})
    count = 0
    for key in ("reading_list", "synced"):
        for item in walk_bookmarks(roots.get(key, {})):
            yield {"title": item.get("name", ""), "url": item.get("url", "")}
            count += 1
            if count >= limit:
                return


def print_profile(args):
    profile = resolve_profile(args.base, args.wanted, args.override)
    print(profile["path"])
    print(profile["dirname"])
    print(profile["name"])
    print(profile["match"])
    return 0


def print_downloads(args):
    print("| Started | Path | URL |")
    print("|---|---|---|")
    try:
        for row in iter_downloads(args.history_db, args.limit):
            print(f"| {md_cell(row['started'])} | `{md_cell(row['path'])}` | {md_cell(row['url'])} |")
    except Exception as exc:
        print(f"Downloads unavailable: {md_cell(exc)}")
    return 0


def print_reading_list(args):
    print("| Title | URL |")
    print("|---|---|")
    try:
        count = 0
        for row in iter_reading_list(args.bookmarks, args.limit):
            print(f"| {md_cell(row['title'])} | {md_cell(row['url'])} |")
            count += 1
        if count == 0:
            print("No reading-list entries found in readable bookmark roots.")
    except Exception as exc:
        print(f"Reading list unavailable: {md_cell(exc)}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile = subparsers.add_parser("profile")
    profile.add_argument("base")
    profile.add_argument("wanted")
    profile.add_argument("override", nargs="?", default="")
    profile.set_defaults(func=print_profile)

    downloads = subparsers.add_parser("downloads")
    downloads.add_argument("history_db")
    downloads.add_argument("limit", type=int)
    downloads.set_defaults(func=print_downloads)

    reading_list = subparsers.add_parser("reading-list")
    reading_list.add_argument("bookmarks")
    reading_list.add_argument("limit", type=int)
    reading_list.set_defaults(func=print_reading_list)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
