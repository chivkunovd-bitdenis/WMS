"""Read immutable Git bytes only; never import or execute the recovery adapter."""
import ast
import csv
import hashlib
import io
import json
import subprocess
from collections import Counter
from pathlib import Path

REVIEWED = "fb7850c919314ec62d0c771026e84b38f5fd2acc"
ROOT = "docs/evidence/WMS-675/native-recovery-adapter-20261007/"


def blob(ref, path):
    return subprocess.check_output(["git", "show", f"{ref}:{path}"])


def sha(data):
    return hashlib.sha256(data).hexdigest()


bindings_raw = blob(REVIEWED, ROOT + "source-bindings.json")
bindings = json.loads(bindings_raw)
checks = []
for path, entry in bindings["input_bindings"].items():
    copied = blob(REVIEWED, ROOT + path)
    assert copied == blob(entry["source_ref"], entry["source_path"])
    assert sha(copied) == entry["sha256"]
    if path.endswith(".sql"):
        assert copied.lstrip().upper().startswith(b"SELECT ")
    checks.append({"path": path, "sha256": sha(copied), "source_bytes_equal": True})
assert len(checks) == 14
native = []
for path, expected in bindings["installed_native_files"].items():
    actual = sha(blob(bindings["production_source"], "backend/" + path))
    assert actual == expected
    native.append({"path": path, "sha256": actual})
assert len(native) == 17
for entry in json.loads(blob(REVIEWED, ROOT + "file-manifest.json"))["members"]:
    data = blob(REVIEWED, ROOT + entry["path"])
    assert len(data) == entry["bytes"] and sha(data) == entry["sha256"]
adapter = blob(REVIEWED, ROOT + "adapter.py")
compile(ast.parse(adapter), ROOT + "adapter.py", "exec")  # no exec/import
matrix = json.loads(blob(REVIEWED, ROOT + "inputs/matrix.json"))
assert matrix["scope"] == bindings["scope"] and len(matrix["scope"]) == 5
rows = matrix["positions"]
assert len(rows) == len({r["order_id"] for r in rows}) == 31
assert len({r["position_id"] for r in rows}) == len({r["ledger_id"] for r in rows}) == 31
assert all(r["quantity"] == 1 and not r["children"] for r in rows)
assert sum(r["proved_unique_quantity"] for r in rows) == 26
assert sum(r["already_conducted_quantity"] for r in rows) == 12
assert sum(r["fresh_missing_delta"] for r in rows) == 14
cancelled = [r for r in rows if r["ozon_status"] == "cancelled"]
assert len(cancelled) == 5 and all(r["proved_unique_quantity"] == 0 for r in cancelled)
assert len({r["product_id"] for r in rows if r["proved_unique_quantity"]}) == 5
old_movements = [mid for r in rows for mid in r["recipe_movement_ids"]]
assert len(old_movements) == len(set(old_movements)) == 12
for row in rows:
    proof = blob(REVIEWED, row["proof_file"])
    assert sha(proof) == row["proof_sha256"]
    card = json.loads(proof)["card"]
    product = card["products"][0]
    assert len(card["products"]) == 1 and card["posting_number"] == row["posting_number"]
    assert card["status"] == row["ozon_status"] and card.get("substatus") == row["ozon_substatus"]
    assert int(product["sku"]) == row["sku"] and product["offer_id"] == row["offer_id"]
    assert product["quantity"] == row["quantity"]
tables = {}
for filename, count in (("billing", 52), ("facts", 26)):
    records = list(csv.DictReader(io.StringIO(blob(REVIEWED, ROOT + f"inputs/{filename}.csv").decode())))
    assert len(records) == len({r["id"] for r in records}) == count
    tables[filename] = records
assert all(r["amount"] == "" for r in tables["billing"])
assert Counter(r["service_code"] for r in tables["billing"]) == {"fbs_order": 26, "packing": 26}
assert {r["id"] for r in tables["billing"]} == {bid for r in rows for bid in r["billing_ids"]}
assert {r["id"] for r in tables["facts"]} == {fid for r in rows for fid in r["operation_fact_ids"]}
result = {
    "reviewed_source": REVIEWED,
    "production_source": bindings["production_source"],
    "evidence_base": bindings["evidence_base"],
    "adapter_sha256": sha(adapter),
    "bindings_sha256": sha(bindings_raw),
    "input_bindings": checks,
    "native_bindings": native,
    "scope": bindings["scope"],
    "matrix": {"positions": 31, "proved": 26, "conducted": 12, "snapshot_missing": 14,
               "cancelled_excluded": 5, "positive_products": 5, "unique_original_movements": 12,
               "billing_entries": 52, "operation_facts": 26},
    "syntax": "AST parse/compile PASS; adapter not imported or executed",
    "production_access": False,
    "native_tests_or_execution": False,
}
Path(__file__).with_name("bindings-verification.json").write_text(json.dumps(result, indent=2) + "\n")
print("PASS: 14 input copies, 17 native Git hashes, 31 proofs, 12 movements, 52 charges, 26 facts; no adapter execution")
