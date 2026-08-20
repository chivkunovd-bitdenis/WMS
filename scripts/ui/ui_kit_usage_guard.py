#!/usr/bin/env python3
"""Guard WMS screens against new UI that bypasses frontend/src/ui-kit.

The existing ui_guard.py is a ratchet for raw MUI primitives. This guard covers
the missing W12 rule: a new screen, or a changed screen that adds visible UI
markup, must import the canonical ui-kit. Legacy screens are kept in the
baseline so the project does not have to rewrite production UI in one wave.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
SCREEN_ROOT = FRONTEND / "src" / "screens"
REGISTRY = FRONTEND / "screens.registry.json"
BASELINE = ROOT / "docs" / "product" / "ui-kit-usage-baseline.json"

UI_KIT_IMPORT_RE = re.compile(r"from\s+['\"](?:[^'\"]*/)?ui-kit(?:/index)?['\"]")
UI_KIT_NAMED_IMPORT_RE = re.compile(
    r"import\s*\{(?P<names>[^}]+)\}\s*from\s*['\"](?:[^'\"]*/)?ui-kit(?:/index)?['\"]",
    re.S,
)
UI_KIT_TAGS = {
    "ActionGroup",
    "ActionMenu",
    "CheckboxField",
    "DangerAction",
    "DataTable",
    "EmptyState",
    "ErrorNotice",
    "FilterBar",
    "IconAction",
    "MarkChip",
    "ModalDialog",
    "PlanFactCell",
    "PrimaryAction",
    "PrintAction",
    "ProductCell",
    "QtyCell",
    "ScannerLine",
    "ScreenHeader",
    "ScreenSection",
    "ScreenShell",
    "SecondaryAction",
    "SelectField",
    "StatusChip",
    "TableSkeletonBody",
    "TabsBar",
    "TextCell",
    "TextInput",
    "ToolbarLine",
}
UI_KIT_TAG_RE = re.compile(r"<(?:" + "|".join(sorted(UI_KIT_TAGS)) + r")\b")
RAW_UI_ADDITION_RE = re.compile(
    r"<(?:"
    r"Alert|Autocomplete|Box|Button|Checkbox|Chip|Dialog|FormControl|Grid|IconButton|Menu|"
    r"Paper|Select|Stack|Tab|Table|TableBody|TableCell|TableContainer|TableHead|TableRow|"
    r"Tabs|TextField|ToggleButton|Toolbar|Tooltip|Typography"
    r")\b|"
    r"\bsx=\{|"
    r"\bstyle=\{|"
    r"#[0-9a-fA-F]{6}\b"
)


def frontend_rel(path: Path) -> str:
    return str(path.relative_to(FRONTEND))


def load_screen_map() -> dict[str, list[str]]:
    if not REGISTRY.exists():
        return {}
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    files: dict[str, set[str]] = {}
    for screen in registry.get("screens", []):
        screen_id = str(screen.get("id", ""))
        for rel in screen.get("files", []):
            files.setdefault(rel, set()).add(screen_id)
        for rel, owners in screen.get("shared", {}).items():
            bucket = files.setdefault(rel, set())
            for owner in owners:
                bucket.add(str(owner))
    return {rel: sorted(owners) for rel, owners in files.items()}


def iter_screen_files() -> list[Path]:
    return sorted(path for path in SCREEN_ROOT.rglob("*.tsx") if path.is_file())


def ui_kit_symbols(text: str) -> list[str]:
    symbols: set[str] = set()
    for match in UI_KIT_NAMED_IMPORT_RE.finditer(text):
        for raw in match.group("names").split(","):
            name = raw.strip().split(" as ", 1)[0].strip()
            if name:
                symbols.add(name)
    return sorted(symbols)


def scan() -> dict[str, dict[str, object]]:
    screen_map = load_screen_map()
    found: dict[str, dict[str, object]] = {}
    for path in iter_screen_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = frontend_rel(path)
        symbols = ui_kit_symbols(text)
        found[rel] = {
            "ui_kit_imports": len(UI_KIT_IMPORT_RE.findall(text)),
            "ui_kit_symbols": symbols,
            "screen_ids": screen_map.get(rel, []),
        }
    return found


def write_baseline(current: dict[str, dict[str, object]]) -> None:
    payload = {
        "version": 1,
        "generated_by": "scripts/ui/ui_kit_usage_guard.py --update",
        "rule": "New screens and changed visible UI zones must import frontend/src/ui-kit.",
        "legacy_policy": "Existing screens without ui-kit are baseline debt; new debt is blocked.",
        "screen_files": current,
    }
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def changed_screen_paths(base: str) -> set[str]:
    commands = [
        ["diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD", "--", "frontend/src/screens"],
        ["diff", "--name-only", "--diff-filter=AM", base, "--", "frontend/src/screens"],
    ]
    for command in commands:
        result = run_git(command)
        if result.returncode == 0:
            return {
                path.removeprefix("frontend/")
                for path in result.stdout.splitlines()
                if path.startswith("frontend/src/screens/") and path.endswith(".tsx")
            }
    print(f"ui-kit usage guard: cannot diff from {base}: {result.stderr}", file=sys.stderr)
    return set()


def added_lines(base: str, rel: str) -> list[str]:
    path = f"frontend/{rel}"
    commands = [
        ["diff", "--unified=0", f"{base}...HEAD", "--", path],
        ["diff", "--unified=0", base, "--", path],
    ]
    for command in commands:
        result = run_git(command)
        if result.returncode == 0:
            return [
                line[1:]
                for line in result.stdout.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ]
    return []


def diff_adds_visible_ui(base: str, rel: str) -> bool:
    return any(RAW_UI_ADDITION_RE.search(line) or UI_KIT_TAG_RE.search(line) for line in added_lines(base, rel))


def diff_adds_raw_ui(base: str, rel: str) -> bool:
    return any(RAW_UI_ADDITION_RE.search(line) for line in added_lines(base, rel))


def file_contains_raw_ui(path: Path) -> bool:
    return bool(RAW_UI_ADDITION_RE.search(path.read_text(encoding="utf-8", errors="replace")))


def validate(current: dict[str, dict[str, object]], *, changed_from: str | None) -> list[str]:
    if not BASELINE.exists():
        return [f"нет базовой линии {BASELINE}; запусти scripts/ui/ui_kit_usage_guard.py --update"]
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline_files = baseline.get("screen_files", {})
    if not isinstance(baseline_files, dict):
        return [f"{BASELINE} имеет неверный формат: нет screen_files"]

    errors: list[str] = []
    for rel, meta in current.items():
        if rel not in baseline_files:
            path = FRONTEND / rel
            if not meta.get("ui_kit_imports"):
                errors.append(f"НОВЫЙ ЭКРАН БЕЗ UI-KIT: frontend/{rel}")
            if file_contains_raw_ui(path):
                errors.append(f"НОВЫЙ ЭКРАН С RAW UI МИМО UI-KIT: frontend/{rel}")

    if changed_from:
        for rel in sorted(changed_screen_paths(changed_from)):
            if rel not in current:
                continue
            meta = current[rel]
            if diff_adds_raw_ui(changed_from, rel):
                errors.append(
                    "НОВАЯ RAW UI-РАЗМЕТКА МИМО UI-KIT: "
                    f"frontend/{rel} добавляет MUI/inline style вместо frontend/src/ui-kit"
                )
            elif diff_adds_visible_ui(changed_from, rel) and not meta.get("ui_kit_imports"):
                errors.append(
                    "НОВАЯ UI-ЗОНА БЕЗ UI-KIT: "
                    f"frontend/{rel} добавляет видимую разметку, но не импортирует frontend/src/ui-kit"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="rewrite legacy baseline")
    parser.add_argument(
        "--changed-from",
        default=os.environ.get("PR_BASE_SHA") or None,
        help="git base SHA/ref for changed-zone checks; defaults to PR_BASE_SHA",
    )
    args = parser.parse_args()

    current = scan()
    if args.update:
        write_baseline(current)
        legacy = sum(1 for meta in current.values() if not meta.get("ui_kit_imports"))
        print(f"ui-kit usage baseline written: {len(current)} screen files, {legacy} legacy without ui-kit")
        return 0

    errors = validate(current, changed_from=args.changed_from)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(
            "\nКанон WMS: новая экранная работа собирается из frontend/src/ui-kit. "
            "Если нужного элемента нет, он добавляется в ui-kit до правки экрана.",
            file=sys.stderr,
        )
        return 1

    imported = sum(1 for meta in current.values() if meta.get("ui_kit_imports"))
    print(f"ui-kit usage ok: {imported}/{len(current)} screen files import ui-kit; legacy debt is unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
