from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateWithdrawal(StrictInput):
    client_request_id: uuid.UUID
    row_ids: list[uuid.UUID] = Field(min_length=1, max_length=250)


class RetryWithdrawal(StrictInput):
    expected_attempt: int = Field(ge=1)


class AuthSignature(StrictInput):
    thumbprint: str = Field(min_length=1, max_length=128)
    signature: SecretStr = Field(min_length=1, max_length=1_000_000)


class DocumentSignature(StrictInput):
    document_id: uuid.UUID
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    thumbprint: str = Field(min_length=1, max_length=128)
    signature: SecretStr = Field(min_length=1, max_length=1_000_000)


class DocumentSignatures(StrictInput):
    documents: list[DocumentSignature] = Field(min_length=1, max_length=250)


class WithdrawalRow(BaseModel):
    row_id: uuid.UUID
    delivered_at: datetime
    wb_order_id: str
    sku: str
    product_name: str
    cis: str
    status: Literal["not_withdrawn", "withdrawn", "error"]
    error: dict[str, Any] | None = None
    operation_id: uuid.UUID | None = None


class WithdrawalPage(BaseModel):
    rows: list[WithdrawalRow]
    total: int


class OperationItem(BaseModel):
    row_id: uuid.UUID
    cis: str
    status: Literal["not_withdrawn", "withdrawn", "error"]
    error: dict[str, Any] | None = None


class OperationOut(BaseModel):
    operation_id: uuid.UUID
    state: str
    attempt: int
    integration_gate: Literal["B3_AUTH_PROFILE_UNCONFIRMED"]
    items: list[OperationItem]
