"""Review only the immutable remaining delta; no implementation changes."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from types import ModuleType
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TARGET = "c4faeb3a58c42e2d2e04bff790230532e8970b90"
PRIOR = "6da0eb63b143d71d789c25a20ee04e3c49cbf14b"
OLD = "0151a555ac429957d0eee591317cc4326e909dfd"
P = "5868c3b1300d0969bf4283b5df18635eec9481f2"

def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])

def blob(ref, path):
    return git("show", f"{ref}:{path}")

def policy(ref):
    return json.loads(blob(ref, "guards/PROCESS_CONTRACTS.json"))

current, prior, old = [policy(ref) for ref in (TARGET, PRIOR, OLD)]
assert len(current["files"]) == 262 and len(current["suites"]) == 23
assert sum(len(s["cases"]) for s in current["suites"].values()) == 1644
retained, additions = [], {}
for name, suite in old["suites"].items():
    now = current["suites"][name]
    assert all(suite[k] == now[k] for k in ["report", "format", "exact"])
    assert set(suite["cases"]) <= set(now["cases"])
    retained.append(dict(suite=name, cases=len(suite["cases"]),
                         **{k: now[k] for k in ["report", "format", "exact"]}))
assert len(retained) == 18 and sum(r["cases"] for r in retained) == 1146
assert current["files"].keys() == prior["files"].keys()
for name, suite in prior["suites"].items():
    now = current["suites"][name]
    assert all(suite[k] == now[k] for k in ["report", "format", "exact"])
    assert set(suite["cases"]) <= set(now["cases"])
    extra = sorted(set(now["cases"]) - set(suite["cases"]))
    if extra:
        additions[name] = extra
assert len(additions["ci-shards"]) == 4 and len(additions["backend-fbs"]) == 5
assert len(additions) == 2
mismatches = []
for name, expected in current["files"].items():
    actual = hashlib.sha256(blob(TARGET, name)).hexdigest()
    if actual != expected:
        mismatches.append(dict(path=name, expected=expected, actual=actual))
assert [r["path"] for r in mismatches] == ["frontend/src/utils/wms680PrintGeometry.test.ts"]
canary_name = "C680-18: канарейка не принимает обрезанное название, даже если остальные слова PDF сохранены"
assert not any(canary_name in case for s in current["suites"].values() for case in s["cases"])

scope_path = "backend/tests/test_wms684_586_scope_contract.py"
def test_defs(raw):
    return {node.name: ast.dump(node, include_attributes=False) for node in ast.walk(ast.parse(raw))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")}
old_scope, new_scope = test_defs(blob(PRIOR, scope_path)), test_defs(blob(TARGET, scope_path))
assert len(old_scope) == 4 and all(new_scope.get(name) == value for name, value in old_scope.items())
scope_xml = ET.parse(HERE / "scope.xml")
assert len(list(scope_xml.iter("testcase"))) == 7
assert not any(list(scope_xml.iter(tag)) for tag in ["failure", "error", "skipped"])
seller = "backend/tests/test_seller_requisites_autofill.py"
old_seller, new_seller = test_defs(blob(PRIOR, seller)), test_defs(blob(TARGET, seller))
changed_seller = [name for name, code in old_seller.items() if new_seller.get(name) != code]
assert changed_seller == ["test_c4_wb_self_service_creates_requisites_with_single_call_and_journal_event"]
assert new_seller.keys() == old_seller.keys()

case673 = lambda p: sorted(case for s in p["suites"].values() for case in s["cases"]
                          if "/fbsPickingColor.wms673." in case)
assert case673(current) == case673(prior) and len(case673(current)) == 5
source_case_counts = {}
for suffix in ["dom.test.tsx", "pdf.test.ts"]:
    name = "frontend/src/screens/v2/fbsPickingColor.wms673." + suffix
    test_lines = lambda raw: [line.strip() for line in raw.decode().splitlines() if re.match(r"\s*it(?:\(|\.each)", line)]
    assert test_lines(blob(PRIOR, name)) == test_lines(blob(TARGET, name)), name
    lines = test_lines(blob(TARGET, name))
    source_case_counts[suffix] = sum(2 if "it.each(['single', 'group']" in line else 1 for line in lines)
assert source_case_counts == {"dom.test.tsx": 19, "pdf.test.ts": 5}
renderer = "frontend/src/screens/v2/wms673PrintRenderer.ts"
before = blob(PRIOR, renderer).decode()
after = blob(TARGET, renderer).decode()
assert after == before.replace("geometry.columnBounds.length !== 11", "geometry.columnBounds.length !== 12").replace("границы одиннадцати колонок", "границы двенадцати колонок")

ps = ModuleType("immutable_product_scope")
ps.__file__ = str(ROOT / "scripts/ci/product_scope.py")
exec(compile(blob(TARGET, "scripts/ci/product_scope.py"), ps.__file__, "exec"), ps.__dict__)
changed = git("diff", "--name-only", "--no-renames", P, TARGET).decode().splitlines()
product_delta = [name for name in changed if ps.product_path(name)]
assert product_delta == []
proposal = json.loads(blob(TARGET, "docs/evidence/WMS-652/final-closure-20261007/proposed-final-P-S.json"))
assert proposal["product_reference_P"] == P
(HERE / "published-proposal.json").write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n")
result = dict(target=TARGET, prior=PRIOR, paths=262, reports=23, cases=1644,
              retained_original_bindings=retained, new_ids=additions,
              pending_hash_mismatches=mismatches, pending_pdf_canary_registration=canary_name,
              scope_old_tests_unchanged=len(old_scope), scope_local_pass=7,
              seller_changed_test=changed_seller, seller_unchanged_test_definitions=len(old_seller)-1,
              old_673_registered_pdf_case_ids=case673(current),
              old_673_source_case_counts=source_case_counts, old_673_test_titles_preserved=True,
              renderer_only_change="11 → 12 column count and corresponding error message",
              proposed_P=P, immutable_product_delta_from_P=product_delta,
              template_status="proposal only; final handoff/exact activation files not available")
(HERE / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print("PASS bounded scope-fix/673-preservation/seller-test/policy-retention audit")
print("Overall candidate FAIL: real PDF row-mixing negative accepted; final activation not approved")
