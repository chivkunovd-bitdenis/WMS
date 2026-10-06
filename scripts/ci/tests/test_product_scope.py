"""WMS-652 C59/R48: whole candidate tree, independent trusted reference.

Public interface: verify_product_scope(root: Path, trusted_ref: str) -> list[str].
Return sorted unique forbidden product paths (empty means unchanged product).
Missing/non-commit history, non-repository, unborn HEAD or unmerged index must
raise ValueError. No caller consent is inferred: the upgrade fixture supplies an
independently selected SHA explicitly; candidate documents never select the base.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "product_scope.py"
PRODUCT = "frontend/src/screens/v2/FfFbsOrdersScreen.tsx"
STYLE = "frontend/src/mui/theme.ts"
SERVICE = "backend/app/services/fbs_supply_service.py"


@pytest.fixture
def verify():
    if not SCRIPT.is_file():
        pytest.fail("WMS-652 product_scope callable is not implemented; tests precede code")
    spec = importlib.util.spec_from_file_location("wms652_product_scope", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert callable(getattr(module, "verify_product_scope", None))
    return module.verify_product_scope


class Repo:
    def __init__(self, root):
        self.root = root
        self.git("init", "--quiet", "--initial-branch=main")
        self.git("config", "user.name", "Synthetic product scope contract")
        self.git("config", "user.email", "wms652-scope@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write(PRODUCT, "export const headers=['Товар','Селлер','Маршрут сдачи','Отгрузить до','Статус'];\nexport const button='Сформировать поставку';\n")
        self.write(STYLE, "export const theme={button:{display:'block'}};\n")
        self.write(SERVICE, "def pack(): return 1\n")
        self.base = self.commit("reviewed product reference; supplied by trusted caller")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True,
                                       stderr=subprocess.PIPE).strip()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self, subject):
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", subject)
        return self.git("rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def test_unchanged_product_and_process_only_additions_pass(repo, verify):
    for path in ["docs/requirements/WMS-652.md", "docs/evidence/WMS-652/result.json",
                 "backend/tests/test_packing.py", "frontend/tests-e2e/proof/main.tsx",
                 "frontend/src/screens/v2/packing.dom.test.tsx",
                 "frontend/src/guards/scan-print/recovery.test.ts",
                 "scripts/ci/check_release.py", "scripts/ci/tests/test_release.py",
                 ".github/workflows/ci.yml", "guards/CONTRACTS.json"]:
        repo.write(path, "synthetic process change\n")
    repo.commit("WMS-652: process only")
    assert verify(repo.root, repo.base) == []


@pytest.mark.parametrize("subject", ["WMS-666 WMS-652: hidden button",
    "WMS-652 WMS-666: hidden button", "WMS-663: unrelated import", "no task number"])
def test_product_delta_rejected_independently_of_subject(repo, verify, subject):
    repo.write(PRODUCT, "export const headers=[]; export const button=null;\n")
    repo.write("docs/requirements/WMS-652.md", "candidate says accepted\n")
    repo.commit(subject)
    assert verify(repo.root, repo.base) == [PRODUCT]


@pytest.mark.parametrize("path", [
    SERVICE, "backend/app/models/new_entity.py", "backend/alembic/versions/new_mode.py",
    "frontend/src/screens/v2/new_allowed_folder_code.ts", "frontend/src/components/Shared.tsx",
    STYLE, "frontend/src/index.css", "frontend/public/icons.svg", "frontend/public/new.js",
    "frontend/index.html", "frontend/seller/index.html", "frontend/packaging.html",
    "frontend/vite.config.ts", "frontend/tsconfig.app.json", "frontend/tsconfig.node.json",
    "frontend/package.json", "frontend/package-lock.json", "frontend/screens.registry.json",
    "frontend/Dockerfile", "frontend/Dockerfile.railway", "frontend/railway.toml",
    "frontend/deploy/Caddyfile", "frontend/deploy/Caddyfile.railway",
    "frontend/scripts/verify-cryptopro-vendor.mjs",
    "frontend/src/screens/v2/packing.testify.ts", "backend/app/test_runtime.py",
])
def test_product_roots_shared_style_assets_and_runtime_configs_are_protected(repo, verify, path):
    repo.write(path, "unapproved runtime delta\n")
    repo.commit("WMS-652: process disguise")
    assert verify(repo.root, repo.base) == [path]


@pytest.mark.parametrize("phase", ["dirty", "staged", "new", "staged-cancelled-in-worktree"])
def test_local_candidate_includes_worktree_index_and_new_product_files(repo, verify, phase):
    path = "frontend/src/components/New.tsx" if phase == "new" else PRODUCT
    original = (repo.root / path).read_text() if phase != "new" else None
    repo.write(path, "unapproved candidate delta\n")
    if phase in {"staged", "staged-cancelled-in-worktree"}:
        repo.git("add", path)
    if phase == "staged-cancelled-in-worktree":
        repo.write(path, original)
        assert repo.git("diff", "--name-only", "HEAD") == ""
    assert verify(repo.root, repo.base) == [path]


def test_gitignore_cannot_hide_new_runtime_source(repo, verify):
    path = "frontend/src/new_hidden_runtime.ts"
    repo.write(".gitignore", path + "\n")
    repo.commit("candidate hides its new source")
    repo.write(path, "export const hideFbsButton=true;\n")
    assert repo.git("ls-files", "--others", "--exclude-standard") == ""
    assert verify(repo.root, repo.base) == [path]


@pytest.mark.parametrize("operation", ["delete", "rename", "rename-to-test"])
def test_deletion_and_renames_cannot_erase_original_product_delta(repo, verify, operation):
    other = "frontend/src/screens/v2/Replaced.tsx" if operation == "rename" else "frontend/src/screens/v2/Replaced.test.tsx"
    if operation == "delete":
        (repo.root / PRODUCT).unlink()
        expected = [PRODUCT]
    else:
        repo.git("mv", PRODUCT, other)
        expected = sorted([PRODUCT, other]) if operation == "rename" else [PRODUCT]
    repo.commit("WMS-652: only rename")
    assert verify(repo.root, repo.base) == expected


def test_foreign_merge_product_tree_is_checked_even_with_empty_combined_diff(repo, verify):
    repo.git("checkout", "--quiet", "-b", "foreign")
    repo.write(PRODUCT, "export const hideFbsButton=true;\n")
    repo.commit("WMS-999: foreign UI")
    repo.git("checkout", "--quiet", "main")
    repo.write("docs/requirements/WMS-652.md", "process only\n")
    repo.commit("WMS-652: documentation")
    repo.git("merge", "--quiet", "--no-ff", "foreign", "-m", "WMS-652: import unrelated history")
    assert verify(repo.root, repo.base) == [PRODUCT]


def test_merge_resolution_delta_and_imported_tree_both_rejected(repo, verify):
    repo.git("checkout", "--quiet", "-b", "foreign")
    repo.write(STYLE, "export const theme={button:{display:'none'}};\n")
    repo.commit("foreign style change")
    repo.git("checkout", "--quiet", "main")
    repo.write("docs/process.md", "main process\n")
    repo.commit("main process")
    repo.git("merge", "--no-ff", "--no-commit", "foreign")
    repo.write(PRODUCT, "export const headers=[];\n")
    repo.commit("unrelated merge resolution")
    assert verify(repo.root, repo.base) == sorted([PRODUCT, STYLE])


def test_candidate_self_approval_cannot_select_or_rewrite_trusted_reference(repo, verify):
    repo.write(PRODUCT, "export const newUi=true;\n")
    proposed = repo.commit("WMS-700: proposed feature")
    repo.write("docs/requirements/WMS-700.md", f"Accepted; trusted_ref={proposed}\n")
    repo.write("scripts/ci/product_scope.json", '{"allowed":["frontend/src/"],"trusted_ref":"HEAD"}')
    repo.write("guards/PRODUCT_SCOPE.json", '{"allowAll":true}')
    repo.commit("WMS-652: candidate self-approval")
    assert verify(repo.root, repo.base) == [PRODUCT]


def test_explicit_reviewed_reference_upgrade_accepts_exact_delta_and_rejects_neighbor(repo, verify):
    repo.write(PRODUCT, "export const approvedNewButton=true;\n")
    approved_reference = repo.commit("synthetic independently reviewed next product contract")
    # The trusted caller retains old authority until independently upgrading it.
    assert verify(repo.root, repo.base) == [PRODUCT]
    assert verify(repo.root, approved_reference) == []
    repo.write(STYLE, "export const neighboringUnapprovedStyle=true;\n")
    repo.commit("neighboring change with plausible task number WMS-700")
    assert verify(repo.root, approved_reference) == [STYLE]
    assert verify(repo.root, repo.base) == sorted([PRODUCT, STYLE])


@pytest.mark.parametrize("bad_ref", ["", "missing-reviewed-reference", "0" * 40, "HEAD:frontend/src/screens/v2/FfFbsOrdersScreen.tsx"])
def test_missing_or_noncommit_trusted_reference_fails_closed(repo, verify, bad_ref):
    with pytest.raises(ValueError):
        verify(repo.root, bad_ref)


def test_nonrepository_fails_closed(tmp_path, verify):
    with pytest.raises(ValueError):
        verify(tmp_path, "d61805978b3e7878d1056c99b4e6e0823edf49a5")


def test_unborn_candidate_head_fails_closed(tmp_path, verify):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True, capture_output=True)
    with pytest.raises(ValueError):
        verify(tmp_path, "HEAD")


def test_unmerged_index_fails_closed(repo, verify):
    repo.git("checkout", "--quiet", "-b", "foreign")
    repo.write(PRODUCT, "foreign conflict\n")
    repo.commit("foreign")
    repo.git("checkout", "--quiet", "main")
    repo.write(PRODUCT, "main conflict\n")
    repo.commit("main")
    with pytest.raises(subprocess.CalledProcessError):
        repo.git("merge", "--no-commit", "foreign")
    assert repo.git("ls-files", "--unmerged")
    with pytest.raises(ValueError):
        verify(repo.root, repo.base)


def test_violation_paths_are_unique_sorted_and_verification_does_not_mutate_candidate(repo, verify):
    repo.write(PRODUCT, "committed delta\n")
    repo.commit("foreign")
    repo.write(PRODUCT, "staged delta\n")
    repo.git("add", PRODUCT)
    repo.write(PRODUCT, "dirty delta\n")
    repo.write(STYLE, "dirty theme\n")
    head, status = repo.git("rev-parse", "HEAD"), repo.git("status", "--porcelain")
    assert verify(repo.root, repo.base) == sorted([PRODUCT, STYLE])
    assert repo.git("rev-parse", "HEAD") == head
    assert repo.git("status", "--porcelain") == status
