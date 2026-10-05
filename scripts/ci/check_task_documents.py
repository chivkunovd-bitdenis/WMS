#!/usr/bin/env python3
"""Check that new tasks have filled acceptance documents, not whether they passed."""

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

SCRIPT_PATH = "scripts/ci/check_task_documents.py"
CONTRACT_CORRECTIONS_DIR = "docs/reviews/contract-corrections"


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
        test_col = headers.index("тест") if "тест" in headers else None
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


def commit_changed_paths(root: Path, commit: str) -> set[str]:
    revision = git(root, "rev-list", "--parents", "-n", "1", commit).split()
    if len(revision) == 1:
        return set(git(root, "ls-tree", "-r", "--name-only", commit).splitlines())
    return set(
        git(root, "diff", "--no-renames", "--name-only", revision[1], commit).splitlines()
    )


def is_task_contract_commit(root: Path, commit: str, task_id: str) -> bool:
    """Return whether commit is this task's real contract in current history."""
    exists = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=root,
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    if not exists:
        return False
    if git(root, "show", "-s", "--format=%s", commit) != f"{task_id}: контракт тестов":
        return False
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=root,
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def reviewed_contract_correction(
    root: Path,
    task_id: str,
    contract_commit: str,
    task_contracts: set[str],
    frozen: list[str],
) -> tuple[str | None, set[str], list[str]]:
    """Return the reviewed correction SHA, or explain why its ledger is invalid.

    A correction is deliberately stricter than an ordinary follow-up commit: it
    may touch only files frozen by the original contract and must have a separate
    machine-readable ledger recording the independent Astra-high PASS. CI can
    validate the Git facts; the controller remains responsible for obtaining
    and recording the review before the ledger is committed.
    """
    ledger_rel = f"{CONTRACT_CORRECTIONS_DIR}/{task_id}.json"
    ledger_result = subprocess.run(
        ["git", "show", f"HEAD:{ledger_rel}"], cwd=root, check=False,
        capture_output=True, text=True,
    )
    if ledger_result.returncode != 0:
        return None, set(), []
    ledger_text = ledger_result.stdout.strip()
    try:
        ledger = json.loads(ledger_text)
    except json.JSONDecodeError:
        return None, set(), [
            f"{task_id}: некорректный реестр коррекции контракта {ledger_rel}"
        ]
    if not isinstance(ledger, dict):
        return None, set(), [
            f"{task_id}: реестр коррекции контракта должен быть JSON-объектом"
        ]
    ledger_contract = str(ledger.get("contract_commit") or "")
    correction = str(ledger.get("correction_commit") or "")
    files = ledger.get("files")
    review = ledger.get("review")
    if (
        ledger.get("task") != task_id
        or not re.fullmatch(r"[0-9a-f]{40}", ledger_contract)
        or not re.fullmatch(r"[0-9a-f]{40}", correction)
        or not isinstance(files, list)
        or not files
        or any(not isinstance(path, str) or not path for path in files)
        or not isinstance(review, dict)
        or review.get("model") != "gpt-6-astra"
        or review.get("effort") != "high"
        or review.get("verdict") != "PASS"
    ):
        return None, set(), [
            f"{task_id}: реестр коррекции контракта заполнен не полностью"
        ]
    if ledger_contract != contract_commit:
        # One task may acquire several independent contract commits.  Its one
        # correction ledger applies only to the exact existing contract named
        # there; an absent or invented source commit must not disappear merely
        # because this invocation is currently checking another contract.
        if ledger_contract in task_contracts or is_task_contract_commit(
            root, ledger_contract, task_id
        ):
            return None, set(), []
        return None, set(), [
            f"{task_id}: реестр ссылается на неизвестный исходный контракт"
        ]
    if correction == contract_commit:
        return None, set(), [
            f"{task_id}: коррекция должна быть отдельным последующим коммитом"
        ]
    for older, newer, label in (
        (contract_commit, correction, "коррекция не следует за исходным контрактом"),
        (correction, "HEAD", "коррекция отсутствует в текущей версии"),
    ):
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer], cwd=root,
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode != 0:
            return None, set(), [f"{task_id}: {label}"]
    expected = set(files)
    frozen_set = set(frozen)
    if not expected.issubset(frozen_set) or (
        len(frozen_set) > 1 and expected == frozen_set
    ):
        return None, set(), [
            f"{task_id}: коррекция должна менять только часть исходного контракта"
        ]
    changed = commit_changed_paths(root, correction)
    if changed != expected:
        return None, set(), [
            f"{task_id}: коммит коррекции должен менять ровно перечисленные файлы"
        ]
    return correction, expected, []


def contract_change_errors(root: Path, base: str) -> list[str]:
    # Сравниваем содержимое файлов контракта в его коммите и в HEAD, а не пути
    # каждого последующего коммита: на pull_request HEAD — служебный merge-коммит
    # PR, его diff к первому родителю содержит весь PR, и контракт ложно считался
    # изменённым. Документ требований входит в коммит контракта (столбец «Тест»),
    # но вердикты и заключение в нём по процессу заполняет аналитик на приёмке,
    # поэтому он не замораживается.
    commits = git(root, "rev-list", "--reverse", f"{base}..HEAD").splitlines()
    errors = []
    contracts = []
    contracts_by_task: dict[str, set[str]] = {}
    for commit in commits:
        subject = git(root, "show", "-s", "--format=%s", commit)
        match = re.fullmatch(r"(WMS-\d+): контракт тестов", subject)
        if not match:
            continue
        frozen = sorted(
            path for path in commit_changed_paths(root, commit)
            if not path.startswith("docs/requirements/")
        )
        if not frozen:
            continue
        task_id = match[1]
        contracts.append((commit, task_id, frozen))
        contracts_by_task.setdefault(task_id, set()).add(commit)
    for commit, task_id, frozen in contracts:
        correction, corrected, correction_errors = reviewed_contract_correction(
            root, task_id, commit, contracts_by_task[task_id], frozen
        )
        errors.extend(correction_errors)
        if correction_errors:
            continue
        overlap = set()
        untouched = sorted(set(frozen) - corrected)
        if untouched:
            overlap.update(
                git(root, "diff", "--no-renames", "--name-only", commit, "HEAD", "--", *untouched)
                .splitlines()
            )
        if corrected:
            assert correction is not None
            overlap.update(
                git(root, "diff", "--no-renames", "--name-only", correction, "HEAD", "--", *sorted(corrected))
                .splitlines()
            )
        overlap = sorted(overlap)
        if overlap:
            errors.append(
                f"изменён контракт тестов {task_id} после его фиксации: "
                + ", ".join(overlap)
            )
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
    errors.extend(contract_change_errors(root, base))
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
