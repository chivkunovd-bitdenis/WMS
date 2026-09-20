from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_current_user
from app.models.user import User
from app.services.client_error_service import MAX_BODY_BYTES, record_client_error

router = APIRouter(prefix="/client-errors", tags=["client-errors"])


@router.post("", status_code=204)
async def client_errors(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    try:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk[: MAX_BODY_BYTES - len(body)])
            if len(body) >= MAX_BODY_BYTES:
                break
        record_client_error(bytes(body), user)
    except Exception:
        pass
    return Response(status_code=204)
