#!/usr/bin/env python3
"""Check that new tasks have filled acceptance documents, not whether they passed."""

import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath

SCRIPT_PATH = "scripts/ci/check_task_documents.py"

def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def task_refs(root: Path, base: str) -> list[str]:
    # Old commits in a long-lived PR must not acquire retrospective obligations.
    introductions = git(root, "log", "--diff-filter=A", "--format=%H", "HEAD",
                        "--", SCRIPT_PATH).splitlines()
    refs = set()
    for commit in git(root, "rev-list", f"{base}..HEAD").splitlines():
        if not any(subprocess.run(
            ["git", "merge-base", "--is-ancestor", start, commit], cwd=root,
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0 for start in introductions):
            continue
        refs.update(re.findall(r"\bWMS-\d+\b", git(root, "show", "-s", "--format=%B", commit)))
    return sorted(refs)


def visible_lines(text: str) -> list[str]:
    """Ignore examples inside fenced code blocks."""
    lines = []
    fence = ""
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = ""
            continue
        if marker:
            fence = marker[1]
        else:
            lines.append(line)
    return lines


def cells(line: str) -> list[str]:
    line = line.strip().removeprefix("|").removesuffix("|")
    return [part.strip() for part in re.split(r"(?<!\\)\|", line)]


def plain(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(str.maketrans("", "", "*_`"))).strip()


def test_reference(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(str.maketrans("", "", "*`"))).strip()


def test_references(value: str) -> list[str]:
    """Validate every test link stored in one Markdown table cell."""
    return [
        reference
        for part in re.split(r"<br\s*/?>", value, flags=re.IGNORECASE)
        if (reference := test_reference(part))
    ]


def test_reference_errors(root: Path, reference: str) -> list[str]:
    path_text, separator, test_name = test_reference(reference).partition("::")
    pure = PurePosixPath(path_text)
    if (
        not separator
        or not path_text
        or not test_name
        or pure.is_absolute()
        or str(pure) != path_text
        or ".." in pure.parts
    ):
        return [f"Некорректная ссылка на тест: {reference}; ожидается путь::имя теста."]
    path = root / path_text
    if not path.is_file():
        return [f"Нет файла теста {path_text}."]
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"Файл теста {path_text} не является текстовым."]
    # Exact saved original/hash/case/report proof also covers it.each expansion.
    # Unprotected legacy references still use the literal source contract.
    import sys
    project_root = str(Path(__file__).resolve().parents[2])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from scripts.ci.promote_guards import saved_process_policy, verify_registered_case
    try:
        policy = (saved_process_policy(root)
                  if (root / "guards/PROCESS_CONTRACTS.json").exists()
                  or (root / "guards/PROCESS_CONTRACTS.json").is_symlink() else None)
        if policy is not None and path_text in policy["files"]:
            if verify_registered_case(root, policy, pure, test_name):
                return []
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        return [f"Не подтверждена постоянная охрана {path_text}::{test_name}: {exc}"]
    if test_name not in content:
        return [f"В {path_text} не найдено имя теста {test_name}."]
    return []


def document_errors(text: str, root: Path | None = None) -> list[str]:
    lines = visible_lines(text)
    errors = []
    checks = 0
    for i, line in enumerate(lines[:-1]):
        headers = [plain(cell).casefold() for cell in cells(line)]
        check_names = {"проверка", "сценарий", "check", "scenario"}
        verdict_names = {"вердикт", "результат", "результат проверки", "verdict"}
        if not check_names.intersection(headers) or not verdict_names.intersection(headers):
            continue
        separator = cells(lines[i + 1])
        if len(separator) != len(headers) or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
            errors.append("У таблицы проверок нет корректной строки разделителей Markdown.")
            continue
        check_col = next(j for j, header in enumerate(headers) if header in check_names)
        verdict_col = next(j for j, header in enumerate(headers) if header in verdict_names)
        class_col = headers.index("класс") if "класс" in headers else None
        test_col = next(
            (index for index, header in enumerate(headers)
             if header == "тест" or header.startswith("тест / ")),
            None,
        )
        if class_col is not None and test_col is None:
            errors.append("В таблице с колонкой «Класс» нет колонки «Тест».")
        for row in lines[i + 2:]:
            if "|" not in row or not row.strip():
                break
            values = cells(row)
            checks += 1
            if len(values) != len(headers):
                errors.append(f"Неверное число ячеек в проверке: {row.strip()}")
                continue
            if not plain(values[check_col]):
                errors.append("В таблице есть проверка без описания или названия.")
            if not plain(values[verdict_col]):
                errors.append(f"Нет вердикта у проверки: {values[check_col]}")
            if class_col is not None and test_col is not None:
                check_class = plain(values[class_col]).casefold()
                references = test_references(values[test_col])
                if check_class in {"навсегда", "разово"}:
                    if not references:
                        errors.append(
                            f"У автоматической проверки {values[check_col]} нет ссылки на тест."
                        )
                    elif root is not None:
                        for reference in references:
                            errors.extend(test_reference_errors(root, reference))
    if not checks:
        errors.append("Нет проверок в таблице с колонками «Проверка» и «Вердикт».")

    conclusion = False
    for i, line in enumerate(lines):
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not heading:
            continue
        title = re.sub(r"^\d+[.)]\s*", "", plain(heading[2])).casefold()
        if title not in {"заключение", "итоговое заключение", "conclusion"}:
            continue
        for following in lines[i + 1:]:
            next_heading = re.match(r"^\s{0,3}(#{1,6})\s+", following)
            if next_heading:
                if len(next_heading[1]) <= len(heading[1]):
                    break
                continue
            if plain(following):
                conclusion = True
                break
    if not conclusion:
        errors.append("Не заполнен раздел «Заключение».")
    return errors


def check(root: Path, base: str) -> list[str]:
    errors = []
    if not all((root / name).is_file() for name in ("AGENTS.md", "CLAUDE.md")) or (root / "AGENTS.md").read_bytes() != (root / "CLAUDE.md").read_bytes():
        errors.append("AGENTS.md и CLAUDE.md должны существовать и содержать одинаковые правила.")
    for ref in task_refs(root, base):
        path = root / "docs" / "requirements" / f"{ref}.md"
        if not path.is_file():
            errors.append(f"{ref}: нет документа {path.relative_to(root)}.")
        else:
            errors.extend(
                f"{ref}: {error}"
                for error in document_errors(path.read_text(encoding="utf-8"), root)
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", nargs="?", default="origin/etalon")
    args = parser.parse_args()
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel"))
    errors = check(root, args.base)
    if errors:
        print("\n".join(errors))
        return 1
    print("Документы задач заполнены; AGENTS.md и CLAUDE.md совпадают.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
