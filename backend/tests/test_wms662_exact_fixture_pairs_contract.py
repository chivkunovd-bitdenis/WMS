"""Exact historical WMS-662 fixture pairs through the actual ledger checker."""

import base64
import copy
import json
import subprocess
import types
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = "scripts/ci/check_task_documents.py"
INPUTS_PATH = (
    "docs/evidence/WMS-652/batch-exact-ledger-test-contract-20261007/historical-inputs.json"
)
INPUTS = json.loads((ROOT / INPUTS_PATH).read_text())
PAIRS = {
    "wms662-live-delivery-test-format": (
        "WMS-662", "backend/tests/test_wms662_live_delivery_substatuses.py",
        "a6fc67e70364b0c84e9d2d41d734cd5af1cd61b4", "cefb7d8ac635c3da443a6f623c2fef4a1ff75850",
    ),
    "wms662-batch-first-wait-pid-snapshot": (
        "WMS-662", "backend/tests/test_wms662_batch_handoff_lock_order.py",
        "eb2255ca93ac453af1117339aa6cc9aba07ee2a0", "03d744d54222dc6ee13014d1f378bf07e6eb4e8a",
    ),
}
checker = types.ModuleType("actual_exact_fixture_checker")
checker.__file__ = str(ROOT / CHECKER)
checker_source = ((ROOT / CHECKER).read_bytes() if (ROOT / CHECKER).exists()
                  else subprocess.check_output(["git", "show", f"HEAD:{CHECKER}"], cwd=ROOT))
exec(compile(checker_source, checker.__file__, "exec"), checker.__dict__)


def decoded(value):
    return zlib.decompress(base64.b64decode(value)).decode()


class Replay:
    def __init__(self, root):
        self.root = root
        self.git("init", "-q")
        self.git("config", "user.name", "Isolated exact-pair replay")
        self.git("config", "user.email", "fixture@example.invalid")
        self.base = self.commit("base")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def blob(self, text):
        return subprocess.check_output(["git", "hash-object", "--stdin"], input=text,
                                       cwd=self.root, text=True).strip()

    def commit(self, subject):
        self.git("add", ".")
        self.git("commit", "-qm", subject, "--allow-empty")
        return self.git("rev-parse", "HEAD")

    def ledger(self, names):
        entries = []
        for name in names:
            item = INPUTS["pairs"][name]
            _, path, before, after = PAIRS[name]
            assert (item["path"], item["before_blob"], item["after_blob"]) == (path, before, after)
            for frozen_path, content in item["original_context"].items():
                value = decoded(content["zlib_base64"])
                assert self.blob(value) == content["blob"]
                self.write(frozen_path, value)
            assert self.blob((self.root / path).read_text()) == before
            original = self.commit("WMS-662: контракт тестов")
            assert len(checker.commit_changed_paths(self.root, original)) == (
                13 if "batch" in name else 1
            )
            value = decoded(item["after_zlib_base64"])
            assert self.blob(value) == after
            self.write(path, value)
            correction = self.commit("WMS-662: isolated exact correction")
            assert checker.commit_changed_paths(self.root, correction) == {path}
            evidence = f"docs/reviews/{name}-replay.md"
            self.write(evidence, "Controlled review-binding fixture, not independent approval.\n"
                       f"Source {original}; correction {correction}.\n")
            evidence_commit = self.commit("record isolated review binding")
            entries.append({
                "contract_commit": original, "source_commit": original,
                "correction_commit": correction,
                "files": [{"path": path, "transform": name,
                           "before_blob": before, "after_blob": after}],
                "review": {"model": "gpt-6.1-sol", "effort": "high", "verdict": "PASS",
                           "source_commit": original, "correction_commit": correction,
                           "evidence": evidence, "evidence_commit": evidence_commit,
                           "evidence_blob": self.git("rev-parse", f"HEAD:{evidence}")},
            })
        return {"task": "WMS-662", "fixture_corrections": entries,
                "owner_supersessions": copy.deepcopy(INPUTS["owner_supersessions"])}

    def validate(self, ledger, original=None):
        original = original or ledger["fixture_corrections"][0]["contract_commit"]
        return checker.exact_fixture_corrections(
            self.root, ledger["task"], original, ledger,
        )


@pytest.mark.parametrize("transform", tuple(PAIRS), ids=("legacy-format", "batch-pid"))
def test_exact_historical_fixture_pair_is_accepted(tmp_path, transform):
    replay = Replay(tmp_path)
    ledger = replay.ledger([transform])
    baselines, errors = replay.validate(ledger)
    assert errors == [], f"the exact reviewed full-file pair must be supported: {errors}"
    entry = ledger["fixture_corrections"][0]
    assert baselines == {entry["correction_commit"]: {PAIRS[transform][1]}}


def test_two_exact_original_contracts_share_ledger_without_legacy_array_waiver(tmp_path):
    replay = Replay(tmp_path)
    ledger = replay.ledger(PAIRS)
    owner_before = copy.deepcopy(ledger["owner_supersessions"])
    for entry in ledger["fixture_corrections"]:
        baselines, errors = replay.validate(ledger, entry["contract_commit"])
        assert errors == [], f"both exact frontiers must coexist: {errors}"
        assert baselines == {entry["correction_commit"]: {entry["files"][0]["path"]}}
    assert ledger["owner_supersessions"] == owner_before


def test_wrong_task_path_transform_and_blob_pairs_remain_rejected(tmp_path):
    replay = Replay(tmp_path)
    ledger = replay.ledger(PAIRS)
    for index in (0, 1):
        for field, value in (("path", "backend/tests/unapproved.py"),
                             ("transform", "unlisted-transform"),
                             ("before_blob", "f" * 40), ("after_blob", "e" * 40)):
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][index]["files"][0][field] = value
            assert replay.validate(changed)[1], (index, field)
    changed = copy.deepcopy(ledger)
    changed["task"] = "WMS-652"
    assert replay.validate(changed)[1]


def test_mutated_assertion_or_later_candidate_cannot_self_update_allowed_blob(tmp_path):
    replay = Replay(tmp_path)
    ledger = replay.ledger(PAIRS)
    for index, entry in enumerate(ledger["fixture_corrections"]):
        path = entry["files"][0]["path"]
        original = (tmp_path / path).read_text()
        altered = original.replace("assert ", "assert True or ", 1)
        assert altered != original
        replay.write(path, altered)
        candidate = replay.commit("unreviewed assertion mutation")
        changed = copy.deepcopy(ledger)
        changed["fixture_corrections"][index]["files"][0]["after_blob"] = replay.blob(altered)
        changed["fixture_corrections"][index]["correction_commit"] = candidate
        assert replay.validate(changed)[1], "candidate hash cannot grant its own permission"
        assert replay.validate(ledger)[1], "later HEAD mutation must also be denied"
        replay.write(path, original)
        replay.commit("restore isolated copy")


def test_missing_changed_review_or_rebound_source_remains_rejected(tmp_path):
    replay = Replay(tmp_path)
    ledger = replay.ledger(PAIRS)
    for index in (0, 1):
        for field, value in (("model", "unknown"), ("verdict", "FAIL"),
                             ("evidence_blob", "f" * 40), ("evidence_commit", replay.base),
                             ("source_commit", replay.base)):
            changed = copy.deepcopy(ledger)
            changed["fixture_corrections"][index]["review"][field] = value
            assert replay.validate(changed)[1], (index, field)
        changed = copy.deepcopy(ledger)
        changed["fixture_corrections"][index].pop("review")
        assert replay.validate(changed)[1]
        changed = copy.deepcopy(ledger)
        changed["fixture_corrections"][index]["source_commit"] = replay.base
        assert replay.validate(changed)[1]
    evidence = ledger["fixture_corrections"][0]["review"]["evidence"]
    replay.write(evidence, "changed immutable review\n")
    replay.commit("alter review copy")
    assert replay.validate(ledger)[1]
