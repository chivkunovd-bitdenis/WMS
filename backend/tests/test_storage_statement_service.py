from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.api.storage import _print_measurements
from app.services.storage_statement_service import _statement_source_ids


def test_zero_statement_uses_its_own_id_as_the_single_ledger_source() -> None:
    """A zero document never shares a nullable ledger source with another month."""
    statement = SimpleNamespace(id=uuid.uuid4())

    assert _statement_source_ids(statement, []) == {statement.id}


def test_measurement_statement_uses_each_measurement_as_its_ledger_source() -> None:
    statement = SimpleNamespace(id=uuid.uuid4())
    first = SimpleNamespace(id=uuid.uuid4())
    second = SimpleNamespace(id=uuid.uuid4())

    assert _statement_source_ids(statement, [first, second]) == {first.id, second.id}


def test_print_rows_do_not_pair_a_zero_ledger_entry_with_a_missing_sku() -> None:
    """TC-NEW-S11-08: zero statement printing is stable and has no phantom SKU."""
    zero_ledger = SimpleNamespace(source_id=uuid.uuid4())

    assert _print_measurements([], [zero_ledger]) == []
