"""Same-origin seller boundary. No browser profile means no auth/sign/create."""

from __future__ import annotations

import base64
import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import assert_seller_permission, get_current_user, get_effective_seller_id
from app.api.withdrawal_schemas import (
    AuthSignature,
    CreateWithdrawal,
    DocumentSignatures,
    OperationItem,
    OperationOut,
    ReauthWithdrawal,
    RetryWithdrawal,
    WithdrawalChallenge,
    WithdrawalDocumentBlob,
    WithdrawalPage,
    WithdrawalRow,
)
from app.core.roles import FULFILLMENT_SELLER
from app.db.session import get_db
from app.db.withdrawal_repository import (
    WithdrawalError,
    WithdrawalScope,
    current_items,
    eligible_rows,
    get_operation,
    registry,
)
from app.models.fbs_order import FbsOrder
from app.models.marking_withdrawal import WithdrawalOperation
from app.models.product import Product
from app.models.user import User
from app.services.seller_staff_permissions_service import PERM_HONEST_SIGN
from app.services.withdrawal_orchestration import (
    CertificateSelection,
    SignedWithdrawalDocument,
    accept_document_signatures,
    authenticate_and_build,
    prepare_challenge,
    prepare_reauth,
    reauth_required,
    scoped_documents,
)
from app.services.withdrawal_runtime import WithdrawalRuntime, get_withdrawal_runtime
from app.services.withdrawal_service import create_operation, retry_operation

router = APIRouter(prefix="/operations/marking-codes/self/withdrawals", tags=["operations"])
Db = Annotated[AsyncSession, Depends(get_db)]
Runtime = Annotated[WithdrawalRuntime, Depends(get_withdrawal_runtime)]


async def _scope(
    session: Db,
    user: Annotated[User, Depends(get_current_user)],
    seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> WithdrawalScope:
    if user.role != FULFILLMENT_SELLER or seller_id is None:
        raise HTTPException(403, "seller_session_required")
    await assert_seller_permission(session, user, PERM_HONEST_SIGN)
    return WithdrawalScope(user.tenant_id, seller_id, user.id)


Scope = Annotated[WithdrawalScope, Depends(_scope)]


async def _output(
    session: AsyncSession,
    scope: WithdrawalScope,
    operation: WithdrawalOperation,
    runtime: WithdrawalRuntime,
) -> OperationOut:
    items = await current_items(session, scope, operation.id)
    orders: dict[uuid.UUID, int] = {
        identifier: wb_id
        for identifier, wb_id in (
            await session.execute(
                select(FbsOrder.id, FbsOrder.wb_order_id).where(
                    FbsOrder.id.in_([item.order_id for item in items]),
                    FbsOrder.tenant_id == scope.tenant_id,
                    FbsOrder.seller_id == scope.seller_id,
                )
            )
        ).all()
    }
    documents = await scoped_documents(session, scope, operation)
    return OperationOut(
        operation_id=operation.id,
        state=operation.state,
        attempt=operation.attempt,
        integration_gate=None if runtime.enabled else "WITHDRAWAL_PRODUCTION_SUBMIT_DISABLED",
        reauth_required=reauth_required(operation, documents),
        certificate_thumbprint=operation.certificate_thumbprint,
        auth_error=operation.workflow_error,
        auth_challenge=(
            WithdrawalChallenge(uuid=operation.auth_uuid, data=operation.auth_challenge)
            if (operation.state == "auth_pending" or reauth_required(operation, documents))
            and operation.token_enc is None
            and operation.auth_uuid
            and operation.auth_challenge
            else None
        ),
        documents=[
            WithdrawalDocumentBlob(
                document_id=doc.id,
                payload_base64=base64.b64encode(doc.exact_payload).decode(),
                payload_sha256=doc.payload_sha256,
                thumbprint=doc.certificate_thumbprint,
            )
            for doc in documents
            if runtime.enabled
            and operation.state == "documents_pending_signature"
            and doc.state == "pending_signature"
            and doc.signature is None
        ],
        items=[
            OperationItem(
                row_id=item.marking_id,
                cis=item.cis,
                wb_order_id=str(orders.get(item.order_id, "")),
                status=(
                    "withdrawn"
                    if item.state == "succeeded"
                    else "error"
                    if item.state == "failed"
                    else "not_withdrawn"
                ),
                error=item.error if item.state == "failed" else None,
            )
            for item in items
        ],
    )


@router.get("", response_model=WithdrawalPage)
async def list_withdrawals(
    session: Db,
    scope: Scope,
    date_from: date | None = None,
    date_to: date | None = None,
    search: Annotated[str | None, Query(max_length=256)] = None,
    product_id: uuid.UUID | None = None,
    only_not_withdrawn: bool = False,
    limit: Literal[50, 100, 250] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WithdrawalPage:
    try:
        rows, total = await registry(
            session,
            scope,
            date_from=date_from,
            date_to=date_to,
            search=search,
            product_id=product_id,
            only_not_withdrawn=only_not_withdrawn,
            limit=limit,
            offset=offset,
        )
    except WithdrawalError as exc:
        raise HTTPException(exc.status_code, exc.code) from None
    return WithdrawalPage(rows=[WithdrawalRow.model_validate(row) for row in rows], total=total)


@router.post("/operations", response_model=OperationOut)
async def start_withdrawal(
    payload: CreateWithdrawal, session: Db, scope: Scope, runtime: Runtime
) -> OperationOut:
    try:
        operation = await create_operation(
            session,
            scope,
            row_ids=payload.row_ids,
            client_request_id=payload.client_request_id,
            environment=runtime.config.environment,
        )
        await session.commit()
        operation = await prepare_challenge(
            session,
            scope,
            operation.id,
            CertificateSelection(**payload.certificate.model_dump())
            if payload.certificate
            else None,
            runtime,
        )
    except WithdrawalError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, exc.code) from None
    except IntegrityError:
        await session.rollback()
        # Never include SQL parameters, CIS or payload in an exception/log.
        raise HTTPException(409, "withdrawal_selection_conflict") from None
    return await _output(session, scope, operation, runtime)


@router.get("/operations/{operation_id}", response_model=OperationOut)
async def read_withdrawal(
    operation_id: uuid.UUID, session: Db, scope: Scope, runtime: Runtime
) -> OperationOut:
    try:
        operation = await get_operation(session, scope, operation_id)
    except WithdrawalError as exc:
        raise HTTPException(exc.status_code, exc.code) from None
    return await _output(session, scope, operation, runtime)


@router.post("/operations/{operation_id}/retry", response_model=OperationOut)
async def retry_withdrawal(
    operation_id: uuid.UUID,
    payload: RetryWithdrawal,
    session: Db,
    scope: Scope,
    runtime: Runtime,
) -> OperationOut:
    try:
        operation = await retry_operation(
            session,
            scope,
            operation_id,
            expected_attempt=payload.expected_attempt,
        )
        await session.commit()
        operation = await prepare_challenge(
            session,
            scope,
            operation.id,
            CertificateSelection(**payload.certificate.model_dump())
            if payload.certificate
            else None,
            runtime,
        )
    except WithdrawalError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, exc.code) from None
    return await _output(session, scope, operation, runtime)


@router.post("/operations/{operation_id}/reauth-challenge", response_model=OperationOut)
async def reauth_challenge(
    operation_id: uuid.UUID, payload: ReauthWithdrawal, session: Db, scope: Scope, runtime: Runtime
) -> OperationOut:
    try:
        operation = await prepare_reauth(
            session,
            scope,
            operation_id,
            CertificateSelection(**payload.certificate.model_dump()),
            runtime,
        )
    except WithdrawalError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, {"code": exc.code}) from None
    return await _output(session, scope, operation, runtime)


@router.post("/operations/{operation_id}/auth-signature", response_model=OperationOut)
async def auth_signature(
    operation_id: uuid.UUID,
    payload: AuthSignature,
    session: Db,
    scope: Scope,
    runtime: Runtime,
) -> OperationOut:
    try:
        operation = await authenticate_and_build(
            session,
            scope,
            operation_id,
            thumbprint=payload.thumbprint,
            challenge_uuid=payload.challenge_uuid,
            expected_attempt=payload.expected_attempt,
            signature=payload.signature.get_secret_value(),
            runtime=runtime,
        )
    except WithdrawalError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, {"code": exc.code}) from None
    return await _output(session, scope, operation, runtime)


@router.post("/operations/{operation_id}/document-signatures", response_model=OperationOut)
async def document_signatures(
    operation_id: uuid.UUID,
    payload: DocumentSignatures,
    session: Db,
    scope: Scope,
    runtime: Runtime,
) -> OperationOut:
    try:
        operation = await accept_document_signatures(
            session,
            scope,
            operation_id,
            [
                SignedWithdrawalDocument(
                    value.document_id,
                    value.payload_sha256,
                    value.thumbprint,
                    value.signature.get_secret_value(),
                )
                for value in payload.documents
            ],
            runtime,
        )
    except WithdrawalError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, {"code": exc.code}) from None
    return await _output(session, scope, operation, runtime)


@router.get("/products")
async def withdrawal_products(
    session: Db,
    scope: Scope,
    search: Annotated[str | None, Query(max_length=256)] = None,
    limit: Annotated[int, Query(ge=1, le=250)] = 100,
) -> list[dict[str, object]]:
    eligible = eligible_rows(scope).with_only_columns(FbsOrder.product_id)
    statement = select(Product).where(
        Product.id.in_(eligible),
        Product.tenant_id == scope.tenant_id,
        Product.seller_id == scope.seller_id,
    )
    if search:
        pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        statement = statement.where(
            or_(
                Product.name.ilike(pattern, escape="\\"),
                Product.sku_code.ilike(pattern, escape="\\"),
            )
        )
    return [
        {"id": product.id, "sku": product.sku_code, "name": product.name}
        for product in await session.scalars(
            statement.order_by(Product.name, Product.id).limit(limit)
        )
    ]
