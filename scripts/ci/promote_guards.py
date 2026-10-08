#!/usr/bin/env python3
"""Promote WMS checks classified as permanent into regression guard directories."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.process_contracts import POLICY_PATH, local_file, validate_policy

MANIFEST = "guards/MANIFEST.json"
BACKEND_ROOT = PurePosixPath("backend/tests/guards")
FRONTEND_ROOT = PurePosixPath("frontend/src/guards")
GUARD_ROOTS = (BACKEND_ROOT, FRONTEND_ROOT)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def cells(line: str) -> list[str]:
    stripped = line.strip().removeprefix("|").removesuffix("|")
    return [part.strip() for part in re.split(r"(?<!\\)\|", stripped)]


def plain(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(str.maketrans("", "", "*_`"))).strip()


def parse_reference(reference: str) -> tuple[PurePosixPath, str]:
    normalized = re.sub(r"\s+", " ", reference.translate(str.maketrans("", "", "*`"))).strip()
    path_text, separator, test_name = normalized.partition("::")
    path = PurePosixPath(path_text)
    if (
        not separator
        or not path_text
        or not test_name
        or path.is_absolute()
        or str(path) != path_text
        or ".." in path.parts
    ):
        raise ValueError(f"Некорректная ссылка на тест: {reference}")
    return path, test_name


def guard_target(source: PurePosixPath) -> PurePosixPath:
    if source == BACKEND_ROOT or BACKEND_ROOT in source.parents:
        return source
    if source.parts[:2] == ("backend", "tests"):
        return BACKEND_ROOT.joinpath(*source.parts[2:])
    if source == FRONTEND_ROOT or FRONTEND_ROOT in source.parents:
        return source
    if source.parts[:2] == ("frontend", "src"):
        return FRONTEND_ROOT.joinpath(*source.parts[2:])
    raise ValueError(f"Тест вне поддерживаемых backend/frontend каталогов: {source}")


JS_IMPORT = re.compile(
    r"(?P<prefix>\b(?:from|import|require|vi\.mock|jest\.mock)\s*(?:\(\s*)?)"
    r"(?P<quote>['\"])(?P<path>\.\.?/[^'\"]+)(?P=quote)"
)


def rewrite_javascript_imports(text: str, source: PurePosixPath, target: PurePosixPath) -> str:
    def replace(match: re.Match[str]) -> str:
        resolved = posixpath.normpath(posixpath.join(str(source.parent), match["path"]))
        relative = posixpath.relpath(resolved, str(target.parent))
        if not relative.startswith("."):
            relative = "./" + relative
        quote = match["quote"]
        return f"{match['prefix']}{quote}{relative}{quote}"

    return JS_IMPORT.sub(replace, text)


PYTHON_FROM = re.compile(
    r"^(?P<indent>\s*)from\s+(?P<dots>\.+)(?P<module>[A-Za-z_][\w.]*)?\s+import\s+",
    re.MULTILINE,
)


def rewrite_python_imports(text: str, source: PurePosixPath) -> str:
    def replace(match: re.Match[str]) -> str:
        package = list(source.parent.parts)
        package = package[: max(0, len(package) - len(match["dots"]) + 1)]
        module = match["module"]
        if module:
            package.extend(module.split("."))
        if package and package[0] == "backend":
            package.pop(0)
        return f"{match['indent']}from {'.'.join(package)} import "

    return PYTHON_FROM.sub(replace, text)


def rewrite_imports(text: str, source: PurePosixPath, target: PurePosixPath) -> str:
    if source.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        return rewrite_javascript_imports(text, source, target)
    if source.suffix == ".py":
        return rewrite_python_imports(text, source)
    return text


def permanent_references(lines: list[str]) -> list[tuple[int, int, PurePosixPath, str]]:
    references = []
    for index, line in enumerate(lines[:-1]):
        headers = [plain(value).casefold() for value in cells(line)]
        if "класс" not in headers or "тест" not in headers:
            continue
        separator = cells(lines[index + 1])
        if len(separator) != len(headers) or not all(
            re.fullmatch(r":?-{3,}:?", value) for value in separator
        ):
            continue
        class_col = headers.index("класс")
        test_col = headers.index("тест")
        for row_index in range(index + 2, len(lines)):
            if "|" not in lines[row_index] or not lines[row_index].strip():
                break
            values = cells(lines[row_index])
            if len(values) != len(headers) or plain(values[class_col]).casefold() != "навсегда":
                continue
            for reference in re.split(r"<br\s*/?>|;", values[test_col], flags=re.IGNORECASE):
                source, test_name = parse_reference(reference)
                references.append((row_index, test_col, source, test_name))
    return references


def saved_process_policy(root: Path) -> dict | None:
    saved_entry = git(root, "ls-tree", "HEAD", "--", POLICY_PATH)
    if not saved_entry:
        if not (root / POLICY_PATH).exists() and not (root / POLICY_PATH).is_symlink():
            return None
        raise ValueError("Process protection должна быть сохранена в Git до promotion")
    try:
        raw = local_file(root, POLICY_PATH).read_bytes()
    except ValueError as exc:
        raise ValueError(f"Process protection сохранена в HEAD, но недоступна: {exc}") from exc
    policy = json.loads(raw)
    validate_policy(policy)
    saved = subprocess.check_output(["git", "-C", str(root), "show", f"HEAD:{POLICY_PATH}"])
    if saved != raw:
        raise ValueError("Process protection должна быть сохранена в Git до promotion")
    return policy


def verify_registered_case(root: Path, policy: dict, source: PurePosixPath, test_name: str) -> bool:
    if str(source) not in policy["files"]:
        return False
    local_file(root, str(source))
    known_687_groups = {
        "frontend/src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx": "WMS-687 shared FBS stock dialog from an inbound document",
        "frontend/src/screens/ff/FfInboundRequestView.wms687.regression.dom.test.tsx": "WMS-687 real shared stock dialog",
        "frontend/src/screens/ff/FfInboundRequestView.wms687.permission.test.ts": "WMS-687 catalog permission wiring",
    }
    group = known_687_groups.get(str(source))
    module_parts = source.with_suffix("").parts
    module = ".".join(module_parts[1:] if module_parts[0] == "backend" else module_parts)
    if str(source) == "scripts/ci/wms663-proof/c10_mixed.py":
        module = "tests.test_wms663_remote_c10"
    frontend = str(source).removeprefix("frontend/")
    script_reports = {
        "scripts/ci/wms663-proof/c10_mixed.py": "release-postgres/663-669-670-683.xml",
        "scripts/ci/test_check_task_documents.py": "docgate-687.xml",
        "scripts/ci/tests/test_product_scope.py": "product-scope.xml",
        **{f"scripts/ci/tests/{name}.py": "ci-shards.xml" for name in (
            "test_backend_shards", "test_backend_shard_failclosed", "test_ci_release_additions",
            "test_backend_shard_redis_setup", "test_promote_guards", "test_process_contracts",
            "test_process_deploy_gate", "test_server_process_gate",
        )},
    }
    for suite in policy["suites"].values():
        required_report = script_reports.get(str(source))
        if required_report and (suite["format"] != "junit" or suite["report"] != required_report):
            continue
        # These two accepted test.each templates represent fixed four-mode
        # matrices. A wildcard/one matching case would silently lose a mode.
        if (str(source) == "frontend/src/sections/CatalogSection.wms654.test.tsx"
                and test_name in ("C6 independent coordinates sides=%s tiers=%s",
                                  "C6 ${entry} sides=%s tiers=%s")):
            if suite["format"] != "vitest" or suite["report"] != "frontend-all.json":
                continue
            if test_name.startswith("C6 independent"):
                titles = ["WMS-654 actual CatalogSection contract C6 independent coordinates"]
            else:
                titles = ["WMS-654 real map form openings C6 " + entry for entry in
                          ("warehouse-map-create-cell", "warehouse-map-create-first-cell")]
            required = {f"{frontend}::{title} sides={sides} tiers={tiers}"
                        for title in titles for sides, tiers in
                        (("false", "false"), ("true", "false"), ("false", "true"), ("true", "true"))}
            if required.issubset(suite["cases"]):
                return True
            continue
        for case in suite["cases"]:
            owner, separator, name = case.partition("::")
            if suite["format"] == "junit":
                matches = (owner == module or owner.startswith(module + ".")) and (
                    name == test_name or name.startswith(test_name + "[")
                )
            elif suite["format"] == "vitest":
                matches = owner == frontend and (name == test_name or name.endswith(" " + test_name))
                if group is not None:
                    matches = (suite["report"] == "frontend-all.json" and owner == frontend
                               and (name == group + " " + test_name
                                    or name == test_name and name.startswith(group + " ")))
            else:
                matches = not separator and case == test_name
            if matches:
                return True
    raise ValueError(f"Защищённый original не имеет обязательного case/report: {source}::{test_name}")


def update_manifest(root: Path) -> None:
    files = {}
    for directory in GUARD_ROOTS:
        for path in (root / directory).rglob("*"):
            if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"version": 1, "state": "active", "files": dict(sorted(files.items()))}
    (root / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def promote(root: Path, task: str) -> list[str]:
    if not re.fullmatch(r"WMS-\d+", task):
        raise ValueError("Номер задачи должен иметь вид WMS-NNN")
    document = root / "docs" / "requirements" / f"{task}.md"
    if not document.is_file():
        raise ValueError(f"Нет документа {document.relative_to(root)}")
    lines = document.read_text(encoding="utf-8").splitlines()
    references = permanent_references(lines)
    if not references:
        return []

    policy = saved_process_policy(root)
    moves: dict[PurePosixPath, PurePosixPath] = {}
    for _, _, source, test_name in references:
        path = root / source
        if not path.is_file():
            raise ValueError(f"Нет файла теста {source}")
        registered = policy is not None and verify_registered_case(root, policy, source, test_name)
        if not registered and test_name not in path.read_text(encoding="utf-8"):
            raise ValueError(f"В {source} не найдено имя теста {test_name}")
        target = source if registered else guard_target(source)
        if target in moves.values() and moves.get(source) != target:
            raise ValueError(f"Несколько тестов претендуют на {target}")
        if target != source and (root / target).exists():
            raise ValueError(f"Целевой файл уже существует: {target}")
        moves[source] = target

    for source, target in moves.items():
        if source == target:
            continue
        source_path = root / source
        target_path = root / target
        target_path.parent.mkdir(parents=True, exist_ok=True)
        rewritten = rewrite_imports(source_path.read_text(encoding="utf-8"), source, target)
        source_path.write_text(rewritten, encoding="utf-8")
        subprocess.check_call(["git", "-C", str(root), "mv", str(source), str(target)])

    # A fully registered contract is already permanent. Preserve its bytes and
    # document verbatim; in particular a second invocation must have no diff.
    if any(source != target for source, target in moves.items()):
        rows: dict[tuple[int, int], list[str]] = {}
        for row_index, test_col, source, test_name in references:
            rows.setdefault((row_index, test_col), []).append(f"{moves[source]}::{test_name}")
        for (row_index, test_col), row_references in rows.items():
            values = cells(lines[row_index])
            values[test_col] = "<br>".join(row_references)
            lines[row_index] = "| " + " | ".join(values) + " |"
        document.write_text("\n".join(lines) + "\n", encoding="utf-8")
        update_manifest(root)
    return [str(target) for target in moves.values()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="WMS-NNN")
    args = parser.parse_args()
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel"))
    try:
        promoted = promote(root, args.task)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"promote_guards: {exc}") from exc
    print("Перенесены в охрану: " + ", ".join(promoted))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
