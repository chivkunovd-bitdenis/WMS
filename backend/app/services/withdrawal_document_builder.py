"""Pure exact-byte LK_RECEIPT builder; no provider/network or signing behavior."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.true_api_withdrawal import MAX_DOCUMENT_BYTES, MAX_DOCUMENT_CISES


@dataclass(frozen=True)
class WithdrawalProduct:
    item_id: uuid.UUID
    cis: str = field(repr=False)
    product_cost: int
    pg: str
    fias_id: str | None = None
    kpp: str | None = None


@dataclass(frozen=True)
class BuiltWithdrawalDocument:
    pg: str
    item_ids: tuple[uuid.UUID, ...]
    exact_payload: bytes = field(repr=False)
    payload_sha256: str


def build_withdrawal_documents(
    *,
    inn: str,
    attempt_started_at: datetime,
    products: list[WithdrawalProduct],
    max_codes: int = MAX_DOCUMENT_CISES,
    max_bytes: int = MAX_DOCUMENT_BYTES,
) -> list[BuiltWithdrawalDocument]:
    if not inn.isascii() or not inn.isdigit() or len(inn) not in {10, 12}:
        raise ValueError("invalid_participant_inn")
    if attempt_started_at.tzinfo is None:
        raise ValueError("withdrawal_date_requires_timezone")
    if not 1 <= max_codes <= MAX_DOCUMENT_CISES or not 1 <= max_bytes <= MAX_DOCUMENT_BYTES:
        raise ValueError("invalid_document_limits")
    if len({product.cis for product in products}) != len(products):
        raise ValueError("duplicate_withdrawal_cis")
    if len({product.item_id for product in products}) != len(products):
        raise ValueError("duplicate_withdrawal_item")
    grouped: dict[tuple[str, str | None, str | None], list[WithdrawalProduct]] = defaultdict(list)
    for product in products:
        if not product.cis or not product.pg:
            raise ValueError("missing_withdrawal_identity")
        if (
            type(product.product_cost) is not int
            or not 0 <= product.product_cost <= 99999999999999999
        ):
            raise ValueError("invalid_product_cost")
        if product.fias_id is not None:
            uuid.UUID(product.fias_id)
        if product.kpp is not None and (
            len(inn) != 10
            or len(product.kpp) != 9
            or not product.kpp.isascii()
            or not product.kpp.isdigit()
        ):
            raise ValueError("invalid_mod_kpp")
        grouped[(product.pg, product.fias_id, product.kpp)].append(product)
    action_date = attempt_started_at.astimezone(ZoneInfo("Europe/Moscow")).date().isoformat()
    result: list[BuiltWithdrawalDocument] = []
    for (pg, fias, kpp), group in grouped.items():
        header = {"inn": inn, "action": "DISTANCE", "action_date": action_date}
        if fias is not None:
            header["fias_id"] = fias
        if kpp is not None:
            header["kpp"] = kpp
        prefix = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode()[:-1]
        prefix += b',"products":['
        chunks: list[bytes] = []
        ids: list[uuid.UUID] = []
        size = len(prefix) + 2

        def finish(prefix: bytes, chunks: list[bytes], ids: list[uuid.UUID], pg: str) -> None:
            payload = prefix + b",".join(chunks) + b"]}"
            result.append(
                BuiltWithdrawalDocument(
                    pg,
                    tuple(ids),
                    payload,
                    hashlib.sha256(payload).hexdigest(),
                )
            )

        for product in sorted(group, key=lambda value: value.item_id):
            chunk = json.dumps(
                {"cis": product.cis, "product_cost": product.product_cost},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(prefix) + len(chunk) + 2 > max_bytes:
                raise ValueError("withdrawal_product_exceeds_document_limit")
            if chunks and (len(chunks) == max_codes or size + len(chunk) + 1 > max_bytes):
                finish(prefix, chunks, ids, pg)
                chunks, ids, size = [], [], len(prefix) + 2
            size += len(chunk) + bool(chunks)
            chunks.append(chunk)
            ids.append(product.item_id)
        if chunks:
            finish(prefix, chunks, ids, pg)
    return result
