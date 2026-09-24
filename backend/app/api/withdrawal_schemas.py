from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WithdrawalCertificate(StrictInput):
    thumbprint: str = Field(min_length=1, max_length=128)
    expires_at: AwareDatetime
    subject: str | None = Field(default=None, max_length=2048)
    issuer: str | None = Field(default=None, max_length=2048)


class ReauthWithdrawal(StrictInput):
    certificate: WithdrawalCertificate


class CreateWithdrawal(StrictInput):
    client_request_id: uuid.UUID
    row_ids: list[uuid.UUID] = Field(min_length=1, max_length=250)
    certificate: WithdrawalCertificate | None = None


class RetryWithdrawal(StrictInput):
    expected_attempt: int = Field(ge=1)
    certificate: WithdrawalCertificate | None = None


class AuthSignature(StrictInput):
    thumbprint: str = Field(min_length=1, max_length=128)
    signature: SecretStr = Field(min_length=1, max_length=1_000_000)
    challenge_uuid: uuid.UUID | None = None
    expected_attempt: int | None = Field(default=None, ge=1)


class DocumentSignature(StrictInput):
    document_id: uuid.UUID
    payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    thumbprint: str = Field(min_length=1, max_length=128)
    signature: SecretStr = Field(min_length=1, max_length=1_000_000)


class DocumentSignatures(StrictInput):
    documents: list[DocumentSignature] = Field(min_length=1, max_length=250)


class WithdrawalRow(BaseModel):
    row_id: uuid.UUID
    product_id: uuid.UUID | None = None
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
    wb_order_id: str = ""
    status: Literal["not_withdrawn", "withdrawn", "error"]
    error: dict[str, Any] | None = None


class WithdrawalChallenge(BaseModel):
    uuid: str
    data: str


class WithdrawalDocumentBlob(BaseModel):
    document_id: uuid.UUID
    payload_base64: str
    payload_sha256: str
    thumbprint: str


class OperationOut(BaseModel):
    operation_id: uuid.UUID
    state: str
    attempt: int
    integration_gate: Literal["WITHDRAWAL_PRODUCTION_SUBMIT_DISABLED"] | None
    reauth_required: bool = False
    certificate_thumbprint: str | None = None
    items: list[OperationItem]
    auth_challenge: WithdrawalChallenge | None = None
    documents: list[WithdrawalDocumentBlob] = Field(default_factory=list)
    auth_error: dict[str, Any] | None = None
