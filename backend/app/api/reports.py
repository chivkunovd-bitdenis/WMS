from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import assert_inventory_read_access, get_current_user, seller_line_product_scope
from app.db.session import get_db
from app.models.user import User
from app.services.reporting_service import build_overview

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/overview")
async def get_reports_overview(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    date_from: Annotated[datetime, Query()],
    date_to: Annotated[datetime, Query()],
) -> dict[str, object]:
    await assert_inventory_read_access(session, user)
    try:
        return await build_overview(
            session,
            user.tenant_id,
            date_from=date_from,
            date_to=date_to,
            seller_id=seller_scope,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
