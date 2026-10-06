#!/usr/bin/env python3
"""Resolve a non-empty, explicit CI comparison range for PR, push and manual runs."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


def resolve_base(event_name: str, event: dict, head: str) -> str:
    if event_name == "pull_request":
        base = event["pull_request"]["base"]["sha"]
    elif event_name == "push":
        base = event.get("before", "")
    elif event_name == "workflow_dispatch":
        base = event.get("inputs", {}).get("base_sha", "")
    else:
        raise ValueError(f"Unsupported CI event: {event_name}")
    if not re.fullmatch(r"[0-9a-f]{40}", base) or base == "0" * 40:
        raise ValueError(
            "No trustworthy baseline (first push or missing SHA). "
            "Run workflow_dispatch with an explicit earlier base_sha; refusing an empty range."
        )
    if base == head:
        raise ValueError("Baseline equals HEAD; refusing an empty comparison range")
    subprocess.run(["git", "cat-file", "-e", f"{base}^{{commit}}"], check=True)
    subprocess.run(["git", "merge-base", "--is-ancestor", base, head], check=True)
    return base


def main() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    try:
        base = resolve_base(
            os.environ["GITHUB_EVENT_NAME"], event, os.environ["GITHUB_SHA"]
        )
    except (ValueError, KeyError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"CI baseline error: {exc}") from exc
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"base_sha={base}\n")
    print(f"CI baseline: {base}")


if __name__ == "__main__":
    main()
