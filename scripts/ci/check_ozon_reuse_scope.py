#!/usr/bin/env python3
"""Fail a PR that turns the Ozon reuse-first prototype into a parallel UI."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "tasks/ozon-module-20260824/REUSE_MAP.json"
REPORT = ROOT / "docs/runs/ozon-module-20260824/10-replacement-prototype-report.md"
SPECIAL = {str(MAP_PATH.relative_to(ROOT)), "scripts/ci/check_ozon_reuse_scope.py", str(REPORT.relative_to(ROOT))}


def fail(errors: list[str]) -> int:
    for error in errors:
        print(f"Ozon reuse scope: {error}", file=sys.stderr)
    return 1 if errors else 0


def load_map() -> tuple[dict, set[str], list[str]]:
    errors: list[str] = []
    try:
        mapping = json.loads(MAP_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {}, set(), [f"cannot read REUSE_MAP.json: {exc}"]
    if mapping.get("policy") != "reuse_first":
        errors.append("REUSE_MAP policy must be reuse_first")
    allowed: set[str] = set()
    required = {"requirement_id", "existing_surface", "existing_route", "minimal_delta", "allowed_files", "forbidden_scope", "new_surface_required"}
    for index, row in enumerate(mapping.get("requirements", [])):
        missing = required - set(row)
        if missing:
            errors.append(f"map row {index} is missing {', '.join(sorted(missing))}")
        allowed.update(row.get("allowed_files", []))
        if row.get("new_surface_required") and not row.get("incompatibility_evidence", "").strip():
            errors.append(f"{row.get('requirement_id', index)} has a new surface without concrete incompatibility evidence")
    return mapping, allowed, errors


def diff(base: str, head: str) -> tuple[dict[str, str], str]:
    revision = [base] if head == "WORKTREE" else [f"{base}...{head}"]
    names = subprocess.check_output(["git", "diff", "--name-status", *revision], cwd=ROOT, text=True)
    patch = subprocess.check_output(["git", "diff", "--unified=0", *revision], cwd=ROOT, text=True)
    changed: dict[str, str] = {}
    for line in names.splitlines():
        parts = line.split("\t")
        if not parts:
            continue
        changed[parts[-1]] = parts[0]
    return changed, patch


def frontend_source_additions(patch: str) -> str:
    """Return additions from frontend source files, excluding evidence and gate text."""
    additions: list[str] = []
    is_frontend_source = False
    for line in patch.splitlines():
        if line.startswith("+++ "):
            path = line[4:]
            if path.startswith("b/"):
                path = path[2:]
            is_frontend_source = path.startswith("frontend/src/")
        elif is_frontend_source and line.startswith("+") and not line.startswith("+++"):
            additions.append(line[1:])
    return "\n".join(additions)


def evaluate(mapping: dict, allowed: set[str], changed: dict[str, str], additions: str) -> list[str]:
    errors: list[str] = []
    ui_prefixes = ("frontend/src/screens/", "frontend/src/pages/", "frontend/src/prototypes/", "frontend/src/layouts/", "frontend/src/App.tsx")
    for path, status in changed.items():
        if path.startswith(ui_prefixes) and path not in allowed and path not in SPECIAL:
            errors.append(f"unmapped UI file {path}; map it to a requirement or keep the change inside an existing allowed surface")
        if status.startswith("A") and path.startswith("frontend/src/") and path.endswith((".tsx", ".ts")) and path not in allowed:
            errors.append(f"new frontend helper/screen file {path} is forbidden by reuse-first map")
    lowered = additions.lower()
    forbidden = ("/app/ff/ozon", "ozon/fbs", "ozon/fbo", "ozon/catalog", "ozon/connection", "ozon/returns")
    for token in forbidden:
        if token in lowered:
            errors.append(f"added forbidden Ozon route/navigation token {token}")
    if "OzonModulePrototype" in additions:
        errors.append("standalone OzonModulePrototype must be removed, not amended")
    # Reuse-first is semantic, not merely a list of permitted paths.  These
    # patterns catch a replacement UI hidden inside an otherwise allowed file.
    if re.search(r"if\s*\(\s*ozonPrototype\s*\)\s*return\b", additions, re.I):
        errors.append("ozonPrototype-conditioned early screen/workspace return is forbidden")
    if re.search(r"(?:function|const)\s+Ozon\w*(?:Queue|Screen|Workspace|Document)\w*\b", additions):
        errors.append("Ozon-named full-surface Queue/Screen/Workspace/Document component is forbidden")
    added_lines = additions.splitlines()
    has_ozon_fbo_modal = any(
        "<dialog" in line.lower()
        and "ozon-fbo" in "\n".join(added_lines[index:index + 4]).lower()
        and re.search(r"(?:<Tabs\b|<DialogTitle\b|<DialogActions\b)", "\n".join(added_lines[index:index + 8]))
        for index, line in enumerate(added_lines)
    )
    if has_ozon_fbo_modal:
        errors.append("Ozon-only FBO document modal or copied top-level Tabs/Header/Footer is forbidden")
    return errors


def self_test() -> int:
    mapping, allowed, errors = load_map()
    errors += evaluate(mapping, allowed, {"frontend/src/screens/v2/FfFbsOrdersScreen.tsx": "M"}, "")
    if errors:
        return fail([f"self-test passing model failed: {item}" for item in errors])
    forbidden_literals = "\n".join((
        "/app/ff/ozon",
        "ozon/fbs",
        "ozon/fbo",
        "ozon/catalog",
        "ozon/connection",
        "ozon/returns",
        "OzonModulePrototype",
        "if (ozonPrototype) return <Queue />",
        "function OzonQueueFixture() { return <div /> }",
        "<Dialog data-testid=\"ozon-fbo-inline-document\"><DialogTitle>Ozon</DialogTitle><Tabs /></Dialog>",
    ))
    docs_patch = f"+++ b/docs/runs/evidence.md\n+{''.join(f'+{line}\\n' for line in forbidden_literals.splitlines())}"
    documentation_errors = evaluate(mapping, allowed, {"docs/runs/evidence.md": "M"}, frontend_source_additions(docs_patch))
    if documentation_errors:
        return fail([f"self-test documentation evidence was treated as UI source: {item}" for item in documentation_errors])
    frontend_patch = f"+++ b/frontend/src/App.tsx\n+{''.join(f'+{line}\\n' for line in forbidden_literals.splitlines())}"
    frontend_additions = frontend_source_additions(frontend_patch)
    route_errors = evaluate(mapping, allowed, {"frontend/src/App.tsx": "M"}, frontend_additions)
    screen_errors = evaluate(mapping, allowed, {"frontend/src/screens/v2/OzonDashboardScreen.tsx": "A"}, "")
    early_return_errors = evaluate(mapping, allowed, {"frontend/src/screens/v2/FfFbsOrdersScreen.tsx": "M"}, frontend_additions)
    component_errors = evaluate(mapping, allowed, {"frontend/src/screens/v2/FfFbsOrdersScreen.tsx": "M"}, frontend_additions)
    modal_errors = evaluate(mapping, allowed, {"frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx": "M"}, frontend_additions)
    expected_errors = (
        (route_errors, "added forbidden Ozon route/navigation token /app/ff/ozon"),
        (screen_errors, "unmapped UI file frontend/src/screens/v2/OzonDashboardScreen.tsx"),
        (early_return_errors, "ozonPrototype-conditioned early screen/workspace return is forbidden"),
        (component_errors, "Ozon-named full-surface Queue/Screen/Workspace/Document component is forbidden"),
        (modal_errors, "Ozon-only FBO document modal or copied top-level Tabs/Header/Footer is forbidden"),
    )
    if any(not any(error.startswith(expected) for error in result) for result, expected in expected_errors):
        return fail(["self-test did not reject route, unmapped screen, early return, full-surface component, and Ozon FBO modal patterns"])
    print("Ozon reuse scope self-test passed: documentation evidence ignored; frontend route, unmapped screen, early return, full-surface component and Ozon FBO modal rejected.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/etalon")
    parser.add_argument("--head", default="HEAD", help="commit/ref or WORKTREE to validate uncommitted current changes")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    mapping, allowed, errors = load_map()
    try:
        changed, patch = diff(args.base, args.head)
    except subprocess.CalledProcessError as exc:
        return fail([f"cannot compare {args.base}...{args.head}: {exc}"])
    errors += evaluate(mapping, allowed, changed, frontend_source_additions(patch))
    if errors:
        return fail(errors)
    print(f"Ozon reuse scope passed for {args.base}...{args.head}: {len(changed)} changed files are mapped or contract artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
