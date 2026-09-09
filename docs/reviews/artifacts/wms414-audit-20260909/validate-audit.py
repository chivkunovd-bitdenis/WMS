"""Validate audit coverage and cited source ranges; this does not judge conclusions."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--complete", action="store_true")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[4]
    mobile = repository.parent / "wms397-mobile"
    errors: list[str] = []
    rows: list[dict] = []
    checked = 0
    sources: dict[tuple[str, str], list[str] | None] = {}
    expected: set[str] = set()
    required = {"id", "title", "prior_status", "verdict", "canonical_status", "code_state",
                "remaining", "evidence", "test_evidence", "release_evidence", "confidence",
                "needs_root_check"}
    for lane in range(1, 7):
        assignment = args.input_dir / f"lane{lane}-ids.json"
        lane_ids = set(json.loads(assignment.read_text()))
        expected.update(lane_ids)
        path = args.input_dir / f"lane{lane}.json"
        if not path.exists():
            if args.complete:
                errors.append(f"Missing lane {lane}")
            continue
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            errors.append(f"Lane {lane} is not an array")
            continue
        found = {row.get("id") for row in data}
        if found - lane_ids:
            errors.append(f"Lane {lane} contains foreign IDs: {sorted(found - lane_ids)}")
        if args.complete and lane_ids - found:
            errors.append(f"Lane {lane} misses IDs: {sorted(lane_ids - found)}")
        for row in data:
            rows.append(row)
            task = row.get("id", "<missing>")
            if required - row.keys():
                errors.append(f"{task}: missing fields {sorted(required - row.keys())}")
            if not row.get("evidence"):
                errors.append(f"{task}: no evidence")
            for cite in row.get("evidence", []):
                ref, filename = cite.get("ref", ""), cite.get("path", "")
                start, end = cite.get("line_start"), cite.get("line_end")
                if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
                    errors.append(f"{task}: invalid range {filename}:{start}-{end}")
                    continue
                key = (ref, filename)
                if key not in sources:
                    source = None
                    path_obj = Path(filename)
                    if re.fullmatch(r"[0-9a-f]{7,40}", ref):
                        # Prefer the exact committed source; absolute paths do not
                        # silently replace a cited Git revision with a working tree.
                        for repo in (repository, mobile):
                            relative = filename
                            if path_obj.is_absolute():
                                try:
                                    relative = str(path_obj.relative_to(repo))
                                except ValueError:
                                    continue
                            result = subprocess.run(
                                ["git", "show", f"{ref}:{relative}"], cwd=repo,
                                capture_output=True, text=True,
                            )
                            if result.returncode == 0:
                                source = result.stdout.splitlines()
                                break
                    else:
                        # Non-Git evidence must name its checked working tree or
                        # a saved result explicitly. It is not treated as deployed.
                        candidates = [path_obj] if path_obj.is_absolute() else [repository / filename]
                        for candidate in candidates:
                            if candidate.is_file():
                                source = candidate.read_text().splitlines()
                                break
                    sources[key] = source
                source = sources[key]
                if source is None:
                    errors.append(f"{task}: cannot resolve {ref}:{filename}")
                elif end > len(source):
                    errors.append(f"{task}: {filename}:{end} exceeds {len(source)} lines")
                else:
                    checked += 1
    counts = Counter(row.get("id") for row in rows)
    duplicates = [task for task, count in counts.items() if count != 1]
    if duplicates:
        errors.append(f"Duplicate IDs: {duplicates}")
    output = {"assigned": len(expected), "covered": len(counts),
              "missing": sorted(expected - counts.keys()), "citations_checked": checked,
              "source_files_checked": len(sources), "errors": errors,
              "note": "Coverage/source-range validation only; human root review judges findings."}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
