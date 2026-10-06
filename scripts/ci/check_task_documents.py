#!/usr/bin/env python3
"""Check that new tasks have filled acceptance documents, not whether they passed."""

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

SCRIPT_PATH = "scripts/ci/check_task_documents.py"
CONTRACT_CORRECTIONS_DIR = "docs/reviews/contract-corrections"

# An exact-content allowlist, NOT a generic permission to edit fixture code.
# Each pair is the entire historical file, including assertions, test names,
# decorators, imports and control flow. Changing even one other byte is denied.
# New pairs require a process change with RED regressions and independent review.
FIXTURE_BLOB_PAIRS = {
    "wms517-uuid-before-rollback": (
        "WMS-517", "backend/tests/test_wms517_sales_contract.py",
        "a36ab064c9a70b8c3df472f176e4e5ba9d567fcb",
        "393cb668b7b7fb702f75d949ba41421a46f5676e",
    ),
    "wms517-explicit-sales-fixture": (
        "WMS-517", "backend/tests/test_wms517_sales_contract.py",
        "393cb668b7b7fb702f75d949ba41421a46f5676e",
        "b5ddcb3b42810902b05da09726222b7e500684cf",
    ),
    "wms663-uuid-before-expire": (
        "WMS-663", "backend/tests/test_wms663_customs_documents_contract.py",
        "5fb61d0c51a6b4f2d84f3b5bf17397f622059283",
        "4e1aff5a80445fa61b5697d60a26985427dfd28e",
    ),
    "wms663-exemplar-save-selector": (
        "WMS-663", "frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx",
        "21baad5243f664aca69ff817407ea17e66f59155",
        "8548a75eb6963edcd5e3b3755e0a618d918f9f94",
    ),
    "wms663-close-accessible-selector": (
        "WMS-663", "frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx",
        "8548a75eb6963edcd5e3b3755e0a618d918f9f94",
        "7b41916c43bf144d9fdeb7772d415bdf5535ff05",
    ),
    "wms663-complete-positive-status-fixtures": (
        "WMS-663", "backend/tests/test_wms663_customs_documents_contract.py",
        "4e1aff5a80445fa61b5697d60a26985427dfd28e",
        "c92c075ba9f375c578538b776207cdc6b8b56ab3",
    ),
}
POSITIVE_STATUS_TRANSFORM = "wms663-complete-positive-status-fixtures"
POSITIVE_STATUS_HANDOFF = (
    "docs/reviews/wms663-healthy-positive-fixture-correction-handoff.md",
    "75319cb7026d032af7e47946b4b636aadc39c8eb",
)
LEGACY_SALES_COMPANION = {
    "path": "backend/tests/test_withdrawal_ledger.py",
    "before_blob": "d7f0d01d0f417aea487d0d7f616ba240b133f5a4",
    "after_blob": "a7ba000fd763b978784d0a5b6f4120df188c3084",
}


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


def git_blob(root: Path, commit: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "ls-tree", "-z", "--full-tree", commit, "--", path], cwd=root,
        check=False, capture_output=True, text=True,
    )
    if result.returncode != 0 or "\t" not in result.stdout:
        return None
    metadata, found_path = result.stdout.removesuffix("\0").split("\t", 1)
    fields = metadata.split()
    # A matching blob in a symlink, executable or gitlink is not this test file.
    if len(fields) != 3 or fields[:2] != ["100644", "blob"] or found_path != path:
        return None
    return fields[2]


def ancestor(root: Path, older: str, newer: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer], cwd=root,
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def exact_fixture_corrections(
    root: Path, task_id: str, contract_commit: str, ledger: dict,
) -> tuple[dict[str, set[str]], list[str]]:
    """Validate an explicit, exact-content chain without relaxing legacy rules.

    The committed ledger binds each independent review to one exact source and
    correction. Git facts and artifacts are checked here; obtaining a real
    independent Astra high verdict remains the controller's responsibility.
    Companions prove the whole correction commit's scope but are not silently
    promoted into frozen business contracts.
    """
    def fail(reason: str) -> tuple[dict[str, set[str]], list[str]]:
        return {}, [f"{task_id}: fixture-only: {reason}"]

    head = git(root, "rev-parse", "HEAD")
    entries = ledger.get("fixture_corrections")
    if (
        ledger.get("task") != task_id or not isinstance(entries, list) or not entries
        or any(key in ledger for key in (
            "corrections", "contract_commit", "correction_commit", "files", "review",
        ))
    ):
        return fail("неполный или смешанный формат")
    # Per original contract and file, track exact reviewed SHA and content.
    frontier: dict[str, dict[str, tuple[str, str]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            return fail("запись должна быть объектом")
        original = entry.get("contract_commit")
        source = entry.get("source_commit")
        correction = entry.get("correction_commit")
        if any(not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
               for sha in (original, source, correction)):
            return fail("нужны полные SHA исходного контракта, источника и коррекции")
        if not is_task_contract_commit(root, original, task_id):
            return fail("неизвестный исходный контракт")
        if (source == correction or not ancestor(root, original, source)
                or not ancestor(root, source, correction)
                or not ancestor(root, correction, head)):
            return fail("неверная последовательность коммитов")
        parents = git(root, "rev-list", "--parents", "-n", "1", correction).split()
        if len(parents) != 2:
            return fail("коррекция должна быть обычным коммитом с одним родителем")
        parent = parents[1]
        frozen = {path for path in commit_changed_paths(root, original)
                  if not path.startswith("docs/requirements/")}
        if original not in frontier:
            originals = {path: git_blob(root, original, path) for path in frozen}
            if any(blob is None for blob in originals.values()):
                return fail("исходные frozen файлы должны быть обычными Git blob")
            frontier[original] = {path: (original, blob) for path, blob in originals.items()}
        state = frontier[original]
        files = entry.get("files")
        companions = entry.get("companion_files", [])
        if (not isinstance(files, list) or not files
                or not isinstance(companions, list)):
            return fail("нужны точные списки файлов")
        expected: set[str] = set()
        transforms = set()
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get("transform"), str):
                return fail("неверное описание преобразования")
            transform = item["transform"]
            allowed = FIXTURE_BLOB_PAIRS.get(transform)
            if allowed is None or allowed != (
                task_id, item.get("path"), item.get("before_blob"), item.get("after_blob"),
            ):
                return fail("неподдерживаемое преобразование или изменены frozen expectations")
            _, path, before, after = allowed
            if path not in frozen or path in expected:
                return fail("повторный или незамороженный файл")
            expected.add(path)
            transforms.add(transform)
            prior_sha, prior_blob = state.get(path, (original, git_blob(root, original, path)))
            # Only this reviewed fifth pair has a later product source. Reject
            # even a reverted intervening mutation, not merely differing bytes.
            source_matches = source == prior_sha
            if transform == POSITIVE_STATUS_TRANSFORM and not source_matches:
                source_matches = ancestor(root, prior_sha, source) and not git(
                    root, "log", "--full-history", "--format=%H", f"{prior_sha}..{source}",
                    "--", path,
                )
            if (not source_matches or before != prior_blob
                    or git_blob(root, source, path) != before
                    or git_blob(root, parent, path) != before
                    or git_blob(root, correction, path) != after):
                return fail("подменён source/blob или пропущена дельта цепочки")
            state[path] = (correction, after)
        required_companions = ([LEGACY_SALES_COMPANION]
                               if "wms517-explicit-sales-fixture" in transforms else [])
        if companions != required_companions:
            return fail("неподдерживаемые дополнительные файлы")
        for companion in required_companions:
            path = companion["path"]
            if (path in expected or path in frozen
                    or git_blob(root, parent, path) != companion["before_blob"]
                    or git_blob(root, correction, path) != companion["after_blob"]):
                return fail("подменён точный companion blob")
            expected.add(path)
        if POSITIVE_STATUS_TRANSFORM in transforms:
            handoff_path, handoff_blob = POSITIVE_STATUS_HANDOFF
            if (git(root, "ls-tree", "-z", "--full-tree", parent, "--", handoff_path)
                    or git_blob(root, correction, handoff_path) != handoff_blob
                    or git_blob(root, head, handoff_path) != handoff_blob):
                return fail("подменён точный positive STATUS handoff")
            expected.add(handoff_path)
        if commit_changed_paths(root, correction) != expected:
            return fail("коммит меняет не ровно перечисленные файлы")
        review = entry.get("review")
        if (not isinstance(review, dict) or review.get("model") != "gpt-6-astra"
                or review.get("effort") != "high" or review.get("verdict") != "PASS"
                or review.get("source_commit") != source
                or review.get("correction_commit") != correction):
            return fail("нет отдельного Astra high PASS точной дельты")
        evidence_commit = review.get("evidence_commit")
        evidence_blob = review.get("evidence_blob")
        evidence = review.get("evidence")
        if (not isinstance(evidence_commit, str)
                or not re.fullmatch(r"[0-9a-f]{40}", evidence_commit)
                or not isinstance(evidence_blob, str)
                or not re.fullmatch(r"[0-9a-f]{40}", evidence_blob)
                or not isinstance(evidence, str)
                or not evidence.startswith("docs/reviews/")
                or not evidence.endswith(".md")
                or str(PurePosixPath(evidence)) != evidence
                or ".." in PurePosixPath(evidence).parts
                or correction == evidence_commit
                or not ancestor(root, correction, evidence_commit)
                or not ancestor(root, evidence_commit, head)
                or git_blob(root, evidence_commit, evidence) != evidence_blob
                or git_blob(root, head, evidence) != evidence_blob
                or evidence not in commit_changed_paths(root, evidence_commit)):
            return fail("нет неизменного отдельного review artifact в HEAD")
        # Historical reports sometimes spell an unambiguous 9-character SHA.
        evidence_text = git(root, "show", f"{evidence_commit}:{evidence}")
        if not any(correction.startswith(token)
                   for token in re.findall(r"\b[0-9a-f]{9,40}\b", evidence_text)):
            return fail("review artifact не называет проверенную коррекцию")
    baselines: dict[str, set[str]] = {}
    for original, state in frontier.items():
        for path, (sha, blob) in state.items():
            if git_blob(root, head, path) != blob:
                return fail(f"последующая мутация HEAD: {path}")
            if original == contract_commit and sha != original:
                baselines.setdefault(sha, set()).add(path)
    if git(root, "rev-parse", "HEAD") != head:
        return fail("HEAD изменился во время проверки; нужен повтор на точном SHA")
    return baselines, []


def reviewed_contract_correction(
    root: Path,
    task_id: str,
    contract_commit: str,
) -> tuple[dict[str, set[str]], list[str]]:
    """Return independent correction baselines, or explain an invalid ledger.

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
        return {}, []
    ledger_text = ledger_result.stdout.strip()
    try:
        ledger = json.loads(ledger_text)
    except json.JSONDecodeError:
        return {}, [
            f"{task_id}: некорректный реестр коррекции контракта {ledger_rel}"
        ]
    if not isinstance(ledger, dict):
        return {}, [
            f"{task_id}: реестр коррекции контракта должен быть JSON-объектом"
        ]
    if "fixture_corrections" in ledger:
        return exact_fixture_corrections(root, task_id, contract_commit, ledger)
    incomplete = [
        f"{task_id}: реестр коррекции контракта заполнен не полностью"
    ]
    if ledger.get("task") != task_id:
        return {}, incomplete
    array_format = "corrections" in ledger
    if array_format:
        entries = ledger["corrections"]
        if (
            not isinstance(entries, list) or not entries
            or any(key in ledger for key in ("contract_commit", "correction_commit", "files", "review"))
        ):
            return {}, incomplete
    else:
        entries = [ledger]

    baselines: dict[str, set[str]] = {}
    corrected_by_contract: dict[str, set[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            return {}, incomplete
        original = str(entry.get("contract_commit") or "")
        correction = str(entry.get("correction_commit") or "")
        files = entry.get("files")
        review = entry.get("review")
        if (
            not re.fullmatch(r"[0-9a-f]{40}", original)
            or not re.fullmatch(r"[0-9a-f]{40}", correction)
            or not isinstance(files, list) or not files
            or any(not isinstance(path, str) or not path for path in files)
            or len(files) != len(set(files))
            or not isinstance(review, dict)
            or review.get("model") != "gpt-6-astra"
            or review.get("effort") != "high"
            or review.get("verdict") != "PASS"
        ):
            return {}, incomplete
        # Validate every entry, even when its original is before the CI range.
        # A second contract for the task must not hide an invented source or
        # an invalid correction of the first contract.
        if not is_task_contract_commit(root, original, task_id):
            return {}, [f"{task_id}: реестр ссылается на неизвестный исходный контракт"]
        if correction == original:
            return {}, [f"{task_id}: коррекция должна быть отдельным последующим коммитом"]
        for older, newer, label in (
            (original, correction, "коррекция не следует за исходным контрактом"),
            (correction, "HEAD", "коррекция отсутствует в текущей версии"),
        ):
            if subprocess.run(
                ["git", "merge-base", "--is-ancestor", older, newer], cwd=root,
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).returncode != 0:
                return {}, [f"{task_id}: {label}"]
        expected = set(files)
        frozen = {
            path for path in commit_changed_paths(root, original)
            if not path.startswith("docs/requirements/")
        }
        # Preserve the historical single-file legacy ledger only. New array
        # entries must always be strict subsets of their original contract.
        if not expected.issubset(frozen) or (
            expected == frozen and (array_format or len(frozen) > 1)
        ):
            return {}, [f"{task_id}: коррекция должна менять только часть исходного контракта"]
        if commit_changed_paths(root, correction) != expected:
            return {}, [f"{task_id}: коммит коррекции должен менять ровно перечисленные файлы"]
        already_corrected = corrected_by_contract.setdefault(original, set())
        if already_corrected & expected:
            return {}, [f"{task_id}: файлы коррекций одного контракта пересекаются"]
        already_corrected.update(expected)
        if original == contract_commit:
            baselines.setdefault(correction, set()).update(expected)
    return baselines, []


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
    for commit, task_id, frozen in contracts:
        baselines, correction_errors = reviewed_contract_correction(
            root, task_id, commit
        )
        errors.extend(correction_errors)
        if correction_errors:
            continue
        overlap = set()
        corrected = set().union(*baselines.values())
        untouched = sorted(set(frozen) - corrected)
        if untouched:
            overlap.update(
                git(root, "diff", "--no-renames", "--name-only", commit, "HEAD", "--", *untouched)
                .splitlines()
            )
        for correction, paths in baselines.items():
            overlap.update(
                git(root, "diff", "--no-renames", "--name-only", correction, "HEAD", "--", *sorted(paths))
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
