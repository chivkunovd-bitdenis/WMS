"""WMS-517 durable withdrawal ledger. Payloads/tokens are restricted audit data."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    inspect,
    text,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.models.base import Base


class WithdrawalOperation(Base):
    __tablename__ = "withdrawal_operations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "seller_id", "client_request_id", name="uq_withdrawal_client_request"
        ),
        UniqueConstraint("id", "tenant_id", "seller_id", name="uq_withdrawal_operation_scope"),
        CheckConstraint(
            "environment IN ('sandbox', 'production')", name="ck_withdrawal_environment"
        ),
        CheckConstraint("attempt >= 1", name="ck_withdrawal_attempt"),
        CheckConstraint(
            "state IN ('created','auth_pending','documents_pending_signature','submitting',"
            "'submitted','reconciling','succeeded','partial_failed','failed','cancelled')",
            name="ck_withdrawal_operation_state",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sellers.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    client_request_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    selection_hash: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16), default="sandbox")
    state: Mapped[str] = mapped_column(String(32), default="created")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    # Auth is deliberately not populated by the B3-gated public API.
    certificate_thumbprint: Mapped[str | None] = mapped_column(String(128))
    certificate_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    auth_uuid: Mapped[str | None] = mapped_column(String(36))
    auth_challenge: Mapped[str | None] = mapped_column(Text)
    token_enc: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    participant_inn: Mapped[str | None] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WithdrawalDocument(Base):
    """One immutable document attempt; retries insert new rows, never reuse bytes/signatures."""

    __tablename__ = "withdrawal_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["operation_id", "tenant_id", "seller_id"],
            [
                "withdrawal_operations.id",
                "withdrawal_operations.tenant_id",
                "withdrawal_operations.seller_id",
            ],
            name="fk_withdrawal_document_scope",
        ),
        UniqueConstraint(
            "id",
            "operation_id",
            "tenant_id",
            "seller_id",
            "attempt",
            name="uq_withdrawal_document_scope",
        ),
        UniqueConstraint("environment", "gis_document_id", name="uq_withdrawal_gis_document"),
        CheckConstraint("attempt >= 1", name="ck_withdrawal_document_attempt"),
        CheckConstraint(
            "state NOT IN ('submitting','submitted','reconciling') OR "
            "(next_poll_at IS NOT NULL AND request_started_at IS NOT NULL)",
            name="ck_withdrawal_recoverable",
        ),
        CheckConstraint(
            "state IN ('pending_signature','submitting','submitted','reconciling',"
            "'succeeded','failed')",
            name="ck_withdrawal_document_state",
        ),
        Index("ix_withdrawal_due", "next_poll_at", "lease_until"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    attempt: Mapped[int] = mapped_column(Integer)
    environment: Mapped[str] = mapped_column(String(16))
    pg: Mapped[str] = mapped_column(String(64))
    participant_inn: Mapped[str] = mapped_column(String(12))
    exact_payload: Mapped[bytes] = mapped_column(LargeBinary)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    signature: Mapped[str | None] = mapped_column(Text)
    certificate_thumbprint: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(32), default="pending_signature")
    request_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gis_document_id: Mapped[str | None] = mapped_column(String(36))
    gis_status: Mapped[str | None] = mapped_column(String(64))
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[bytes | None] = mapped_column(LargeBinary)
    errors: Mapped[Any] = mapped_column(JSON, nullable=True)
    common_errors: Mapped[Any] = mapped_column(JSON, nullable=True)
    incident: Mapped[str | None] = mapped_column(String(64))
    reconciliation_ids: Mapped[list[str] | None] = mapped_column(JSON)
    poll_count: Mapped[int] = mapped_column(Integer, default=0)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WithdrawalItem(Base):
    __tablename__ = "withdrawal_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["operation_id", "tenant_id", "seller_id"],
            [
                "withdrawal_operations.id",
                "withdrawal_operations.tenant_id",
                "withdrawal_operations.seller_id",
            ],
            name="fk_withdrawal_item_scope",
        ),
        ForeignKeyConstraint(
            ["document_id", "operation_id", "tenant_id", "seller_id", "attempt"],
            [
                "withdrawal_documents.id",
                "withdrawal_documents.operation_id",
                "withdrawal_documents.tenant_id",
                "withdrawal_documents.seller_id",
                "withdrawal_documents.attempt",
            ],
            name="fk_withdrawal_item_document_scope",
        ),
        UniqueConstraint(
            "operation_id", "marking_id", "attempt", name="uq_withdrawal_item_attempt"
        ),
        Index(
            "uq_withdrawal_marking_claim",
            "marking_id",
            unique=True,
            postgresql_where=text("holds_claim"),
            sqlite_where=text("holds_claim = 1"),
        ),
        Index(
            "uq_withdrawal_cis_claim",
            "tenant_id",
            "cis",
            unique=True,
            postgresql_where=text("holds_claim"),
            sqlite_where=text("holds_claim = 1"),
        ),
        CheckConstraint(
            "state IN ('pending','succeeded','failed')", name="ck_withdrawal_item_state"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    operation_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    seller_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    attempt: Mapped[int] = mapped_column(Integer)
    marking_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("fbs_order_markings.id"))
    marking_code_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("marking_codes.id"))
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("fbs_orders.id"))
    supply_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("fbs_supplies.id"))
    cis: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(16))
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("wb_order_price_snapshots.id")
    )
    product_cost: Mapped[int | None] = mapped_column(BigInteger)
    pg: Mapped[str | None] = mapped_column(String(64))
    owner_inn: Mapped[str | None] = mapped_column(String(12))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    holds_claim: Mapped[bool] = mapped_column(Boolean, default=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WithdrawalObservation(Base):
    """Append-only read/submit evidence, separate from the current document projection."""

    __tablename__ = "withdrawal_observations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("withdrawal_documents.id"))
    status: Mapped[str | None] = mapped_column(String(64))
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[bytes | None] = mapped_column(LargeBinary)
    errors: Mapped[Any] = mapped_column(JSON, nullable=True)
    common_errors: Mapped[Any] = mapped_column(JSON, nullable=True)
    incident: Mapped[str | None] = mapped_column(String(64))
    reconciliation_ids: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


@event.listens_for(WithdrawalObservation, "before_update")
@event.listens_for(WithdrawalObservation, "before_delete")
def _immutable_observation(
    mapper: Mapper[WithdrawalObservation],
    connection: Connection,
    target: WithdrawalObservation,
) -> None:
    raise ValueError("withdrawal_observation_is_immutable")


@event.listens_for(WithdrawalDocument, "before_update")
def _immutable_document(
    mapper: Mapper[WithdrawalDocument],
    connection: Connection,
    target: WithdrawalDocument,
) -> None:
    state = inspect(target)
    immutable = (
        "operation_id",
        "tenant_id",
        "seller_id",
        "attempt",
        "environment",
        "pg",
        "participant_inn",
        "exact_payload",
        "payload_sha256",
        "certificate_thumbprint",
    )
    if any(state.attrs[name].history.has_changes() for name in immutable):
        raise ValueError("withdrawal_document_is_immutable")
    history = state.attrs.signature.history
    if history.has_changes() and history.deleted and history.deleted[0] is not None:
        raise ValueError("withdrawal_signature_is_immutable")
