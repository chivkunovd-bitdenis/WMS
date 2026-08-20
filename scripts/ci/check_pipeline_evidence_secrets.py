#!/usr/bin/env python3
"""Fail-closed scan for raw secrets in pipeline evidence/task artifacts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = [
    "docs/evidence",
    "tasks/BUG-WMS-*",
    "tasks/20260820-night-bug-queue",
]
SECRET_PATTERNS = [
    re.compile(r"\bAuthorization\s*:\s*(?:Bearer\s+)?[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    re.compile(r"\b(?:Cookie|Set-Cookie)\s*:\s*[^\\s]{20,}", re.IGNORECASE),
    re.compile(r"\b(?:access|refresh|id)_token\b\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret)\b\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
]
TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".csv",
    ".env",
    ".har",
    ".html",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
}


def iter_files(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        matches = sorted(ROOT.glob(pattern))
        for match in matches:
            if match.is_dir():
                files.extend(path for path in sorted(match.rglob("*")) if path.is_file())
            elif match.is_file():
                files.append(match)
    return files


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {".env", "Dockerfile"}


def scan_file(path: Path) -> list[str]:
    if not is_text_candidate(path):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    findings: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "[REDACTED" in line or "<REDACTED" in line:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(f"{path.relative_to(ROOT)}:{line_no}: possible raw secret")
                break
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", nargs="*", default=DEFAULT_TARGETS)
    args = parser.parse_args(argv)

    findings: list[str] = []
    for path in iter_files(args.targets):
        findings.extend(scan_file(path))
    if findings:
        for finding in findings:
            print(f"error: {finding}", file=sys.stderr)
        return 1
    print("pipeline evidence secret scan ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
