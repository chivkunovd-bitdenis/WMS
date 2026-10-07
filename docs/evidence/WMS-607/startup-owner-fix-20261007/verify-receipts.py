"""Verify existing raw receipts and frozen Git bytes; does not rerun tests."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = "a04a7b35f1e866c1283bdc46fff2d41eaf68b4d6"
PRODUCT = "7bbcdd8a8aba9fd44dd4ee4ce2dbdee5af26b880"
FROZEN = "7b94a8dd0f1d6a772272930df3894d3ccd299686"
SOURCE = "tools/print-agent/update_macos_direct.sh"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def blob(ref, path):
    return git("show", f"{ref}:{path}")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def names(ref):
    return git("diff-tree", "--no-commit-id", "--name-only", "-r", ref).decode().splitlines()


unchanged = []


def preserve(ref, paths):
    for path in paths:
        expected = blob(ref, path)
        assert blob("HEAD", path) == expected, (ref, path, "Git bytes changed")
        local = ROOT / path
        if local.exists():
            assert local.read_bytes() == expected, (ref, path, "working bytes changed")
        unchanged.append({"reference": ref, "path": path, "sha256": sha(expected),
                          "bytes": len(expected), "local_checked": local.exists()})


preserve(FROZEN, names(FROZEN))
for ref in ("a40bf5b9a2f833a16cb9ff8c941c46c02a0b9d72",
            "040e94c956b8cc99d69d04e8cc90499a01e61a95"):
    preserve(ref, [p for p in names(ref) if p.startswith(("tools/print-agent/", "docs/evidence/"))])
preserve(BASE, [p for p in git("ls-tree", "-r", "--name-only", BASE, "tools/print-agent").decode().splitlines()
                if p != SOURCE])
preserve(BASE, ["docs/requirements/WMS-607.md",
                "docs/evidence/WMS-607/updater-implementation-20261007/run-existing.py"])
assert git("diff", "--name-only", f"{PRODUCT}^", PRODUCT).decode().splitlines() == [SOURCE]
source = blob(PRODUCT, SOURCE)
assert (ROOT / SOURCE).read_bytes() == source == blob("HEAD", SOURCE)
syntax = subprocess.run(["bash", "-n", str(ROOT / SOURCE)], capture_output=True, text=True)
assert syntax.returncode == 0, syntax.stderr

contracts = {
    "precode": "startup-owner-test-contract-20261007",
    "green": "startup-owner-test-contract-20261007",
    "rollback": "updater-stop-test-contract-20261007",
    "updater": "updater-test-contract-20261007",
}
reports = {}
for name, total, failures in (("precode", 3, 1), ("green", 3, 0),
                              ("rollback", 4, 0), ("updater", 10, 0), ("existing", 19, 0)):
    report = ET.parse(HERE / f"{name}.xml").getroot()
    actual_ids = [f"{c.get('classname')}::{c.get('name')}" for c in report.findall("testcase")]
    assert (int(report.get("tests")), int(report.get("failures")),
            int(report.get("errors")), int(report.get("skipped"))) == (total, failures, 0, 0)
    assert len(actual_ids) == len(set(actual_ids)) == total
    if name in contracts:
        contract = json.loads(blob("HEAD", f"docs/evidence/WMS-607/{contracts[name]}/contract.json"))
        assert report.get("name") == contract["suite"]["name"]
        assert set(actual_ids) == set(contract["suite"]["xml_ids"])
    else:
        expected_ids = []
        for module in ("test_macos_artmaks_contract", "test_macos_default_printer",
                       "test_macos_native", "test_macos_artmaks_http_contract"):
            tree = ast.parse(blob(BASE, f"tools/print-agent/{module}.py"))
            for cls in tree.body:
                if isinstance(cls, ast.ClassDef):
                    expected_ids.extend(f"{module}.{cls.name}::{f.name}" for f in cls.body
                                        if isinstance(f, ast.FunctionDef) and f.name.startswith("test_"))
        assert set(actual_ids) == set(expected_ids)
    reports[name] = {**report.attrib, "sha256": sha((HERE / f"{name}.xml").read_bytes()),
                     "xml_ids": actual_ids}

raw = {}
native_sha = sha(blob(BASE, "tools/print-agent/wms_print_direct_macos.swift"))
for folder, count in (("precode", 3), ("green", 3), ("rollback", 4), ("updater", 10), ("http", 5)):
    files = sorted((HERE / folder).glob("*.json"))
    assert len(files) == count
    for path in files:
        record = json.loads(path.read_text())
        if folder in ("precode", "green", "rollback"):
            assert record["source_sha256"] == sha(blob(BASE, SOURCE) if folder == "precode" else source)
            test = "test_macos_direct_updater_stop_contract.py" if folder == "rollback" else "test_macos_direct_updater_start_owner_contract.py"
            assert record["test_sha256"] == sha(blob("HEAD", f"tools/print-agent/{test}"))
        elif folder == "updater":
            assert record["entry_sha256"] == sha(source)
            assert record["source_sha256"] == native_sha
            assert record["test_sha256"] == sha(blob("HEAD", "tools/print-agent/test_macos_direct_updater_contract.py"))
        else:
            assert record["provenance"]["source_sha256"] == native_sha
        raw[str(path.relative_to(HERE))] = sha(path.read_bytes())

foreign = {}
for phase in ("precode", "green"):
    d = json.loads((HERE / phase / "test_confirmed_foreign_owner_aborts_without_later_startup_wait_or_poll.json").read_text())
    events = d["events"]
    assert d["native_exit"] == 1 and d["app_unchanged"] and d["state_unchanged"] and d["intent_unchanged"]
    if phase == "green":
        at = next(i for i, value in enumerate(events) if value.startswith("ps|foreign|"))
        assert not any(value in ("lsof", "startup-sleep", "readiness", "curl|health200") for value in events[at + 1:])
        assert "foreign executable" in d["stderr"]
    foreign[phase] = {"exit": d["native_exit"], "lsof": events.count("lsof"),
                      "startup_sleep": events.count("startup-sleep"), "stderr": d["stderr"]}

out = {"task": "WMS-607", "base": BASE, "frozen_test_first_commit": FROZEN,
       "product_source_commit": PRODUCT, "product_source_sha256": sha(source),
       "native_source_sha256": native_sha, "source_only_commit": True,
       "bash_syntax_exit": syntax.returncode, "unchanged": unchanged,
       "reports": reports, "raw_sha256": raw, "foreign_before_after": foreign,
       "independent_rereview": "pending", "distinct_analytical_acceptance": "pending",
       "both_architectures_verified": False, "publication_or_chat_sent": False}
(HERE / "preservation.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
print(f"Verified frozen bytes, source-only commit, syntax, 1 RED/2 PASS before code and 36 PASS after code; {len(unchanged)} preservation records.")
