"""One-time architectural boundary for WMS-653 (C12)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "9f131c42bec5266b90abb499c56060c0f3bd4b70"
PRODUCT_PATHS = {
    "backend/app/api/fbs_supplies.py",
    "backend/app/services/fbs_shipment_service.py",
    "backend/app/services/fbs_workspace_service.py",
    "frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx",
    "frontend/src/screens/v2/fbsApi.ts",
}
TASK_FILES = PRODUCT_PATHS | {
    "backend/tests/conftest.py",
    "backend/tests/test_fbs_shipment_deliver_gate_unit.py",
    "backend/tests/test_fbs_shipment_warehouse_sc.py",
    "backend/tests/test_wms653_delivery_error_contract.py",
    "backend/tests/test_wms653_scope_contract.py",
    "frontend/src/screens/v2/FfFbsSupplyWorkspace.load.test.ts",
    "frontend/src/screens/v2/FfFbsSupplyWorkspace.wms477.test.ts",
    "frontend/src/screens/v2/FfFbsSupplyWorkspace.wms653.dom.test.tsx",
    "docs/KANONICHESKIY_BACKLOG.md",
    "docs/requirements/WMS-653.md",
    "docs/reviews/contract-corrections/WMS-653.json",
    # Exact shared release metadata; adjacent reports remain foreign files.
    "docs/reviews/priority-five-progress-20261006.md",
    "docs/reviews/priority-five-source-map-20261006.json",
}
# Accepted historical process/integration changes, tied to immutable commits.
# They never authorize another WMS-653 edit of these foreign files.
HISTORICAL_SHARED_PATHS = {
    "ae3ad298dac5fe031662626a2e751becc7cac6f9": {
        "scripts/ci/check_task_documents.py",
        "scripts/ci/test_check_task_documents.py",
    },
    "d45d64434558c0b8ac1a13b78487f1cc68b35f3e": {
        "scripts/ci/check_task_documents.py",
        "scripts/ci/test_check_task_documents.py",
    },
    "88dc3c5d49fe4b0e2c6f9698e1410e3c19d458ea": {".github/workflows/ci.yml"},
    "c2757bb0dda090e6605d8c7f2cd0c9bdcbd2dd4e": {".github/workflows/ci.yml"},
    # This exact accepted multi-task merge includes 657/659/670 resolutions.
    "6e91afe69f5d7cf5b5643db78d7e574b1e4659b0": {
        "backend/app/api/inbound_intake.py",
        "backend/app/services/warehouse_map_service.py",
        "backend/tests/test_fbs_kiz.py",
        "frontend/src/screens/ff/products-fbs/FbsStockDialogContainer.tsx",
        "frontend/src/screens/v2/FfProductsCatalogScreen.tsx",
        "frontend/src/screens/v2/SellerInboundDraftScreen.tsx",
        "frontend/src/screens/v2/fbsUx.ts",
    },
}
FORBIDDEN_ROOTS = (
    "backend/alembic/versions/",
    "backend/app/models/",
    "backend/app/tasks/",
)
FORBIDDEN_ADDITIONS = {
    "setInterval(": "automatic polling/timer",
    "setTimeout(": "automatic timer",
    "BackgroundTasks(": "background task",
    "@celery_app.task": "Celery task",
}


def _git(*args: str, root: Path = ROOT) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _added_lines(diff: str, parents: int = 1) -> list[str]:
    # Combined merge diffs: only additions relative to every parent are the
    # merge's own new code. Imported code from one parent is not task delta.
    return [
        line[parents:]
        for line in diff.splitlines()
        if line.startswith("+" * parents) and not line.startswith("+++ ")
    ]


def wms653_task_delta(
    root: Path = ROOT,
    contract: str = CONTRACT,
) -> tuple[set[str], set[str], str]:
    assert _git("rev-parse", "--is-shallow-repository", root=root).strip() == "false", (
        "WMS-653 scope requires complete Git history"
    )
    _git("merge-base", "--is-ancestor", contract, "HEAD", root=root)
    head = _git("rev-parse", "HEAD", root=root).strip()
    history = _git("show", "-s", "--format=%H%x09%P%x09%s", contract, root=root)
    history += _git(
        "log",
        "--ancestry-path",
        "--format=%H%x09%P%x09%s",
        f"{contract}..{head}",
        root=root,
    )
    changed: set[str] = set()
    strict: set[str] = set()
    added: list[str] = []
    product_filters = (
        "backend/app",
        "frontend/src",
        ":(exclude)frontend/src/**/*.test.ts",
        ":(exclude)frontend/src/**/*.test.tsx",
    )
    for line in history.splitlines():
        commit, parents, subject = line.split("\t", 2)
        if not re.match(r"^WMS-653(?:\s+WMS-\d+)*:", subject):
            continue
        parent_count = len(parents.split())
        merge_flag = "--cc" if parent_count > 1 else "--root"
        paths = set(
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
        changed.update(paths)
        strict.update(paths - HISTORICAL_SHARED_PATHS.get(commit, set()))
        added.extend(
            _added_lines(
                _git(
                    "show",
                    "--format=",
                    "--no-renames",
                    "--unified=0",
                    "--cc",
                    commit,
                    "--",
                    *product_filters,
                    root=root,
                ),
                max(1, parent_count),
            )
        )

    # Index and worktree are independent: a staged forbidden change reverted
    # only in the worktree still belongs to the candidate and must fail.
    for options in ((), ("--cached",)):
        paths = set(
            filter(
                None,
                _git(
                    "diff",
                    *options,
                    "--name-only",
                    "--no-renames",
                    "-z",
                    head,
                    "--",
                    root=root,
                ).split("\0"),
            )
        )
        changed.update(paths)
        strict.update(paths)
        added.extend(
            _added_lines(
                _git(
                    "diff",
                    *options,
                    "--unified=0",
                    "--no-renames",
                    head,
                    "--",
                    *product_filters,
                    root=root,
                )
            )
        )
    untracked = set(
        filter(
            None,
            _git(
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                root=root,
            ).split("\0"),
        )
    )
    changed.update(untracked)
    strict.update(untracked)
    for path in untracked & PRODUCT_PATHS:
        added.append((root / path).read_text(encoding="utf-8"))
    assert _git("rev-parse", "HEAD", root=root).strip() == head, "HEAD changed during scope check"
    return changed, strict, "\n".join(added)


def assert_wms653_scope(root: Path = ROOT, contract: str = CONTRACT) -> None:
    changed, strict, added = wms653_task_delta(root, contract)
    forbidden = sorted(path for path in changed if path.startswith(FORBIDDEN_ROOTS))
    assert forbidden == [], (
        "WMS-653 must not add a table/migration, model-backed status or background task: "
        f"{forbidden}"
    )
    outside = sorted(
        path
        for path in strict
        if path not in TASK_FILES and not path.startswith("docs/evidence/WMS-653/")
    )
    assert outside == [], f"WMS-653 changed foreign files: {outside}"
    found = [label for marker, label in FORBIDDEN_ADDITIONS.items() if marker in added]
    assert found == [], f"WMS-653 added forbidden automation: {found}"


def test_wms653_diff_does_not_add_storage_status_background_retry_or_timer() -> None:
    """C12: WMS-653 remains presentation over the existing delivery operation."""
    assert_wms653_scope()
    for relative in (
        "backend/tests/test_fbs_kiz.py",
        "backend/tests/test_fbs_print_assets.py",
        "frontend/src/screens/v2/FfFbsSupplyWorkspace.scan.dom.test.tsx",
    ):
        assert (ROOT / relative).is_file(), f"neighbour regression disappeared: {relative}"


@pytest.fixture
def scope_repo(tmp_path: Path) -> tuple[Path, str]:
    _git("init", "--quiet", root=tmp_path)
    _git("config", "user.email", "scope-test@example.invalid", root=tmp_path)
    _git("config", "user.name", "WMS-653 isolated scope test", root=tmp_path)
    _git("config", "commit.gpgsign", "false", root=tmp_path)
    _write(tmp_path, "docs/requirements/WMS-653.md", "contract\n")
    return tmp_path, _commit(tmp_path, "WMS-653: контракт тестов")


def _write(root: Path, path: str, value: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding="utf-8")


def _commit(root: Path, subject: str) -> str:
    _git("add", ".", root=root)
    _git("commit", "-m", subject, root=root)
    return _git("rev-parse", "HEAD", root=root).strip()


def test_foreign_migration_is_not_wms653_delta(scope_repo: tuple[Path, str]) -> None:
    root, contract = scope_repo
    _write(root, "backend/alembic/versions/foreign.py", "foreign migration\n")
    _write(root, "backend/app/services/foreign.py", "setTimeout(foreign)\n")
    _commit(root, "WMS-660: independent accepted compatibility")
    _write(root, "frontend/src/screens/v2/fbsApi.ts", "own presentation\n")
    _commit(root, "WMS-653: presentation")
    assert_wms653_scope(root, contract)


def test_exact_shared_release_metadata_passes(scope_repo: tuple[Path, str]) -> None:
    root, contract = scope_repo
    for path in (
        "docs/reviews/priority-five-progress-20261006.md",
        "docs/reviews/priority-five-source-map-20261006.json",
    ):
        _write(root, path, "shared integration evidence\n")
    _commit(root, "WMS-653 WMS-475 WMS-537: record shared release metadata")
    assert_wms653_scope(root, contract)


@pytest.mark.parametrize(
    "path",
    [
        "docs/reviews/priority-five-progress-20261007.md",
        "docs/reviews/priority-five-source-map-20261007.json",
        "docs/reviews/priority-five-source-map-20261006.md",
        "docs/reviews/wms663-priority-proof-20261006.md",
    ],
)
def test_adjacent_shared_metadata_remains_forbidden(
    scope_repo: tuple[Path, str],
    path: str,
) -> None:
    root, contract = scope_repo
    _write(root, path, "foreign proof\n")
    _commit(root, "WMS-653: foreign release proof")
    with pytest.raises(AssertionError, match="foreign files"):
        assert_wms653_scope(root, contract)


@pytest.mark.parametrize(
    "path",
    [
        "backend/alembic/versions/foreign.py",
        "backend/alembic/versions/own.py",
        "backend/app/models/new_status.py",
        "backend/app/tasks/retry.py",
        "backend/app/services/inventory_service.py",
        "backend/app/services/warehouse_map_service.py",
        "backend/app/api/inbound_intake.py",
        "frontend/src/screens/v2/fbsUx.ts",
        "docs/evidence/WMS-666/foreign.md",
        "docs/reviews/contract-corrections/WMS-666.json",
        ".github/workflows/ci.yml",
        "scripts/ci/check_task_documents.py",
    ],
)
def test_new_own_foreign_paths_fail(
    scope_repo: tuple[Path, str],
    path: str,
) -> None:
    root, contract = scope_repo
    _write(root, path, "accepted independent file\n")
    _commit(root, "WMS-660: foreign baseline")
    _write(root, path, "new own forbidden change\n")
    _commit(root, "WMS-653 WMS-657: new own delta")
    with pytest.raises(AssertionError):
        assert_wms653_scope(root, contract)


@pytest.mark.parametrize("marker", list(FORBIDDEN_ADDITIONS))
def test_new_own_automation_fails(scope_repo: tuple[Path, str], marker: str) -> None:
    root, contract = scope_repo
    _write(root, "frontend/src/screens/v2/fbsApi.ts", marker + "forbidden)\n")
    _commit(root, "WMS-653: new automation")
    with pytest.raises(AssertionError, match="forbidden automation"):
        assert_wms653_scope(root, contract)


@pytest.mark.parametrize("phase", ["untracked", "unstaged", "staged", "index-only"])
def test_pending_foreign_change_cannot_hide(
    scope_repo: tuple[Path, str],
    phase: str,
) -> None:
    root, contract = scope_repo
    path = "backend/app/services/warehouse_map_service.py"
    if phase != "untracked":
        _write(root, path, "accepted foreign\n")
        _commit(root, "WMS-660: foreign baseline")
    _write(root, path, "pending forbidden\n")
    if phase in ("staged", "index-only"):
        _git("add", path, root=root)
    if phase == "index-only":
        _write(root, path, "accepted foreign\n")
        assert _git("diff", "--name-only", "HEAD", "--", path, root=root) == ""
        assert (
            _git("diff", "--cached", "--name-only", "HEAD", "--", path, root=root).strip() == path
        )
    with pytest.raises(AssertionError, match="foreign files"):
        assert_wms653_scope(root, contract)


def test_index_only_automation_cannot_hide(scope_repo: tuple[Path, str]) -> None:
    root, contract = scope_repo
    path = "frontend/src/screens/v2/fbsApi.ts"
    _write(root, path, "accepted presentation\n")
    _commit(root, "WMS-653: presentation")
    _write(root, path, "setTimeout(forbidden)\n")
    _git("add", path, root=root)
    _write(root, path, "accepted presentation\n")
    assert _git("diff", "--name-only", "HEAD", "--", path, root=root) == ""
    with pytest.raises(AssertionError, match="forbidden automation"):
        assert_wms653_scope(root, contract)


def test_untracked_automation_cannot_hide(scope_repo: tuple[Path, str]) -> None:
    root, contract = scope_repo
    _write(root, "frontend/src/screens/v2/fbsApi.ts", "setTimeout(forbidden)\n")
    with pytest.raises(AssertionError, match="forbidden automation"):
        assert_wms653_scope(root, contract)


def test_merge_import_passes_but_own_resolution_fails(scope_repo: tuple[Path, str]) -> None:
    root, contract = scope_repo
    _git("checkout", "-b", "foreign", root=root)
    _write(root, "backend/alembic/versions/foreign.py", "accepted foreign\n")
    _commit(root, "WMS-660: foreign compatibility")
    _git("checkout", "-b", "task", contract, root=root)
    _write(root, "frontend/src/screens/v2/fbsApi.ts", "own presentation\n")
    _commit(root, "WMS-653: own presentation")
    _git("merge", "--no-ff", "--no-commit", "foreign", root=root)
    accepted = _commit(root, "WMS-653: import independent compatibility")
    assert_wms653_scope(root, contract)
    _git("reset", "--hard", accepted + "^1", root=root)
    _git("merge", "--no-ff", "--no-commit", "foreign", root=root)
    _write(root, "backend/app/services/inventory_service.py", "forbidden resolution\n")
    _commit(root, "WMS-653: own integration resolution")
    with pytest.raises(AssertionError, match="foreign files"):
        assert_wms653_scope(root, contract)


def test_missing_history_fails(scope_repo: tuple[Path, str]) -> None:
    root, _contract = scope_repo
    with pytest.raises(subprocess.CalledProcessError):
        assert_wms653_scope(root, "f" * 40)


def test_merge_own_timer_fails(scope_repo: tuple[Path, str]) -> None:
    root, contract = scope_repo
    _git("checkout", "-b", "foreign", root=root)
    _write(root, "backend/alembic/versions/foreign.py", "accepted foreign\n")
    _commit(root, "WMS-660: foreign compatibility")
    _git("checkout", "-b", "task", contract, root=root)
    path = "frontend/src/screens/v2/fbsApi.ts"
    _write(root, path, "own presentation\n")
    _commit(root, "WMS-653: own presentation")
    _git("merge", "--no-ff", "--no-commit", "foreign", root=root)
    _write(root, path, "own presentation\nsetTimeout(forbidden)\n")
    _commit(root, "WMS-653: own timer resolution")
    with pytest.raises(AssertionError, match="forbidden automation"):
        assert_wms653_scope(root, contract)


def test_combined_additions_keep_three_parent_merge_automation() -> None:
    assert _added_lines("+++ b/file\n+++setTimeout(forbidden)\n+ +imported", 3) == [
        "setTimeout(forbidden)"
    ]


def test_shallow_history_fails(scope_repo: tuple[Path, str], tmp_path: Path) -> None:
    root, contract = scope_repo
    _write(root, "frontend/src/screens/v2/fbsApi.ts", "own presentation\n")
    _commit(root, "WMS-653: presentation")
    shallow = tmp_path / "shallow"
    _git("clone", "--depth=1", root.as_uri(), str(shallow), root=root)
    with pytest.raises(AssertionError, match="complete Git history"):
        assert_wms653_scope(shallow, contract)
