#!/usr/bin/env python3
"""Conservative classifier for skipping heavy CI on prose-only changes."""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def is_prose(path: str) -> bool:
    if path in {"AGENTS.md", "CLAUDE.md"} or path.startswith("docs/"):
        return path.endswith((".md", ".rst"))
    return path in {"README.md", "CONTRIBUTING.md"}


def full_wave(paths: list[str], event: str) -> bool:
    if event == "workflow_dispatch":
        return True
    return not paths or any(not is_prose(path) for path in paths)


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    return subprocess.check_output(
        ["git", "-C", str(root), "diff", "--name-only", "-z", f"{base}...{head}"]
    ).decode().split("\0")[:-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--event", required=True)
    args = parser.parse_args()
    run = full_wave(changed_paths(args.root, args.base, args.head), args.event)
    print(f"run_full={str(run).lower()}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"run_full={str(run).lower()}\n")


if __name__ == "__main__":
    main()
