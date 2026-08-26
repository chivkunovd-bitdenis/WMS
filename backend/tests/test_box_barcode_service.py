from __future__ import annotations

import re
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.box_barcode_service import (
    _encode_uuid,
    generate_box_barcode,
    is_wb_compatible_box_barcode,
)
from app.services.inbound_intake_box_service import _new_barcode as new_inbound_barcode
from app.services.warehouse_box_service import (
    _new_barcode as new_warehouse_barcode,
)
from app.services.warehouse_box_service import (
    resolve_barcode,
)


@pytest.mark.parametrize("prefix", ["WHB", "INB"])
def test_generated_box_barcodes_are_wb_compatible_and_unique(prefix: str) -> None:
    barcodes = {generate_box_barcode(prefix) for _ in range(1_000)}

    assert len(barcodes) == 1_000
    assert all(len(barcode) == 30 for barcode in barcodes)
    assert all(barcode.startswith(f"{prefix}-") for barcode in barcodes)
    assert all(re.fullmatch(r"[A-Z0-9-]+", barcode) for barcode in barcodes)
    assert all(is_wb_compatible_box_barcode(barcode) for barcode in barcodes)


def test_every_physical_box_generator_uses_the_shared_format() -> None:
    generated = {
        "WHB": new_warehouse_barcode(),
        "INB": new_inbound_barcode(),
    }

    for prefix, barcode in generated.items():
        assert barcode.startswith(f"{prefix}-")
        assert len(barcode) == 30
        assert is_wb_compatible_box_barcode(barcode)


@pytest.mark.parametrize(
    "barcode",
    [
        "WHB-ABCDEF123456",
        "INB-ABCDEF123456",
        "custom_box-123",
    ],
)
def test_existing_box_barcode_shapes_remain_valid_inputs(barcode: str) -> None:
    assert is_wb_compatible_box_barcode(barcode)


@pytest.mark.asyncio
async def test_legacy_warehouse_box_barcode_is_still_resolved() -> None:
    old_box = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = old_box
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)

    warehouse_box, inbound_box = await resolve_barcode(
        session,
        uuid.uuid4(),
        "WHB-ABCDEF123456",
    )

    assert warehouse_box is old_box
    assert inbound_box is None


@pytest.mark.asyncio
async def test_legacy_inbound_box_barcode_is_still_resolved() -> None:
    old_box = MagicMock()
    not_found = MagicMock()
    not_found.scalar_one_or_none.return_value = None
    found = MagicMock()
    found.scalar_one_or_none.return_value = old_box
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[not_found, found])

    warehouse_box, inbound_box = await resolve_barcode(
        session,
        uuid.uuid4(),
        "INB-ABCDEF123456",
    )

    assert warehouse_box is None
    assert inbound_box is old_box


@pytest.mark.parametrize(
    "barcode",
    [
        "",
        "A-123",
        "WHB-123456789012345678901234567",
        "WB_123456",
        "wb_123456",
        "WHB 123456",
        "КОРОБ-123456",
        "WHB+123456",
        "WHB/123456",
    ],
)
def test_validator_rejects_values_wb_will_not_accept(barcode: str) -> None:
    assert not is_wb_compatible_box_barcode(barcode)


def test_uuid_encoder_preserves_all_128_bits() -> None:
    assert _encode_uuid(uuid.UUID(int=0)) == "0" * 26
    assert _encode_uuid(uuid.UUID(int=(1 << 128) - 1)) == "7" + "Z" * 25


@pytest.mark.parametrize("prefix", ["", "FBS", "TOOLONG", "W-B", "ШК"])
def test_generator_rejects_invalid_prefix(prefix: str) -> None:
    with pytest.raises(ValueError):
        generate_box_barcode(prefix)
