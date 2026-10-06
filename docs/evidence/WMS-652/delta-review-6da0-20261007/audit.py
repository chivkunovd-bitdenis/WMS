"""Bounded audit of exact Git objects; collection is not test execution."""
import ast
import asyncio
from collections import Counter
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import ModuleType, SimpleNamespace
import xml.etree.ElementTree as ET

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
TARGET = "6da0eb63b143d71d789c25a20ee04e3c49cbf14b"
PRIOR = "ef154664e365644f4ba002c6e8affc5607fae725"
OLD = "0151a555ac429957d0eee591317cc4326e909dfd"

def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])

def blob(ref, path):
    return git("show", f"{ref}:{path}")

def data(ref, path):
    return json.loads(blob(ref, path))

def definitions(raw):
    return {n.name: ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(raw))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")}

policy_path = "guards/PROCESS_CONTRACTS.json"
policy, prior, old = [data(ref, policy_path) for ref in (TARGET, PRIOR, OLD)]
pc = ModuleType("immutable_process_contracts")
pc.__file__ = str(ROOT / "scripts/ci/process_contracts.py")
exec(compile(blob(TARGET, "scripts/ci/process_contracts.py"), pc.__file__, "exec"), pc.__dict__)
pc.validate_policy(policy)
assert len(policy["files"]) == 262 and len(policy["suites"]) == 23
assert sum(len(s["cases"]) for s in policy["suites"].values()) == 1635
assert set(old["files"]) <= set(policy["files"])
assert policy["files"].keys() == prior["files"].keys()
bindings, additions = [], {}
for name, suite in old["suites"].items():
    current = policy["suites"][name]
    assert all(suite[k] == current[k] for k in ("report", "format", "exact"))
    assert set(suite["cases"]) <= set(current["cases"])
    bindings.append(dict(suite=name, retained=len(suite["cases"]),
                         **{k: current[k] for k in ("report", "format", "exact")}))
assert sum(b["retained"] for b in bindings) == 1146
for name, suite in prior["suites"].items():
    current = policy["suites"][name]
    assert all(suite[k] == current[k] for k in ("report", "format", "exact"))
    assert set(suite["cases"]) <= set(current["cases"])
    count = len(set(current["cases"]) - set(suite["cases"]))
    if count:
        additions[name] = count
assert additions == {"backend-fbs": 22, "frontend-fbs": 11, "ci-shards": 36, "docgate-687": 64}
mismatches = []
for path, expected in policy["files"].items():
    actual = hashlib.sha256(blob(TARGET, path)).hexdigest()
    if expected != actual:
        mismatches.append(dict(path=path, expected=expected, actual=actual))
assert {r["path"] for r in mismatches} == {
    "scripts/ci/tests/test_promote_guards.py", "scripts/ci/promote_guards.py",
    "backend/tests/test_wms684_586_scope_contract.py"}

unchanged = ["scripts/ci/process_contracts.py", "scripts/ci/build_process_proof.py",
             "scripts/ci/backend_shards.py", "scripts/ci/product_scope.py",
             "scripts/ci/tests/test_ci_release_additions.py"]
assert all(blob(PRIOR, path) == blob(TARGET, path) for path in unchanged)
frozen = []
for source, path in [(PRIOR, "scripts/ci/test_check_task_documents.py"),
                     (PRIOR, "scripts/ci/tests/test_promote_guards.py"),
                     ("23414292039030f025f4e940994a556a95fd6214", "scripts/ci/test_check_task_documents.py"),
                     ("cbb352960", "scripts/ci/tests/test_promote_guards.py"),
                     ("8e010701dccb659b6bd02f22cd0dc09a1fa63323", "scripts/ci/tests/test_promote_guards.py")]:
    before, after = definitions(blob(source, path)), definitions(blob(TARGET, path))
    assert all(after.get(name) == body for name, body in before.items()), source
    frozen.append(dict(source=source, path=path, identical_definitions=len(before)))

collected = set()
for line in (HERE / "collection.log").read_text().splitlines():
    if line.startswith("scripts/") and "::" in line:
        owner, *classes, name = line.split("::")
        module = owner.removesuffix(".py").replace("/", ".")
        collected.add(".".join([module, *classes]) + "::" + name)
process_ids = set(policy["suites"]["ci-shards"]["cases"]) | set(policy["suites"]["docgate-687"]["cases"])
assert process_ids <= collected, sorted(process_ids - collected)
unregistered = sorted(collected - process_ids)
assert len(unregistered) == 4 and all("::test_protected_wms663_c10_copy_" in case for case in unregistered)
workflow = yaml.safe_load(blob(TARGET, ".github/workflows/ci.yml"))["jobs"]
previous_workflow = yaml.safe_load(blob(PRIOR, ".github/workflows/ci.yml"))["jobs"]
assert workflow["process-proof"] == previous_workflow["process-proof"]
assert workflow["backend-checks"] == previous_workflow["backend-checks"]
assert "wms686-mockup" in workflow["process-proof"]["needs"]
ci_command = next(s["run"] for s in workflow["guards"]["steps"] if "ci-shards.xml" in s.get("run", ""))
doc_command = next(s["run"] for s in workflow["guards"]["steps"] if "docgate-687.xml" in s.get("run", ""))
assert "-k" not in doc_command
owners = {line.split("::", 1)[0] for line in (HERE / "collection.log").read_text().splitlines()
          if line.startswith("scripts/") and "::" in line and "test_check_task_documents" not in line}
assert all(owner in ci_command for owner in owners)
release_pg = blob(TARGET, "scripts/ci/run_release_postgres.sh").decode()
assert "cp ../scripts/ci/wms663-proof/c10_mixed.py tests/test_wms663_remote_c10.py" in release_pg
assert "tests/test_wms663_remote_c10.py" in release_pg and "663-669-670-683.xml" in release_pg
local = pc.junit_results((HERE / "targeted.xml").read_bytes())
assert len(local) == 12 and set(local.values()) == {"passed"}
assert set(local) <= process_ids | set(unregistered)
promoter_ids = [case for case in policy["suites"]["ci-shards"]["cases"]
                if case.startswith("scripts.ci.tests.test_promote_guards.")]
raw_c10 = (HERE / "integration-c10-alias-green.xml").read_bytes()
assert len(pc.junit_results(raw_c10)) == 28 and len(promoter_ids) == 24
with tempfile.TemporaryDirectory(dir=HERE) as directory:
    report_root = Path(directory)
    (report_root / "ci-shards.xml").write_bytes(raw_c10)
    focused = {"version": 1, "files": {}, "suites": {"promoter-subset": {
        "report": "ci-shards.xml", "format": "junit", "exact": True, "cases": promoter_ids}}}
    try:
        pc.verify_reports(focused, report_root)
        raise AssertionError("accepted four unregistered C10 tests")
    except ValueError as exc:
        exact_closure_rejection = str(exc)
        assert all(case in exact_closure_rejection for case in unregistered)

def migration_graph(ref):
    nodes = {}
    for path in git("ls-tree", "-r", "--name-only", ref, "backend/alembic/versions").decode().splitlines():
        if not path.endswith(".py"):
            continue
        values = {}
        for node in ast.parse(blob(ref, path)).body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                key = node.target.id
            elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                key = node.targets[0].id
            else:
                continue
            if key in {"revision", "down_revision"}:
                values[key] = ast.literal_eval(node.value)
        if "revision" in values:
            parent = values["down_revision"]
            nodes[values["revision"]] = set(parent if isinstance(parent, (tuple, list)) else [parent]) - {None}
    assert all(parents <= nodes.keys() for parents in nodes.values())
    return sorted(nodes.keys() - set.union(set(), *nodes.values()))
before_heads = migration_graph("2aacfd1218^")
after_heads = migration_graph(TARGET)
assert before_heads == ["20261003_0001", "20261005_0658b", "20261007_2302"]
assert after_heads == ["20261007_2303"]
merge_path = "backend/alembic/versions/20261007_2303_wms652_merge_night.py"
merge_ast = ast.parse(blob(TARGET, merge_path))
functions = [n for n in merge_ast.body if isinstance(n, ast.FunctionDef)]
assert {n.name for n in functions} == {"upgrade", "downgrade"}
assert all(len(n.body) == 1 and isinstance(n.body[0], ast.Pass) for n in functions)

pg_path = "backend/tests/test_wms681_postgres_recovery.py"
pg_tree = ast.parse(blob(TARGET, pg_path))
pg_before = ast.parse(blob("22944029^", pg_path))
assert blob(TARGET, pg_path) == blob("22944029", pg_path)
def product_assertions(tree):
    return Counter(ast.dump(n, include_attributes=False) for top in tree.body
                   if not isinstance(top, ast.AsyncFunctionDef) or top.name != "_line"
                   for n in ast.walk(top) if isinstance(n, ast.Assert))
old_asserts, new_asserts = product_assertions(pg_before), product_assertions(pg_tree)
assert old_asserts <= new_asserts
# Execute only the exact protocol prefix and two pure helpers. No app/DB imports.
selected = []
for node in pg_tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith("_C6_") for t in node.targets):
        selected.append(node)
    elif isinstance(node, ast.If) and "_C6_WORKER_MODE" in ast.unparse(node.test):
        selected.append(node)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {"_emit_worker_receipt", "_line"}:
        selected.append(node)
protocol_checks = []
for worker in (False, True):
    stdout, stderr = io.StringIO(), io.StringIO()
    fake_sys = SimpleNamespace(argv=["worker", "--c6-worker"] if worker else ["parent"], stdout=stdout, stderr=stderr)
    def routed_print(*values, file=None, **kwargs):
        print(*values, file=file if file is not None else fake_sys.stdout, **kwargs)
    namespace = dict(sys=fake_sys, os=SimpleNamespace(environ={"WMS681_C6_TEST_STARTUP_DIAGNOSTIC": "1"}),
                     json=json, asyncio=asyncio, Any=object, print=routed_print)
    code = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)] + selected,
                      type_ignores=[])
    exec(compile(ast.fix_missing_locations(code), "immutable_protocol", "exec"), namespace)
    namespace["_emit_worker_receipt"]({"ready": True})
    namespace["_emit_worker_receipt"]({"status": 200})
    assert [json.loads(line) for line in stdout.getvalue().splitlines()] == [{"ready": True}, {"status": 200}]
    assert ("controlled worker startup diagnostic" in stderr.getvalue()) == worker
    protocol_checks.append(dict(worker=worker, stdout_json_lines=2, stderr_startup_warning=worker))

async def protocol_negatives():
    outcomes = []
    for value in (b'{"ready": true}\n', b"", b"warning\n", b"[]\n"):
        reader = asyncio.StreamReader()
        reader.feed_data(value)
        reader.feed_eof()
        process = SimpleNamespace(stdout=reader, returncode=1)
        try:
            result = await namespace["_line"](process, "review")
            assert value.startswith(b"{") and result == {"ready": True}
            outcomes.append("valid-object: accepted")
        except AssertionError as exc:
            assert not value.startswith(b"{")
            outcomes.append(str(exc))
    async def immediate_timeout(awaitable, timeout):
        assert timeout == 30
        awaitable.close()
        raise TimeoutError
    namespace["asyncio"] = SimpleNamespace(wait_for=immediate_timeout)
    try:
        await namespace["_line"](SimpleNamespace(stdout=asyncio.StreamReader()), "review")
        raise AssertionError("timeout accepted")
    except AssertionError as exc:
        assert "timed out" in str(exc)
        outcomes.append(str(exc))
    return outcomes
negative_outcomes = asyncio.run(protocol_negatives())

result = dict(target=TARGET, prior=PRIOR, original=OLD, paths=262, reports=23, cases=1635,
              retained_original_bindings=bindings, additions=additions,
              pending_policy_hash_mismatches=mismatches, frozen_test_definitions=frozen,
              unchanged_process_modules=unchanged, collected_process_case_ids=len(collected),
              pending_unregistered_producer_cases=unregistered,
              real_c10_report_exact_subset_rejection=exact_closure_rejection,
              actual_ci_commands=dict(ci_shards=ci_command, docgate=doc_command),
              local_targeted_named_cases=len(local), migration_heads_before=before_heads,
              migration_heads_after=after_heads, migration_no_ddl=True,
              pg_original_assertions_preserved=sum(old_asserts.values()),
              pg_protocol_checks=protocol_checks, pg_protocol_negatives=negative_outcomes)
(HERE / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print("PASS bounded policy/frozen contracts/collection/CI mapping/no-DDL graph/pure stdout protocol audit")
print("PENDING: three policy hashes, four C10 producer case IDs, final P/S, full CI; not overall candidate PASS")
