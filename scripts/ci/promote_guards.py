#!/usr/bin/env python3
"""Promote WMS checks classified as permanent into regression guard directories."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import subprocess
from pathlib import Path, PurePosixPath

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
            source, test_name = parse_reference(values[test_col])
            references.append((row_index, test_col, source, test_name))
    return references


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
        raise ValueError(f"В {task} нет проверок класса «навсегда»")

    moves: dict[PurePosixPath, PurePosixPath] = {}
    for _, _, source, test_name in references:
        path = root / source
        if not path.is_file():
            raise ValueError(f"Нет файла теста {source}")
        if test_name not in path.read_text(encoding="utf-8"):
            raise ValueError(f"В {source} не найдено имя теста {test_name}")
        target = guard_target(source)
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

    for row_index, test_col, source, test_name in references:
        values = cells(lines[row_index])
        values[test_col] = f"{moves[source]}::{test_name}"
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
