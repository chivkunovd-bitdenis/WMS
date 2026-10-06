"""One-time WMS-675 contract for the frozen recovery-evidence transfer.

The evidence is intentionally absent until the narrow follow-up transfer.  The
source revision is fixed by the WMS-675 requirements, so this verifier neither
opens a database nor contacts Ozon.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_REVISION = "d61805978b3e7878d1056c99b4e6e0823edf49a5"
CONTRACT_BASE = "5b897e1553f8201fb67a404b26ecae14e46179bb"
EVIDENCE_RELATIVE = Path("docs/reviews/wms675-evidence-20261006")
EVIDENCE = ROOT / EVIDENCE_RELATIVE

EXPECTED_SCOPE = {
    "tenant_id": "b80a893b-ab87-42b6-8fd7-6d41502c900f",
    "seller_id": "cf6d31c5-944b-4382-af34-636ca9aa8cc3",
    "supply_id": "b82d1e9a-30d2-4d7b-b52d-9775c3d266e3",
}


def _source_bytes(relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{SOURCE_REVISION}:{EVIDENCE_RELATIVE / relative}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _target_bytes(relative: str) -> bytes:
    target = EVIDENCE / relative
    assert target.is_file(), (
        f"WMS-675 recovery evidence is absent: expected {target.relative_to(ROOT)} "
        f"from frozen source {SOURCE_REVISION}"
    )
    return target.read_bytes()


def _assert_matches_source(relative: str) -> bytes:
    target = _target_bytes(relative)
    source = _source_bytes(relative)
    assert hashlib.sha256(target).digest() == hashlib.sha256(source).digest(), (
        f"WMS-675 evidence was changed: {relative} must match {SOURCE_REVISION}"
    )
    return target


def _plan() -> dict[str, object]:
    return json.loads(_assert_matches_source("recovery_plan_exact.json"))


def test_p1_exact_identity_and_31_links_match_frozen_source() -> None:
    """P1: transfer must keep the selected identity, not merely 31 rows."""
    plan = _plan()
    assert plan["scope"] == EXPECTED_SCOPE
    positions = plan["positions"]
    assert len(positions) == 31
    assert len({position["order_id"] for position in positions}) == 31
    assert len({position["position_id"] for position in positions}) == 31
    assert all(position["quantity"] == 1 for position in positions)
    assert all(
        position["recipe_source"]["product_id"] == position["product_id"]
        for position in positions
    )
    _assert_matches_source("telegram_identity.json")
    _assert_matches_source("live-ozon-run-20261006-attempt1/scope_snapshot.json")
    _assert_matches_source("accounting-refresh-20261006-attempt1/orders_positions_reserves.csv")


def test_p2_historical_proofs_keep_their_hashes_and_classification() -> None:
    """P2: a missing, altered, or cancelled proof cannot become positive proof."""
    plan = _plan()
    statuses: Counter[str] = Counter()
    proved_quantity = 0
    for position in plan["positions"]:
        proof = json.loads(_assert_matches_source(position["evidence_file"]))
        card = proof["card"]
        assert proof["http_status"] == 200
        assert card["posting_number"] == position["posting_number"]
        assert card["products"] == [
            {
                "sku": position["sku"],
                "quantity": 1,
                "offer_id": position["offer_id"],
            }
        ]
        assert not card["related_postings"]["related_posting_numbers"]
        assert not card["related_weight_postings"]
        statuses[position["ozon_status"]] += 1
        proved_quantity += position["proved_unique_quantity"]

    assert statuses == {
        "delivered": 11,
        "delivering": 15,
        "cancelled": 4,
        "awaiting_packaging": 1,
    }
    assert proved_quantity == 26
    _assert_matches_source("live-ozon-run-20261006-attempt1/manifest.json")


def test_p3_existing_facts_and_charges_are_preserved_by_id_and_fields() -> None:
    """P3: totals alone must not hide a replaced historic fact or charge."""
    facts = list(
        csv.DictReader(_assert_matches_source(
            "accounting-refresh-20261006-attempt1/operation_facts.csv"
        ).decode().splitlines())
    )
    charges = list(
        csv.DictReader(_assert_matches_source(
            "accounting-refresh-20261006-attempt1/billing_entries.csv"
        ).decode().splitlines())
    )
    assert len(facts) == len({row["id"] for row in facts}) == 11
    assert len(charges) == len({row["id"] for row in charges}) == 22
    assert all(row["item_quantity"] == "1" for row in facts)
    assert {row["service_code"] for row in charges} == {"fbs_order", "packing"}
    assert all(
        Decimal(row["physical_quantity"]) == Decimal(row["billing_quantity"]) == Decimal(1)
        for row in charges
    )
    assert all(row["amount"] == "" and row["reversal_of_id"] == "" for row in charges)


def test_p4_current_plan_marks_26_and_no_publish_as_historical_only() -> None:
    """P4: raw historic fields remain raw; the later plan supplies the live order."""
    historical = _plan()
    current_plan = _assert_matches_source("RECOVERY_PLAN.md").decode()
    assert historical["actual_recovery"] == "NOT_PERFORMED"
    assert historical["mutation_authorized"] is False
    assert "WAIT_662_SUBSTATUS_FIX" in historical["execution_state"]
    assert historical["totals"]["current662_missing_delta"] == 11
    assert "штатный сервис662 на exact scope" in current_plan
    assert "свежие external proof/current ledger" in current_plan
    assert "Фактическое восстановление NOT_PERFORMED" in current_plan
    assert "Фоновые публикации не отключать" in current_plan


def test_p5_accepted_662_dependency_is_identified_without_claiming_a_deploy() -> None:
    """P5: the evidence identifies the accepted dependency and its boundary."""
    current_plan = _assert_matches_source("RECOVERY_PLAN.md").decode()
    assert "b4043c0df9fee0419bdfe85167bbd645f820de9c" in current_plan
    assert "c466" in current_plan
    assert "17e50faa3d13981b123ef7b093b2f97aefee9016" in current_plan
    assert "До подтверждённого deployed SHA" in current_plan
    assert "Новых проверок этих результатов в675 не запускали" in current_plan


def test_p6_frozen_bundle_is_complete_and_records_read_only_collection() -> None:
    """P6: the narrow transfer has all 104 frozen files and no saved mutation."""
    source_paths = {
        line
        for line in subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", SOURCE_REVISION, "--", str(EVIDENCE_RELATIVE)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    }
    target_paths = {
        str(path.relative_to(ROOT)) for path in EVIDENCE.rglob("*") if path.is_file()
    } if EVIDENCE.is_dir() else set()
    assert target_paths == source_paths
    assert len(source_paths) == 104
    for source_path in source_paths:
        relative = str(Path(source_path).relative_to(EVIDENCE_RELATIVE))
        _assert_matches_source(relative)

    manifest = json.loads(
        _assert_matches_source("accounting-refresh-20261006-attempt1/manifest.json")
    )
    assert manifest["writes"] == 0
    assert manifest["external_calls"] == 0
    assert all(query["status"] == "ok" for query in manifest["queries"])

    changed = {
        path
        for path in subprocess.run(
            ["git", "diff", "--name-only", f"{CONTRACT_BASE}...HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        if path
    }
    allowed = {
        "backend/tests/test_wms675_recovery_evidence_contract.py",
        "docs/requirements/WMS-675.md",
    }
    forbidden = sorted(
        path
        for path in changed
        if path not in allowed and not path.startswith(f"{EVIDENCE_RELATIVE}/")
    )
    assert forbidden == [], f"WMS-675 preparation changed non-evidence files: {forbidden}"
