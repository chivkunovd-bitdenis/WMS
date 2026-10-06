"""One-time K7/N3 and A11/A12 scope checks against the fixed owner-approved base."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "1943e0f18a51e83a45a647f51fb565f2fab6d074"
REQUIREMENTS_BASE = "21eb4dfc6"
VIEW = "frontend/src/screens/ff/FfInboundRequestView.tsx"
PRODUCT_PATHS = {
    "backend/app/api/inbound_intake.py",
    "backend/app/services/inbound_acceptance_act_service.py",
    "frontend/src/screens/ff/FfInboundRequestView.tsx",
    "frontend/src/utils/printBarcodeLabel.ts",
}
TASK_FILES = PRODUCT_PATHS | {
    ".agent-runs/developer-handoff.md",
    "backend/tests/test_wms586_acceptance_act_contract.py",
    "backend/tests/test_wms586_review_regression_contract.py",
    "backend/tests/test_wms684_586_scope_contract.py",
    "docs/KANONICHESKIY_BACKLOG.md",
    "docs/requirements/WMS-684.md",
    "docs/requirements/WMS-586.md",
    "docs/reviews/2026-10-07-WMS-684-586-acceptance.md",
    "frontend/src/screens/ff/FfInboundRequestView.wms586.dom.test.tsx",
    "frontend/src/screens/ff/FfInboundRequestView.wms684.dom.test.tsx",
    "frontend/src/screens/ff/FfInboundRequestView.wms684.pdf.test.tsx",
    "frontend/src/screens/ff/FfInboundRequestView.wms684.review-regression.dom.test.tsx",
    "frontend/src/test-contracts/inbound684586Harness.tsx",
}
REVIEW_PREFIX = "docs/reviews/2026-10-07-wms684-586"
TASK_SUBJECT = re.compile(r"^WMS-(?:684|586)(?:\s+WMS-\d+)*:")


def read(path):
    return (ROOT / path).read_text()


def _git(*args: str, root: Path = ROOT) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def _task_file_allowed(path: str) -> bool:
    return path in TASK_FILES or path.startswith(REVIEW_PREFIX)


def _wms684_586_task_history(
    root: Path = ROOT,
    contract: str = CONTRACT,
) -> list[tuple[str, list[str]]]:
    assert _git("rev-parse", "--is-shallow-repository", root=root).strip() == "false", (
        "WMS-684/586 scope requires complete Git history"
    )
    head = _git("rev-parse", "HEAD", root=root).strip()
    _git("merge-base", "--is-ancestor", contract, head, root=root)
    history = _git(
        "log",
        "--ancestry-path",
        "--format=%H%x09%P%x09%s",
        f"{contract}..{head}",
        root=root,
    )
    return [
        (commit, parents.split())
        for line in history.splitlines()
        for commit, parents, subject in [line.split("\t", 2)]
        if TASK_SUBJECT.match(subject)
    ]


def wms684_586_task_paths(
    root: Path = ROOT,
    contract: str = CONTRACT,
) -> set[str]:
    """Return only WMS-684/586-owned commits, never a mixed integration diff."""
    changed: set[str] = set()
    for commit, parents in _wms684_586_task_history(root, contract):
        parent_count = len(parents)
        merge_flag = "--cc" if parent_count > 1 else "--root"
        changed.update(
            filter(
                None,
                _git(
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "--no-renames",
                    "-r",
                    "-z",
                    merge_flag,
                    commit,
                    root=root,
                ).split("\0"),
            )
        )
    return changed


def assert_wms684_586_scope(root: Path = ROOT, contract: str = CONTRACT) -> None:
    changed = wms684_586_task_paths(root, contract)
    outside = sorted(path for path in changed if not _task_file_allowed(path))
    assert outside == [], f"WMS-684/586 changed foreign files: {outside}"


def waybill(source):
    start = source.index('data-testid="ff-inbound-print-waybill"')
    return source[start : source.index("</Button>", start)]


def test_protected_waybill_and_existing_settings_are_unchanged():
    protected_files = {
        "frontend/src/utils/printInboundReceivingSheet.ts",
        "frontend/src/utils/printInboundReceivingSheet.test.ts",
    }
    assert protected_files.isdisjoint(wms684_586_task_paths())
    for commit, parents in _wms684_586_task_history():
        if len(parents) != 1:
            own_merge_paths = set(
                filter(
                    None,
                    _git(
                        "diff-tree", "--no-commit-id", "--cc", "--name-only", "-r", "-z", commit
                    ).split("\0"),
                )
            )
            if VIEW in own_merge_paths:
                after = _git("show", f"{commit}:{VIEW}")
                assert any(
                    _protected_view_unchanged(_git("show", f"{parent}:{VIEW}"), after)
                    for parent in parents
                ), commit
            continue
        before, after = (
            _git("show", f"{parents[0]}:{VIEW}"),
            _git("show", f"{commit}:{VIEW}"),
        )
        assert _protected_view_unchanged(before, after), commit
    current = read(VIEW)
    assert 'data-testid="ff-inbound-discrepancy-acts"' not in current
    assert not re.search(r"fetch\([^\n]*(?:discrepancy-acts|discrepancy_acts)", current)


def _protected_view_unchanged(before: str, after: str) -> bool:
    if waybill(before) != waybill(after):
        return False
    # Labels/action changes do not authorize changing other inbound handlers.
    for start, end in (
        ("  const submitToWarehouse =", "  type InboundBoxPrintTarget ="),
        ("  const scanToReceiving =", "  const selectedPalletBoxes ="),
    ):
        before_handler = before[before.index(start) : before.index(end)]
        after_handler = after[after.index(start) : after.index(end)]
        if before_handler != after_handler:
            return False
    return True


def test_task_sources_and_lane_boundaries_preserved():
    w684, w586 = read("docs/requirements/WMS-684.md"), read("docs/requirements/WMS-586.md")
    for marker in ("обращения1", "WMS-659", "WMS-681", "приёмки", "физическая"):
        assert marker in w684, marker
    for marker in (
        "source463",
        "source467",
        "source471",
        "Telegram130",
        "Telegram134",
        "Telegram653",
        "план-факт",
        "не пустой",
        "WMS-680",
        "обращение33",
    ):
        assert marker.lower() in w586.lower(), marker
    # Historical accepted results must survive the extension verbatim.
    for task in ("WMS-684", "WMS-586"):
        path = f"docs/requirements/{task}.md"
        snapshot = subprocess.check_output(
            ["git", "show", f"{REQUIREMENTS_BASE}:{path}"], cwd=ROOT, text=True
        )
        historical = (
            snapshot.split("\n## Новое обращение")[0]
            if task == "WMS-586"
            else snapshot.split("\n\n## Подготовка")[0]
        )
        assert read(path).startswith(historical)
    assert_wms684_586_scope()


@pytest.fixture
def scope_repo(tmp_path: Path) -> tuple[Path, str]:
    _git("init", "--quiet", root=tmp_path)
    _git("config", "user.email", "scope-test@example.invalid", root=tmp_path)
    _git("config", "user.name", "WMS-684/586 scope test", root=tmp_path)
    _git("config", "commit.gpgsign", "false", root=tmp_path)
    _write(tmp_path, "docs/requirements/WMS-586.md", "contract\n")
    return tmp_path, _commit(tmp_path, "WMS-684 WMS-586: контракт тестов")


def _write(root: Path, path: str, value: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")


def _commit(root: Path, subject: str) -> str:
    _git("add", ".", root=root)
    _git("commit", "-m", subject, root=root)
    return _git("rev-parse", "HEAD", root=root).strip()


def test_feature_branch_merged_with_foreign_integration_paths_passes(
    scope_repo: tuple[Path, str],
) -> None:
    root, contract = scope_repo
    _git("checkout", "-b", "foreign", root=root)
    _write(root, "backend/alembic/versions/foreign.py", "foreign migration\n")
    _commit(root, "WMS-680: independent migration")
    _git("checkout", "-b", "task", contract, root=root)
    _write(root, "backend/app/services/inbound_acceptance_act_service.py", "own PDF change\n")
    _commit(root, "WMS-684 WMS-586: PDF act")
    _git("merge", "--no-ff", "foreign", "-m", "WMS-684 WMS-586: integrate foreign lane", root=root)
    assert_wms684_586_scope(root, contract)


def test_task_commit_with_forbidden_product_path_fails(
    scope_repo: tuple[Path, str],
) -> None:
    root, contract = scope_repo
    _write(root, "backend/app/models/forbidden.py", "new model\n")
    _commit(root, "WMS-684 WMS-586: forbidden model")
    with pytest.raises(AssertionError, match="foreign files"):
        assert_wms684_586_scope(root, contract)
