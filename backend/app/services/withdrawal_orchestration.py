"""Durable browser-signing orchestration. All provider waits are outside DB locks."""

from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.withdrawal_repository import (
    WithdrawalError,
    WithdrawalScope,
    current_items,
    eligible_rows,
    get_operation,
    lock_seller,
)
from app.models.billing import BillingProfile
from app.models.fbs_order import FbsOrderMarking
from app.models.marking_withdrawal import (
    WithdrawalDocument,
    WithdrawalItem,
    WithdrawalObservation,
    WithdrawalOperation,
)
from app.services.integration_fernet import decrypt_secret, encrypt_secret
from app.services.true_api_withdrawal import (
    AuthSession,
    CisInfo,
    Environment,
    TrueApiError,
    safe_provider_error,
)
from app.services.wb_order_price_service import WbPriceDataError, resolve_wb_product_cost
from app.services.withdrawal_document_builder import WithdrawalProduct, build_withdrawal_documents
from app.services.withdrawal_mod_service import (
    DISTANCE_MOD_GROUPS,
    required_external_mod,
)
from app.services.withdrawal_recovery import aware
from app.services.withdrawal_runtime import WithdrawalRuntime
from app.services.withdrawal_service import INTEGRATION_GATE

# Intersection of True API v731 LK_RECEIPT creation groups and DISTANCE reasons.
DISTANCE_GROUPS = frozenset(
    {
        "lp",
        "shoes",
        "perfumery",
        "tires",
        "electronics",
        "milk",
        "bicycle",
        "wheelchairs",
        "water",
        "furs",
        "bio",
        "antiseptic",
        "petfood",
        "seafood",
        "nabeer",
        "softdrinks",
        "vetpharma",
        "toys",
        "radio",
        "conserve",
        "vegetableoil",
        "opticfiber",
        "chemistry",
        "books",
        "grocery",
        "construction",
        "fire",
        "heater",
        "autofluids",
        "furslp",
        "gadgets",
    }
)


@dataclass(frozen=True)
class CertificateSelection:
    thumbprint: str
    expires_at: datetime
    subject: str | None = None
    issuer: str | None = None

    def metadata(self) -> dict[str, Any]:
        if self.expires_at.tzinfo is None or aware(self.expires_at) <= datetime.now(UTC):
            raise WithdrawalError("certificate_expired")
        return {
            "expires_at": self.expires_at.isoformat(),
            "subject": self.subject,
            "issuer": self.issuer,
        }


@dataclass(frozen=True)
class SignedWithdrawalDocument:
    document_id: uuid.UUID
    payload_sha256: str
    thumbprint: str
    signature: str = field(repr=False)


async def scoped_documents(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation: WithdrawalOperation,
) -> list[WithdrawalDocument]:
    return list(
        await session.scalars(
            select(WithdrawalDocument)
            .where(
                WithdrawalDocument.operation_id == operation.id,
                WithdrawalDocument.tenant_id == scope.tenant_id,
                WithdrawalDocument.seller_id == scope.seller_id,
                WithdrawalDocument.attempt == operation.attempt,
            )
            .order_by(WithdrawalDocument.id)
        )
    )


async def _rows(
    session: AsyncSession, scope: WithdrawalScope, operation: WithdrawalOperation
) -> None:
    items = [
        item
        for item in await current_items(session, scope, operation.id)
        if item.state == "pending"
    ]
    ids = [item.marking_id for item in items]
    rows = (
        await session.execute(
            eligible_rows(scope)
            .where(
                FbsOrderMarking.id.in_(ids),
            )
            .order_by(FbsOrderMarking.id)
            .with_for_update(of=FbsOrderMarking)
        )
    ).all()
    if len(rows) != len(ids):
        raise WithdrawalError("withdrawal_rows_not_found", 404)
    if any(
        marking.value != item.cis
        for item in items
        for marking, _, _ in rows
        if item.marking_id == marking.id
    ):
        raise WithdrawalError("withdrawal_cis_changed")


def _has_lease(operation: WithdrawalOperation) -> bool:
    return (
        operation.workflow_lease_id is not None
        and operation.workflow_lease_until is not None
        and aware(operation.workflow_lease_until) > datetime.now(UTC)
    )


def _lease(operation: WithdrawalOperation) -> uuid.UUID:
    identifier = uuid.uuid4()
    operation.workflow_lease_id = identifier
    operation.workflow_lease_until = datetime.now(UTC) + timedelta(minutes=5)
    return identifier


def _clear_lease(operation: WithdrawalOperation) -> None:
    operation.workflow_lease_id = None
    operation.workflow_lease_until = None


async def participant_inn(session: AsyncSession, scope: WithdrawalScope) -> str:
    inn = await session.scalar(
        select(BillingProfile.inn).where(
            BillingProfile.tenant_id == scope.tenant_id,
            BillingProfile.seller_id == scope.seller_id,
        )
    )
    if inn is None or len(inn) not in {10, 12} or not inn.isascii() or not inn.isdigit():
        raise WithdrawalError("seller_billing_inn_missing_or_invalid")
    return inn


async def _auth_error(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation_id: uuid.UUID,
    lease: uuid.UUID,
    error: TrueApiError | WithdrawalError,
) -> WithdrawalOperation:
    operation = await get_operation(session, scope, operation_id, lock=True)
    if operation.workflow_lease_id == lease:
        operation.workflow_error = {
            "code": error.reason if isinstance(error, TrueApiError) else error.code,
            "http_status": error.status_code,
            **(safe_provider_error(error.response_body) if isinstance(error, TrueApiError) else {}),
        }
        operation.token_enc = None
        operation.token_expires_at = None
        operation.auth_signature_hash = None
        operation.auth_uuid = None
        operation.auth_challenge = None
        if operation.state not in {"submitting", "submitted", "reconciling"}:
            operation.state = "auth_pending"
        _clear_lease(operation)
    await session.commit()
    return operation


def reauth_required(operation: WithdrawalOperation, documents: list[WithdrawalDocument]) -> bool:
    return any(
        doc.request_started_at is not None
        and doc.state in {"submitting", "submitted", "reconciling"}
        for doc in documents
    ) and (
        operation.token_enc is None
        or operation.token_expires_at is None
        or aware(operation.token_expires_at) <= datetime.now(UTC)
    )


async def prepare_reauth(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation_id: uuid.UUID,
    certificate: CertificateSelection,
    runtime: WithdrawalRuntime,
) -> WithdrawalOperation:
    operation = await get_operation(session, scope, operation_id, lock=True)
    if operation.user_id != scope.user_id:
        raise WithdrawalError("withdrawal_reauth_user_mismatch", 403)
    if operation.certificate_thumbprint != certificate.thumbprint:
        raise WithdrawalError("withdrawal_reauth_certificate_mismatch")
    metadata = certificate.metadata()
    documents = await scoped_documents(session, scope, operation)
    if not reauth_required(operation, documents) or _has_lease(operation):
        await session.commit()
        return operation
    # No eligible_rows: cancellation after a persisted submit cannot prevent reads.
    inn = await participant_inn(session, scope)
    if inn != operation.participant_inn:
        raise WithdrawalError("withdrawal_auth_participant_mismatch")
    operation.certificate_metadata = metadata
    operation.token_enc = None
    operation.token_expires_at = None
    operation.auth_signature_hash = None
    operation.auth_uuid = None
    operation.auth_challenge = None
    operation.workflow_error = {"code": "reauth_required"}
    lease = _lease(operation)
    client = runtime.client(inn, operation.environment)
    await session.commit()
    try:
        challenge = await client.challenge()
    except TrueApiError as exc:
        return await _auth_error(session, scope, operation_id, lease, exc)
    operation = await get_operation(session, scope, operation_id, lock=True)
    if operation.workflow_lease_id == lease:
        operation.auth_uuid, operation.auth_challenge = challenge.uuid, challenge.data
        _clear_lease(operation)
    await session.commit()
    return operation


async def _replace_unsigned(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation: WithdrawalOperation,
    documents: list[WithdrawalDocument],
) -> None:
    # New auth/cert invalidates unsigned preparation without changing successful
    # neighbours or mutating old bytes/signatures. No KIZ error is projected.
    if any(document.state != "pending_signature" for document in documents):
        raise WithdrawalError("withdrawal_already_submitted")
    items = [
        item
        for item in await current_items(session, scope, operation.id)
        if item.state == "pending"
    ]
    operation.attempt += 1
    operation.attempt_started_at = datetime.now(UTC)
    replacements = []
    for item in items:
        values = {
            column.name: getattr(item, column.name)
            for column in WithdrawalItem.__table__.columns
            if column.name
            not in {
                "id",
                "created_at",
                "attempt",
                "document_id",
                "pg",
                "owner_inn",
                "preflight_evidence",
                "error",
            }
        }
        item.holds_claim = False
        replacements.append(WithdrawalItem(**values, attempt=operation.attempt))
    await session.flush()
    for document in documents:
        document.state = "failed"
        document.incident = "unsigned_auth_invalidated"
        session.add(
            WithdrawalObservation(document_id=document.id, incident="unsigned_auth_invalidated")
        )
    session.add_all(replacements)


async def prepare_challenge(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation_id: uuid.UUID,
    certificate: CertificateSelection | None,
    runtime: WithdrawalRuntime,
) -> WithdrawalOperation:
    operation = await get_operation(session, scope, operation_id, lock=True)
    if not runtime.enabled or certificate is None:
        await session.commit()
        return operation
    metadata = certificate.metadata()
    if operation.state in {
        "submitting",
        "submitted",
        "reconciling",
        "succeeded",
        "partial_failed",
        "failed",
        "cancelled",
    }:
        await session.commit()
        return operation
    if _has_lease(operation):
        await session.commit()
        return operation
    await _rows(session, scope, operation)
    same_cert = operation.certificate_thumbprint == certificate.thumbprint
    valid_auth = (
        operation.token_enc is not None
        and operation.token_expires_at is not None
        and aware(operation.token_expires_at) > datetime.now(UTC)
    )
    if same_cert and (
        valid_auth
        or (
            operation.token_enc is None
            and operation.auth_signature_hash is None
            and operation.auth_uuid
            and operation.auth_challenge
        )
    ):
        await session.commit()
        return operation
    documents = await scoped_documents(session, scope, operation)
    if documents:
        await _replace_unsigned(session, scope, operation, documents)
    inn = await participant_inn(session, scope)
    operation.participant_inn = inn
    operation.certificate_thumbprint = certificate.thumbprint
    operation.certificate_metadata = metadata
    operation.token_enc = None
    operation.token_expires_at = None
    operation.auth_signature_hash = None
    operation.auth_uuid = None
    operation.auth_challenge = None
    operation.workflow_error = None
    operation.state = "auth_pending"
    lease = _lease(operation)
    client = runtime.client(inn, operation.environment)
    await session.commit()
    try:
        challenge = await client.challenge()
    except TrueApiError as exc:
        return await _auth_error(session, scope, operation_id, lease, exc)
    operation = await get_operation(session, scope, operation_id, lock=True)
    if operation.workflow_lease_id == lease:
        operation.auth_uuid = challenge.uuid
        operation.auth_challenge = challenge.data
        _clear_lease(operation)
    await session.commit()
    return operation


def cis_error(
    info: CisInfo | None, *, inn: str, traceability_mode: str | None = None
) -> dict[str, Any] | None:
    if info is None:
        return {"source": "local", "code": "cis_response_missing_or_ambiguous"}
    if info.error_code is not None or info.error_message is not None:
        return {"source": "crpt", "code": info.error_code, "message": info.error_message}
    if info.owner_inn != inn:
        return {"source": "local", "code": "cis_owner_mismatch", "owner_inn": info.owner_inn}
    if info.product_group is None or info.product_group_id is None or not info.gtin or not info.cis:
        return {"source": "local", "code": "cis_incomplete_identity"}
    if info.product_group not in DISTANCE_GROUPS:
        return {"source": "local", "code": "distance_not_supported", "pg": info.product_group}
    if traceability_mode not in {"started", "not_started"}:
        return {"source": "local", "code": "traceability_mode_unknown"}
    extended_allowed = (
        info.status_ex in {None, "CONNECT_TAP", "WAIT_TRANSFER_TO_OWNER"}
        if traceability_mode == "started"
        else info.status_ex != "MOVING_BY_UD"
    )
    if info.status != "INTRODUCED" or not extended_allowed:
        return {
            "source": "local",
            "code": "cis_status_not_allowed",
            "status": info.status,
            "statusEx": info.status_ex,
        }
    return None


def current_auth(operation: WithdrawalOperation) -> AuthSession:
    if (
        operation.participant_inn is None
        or operation.token_enc is None
        or operation.token_expires_at is None
        or aware(operation.token_expires_at) <= datetime.now(UTC)
    ):
        raise WithdrawalError("withdrawal_auth_required")
    return AuthSession(
        Environment(operation.environment),
        operation.participant_inn,
        aware(operation.token_expires_at),
        decrypt_secret(operation.token_enc),
    )


async def authenticate_and_build(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation_id: uuid.UUID,
    *,
    thumbprint: str,
    challenge_uuid: uuid.UUID | None,
    expected_attempt: int | None,
    signature: str,
    runtime: WithdrawalRuntime,
) -> WithdrawalOperation:
    operation = await get_operation(session, scope, operation_id, lock=True)
    recovery = operation.state in {"submitting", "submitted", "reconciling"}
    if recovery and operation.user_id != scope.user_id:
        raise WithdrawalError("withdrawal_reauth_user_mismatch", 403)
    if not runtime.enabled and not recovery:
        raise WithdrawalError(INTEGRATION_GATE)
    if (
        operation.certificate_thumbprint != thumbprint
        or challenge_uuid is None
        or operation.auth_uuid != str(challenge_uuid)
        or expected_attempt != operation.attempt
    ):
        raise WithdrawalError("withdrawal_auth_signature_mismatch")
    digest = hashlib.sha256(signature.encode()).hexdigest()
    if operation.auth_signature_hash is not None and operation.auth_signature_hash != digest:
        raise WithdrawalError("withdrawal_auth_signature_mismatch")
    if (
        (operation.state != "auth_pending" and not recovery)
        or _has_lease(operation)
        or (
            recovery
            and operation.auth_signature_hash == digest
            and operation.token_enc
            and operation.token_expires_at
            and aware(operation.token_expires_at) > datetime.now(UTC)
        )
    ):
        await session.commit()
        return operation
    if not recovery:
        await _rows(session, scope, operation)
    inn = await participant_inn(session, scope)
    if operation.participant_inn != inn or operation.certificate_metadata is None:
        raise WithdrawalError("withdrawal_auth_participant_mismatch")
    metadata = operation.certificate_metadata
    certificate_expiry = datetime.fromisoformat(metadata["expires_at"])
    client = runtime.client(inn, operation.environment)
    lease = _lease(operation)
    items = [
        item
        for item in await current_items(session, scope, operation.id)
        if item.state == "pending"
    ]
    codes = [item.provider_cis for item in items if item.provider_cis is not None]
    reusable = operation.token_enc is not None
    auth = current_auth(operation) if reusable else None
    await session.commit()
    try:
        if auth is None:
            auth = await client.sign_in(
                str(challenge_uuid),
                signature,
                certificate_expires_at=certificate_expiry,
            )
            operation = await get_operation(session, scope, operation_id, lock=True)
            if operation.workflow_lease_id != lease:
                await session.commit()
                return operation
            operation.token_enc = encrypt_secret(auth.token)
            operation.token_expires_at = auth.expires_at
            operation.auth_signature_hash = digest
            if recovery:
                operation.workflow_error = None
                _clear_lease(operation)
                documents = await scoped_documents(session, scope, operation)
                for document in documents:
                    if document.state in {"submitted", "reconciling"}:
                        document.next_poll_at = datetime.now(UTC)
            await session.commit()
        if recovery:
            return operation  # Reauth can only wake persisted GET recovery, never builder/create.
        valid_codes = [code for code in codes if 18 <= len(code) <= 74]
        by_cis: dict[str, CisInfo] = {}
        for offset in range(0, len(valid_codes), 1000):
            response = await client.cises_info(auth, valid_codes[offset : offset + 1000])
            by_cis.update(response.by_cis)
        groups = {
            info.product_group
            for info in by_cis.values()
            if cis_error(
                info, inn=inn, traceability_mode=runtime.traceability_mode(info.product_group)
            )
            is None
            and info.product_group in DISTANCE_MOD_GROUPS
        }
        discoveries: dict[str, list[dict[str, Any]]] = {}
        discovery_errors: dict[str, dict[str, Any]] = {}
        for pg in sorted(group for group in groups if group is not None):
            try:
                discoveries[pg] = await client.registered_mods(auth, pg=pg)
            except TrueApiError as exc:
                discovery_errors[pg] = {
                    "source": "crpt",
                    "code": exc.reason,
                    "http_status": exc.status_code,
                    "stage": "mods/list",
                }
    except TrueApiError as exc:
        return await _auth_error(session, scope, operation_id, lease, exc)
    except ValueError:
        return await _auth_error(
            session,
            scope,
            operation_id,
            lease,
            WithdrawalError("withdrawal_auth_or_provider_data_invalid"),
        )
    await lock_seller(session, scope)
    operation = await get_operation(session, scope, operation_id, lock=True)
    if operation.workflow_lease_id != lease:
        await session.commit()
        return operation
    await _rows(session, scope, operation)
    if await participant_inn(session, scope) != inn:
        return await _auth_error(
            session,
            scope,
            operation_id,
            lease,
            WithdrawalError("withdrawal_auth_participant_mismatch"),
        )
    prepared: list[WithdrawalProduct] = []
    current = await current_items(session, scope, operation.id)
    group_ids: dict[str, set[int | None]] = {}
    for group_info in by_cis.values():
        if group_info.product_group:
            group_ids.setdefault(group_info.product_group, set()).add(group_info.product_group_id)
    for item in current:
        if item.state != "pending":
            continue
        info = by_cis.get(item.provider_cis or "")
        item.preflight_evidence = (
            {
                "cis": info.raw,
                "provider_cis": item.provider_cis,
                "traceability_metadata_version": runtime.traceability_metadata_version,
                "traceability_mode": runtime.traceability_mode(info.product_group),
                "external_mods": discoveries.get(info.product_group or "", []),
            }
            if info
            else None
        )
        error = cis_error(
            info,
            inn=inn,
            traceability_mode=runtime.traceability_mode(info.product_group if info else None),
        )
        if info and info.product_group and len(group_ids[info.product_group]) != 1:
            error = {"source": "local", "code": "cis_group_identity_conflict"}
        if error:
            item.state, item.error = "failed", error
            continue
        assert info is not None and info.product_group is not None
        item.pg, item.owner_inn = info.product_group, info.owner_inn
        if info.product_group in discovery_errors:
            item.state, item.error = "failed", discovery_errors[info.product_group]
            continue
        try:
            price = await resolve_wb_product_cost(
                session,
                tenant_id=scope.tenant_id,
                seller_id=scope.seller_id,
                order_id=item.order_id,
            )
            item.price_snapshot_id, item.product_cost = price.snapshot_id, price.product_cost
            fias, kpp = required_external_mod(
                inn=inn,
                pg=info.product_group,
                rows=discoveries.get(info.product_group, []),
            )
        except (WithdrawalError, WbPriceDataError) as exc:
            item.state = "failed"
            item.error = {"source": "local", "code": exc.code, "message": str(exc)}
            continue
        prepared.append(
            WithdrawalProduct(
                item.id, item.provider_cis or "", price.product_cost, info.product_group, fias, kpp
            )
        )
    built = build_withdrawal_documents(
        inn=inn,
        attempt_started_at=aware(operation.attempt_started_at or operation.created_at),
        products=prepared,
    )
    by_id = {item.id: item for item in current}
    for value in built:
        document = WithdrawalDocument(
            operation_id=operation.id,
            tenant_id=scope.tenant_id,
            seller_id=scope.seller_id,
            attempt=operation.attempt,
            environment=operation.environment,
            pg=value.pg,
            participant_inn=inn,
            exact_payload=value.exact_payload,
            payload_sha256=value.payload_sha256,
            certificate_thumbprint=thumbprint,
            state="pending_signature",
        )
        session.add(document)
        await session.flush()
        for item_id in value.item_ids:
            by_id[item_id].document_id = document.id
    operation.state = (
        "documents_pending_signature"
        if built
        else "partial_failed"
        if any(item.state == "succeeded" for item in current)
        else "failed"
    )
    operation.workflow_error = None
    _clear_lease(operation)
    await session.commit()
    return operation


async def accept_document_signatures(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation_id: uuid.UUID,
    signatures: list[SignedWithdrawalDocument],
    runtime: WithdrawalRuntime,
) -> WithdrawalOperation:
    operation = await get_operation(session, scope, operation_id, lock=True)
    if not runtime.enabled:
        raise WithdrawalError(INTEGRATION_GATE)
    documents = await scoped_documents(session, scope, operation)
    supplied = {value.document_id: value for value in signatures}
    if (
        not documents
        or len(supplied) != len(signatures)
        or set(supplied) != {doc.id for doc in documents}
    ):
        raise WithdrawalError("withdrawal_document_set_mismatch")
    for document in documents:
        value = supplied[document.id]
        if (
            document.certificate_thumbprint != value.thumbprint
            or operation.certificate_thumbprint != value.thumbprint
            or document.payload_sha256 != value.payload_sha256
            or hashlib.sha256(document.exact_payload).hexdigest() != value.payload_sha256
        ):
            raise WithdrawalError("withdrawal_document_signature_mismatch")
        try:
            if not base64.b64decode(value.signature, validate=True):
                raise ValueError
        except (ValueError, binascii.Error):
            raise WithdrawalError("invalid_document_signature") from None
        if document.signature is not None and document.signature != value.signature:
            raise WithdrawalError("withdrawal_document_signature_mismatch")
    if all(document.signature is not None for document in documents):
        await session.commit()
        return operation
    current_auth(operation)
    await _rows(session, scope, operation)
    if operation.state != "documents_pending_signature":
        raise WithdrawalError("withdrawal_not_awaiting_signatures")
    for document in documents:
        if document.state != "pending_signature":
            raise WithdrawalError("withdrawal_already_submitted")
        document.signature = supplied[document.id].signature
    # The durable signed rows are the submit queue. The scheduler picks them up
    # even if the HTTP response or an optional immediate wakeup is lost.
    await session.commit()
    return operation
