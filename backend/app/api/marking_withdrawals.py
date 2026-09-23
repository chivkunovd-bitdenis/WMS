"""Same-origin seller boundary. No browser profile means no auth/sign/create."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import assert_seller_permission, get_current_user, get_effective_seller_id
from app.api.withdrawal_schemas import (
    AuthSignature,
    CreateWithdrawal,
    DocumentSignatures,
    OperationItem,
    OperationOut,
    RetryWithdrawal,
    WithdrawalPage,
    WithdrawalRow,
)
from app.core.roles import FULFILLMENT_SELLER
from app.db.session import get_db
from app.db.withdrawal_repository import (
    WithdrawalError,
    WithdrawalScope,
    current_items,
    get_operation,
    registry,
)
from app.models.marking_withdrawal import WithdrawalOperation
from app.models.user import User
from app.services.seller_staff_permissions_service import PERM_HONEST_SIGN
from app.services.withdrawal_service import INTEGRATION_GATE, create_operation, retry_operation

router = APIRouter(prefix="/operations/marking-codes/self/withdrawals", tags=["operations"])
Db = Annotated[AsyncSession, Depends(get_db)]


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
    session: AsyncSession, scope: WithdrawalScope, operation: WithdrawalOperation
) -> OperationOut:
    return OperationOut(
        operation_id=operation.id,
        state=operation.state,
        attempt=operation.attempt,
        integration_gate="B3_AUTH_PROFILE_UNCONFIRMED",
        items=[
            OperationItem(
                row_id=item.marking_id,
                cis=item.cis,
                status=(
                    "withdrawn"
                    if item.state == "succeeded"
                    else "error"
                    if item.state == "failed"
                    else "not_withdrawn"
                ),
                error=item.error if item.state == "failed" else None,
            )
            for item in await current_items(session, scope, operation.id)
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
async def start_withdrawal(payload: CreateWithdrawal, session: Db, scope: Scope) -> OperationOut:
    try:
        operation = await create_operation(
            session,
            scope,
            row_ids=payload.row_ids,
            client_request_id=payload.client_request_id,
        )
        await session.commit()
    except WithdrawalError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, exc.code) from None
    except IntegrityError:
        await session.rollback()
        # Never include SQL parameters, CIS or payload in an exception/log.
        raise HTTPException(409, "withdrawal_selection_conflict") from None
    return await _output(session, scope, operation)


@router.get("/operations/{operation_id}", response_model=OperationOut)
async def read_withdrawal(operation_id: uuid.UUID, session: Db, scope: Scope) -> OperationOut:
    try:
        operation = await get_operation(session, scope, operation_id)
    except WithdrawalError as exc:
        raise HTTPException(exc.status_code, exc.code) from None
    return await _output(session, scope, operation)


@router.post("/operations/{operation_id}/retry", response_model=OperationOut)
async def retry_withdrawal(
    operation_id: uuid.UUID,
    payload: RetryWithdrawal,
    session: Db,
    scope: Scope,
) -> OperationOut:
    try:
        operation = await retry_operation(
            session,
            scope,
            operation_id,
            expected_attempt=payload.expected_attempt,
        )
        await session.commit()
    except WithdrawalError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, exc.code) from None
    return await _output(session, scope, operation)


async def _closed_boundary(
    session: AsyncSession, scope: WithdrawalScope, operation_id: uuid.UUID
) -> None:
    try:
        await get_operation(session, scope, operation_id)
    except WithdrawalError as exc:
        raise HTTPException(exc.status_code, exc.code) from None
    raise HTTPException(409, {"code": INTEGRATION_GATE})


@router.post("/operations/{operation_id}/auth-signature")
async def auth_signature(
    operation_id: uuid.UUID,
    payload: AuthSignature,
    session: Db,
    scope: Scope,
) -> None:
    await _closed_boundary(session, scope, operation_id)


@router.post("/operations/{operation_id}/document-signatures")
async def document_signatures(
    operation_id: uuid.UUID,
    payload: DocumentSignatures,
    session: Db,
    scope: Scope,
) -> None:
    await _closed_boundary(session, scope, operation_id)
