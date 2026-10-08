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


def is_generated_evidence_output(path: str) -> bool:
    """Skip only recognized WMS-666 run outputs, never runner inputs or code."""
    prefix = "docs/evidence/WMS-666/release-1008/p2-prefix/"
    if not path.startswith(prefix):
        return False
    name = path.rsplit("/", 1)[-1]
    return (
        name in {
            "chrome.log", "result.json", "cdp-transport.json", "last-requests.json",
            "requests.jsonl", "sink-receipts.jsonl", "source-identity.json",
            "direct-jobs.sqlite3", "handler-receipt-joins.json",
        }
        or name.startswith(("WMS652-geometry-", "WMS652-realQrFlags-", "WMS652-selection-"))
        or name.startswith(("supply_id-", "supply_ids-")) and name.endswith(".json")
        or name.startswith("WMS666-whole-process-") and name.endswith((".html", ".json"))
    )


def full_wave(paths: list[str], event: str) -> bool:
    if event == "workflow_dispatch":
        return True
    return not paths or any(not (is_prose(path) or is_generated_evidence_output(path))
                            for path in paths)


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    return subprocess.check_output(
        [
            "git", "-C", str(root), "diff", "--no-renames", "--name-only", "-z",
            f"{base}...{head}",
        ]
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
