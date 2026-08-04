#!/usr/bin/env python3
"""Export FBS operator-flow OpenAPI subset for docs and contract gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.main import create_app  # noqa: E402

FBS_PATH_PREFIX = "/operations/fbs-"
OUTPUT = ROOT / "tasks" / "fbs-operator-flow" / "openapi" / "fbs-operations.openapi.json"


def _filter_fbs_paths(schema: dict[str, object]) -> dict[str, object]:
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        return schema
    filtered = {
        path: ops
        for path, ops in paths.items()
        if isinstance(path, str) and path.startswith(FBS_PATH_PREFIX)
    }
    return {**schema, "paths": filtered}


def main() -> None:
    schema = create_app().openapi()
    subset = _filter_fbs_paths(schema)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(subset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths = subset.get("paths")
    path_count = len(paths) if isinstance(paths, dict) else 0
    print(f"Wrote {path_count} FBS paths to {OUTPUT}")


if __name__ == "__main__":
    main()
