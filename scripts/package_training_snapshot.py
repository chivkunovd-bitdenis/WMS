#!/usr/bin/env python3
"""WMS-387: package pinned application sources without local data or credentials."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import tarfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = root / "deploy/training"
    manifest = json.loads((config / "snapshot.json").read_text())
    selections = [
        (manifest["application_commit"], "wms", [
            "backend/app", "backend/alembic", "backend/alembic.ini",
            "backend/pyproject.toml", "backend/Dockerfile.railway",
            "frontend",
        ]),
        (manifest["emulator_commit"], "emulator", ["wb_emulator"]),
    ]
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite an earlier snapshot.
    with output.open("xb") as target, tarfile.open(fileobj=target, mode="w:gz") as bundle:
        for name in ("compose.yaml", "snapshot.json", "README.md"):
            bundle.add(config / name, arcname="wms-training/" + name)
        for commit, component, paths in selections:
            archive = subprocess.check_output(["git", "archive", commit, "--", *paths], cwd=root)
            with tarfile.open(fileobj=io.BytesIO(archive)) as source:
                for member in source:
                    path = Path(member.name)
                    if any(p.startswith(".env") for p in path.parts):
                        continue
                    if component == "emulator" and any(p in {"seed", "tests"} for p in path.parts):
                        continue
                    if member.issym() or member.islnk():
                        raise RuntimeError(f"Unexpected link in source archive: {path}")
                    content = source.extractfile(member) if member.isfile() else None
                    member.name = f"wms-training/src/{component}/{member.name}"
                    bundle.addfile(member, content)
    print(output)
    print("Pinned sources only; database and file snapshots are not included.")


if __name__ == "__main__":
    main()
