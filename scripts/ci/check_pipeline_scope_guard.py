#!/usr/bin/env python3
"""Reject control-plane changes unless their authorization is explicit."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "pipeline" / "pipeline.yml"
ALLOWED_AUTHORIZATIONS = {"pipeline_change", "control-plane"}
MINIMUM_PROTECTED_PATHS = {
    "pipeline/**",
    ".github/workflows/**",
    "scripts/deploy/**",
    "scripts/ci/check_pipeline_scope_guard.py",
    "tasks/*/state.json",
}


def load_protected_paths() -> list[str]:
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read pipeline contract: {exc}") from exc
    paths = contract.get("control_plane_protected_paths")
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        raise RuntimeError("pipeline contract has invalid control_plane_protected_paths")
    # A changed pipeline.yml must not be able to weaken its own protection.
    return sorted(set(paths) | MINIMUM_PROTECTED_PATHS)


def normalize_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("/") or ".." in Path(normalized).parts:
        raise ValueError(f"changed path must be relative to repository root: {path!r}")
    return normalized


def protected_changes(paths: list[str], protected_patterns: list[str]) -> list[str]:
    return sorted(
        {
            normalized
            for path in paths
            for normalized in [normalize_path(path)]
            if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in protected_patterns)
        }
    )


def split_authorizations(value: str) -> set[str]:
    return {item.strip().lower() for item in value.replace("\n", ",").split(",") if item.strip()}


def authorization_from_marker(marker: str) -> set[str]:
    authorizations = set()
    for line in marker.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().upper() == "PIPELINE_SCOPE_ALLOW":
            authorizations.update(split_authorizations(value))
    return authorizations


def explicit_authorizations(env: dict[str, str]) -> set[str]:
    authorizations = split_authorizations(env.get("PIPELINE_SCOPE_ALLOW", ""))
    authorizations.update(split_authorizations(env.get("PR_LABELS", "")))
    authorizations.update(authorization_from_marker(env.get("PR_BODY", "")))
    return authorizations & ALLOWED_AUTHORIZATIONS


def git_output(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return [line for line in result.stdout.splitlines() if line]


def resolve_base(requested_base: str | None, env: dict[str, str]) -> str:
    for candidate in (requested_base, env.get("PR_BASE_SHA"), "origin/etalon", "HEAD^"):
        if not candidate:
            continue
        result = subprocess.run(
            ["git", "rev-parse", "--verify", candidate],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            return candidate
    raise RuntimeError("cannot resolve diff base; pass --base or set PR_BASE_SHA")


def changed_paths(base: str) -> list[str]:
    committed = git_output("diff", "--name-only", f"{base}...HEAD")
    local = git_output("diff", "--name-only", base)
    untracked = git_output("ls-files", "--others", "--exclude-standard")
    return sorted(set(committed) | set(local) | set(untracked))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Git base for the PR or local diff")
    parser.add_argument(
        "--changed-path", action="append", default=[], help="path to validate; repeat for deterministic input"
    )
    args = parser.parse_args()

    try:
        paths = args.changed_path or changed_paths(resolve_base(args.base, os.environ))
        protected = protected_changes(paths, load_protected_paths())
    except (RuntimeError, ValueError) as exc:
        print(f"error: pipeline scope guard: {exc}", file=sys.stderr)
        return 2

    if not protected:
        print("pipeline scope guard ok: no protected paths changed")
        return 0

    authorizations = explicit_authorizations(os.environ)
    if authorizations:
        print(
            "pipeline scope guard authorized: "
            f"{', '.join(sorted(authorizations))}; protected paths: {', '.join(protected)}"
        )
        return 0

    print("error: protected control-plane paths changed without explicit authorization:", file=sys.stderr)
    for path in protected:
        print(f"  - {path}", file=sys.stderr)
    print(
        "Set PIPELINE_SCOPE_ALLOW=pipeline_change or control-plane, add that PR label, "
        "or add `PIPELINE_SCOPE_ALLOW: pipeline_change` (or control-plane) to the PR body.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
