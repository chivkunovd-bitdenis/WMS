"""Форма «?» (WMS-624) как источник: опрос бэка только на чтение (R4)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import WmsCfg

log = logging.getLogger(__name__)


class WmsError(Exception):
    pass


class WmsClient:
    def __init__(self, cfg: WmsCfg, http: httpx.Client) -> None:
        self.cfg = cfg
        self.http = http

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        try:
            response = self.http.get(
                f"{self.cfg.base_url.rstrip('/')}{path}",
                params=params,
                headers={"X-Support-Agent-Key": self.cfg.agent_key},
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise WmsError(f"transport_{type(exc).__name__}") from None
        if response.status_code != 200:
            raise WmsError(f"http_{response.status_code}")
        return response.json()

    def new_requests(self, cursor: dict[str, str] | None, limit: int = 50) -> list[dict[str, Any]]:
        params = {"limit": str(limit)}
        if cursor:
            params["after_created_at"] = cursor["created_at"]
            params["after_id"] = cursor["id"]
        result = self._get("/support-agent/developer-requests", params)
        assert isinstance(result, list)
        return result

    def request(self, request_id: str) -> dict[str, Any]:
        result = self._get(f"/support-agent/developer-requests/{request_id}")
        assert isinstance(result, dict)
        return result
