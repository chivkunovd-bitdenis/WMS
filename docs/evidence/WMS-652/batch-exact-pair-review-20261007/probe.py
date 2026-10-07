"""Immutable exact-pair review; no target tests or PostgreSQL actions.
From this repo: python3 -B <this-file> > proof.json
After committing the fresh review artifact: python3 -B <this-file> --ledger
(--ledger updates proof.json with bounded real-Git resolver results.)
"""
import ast
import base64
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zlib

SOURCE = "3867d9e74cce3807b5e719c3f2c912fc0cfbd8d6"
PRIOR = "5b9df5acfba055bf94d5b3b21793ce2a233edff6"
WRITER = "937babc754f1e719ef7d69c48316a50960c02dce"
CODE = "a4324e5524fb2b8b88fa8a7ffc5f5ce11fb34928"
DEV = "a522d4dd4d609a32b2ff6cc56e3065f7dc6e8b84"
CHECKER = "scripts/ci/check_task_documents.py"
LEDGER = "docs/reviews/contract-corrections/WMS-662.json"
ARTIFACT = "docs/reviews/wms652-batch-exact-fixture-review-20261007.md"
DIR = "docs/evidence/WMS-652/batch-exact-ledger-test-contract-20261007/"
DEV_DIR = "docs/evidence/WMS-652/batch-exact-pair-developer-20261007/"
PG = "docs/evidence/WMS-652/all-pg-comparison-37563300572/"
OUT = Path(__file__).with_name("proof.json")


def git(*args, cwd=None, data=None):
    return subprocess.check_output(["git", *args], cwd=cwd, input=data)


def blob(path, ref=SOURCE):
    return git("show", ref + ":" + path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def xml(path, ref=SOURCE):
    raw = blob(path, ref)
    rows = []
    for n in ET.fromstring(raw).iter("testcase"):
        status = next((s for s in ("failure", "error", "skipped") if n.find(s) is not None), "pass")
        rows.append({"id": n.get("classname") + "::" + n.get("name"), "status": status})
    return {"sha256": sha(raw), "counts": dict(collections.Counter(r["status"] for r in rows)), "cases": rows}


def source_checks():
    contract = json.loads(blob(DIR + "contract.json"))
    inputs = json.loads(blob(DIR + "historical-inputs.json"))
    before_ast = ast.parse(blob(CHECKER, PRIOR))
    after_ast = ast.parse(blob(CHECKER))
    def dictionary(module):
        return next(n.value for n in module.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "FIXTURE_BLOB_PAIRS" for t in n.targets))
    new_dict = dictionary(after_ast)
    found = {}
    keep = []
    for k, v in zip(new_dict.keys, new_dict.values):
        name = ast.literal_eval(k)
        if name in contract["proposed_exact_tuples"]:
            found[name] = list(ast.literal_eval(v))
        else:
            keep.append((k, v))
    assert found == contract["proposed_exact_tuples"]
    new_dict.keys, new_dict.values = [k for k, v in keep], [v for k, v in keep]
    assert ast.dump(after_ast, include_attributes=False) == ast.dump(before_ast, include_attributes=False)
    assert blob(CHECKER) == blob(CHECKER, CODE)
    assert git("diff-tree", "--no-commit-id", "--name-only", "-r", CODE).decode().splitlines() == [CHECKER]
    pair_facts = {}
    for name, pair in inputs["pairs"].items():
        original, corrected, path = pair["original"], pair["correction"], pair["path"]
        for ref, oid in ((original, pair["before_blob"]), (corrected, pair["after_blob"]), (corrected + "^", pair["before_blob"]), (SOURCE, pair["after_blob"])):
            assert git("rev-parse", ref + ":" + path).decode().strip() == oid
        git("merge-base", "--is-ancestor", original, corrected)
        git("merge-base", "--is-ancestor", corrected, SOURCE)
        assert git("diff-tree", "--no-commit-id", "--name-only", "-r", corrected).decode().splitlines() == [path]
        for p, context in pair["original_context"].items():
            assert zlib.decompress(base64.b64decode(context["zlib_base64"])) == blob(p, original)
            assert git("rev-parse", original + ":" + p).decode().strip() == context["blob"]
        assert zlib.decompress(base64.b64decode(pair["after_zlib_base64"])) == blob(path, corrected)
        old, current = blob(path, original), blob(path)
        if "live-delivery" in name:
            assert ast.dump(ast.parse(old), include_attributes=False) == ast.dump(ast.parse(current), include_attributes=False)
            assert sum(isinstance(n, ast.Assert) for n in ast.walk(ast.parse(current))) == 7
        else:
            def outside(data):
                node = next(n for n in ast.parse(data).body if isinstance(n, ast.ClassDef) and n.name == "BatchSchedule")
                lines = data.splitlines(keepends=True)
                return b"".join(lines[:node.lineno - 1] + lines[node.end_lineno:])
            assert outside(old) == outside(current)
        pair_facts[name] = {"original": original, "corrected": corrected, "path": path,
                            "before_blob": pair["before_blob"], "after_blob": pair["after_blob"],
                            "original_context_files_verified": len(pair["original_context"])}
    frozen = git("diff-tree", "--no-commit-id", "--name-only", "-r", WRITER).decode().splitlines()
    for path in frozen:
        assert blob(path) == blob(path, WRITER), path
    for path, digest in contract["raw_sha256"].items():
        assert sha(blob(DIR + path)) == digest
    manifest = json.loads(blob(DEV_DIR + "manifest.json", DEV))
    for member in manifest["members"]:
        data = blob(DEV_DIR + member["path"], DEV)
        assert len(data) == member["bytes"] and sha(data) == member["sha256"]
    receipts = {"before": xml(DIR + "before.xml"), "bypass_mutation": xml(DIR + "failclosed-control.xml"),
                "developer_before": xml(DEV_DIR + "precode-red.xml", DEV), "green": xml(DEV_DIR + "targeted-green.xml", DEV)}
    for label in ("before", "developer_before"):
        assert receipts[label]["counts"] == {"failure": 3, "pass": 3}
    assert receipts["bypass_mutation"]["counts"] == {"failure": 3}
    assert receipts["green"]["counts"] == {"pass": 6}
    assert {r["id"] for r in receipts["green"]["cases"]} == set(contract["xml_ids"])
    policy_raw = blob("guards/PROCESS_CONTRACTS.json")
    policy, previous = json.loads(policy_raw), json.loads(blob("guards/PROCESS_CONTRACTS.json", PRIOR))
    tree = {}
    for row in git("ls-tree", "-r", "-z", SOURCE).split(b"\0"):
        if row:
            h, p = row.split(b"\t", 1)
            tree[p.decode()] = h.decode().split()
    for path, digest in policy["files"].items():
        assert tree[path][1] == "blob" and tree[path][0] in ("100644", "100755")
        assert sha(blob(path)) == digest, path
    assert len(policy["files"]) == 238
    assert all(policy["files"][p] == h for p, h in previous["files"].items())
    for name, definition in previous["suites"].items():
        now = policy["suites"][name]
        assert {k: v for k, v in now.items() if k != "cases"} == {k: v for k, v in definition.items() if k != "cases"}
        assert now["cases"] == definition["cases"] + (contract["xml_ids"] if name == "backend-fbs" else [])
    assert len(policy["suites"]) == 22 and sum(len(s["cases"]) for s in policy["suites"].values()) == 1192
    assert len(policy["suites"]["backend-fbs"]["cases"]) == 627
    assert all(path in policy["files"] for path in contract["source_closure"])
    assert git("diff", "--name-only", "1cf85fc500bc6ee7a5f4ef283b250c4bf59c5333", SOURCE, "--", "backend/app", "frontend/src") == b""
    run = json.loads(blob(PG + "run.json"))
    diagnostic = "b568bfdddd8b106799428ce81451b406ffe9860b"
    assert (run["id"], run["run_attempt"], run["head_sha"], run["status"], run["conclusion"]) == (37563300572, 1, diagnostic, "completed", "success")
    outcomes = json.loads(blob(PG + "actual-command-outcomes.json"))
    assert len(outcomes) == len({x["id"] for x in outcomes}) == 16
    for row in outcomes:
        assert row["exit_code"] == 0 and row["sha"] == diagnostic
        assert str(row["run_id"]) == "37563300572" and str(row["run_attempt"]) == "1"
        native = json.loads(blob(PG + "raw/pg-comparison/" + row["id"] + ".exit.json"))
        assert all(native[k] == row[k] for k in ("exit_code", "sha", "run_id", "run_attempt"))
        assert native["command"] == row["command"]
    pg_reports = json.loads(blob(PG + "verified-raw-reports.json"))
    report_facts = {}
    for name, info in pg_reports.items():
        report = xml(PG + "raw/" + info["report"])
        assert report["sha256"] == info["sha256"]
        assert report["counts"] == {"pass": info["executed"]}
        ids = [r["id"] for r in report["cases"]]
        assert len(ids) == len(set(ids))
        assert set(policy["suites"][name]["cases"]) <= set(ids)
        report_facts[name] = {"sha256": info["sha256"], "passed": info["executed"]}
    assert sum(v["passed"] for k, v in report_facts.items() if k != "native-linux") == 37
    assert report_facts["native-linux"]["passed"] == 30
    for command, witness in (("command01", b"writer_pids={'batch': 219, 'ordinary': 209}"),
                             ("command02", b"writer_pids={'batch': 225, 'ordinary': 224}")):
        log = blob(PG + "raw/pg-comparison/" + command + ".log")
        assert witness in log and b"1 passed" in log
    assert blob("backend/tests/test_wms662_batch_handoff_lock_order.py", diagnostic) == blob("backend/tests/test_wms662_batch_handoff_lock_order.py")
    assert blob("scripts/ci/run_release_postgres.sh") == blob(PG + "raw/pg-comparison/ordinary-release-postgres-source.sh")
    return {"source_verdict": "PASS two literal exact-file tuple additions; algorithm unchanged",
            "SOURCE": SOURCE, "checker_code": CODE, "checker_sha256": sha(blob(CHECKER)),
            "pair_facts": pair_facts, "saved_six_case_receipts": receipts,
            "frozen_contract": WRITER, "frozen_contract_files_preserved": len(frozen),
            "developer_receipts": DEV, "developer_manifest_members_verified": len(manifest["members"]),
            "policy_sha256": sha(policy_raw), "regular_files": 238,
            "modes": dict(collections.Counter(tree[p][0] for p in policy["files"])),
            "suites": 22, "required_IDs": 1192, "backend_required_cases": 627,
            "old235_files_1186_IDs_retained": True, "closure_hashes": {p: policy["files"][p] for p in contract["source_closure"]},
            "native_PG_comparison": {"run": 37563300572, "attempt": 1, "head": diagnostic, "outcomes": 16,
                                      "all_native_exits": 0, "required_PG_passed": 37, "native_Linux_passed": 30,
                                      "reports": report_facts, "two_writer_witnesses": [[219, 209], [225, 224]]},
            "APP_equal_PRODUCT1cf": True, "new_target_runs": [], "final_SOURCE_release_deploy_approval": False}


def ledger_checks(proof):
    artifact_commit = git("log", "-1", "--format=%H", "--", ARTIFACT).decode().strip()
    artifact_blob = git("rev-parse", artifact_commit + ":" + ARTIFACT).decode().strip()
    existing_raw = blob(LEDGER)
    existing = json.loads(existing_raw)
    entries = []
    for name, facts in proof["pair_facts"].items():
        original, correction = facts["original"], facts["corrected"]
        entries.append({"contract_commit": original, "source_commit": original, "correction_commit": correction,
                        "files": [{"transform": name, "path": facts["path"], "before_blob": facts["before_blob"], "after_blob": facts["after_blob"]}],
                        "companion_files": [], "review": {"model": "gpt-6.1-sol", "effort": "high", "verdict": "PASS",
                        "source_commit": original, "correction_commit": correction, "evidence": ARTIFACT,
                        "evidence_commit": artifact_commit, "evidence_blob": artifact_blob}})
    draft = {"task": "WMS-662", "fixture_corrections": entries, "owner_supersessions": existing["owner_supersessions"]}
    draft_raw = (json.dumps(draft, ensure_ascii=False, indent=2) + "\n").encode()
    def owner_fragment(raw):
        text = raw.decode()
        start = text.index("[", text.index('"owner_supersessions"'))
        _, end = json.JSONDecoder().raw_decode(text[start:])
        return text[start:start + end]
    assert owner_fragment(existing_raw) == owner_fragment(draft_raw)
    namespace = {"__name__": "exact_real_Git_ledger_probe"}
    exec(compile(blob(CHECKER), CHECKER, "exec"), namespace)
    with tempfile.TemporaryDirectory(prefix="wms652-exact-real-git-") as temp:
        root = Path(temp)
        git("init", "-q", cwd=root)
        objects = Path(git("rev-parse", "--git-common-dir").decode().strip()).resolve() / "objects"
        (root / ".git/objects/info/alternates").write_text(str(objects) + "\n")
        git("read-tree", artifact_commit, cwd=root)
        oid = git("hash-object", "-w", "--stdin", cwd=root, data=draft_raw).decode().strip()
        git("update-index", "--add", "--cacheinfo", "100644," + oid + "," + LEDGER, cwd=root)
        tree_oid = git("write-tree", cwd=root).decode().strip()
        head = git("-c", "user.name=Independent exact ledger probe", "-c", "user.email=probe@example.invalid",
                   "commit-tree", tree_oid, "-p", artifact_commit, cwd=root, data=b"isolated complete exact ledger").decode().strip()
        git("update-ref", "HEAD", head, cwd=root)
        owner_baselines, superseded, errors = namespace["owner_ui_supersessions"](root, "WMS-662", draft)
        assert errors == [], errors
        results = {}
        for entry in entries:
            original, correction = entry["contract_commit"], entry["correction_commit"]
            baselines, errors = namespace["exact_fixture_corrections"](root, "WMS-662", original, draft, superseded)
            assert errors == [] and baselines == {correction: {entry["files"][0]["path"]}}, (baselines, errors)
            results[original] = {"baseline": correction, "files": sorted(baselines[correction]), "errors": errors}
    proof["complete_exact_ledger_verdict"] = "PASS both real historical frontiers and real unchanged owner supersession"
    proof["artifact_commit"] = artifact_commit
    proof["artifact_blob"] = artifact_blob
    proof["proposed_complete_ledger"] = draft
    proof["owner_supersessions_verbatim_value_preserved"] = True
    proof["real_Git_resolver_results"] = results
    proof["real_owner_supersession_validation_errors"] = []
    proof["candidate_ledger_modified"] = False
    return proof


if sys.argv[1:] == ["--ledger"]:
    OUT.write_text(json.dumps(ledger_checks(json.loads(OUT.read_text())), ensure_ascii=False, indent=2) + "\n")
elif not sys.argv[1:]:
    print(json.dumps(source_checks(), ensure_ascii=False, indent=2))
else:
    raise SystemExit("Use no arguments or --ledger")
