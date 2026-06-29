#!/usr/bin/env python3
import datetime as dt
import glob
import os
import struct
import sys


def md_cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def align4(position):
    return (position + 3) & ~3


def read_i32(data, position):
    if position + 4 > len(data):
        raise ValueError("read past end")
    return struct.unpack_from("<i", data, position)[0], position + 4


def read_u64(data, position):
    if position + 8 > len(data):
        raise ValueError("read past end")
    return struct.unpack_from("<Q", data, position)[0], position + 8


def read_string(data, position):
    length, position = read_i32(data, position)
    if length < 0 or position + length > len(data):
        return "", position
    value = data[position : position + length].decode("utf-8", "replace")
    return value, align4(position + length)


def read_string16(data, position):
    length, position = read_i32(data, position)
    byte_length = length * 2
    if length < 0 or position + byte_length > len(data):
        return "", position
    value = data[position : position + byte_length].decode("utf-16-le", "replace")
    return value, align4(position + byte_length)


def latest_session_file(profile_dir):
    files = glob.glob(os.path.join(profile_dir, "Sessions", "Session_*"))
    return max(files, key=os.path.getmtime) if files else ""


def iter_records(path):
    data = open(path, "rb").read()
    if len(data) < 8 or data[:4] != b"SNSS":
        return
    offset = 8
    while offset + 2 <= len(data):
        size = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        record = data[offset : offset + size]
        offset += size
        if record:
            yield record[0], record[1:]


def group_key(payload):
    if len(payload) < 25 or payload[24] == 0:
        return ""
    high = struct.unpack_from("<Q", payload, 8)[0]
    low = struct.unpack_from("<Q", payload, 16)[0]
    if high == 0 and low == 0:
        return ""
    return f"{high:016x}:{low:016x}"


def parse_navigation(payload):
    if len(payload) < 20:
        return None
    try:
        _, position = read_i32(payload, 0)
        tab_id, position = read_i32(payload, position)
        nav_index, position = read_i32(payload, position)
        url, position = read_string(payload, position)
        title, position = read_string16(payload, position)
    except (ValueError, struct.error):
        return None
    return tab_id, nav_index, title, url


def parse_group_metadata(payload):
    if len(payload) < 24:
        return None
    try:
        position = 4
        high, position = read_u64(payload, position)
        low, position = read_u64(payload, position)
        key = f"{high:016x}:{low:016x}"
        title, position = read_string16(payload, position)
        color = ""
        collapsed = ""
        saved_guid = ""
        if position + 4 <= len(payload):
            color = str(struct.unpack_from("<I", payload, position)[0])
            position += 4
        if position + 4 <= len(payload):
            collapsed = str(payload[position] != 0).lower()
            position += 4
        if position + 4 <= len(payload):
            is_saved = payload[position] != 0
            position += 4
            if is_saved:
                saved_guid, position = read_string(payload, position)
        return key, {
            "title": title,
            "color": color,
            "collapsed": collapsed,
            "saved_guid": saved_guid,
        }
    except (ValueError, struct.error):
        return None


def tab_state(tabs, tab_id):
    return tabs.setdefault(
        tab_id,
        {
            "navigations": {},
            "selected_index": None,
            "pinned": False,
            "group": "",
            "visual_index": "",
            "window_id": "",
        },
    )


def selected_navigation(tab):
    navigations = tab.get("navigations", {})
    selected = tab.get("selected_index")
    if selected in navigations:
        return navigations[selected]
    if navigations:
        return navigations[sorted(navigations)[-1]]
    return {"title": "", "url": ""}


def parse_session(path):
    tabs = {}
    metadata = {}
    for command_id, payload in iter_records(path):
        if command_id == 0 and len(payload) >= 8:
            window_id = struct.unpack_from("<i", payload, 0)[0]
            tab_id = struct.unpack_from("<i", payload, 4)[0]
            tab_state(tabs, tab_id)["window_id"] = window_id
        elif command_id == 2 and len(payload) >= 8:
            tab_id = struct.unpack_from("<i", payload, 0)[0]
            visual_index = struct.unpack_from("<i", payload, 4)[0]
            tab_state(tabs, tab_id)["visual_index"] = visual_index
        elif command_id == 6:
            parsed = parse_navigation(payload)
            if parsed:
                tab_id, nav_index, title, url = parsed
                tab_state(tabs, tab_id)["navigations"][nav_index] = {
                    "title": title,
                    "url": url,
                }
        elif command_id == 7 and len(payload) >= 8:
            tab_id = struct.unpack_from("<i", payload, 0)[0]
            selected_index = struct.unpack_from("<i", payload, 4)[0]
            tab_state(tabs, tab_id)["selected_index"] = selected_index
        elif command_id == 12 and len(payload) >= 5:
            tab_id = struct.unpack_from("<i", payload, 0)[0]
            tab_state(tabs, tab_id)["pinned"] = payload[4] != 0
        elif command_id == 16 and len(payload) >= 4:
            tab_id = struct.unpack_from("<i", payload, 0)[0]
            tabs.pop(tab_id, None)
        elif command_id == 25 and len(payload) >= 25:
            tab_id = struct.unpack_from("<i", payload, 0)[0]
            tab_state(tabs, tab_id)["group"] = group_key(payload)
        elif command_id == 27:
            parsed = parse_group_metadata(payload)
            if parsed:
                key, value = parsed
                metadata[key] = value
    return tabs, metadata


def print_source(path, profile_dir):
    modified = dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"- Source: `{md_cell(os.path.relpath(path, profile_dir))}`")
    print(f"- Source modified: {modified}")


def print_pinned_tabs(tabs, limit):
    print("## Pinned Tabs")
    active = [(tab_id, tab) for tab_id, tab in tabs.items() if tab.get("pinned")]
    if not active:
        print("No pinned tabs recorded in latest Chrome session metadata.")
        return
    print("| Tab ID | Window ID | Visual Index | Title | URL | Group ID |")
    print("|---:|---:|---:|---|---|---|")
    for tab_id, tab in sorted(active, key=lambda item: (item[1].get("window_id", 0), item[1].get("visual_index", 0)))[:limit]:
        nav = selected_navigation(tab)
        print(
            f"| {tab_id} | {md_cell(tab.get('window_id'))} | {md_cell(tab.get('visual_index'))} | "
            f"{md_cell(nav.get('title'))} | {md_cell(nav.get('url'))} | {md_cell(tab.get('group'))} |"
        )


def print_session_tabs(tabs, limit):
    print("## Profile Session Tabs")
    if not tabs:
        print("No tabs decoded from latest Chrome session metadata.")
        return
    print("| Tab ID | Window ID | Visual Index | Pinned | Title | URL | Group ID |")
    print("|---:|---:|---:|---|---|---|---|")
    for tab_id, tab in sorted(tabs.items(), key=lambda item: (item[1].get("window_id", 0), item[1].get("visual_index", 0), item[0]))[:limit]:
        nav = selected_navigation(tab)
        print(
            f"| {tab_id} | {md_cell(tab.get('window_id'))} | {md_cell(tab.get('visual_index'))} | "
            f"{str(bool(tab.get('pinned'))).lower()} | {md_cell(nav.get('title'))} | "
            f"{md_cell(nav.get('url'))} | {md_cell(tab.get('group'))} |"
        )


def print_tab_groups(tabs, metadata, limit):
    print()
    print("## Tab Groups")
    groups = {}
    for tab_id, tab in tabs.items():
        key = tab.get("group")
        if key:
            groups.setdefault(key, []).append((tab_id, tab))
    if not groups:
        print("No tab groups recorded in latest Chrome session metadata.")
        return
    print("| Group ID | Group Title | Color | Collapsed | Saved GUID | Tabs |")
    print("|---|---|---:|---|---|---|")
    for key in sorted(groups, key=lambda item: (metadata.get(item, {}).get("title", ""), item))[:limit]:
        meta = metadata.get(key, {})
        tab_bits = []
        for tab_id, tab in sorted(groups[key], key=lambda item: item[1].get("visual_index", 0)):
            nav = selected_navigation(tab)
            label = nav.get("title") or nav.get("url") or str(tab_id)
            tab_bits.append(f"{tab_id}: {label}")
        print(
            f"| {md_cell(key)} | {md_cell(meta.get('title'))} | {md_cell(meta.get('color'))} | "
            f"{md_cell(meta.get('collapsed'))} | {md_cell(meta.get('saved_guid'))} | "
            f"{md_cell('; '.join(tab_bits))} |"
        )


def main():
    if len(sys.argv) != 3:
        print("Usage: chrome_session_context.py PROFILE_DIR LIMIT", file=sys.stderr)
        return 2
    profile_dir = os.path.abspath(os.path.expanduser(sys.argv[1]))
    limit = int(sys.argv[2])
    path = latest_session_file(profile_dir)
    if not path:
        print("## Profile Session Tabs")
        print("Profile session tabs unavailable: no Chrome Session_* files found.")
        print()
        print("## Pinned Tabs")
        print("Pinned tabs unavailable: no Chrome Session_* files found.")
        print()
        print("## Tab Groups")
        print("Tab groups unavailable: no Chrome Session_* files found.")
        return 0
    tabs, metadata = parse_session(path)
    print_source(path, profile_dir)
    print()
    print_session_tabs(tabs, limit)
    print()
    print_pinned_tabs(tabs, limit)
    print_tab_groups(tabs, metadata, limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
