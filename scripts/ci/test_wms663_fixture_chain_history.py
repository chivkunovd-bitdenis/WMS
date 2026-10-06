"""R39 merge-history and pre-existing Git-entry regressions (synthetic only)."""

import unittest
from unittest.mock import patch

import test_wms663_positive_fixture_chain as positive


class FixtureChainHistoryTests(unittest.TestCase):
    def case(self):
        case = positive.PositiveFixtureChainTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def test_reject_merged_side_branch_mutation_and_revert(self):
        case = self.case()
        repo = case.repo
        commit = repo.commit
        path = "backend/tests/test_wms663_customs_documents_contract.py"
        mutations = []

        def merged_commit(subject):
            if subject == "product delta leaves frozen files unchanged":
                branchpoint = repo.git("rev-parse", "HEAD")
                repo.git("checkout", "-qb", "side-probe")
                repo.write(path, positive.DATA["before"] + "\n# unreviewed mutation\n")
                mutations.append(commit("side change"))
                repo.write(path, positive.DATA["before"])
                mutations.append(commit("restore bytes"))
                repo.git("checkout", "--quiet", branchpoint)
                commit("unrelated mainline product commit")
                repo.git("merge", "--no-ff", "-qm", "merge side", "side-probe")
            return commit(subject)

        with patch.object(repo, "commit", merged_commit):
            ledger = case.chain()
        first, second = ledger["fixture_corrections"]
        interval = f"{first['correction_commit']}..{second['source_commit']}"
        self.assertEqual(repo.git("log", "--format=%H", interval, "--", path), "")
        history = repo.git("log", "--full-history", "--format=%H", interval, "--", path)
        for mutation in mutations:
            self.assertIn(mutation, history.splitlines())
        self.assertTrue(repo.errors(ledger), "merged mutation/revert must invalidate source")

    def test_reject_existing_handoff_regardless_of_git_mode(self):
        for mode in ("100755", "120000"):
            with self.subTest(mode=mode):
                case = self.case()
                repo = case.repo
                commit, write = repo.commit, repo.write
                path = positive.DATA["handoff_path"]
                target = repo.root / path

                def existing_commit(subject):
                    if subject == "product delta leaves frozen files unchanged":
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if mode == "120000":
                            target.symlink_to("nonexistent-handoff-target")
                        else:
                            write(path, "existing handoff\n")
                            target.chmod(0o755)
                    return commit(subject)

                def correction_write(file_path, text):
                    if file_path == path:
                        target.unlink()
                    write(file_path, text)

                with patch.object(repo, "commit", existing_commit), patch.object(
                    repo, "write", correction_write,
                ):
                    ledger = case.chain()
                correction = ledger["fixture_corrections"][1]["correction_commit"]
                entry = repo.git("ls-tree", f"{correction}^", "--", path)
                self.assertTrue(entry.startswith(f"{mode} blob "), entry)
                self.assertEqual(
                    repo.git("rev-parse", f"{correction}:{path}"),
                    repo.blob(positive.DATA["handoff"]),
                )
                self.assertTrue(repo.errors(ledger), "existing Git entry is not absence")


if __name__ == "__main__":
    unittest.main()
