"""Additional RED probes of Git modes, artifact identity and exact allowlist."""

import copy
import unittest

import test_fixture_contract_corrections as fixture_harness

FIXTURES = fixture_harness.FIXTURES
checker = fixture_harness.checker


class EdgeTests(unittest.TestCase):
    def setUp(self):
        self.repo = fixture_harness.FixtureChainTests()
        self.repo.setUp()
        self.addCleanup(self.repo.doCleanups)

    def test_reject_later_head_mode_change_with_identical_blob(self):
        repo = self.repo
        ledger = repo.setup_chain()
        repo.save(ledger)
        path = ledger["fixture_corrections"][0]["files"][0]["path"]
        repo.git("update-index", "--chmod=+x", path)
        repo.git("commit", "-qm", "change mode without changing blob")
        self.assertTrue(checker.contract_change_errors(repo.root, repo.base))

    def test_reject_correction_mode_change_with_identical_allowed_blobs(self):
        repo = self.repo
        ledger = repo.setup_chain()
        entry = ledger["fixture_corrections"][0]
        repo.git("checkout", "-q", entry["source_commit"])
        for name in ["wms663-uuid-before-expire", "wms663-exemplar-save-selector"]:
            item = FIXTURES[name]
            repo.write(item["path"], item["after"])
        (repo.root / entry["files"][0]["path"]).chmod(0o755)
        entry["correction_commit"] = repo.commit("fixture edit with forbidden mode")
        review = entry["review"]
        review["correction_commit"] = entry["correction_commit"]
        repo.write(review["evidence"], f"PASS {entry['correction_commit']}\n")
        review["evidence_commit"] = repo.commit("review changed mode")
        review["evidence_blob"] = repo.git("rev-parse", f"HEAD:{review['evidence']}")
        self.assertTrue(repo.errors(ledger))

    def test_reject_review_naming_different_full_sha_with_same_prefix(self):
        repo = self.repo
        ledger = repo.setup_chain()
        entry = ledger["fixture_corrections"][0]
        review = entry["review"]
        correction = entry["correction_commit"]
        different = correction[:9] + ("a" if correction[9] != "a" else "b") + correction[10:]
        repo.write(review["evidence"], f"PASS for {different}\n")
        review["evidence_commit"] = repo.commit("different review target")
        review["evidence_blob"] = repo.git("rev-parse", f"HEAD:{review['evidence']}")
        self.assertTrue(repo.errors(ledger))

    def test_reject_mixed_format_and_changed_companion(self):
        repo = self.repo
        ledger = repo.setup_chain("WMS-517")
        mixed = copy.deepcopy(ledger)
        mixed["corrections"] = []
        self.assertTrue(repo.errors(mixed))
        entry = ledger["fixture_corrections"][-1]
        entry["companion_files"][0]["after_blob"] = "a" * 40
        self.assertTrue(repo.errors(ledger))

    def test_allowlist_is_exactly_the_documented_semantic_edits(self):
        transformations = {
            "wms517-uuid-before-rollback": [(
                "        await db_session.rollback()\n        reloaded = await get_operation(db_session, scope, operation.id)",
                "        operation_id = operation.id\n        await db_session.rollback()\n        reloaded = await get_operation(db_session, scope, operation_id)",
            )],
            "wms517-explicit-sales-fixture": [(
                "scope, marking, order, supply = await seed(db)",
                "scope, marking, order, supply = await seed(db, sales_evidence=False)",
            )],
            "wms663-uuid-before-expire": [(
                "    db_session.expire_all()\n    resume = _operation",
                "    tenant_id, order_id = order.tenant_id, order.id\n    db_session.expire_all()\n    resume = _operation",
            ), (
                "        tenant_id=order.tenant_id,\n        order_id=order.id,\n        provider=OzonMarketplaceProvider(transport=transport),\n        client_id=\"client\",\n        api_key=\"key\",\n    )\n    assert _result_value(resumed",
                "        tenant_id=tenant_id,\n        order_id=order_id,\n        provider=OzonMarketplaceProvider(transport=transport),\n        client_id=\"client\",\n        api_key=\"key\",\n    )\n    assert _result_value(resumed",
            )],
            "wms663-exemplar-save-selector": [(
                "await act(async () => button('Сохранить')!.click())",
                "await act(async () => document.querySelector<HTMLButtonElement>('button[aria-label=\"Сохранить ГТД / РНПТ · SKU 663001 · экземпляр 1\"]')!.click())",
            )],
        }
        for name, changes in transformations.items():
            with self.subTest(transform=name):
                item = FIXTURES[name]
                expected = item["before"]
                for before, after in changes:
                    self.assertEqual(expected.count(before), 2 if name.endswith("selector") else 1)
                    expected = expected.replace(before, after)
                self.assertEqual(expected, item["after"])
                allowed = checker.FIXTURE_BLOB_PAIRS[name]
                self.assertEqual(allowed[1:], (item["path"], self.repo.blob(item["before"]), self.repo.blob(item["after"])))


if __name__ == "__main__":
    unittest.main()
