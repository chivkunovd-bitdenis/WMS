#!/usr/bin/env python3
"""Validate guard bytes against a trusted Git baseline, never candidate hashes alone."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

MANIFEST = "guards/MANIFEST.json"
ROOTS = ("backend/tests/guards", "frontend/src/guards")


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.PIPE
    )


def parse_manifest(raw: bytes) -> dict:
    manifest = json.loads(raw)
    if set(manifest) != {"version", "state", "files"} or manifest["version"] != 1:
        raise ValueError("Unsupported guard manifest schema")
    if manifest["state"] not in {"bootstrap", "active"} or not isinstance(
        manifest["files"], dict
    ):
        raise ValueError("Manifest must explicitly declare bootstrap or active state")
    for path, digest in manifest["files"].items():
        pure = PurePosixPath(path)
        if (
            str(pure) != path
            or ".." in pure.parts
            or not any(path.startswith(r + "/") for r in ROOTS)
        ):
            raise ValueError(f"Invalid protected path: {path}")
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid SHA256: {path}")
    return manifest


def verify(root: Path, base: str, allow_bootstrap: bool = False) -> dict[str, int]:
    git(root, "cat-file", "-e", f"{base}^{{commit}}")
    candidate = parse_manifest((root / MANIFEST).read_bytes())
    base_paths = (
        git(root, "ls-tree", "-r", "--name-only", base, MANIFEST, *ROOTS)
        .decode()
        .splitlines()
    )
    if MANIFEST not in base_paths:
        if not allow_bootstrap or base_paths or candidate["state"] != "bootstrap":
            raise ValueError(
                "Trusted baseline has no manifest: only explicit empty bootstrap is allowed"
            )
        print(
            "BOOTSTRAP: baseline has no guard infrastructure; this is not owner approval."
        )
    else:
        trusted = parse_manifest(git(root, "show", f"{base}:{MANIFEST}"))
        if set(base_paths) - {MANIFEST} != set(trusted["files"]):
            raise ValueError("Trusted BASE contains unregistered guard files")
        for path, digest in trusted["files"].items():
            if hashlib.sha256(git(root, "show", f"{base}:{path}")).hexdigest() != digest:
                raise ValueError(f"Trusted BASE hash mismatch: {path}")
            candidate_path = root / path
            candidate_digest = (
                hashlib.sha256(candidate_path.read_bytes()).hexdigest()
                if candidate_path.is_file() and not candidate_path.is_symlink()
                else None
            )
            if candidate["files"].get(path) != digest or candidate_digest != digest:
                raise ValueError(
                    f"изменён защищённый тест {path} — нужно решение владельца"
                )
    actual = {}
    for directory in ROOTS:
        if not (root / directory).is_dir() or (root / directory).is_symlink():
            raise ValueError(f"Missing or symlinked guard directory: {directory}")
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ValueError(f"Symlinks are not protected files: {relative}")
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.is_file():
                actual[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != candidate["files"]:
        changed = sorted(
            p
            for p in actual.keys() | candidate["files"].keys()
            if actual.get(p) != candidate["files"].get(p)
        )
        raise ValueError(
            "Protected files changed, added or deleted: " + ", ".join(changed)
        )
    counts = {
        "backend_tests": sum(
            p.startswith(ROOTS[0] + "/")
            and Path(p).name.startswith("test_")
            and p.endswith(".py")
            for p in actual
        ),
        "frontend_tests": sum(
            p.startswith(ROOTS[1] + "/") and p.endswith((".test.ts", ".test.tsx"))
            for p in actual
        ),
    }
    total = sum(counts.values())
    if candidate["state"] == "bootstrap" and (
        total or set(actual) != {r + "/README.md" for r in ROOTS}
    ):
        raise ValueError(
            "Bootstrap allows only infrastructure README files, no unapproved business tests"
        )
    if candidate["state"] == "active" and not total:
        raise ValueError("Active guard set must contain business tests")
    print(
        f"Guard integrity passed: {len(actual)} files; {total} business test files; state={candidate['state']}"
    )
    if not total:
        print(
            "BOOTSTRAP ONLY: no approved business guards; stock and printing are NOT protected yet."
        )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--allow-bootstrap", action="store_true")
    args = parser.parse_args()
    try:
        counts = verify(args.root.resolve(), args.base, args.allow_bootstrap)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Охрана: {exc}") from exc
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as file:
            file.writelines(f"{key}={value}\n" for key, value in counts.items())


if __name__ == "__main__":
    main()
