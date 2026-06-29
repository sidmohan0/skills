#!/usr/bin/env python3
"""Filter ps(1) output down to likely developer jobs."""

import argparse
import os
import shlex
import sys
from dataclasses import dataclass


DEV_COMMANDS = {
    "bun",
    "cargo",
    "next",
    "node",
    "npm",
    "pnpm",
    "python",
    "python3",
    "ruby",
    "ssh",
    "tmux",
    "vite",
    "yarn",
}
SHELLS = {"bash", "fish", "sh", "zsh"}
DEV_PHRASES = ("go run",)
IGNORE_COMMAND_SUBSTRINGS = ("terminal_context.sh", "terminal_process_context.py")


@dataclass(frozen=True)
class ProcessRow:
    pid: str
    ppid: str
    pgid: str
    stat: str
    tty: str
    etime: str
    command: str


def split_command(command):
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def command_base(token):
    return os.path.basename(token).lower().rstrip(":")


def parse_ps_line(line):
    parts = line.strip().split(None, 6)
    if len(parts) < 7:
        return None
    return ProcessRow(*parts)


def direct_dev_command(command):
    lower_command = command.lower()
    if any(phrase in lower_command for phrase in DEV_PHRASES):
        return True

    tokens = split_command(command)
    if not tokens:
        return False

    first = command_base(tokens[0])
    if first in DEV_COMMANDS:
        return True

    if first == "env":
        for token in tokens[1:]:
            if token.startswith("-") or "=" in token:
                continue
            return command_base(token) in DEV_COMMANDS

    return False


def shell_embedded_dev_command(tokens):
    for index, token in enumerate(tokens):
        if token.startswith("-") and "c" in token and index + 1 < len(tokens):
            return direct_dev_command(tokens[index + 1])
    return any(command_base(token) in DEV_COMMANDS for token in tokens[1:])


def is_likely_developer_process(command):
    if any(substring in command for substring in IGNORE_COMMAND_SUBSTRINGS):
        return False

    tokens = split_command(command)
    if not tokens:
        return False

    if direct_dev_command(command):
        return True

    first = command_base(tokens[0])
    return first in SHELLS and shell_embedded_dev_command(tokens)


def ignored_pids_from_env():
    ignored = {str(os.getpid())}
    for key in ("TERMINAL_CONTEXT_SCRIPT_PID", "TERMINAL_CONTEXT_IGNORE_PIDS"):
        value = os.environ.get(key, "")
        for pid in value.replace(",", " ").split():
            if pid:
                ignored.add(pid)
    return ignored


def iter_candidates(lines, ignored_pids=None):
    ignored = set(ignored_pids or ())
    for line in lines:
        row = parse_ps_line(line)
        if row is None or row.pid in ignored:
            continue
        if is_likely_developer_process(row.command):
            yield row


def md_cell(value):
    return str(value or "").replace("\n", " ").replace("|", "\\|")


def markdown_row(row):
    return (
        f"| {md_cell(row.pid)} | {md_cell(row.ppid)} | {md_cell(row.pgid)} | "
        f"{md_cell(row.tty)} | {md_cell(row.stat)} | {md_cell(row.etime)} | "
        f"{md_cell(row.command)} |"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Filter ps output to likely developer processes and print Markdown rows."
    )
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args(argv)

    count = 0
    for row in iter_candidates(sys.stdin, ignored_pids=ignored_pids_from_env()):
        print(markdown_row(row))
        count += 1
        if args.limit and count >= args.limit:
            break


if __name__ == "__main__":
    main()
