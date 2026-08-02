"""Authorization middleware: raw Authorization token -> seller_key."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from wb_emulator.settings import Settings, get_settings

API_V3_PREFIX = "/api/v3"


def resolve_seller_key(authorization_header: str | None, settings: Settings | None = None) -> str | None:
    """Map raw Authorization header value to seller_key (no Bearer prefix)."""
    cfg = settings or get_settings()
    token = (authorization_header or "").strip()
    if not token:
        return None
    return cfg.seller_key_for_token(token)


class AuthMiddleware(BaseHTTPMiddleware):
    """Reject unknown tokens on /api/v3/* with HTTP 401."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(API_V3_PREFIX):
            return await call_next(request)

        seller_key = resolve_seller_key(request.headers.get("Authorization"))
        if seller_key is None:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        request.state.seller_key = seller_key
        return await call_next(request)
