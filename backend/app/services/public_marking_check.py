"""Read-only receiving checks through the token-free mobile API (WMS-396)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from app.services.marketplace_provider import MarketplaceBackoff

CHECK_URL = "https://mobile.api.crpt.ru/mobile/check"
REQUEST_INTERVAL = 2.0
# Existing process-local pacing; no new persistent queue or credentials.
_PACING = MarketplaceBackoff()


def unavailable(
    reason: str = "Честный знак не подтвердил статус. Повторите проверку.",
) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "outer_status": None,
        "checked_at": datetime.now(UTC).isoformat(),
        "provider": "mobile_check",
    }


def interpret_check(data: Any) -> dict[str, Any]:
    result = unavailable()
    result["raw_response"] = data
    if not isinstance(data, dict):
        return result
    outer = data.get("outerStatus")
    result["outer_status"] = outer if isinstance(outer, str) else None
    resolved = data.get("codeResolveData")
    if data.get("codeFounded") is False or data.get("status") == "not_found_dm":
        result.update(status="problem", reason="Код не найден в Честном знаке")
        return result
    if not isinstance(resolved, dict):
        return result
    # Reject truthy strings/numbers and malformed optional flags. Missing optional
    # flags do not replace the three explicit positive facts from the public API.
    if (
        type(data.get("checkResult")) is not bool
        or type(resolved.get("verified")) is not bool
        or ("codeFounded" in data and type(data["codeFounded"]) is not bool)
        or ("isBlocked" in resolved and type(resolved["isBlocked"]) is not bool)
    ):
        return result
    if resolved["verified"] is False:
        result.update(status="problem", reason="Криптоподпись кода не подтверждена")
    elif resolved.get("isBlocked") is True:
        result.update(status="problem", reason="Код заблокирован в Честном знаке")
    elif (
        outer == "INTRODUCED"
        and data["checkResult"] is True
        and data.get("status", "ok") == "ok"
        and data.get("warning", "ok") == "ok"
    ):
        result.update(status="introduced", reason="Код введён в оборот")
    elif isinstance(outer, str) and outer in {
        "APPLIED", "EMITTED", "RETIRED", "WRITTEN_OFF", "DISAGGREGATED"
    }:
        result.update(status="problem", reason={
            "APPLIED": "Код нанесён, но не введён в оборот",
            "EMITTED": "Код выпущен, но не введён в оборот",
            "RETIRED": "Код выведен из оборота",
            "WRITTEN_OFF": "Код списан",
            "DISAGGREGATED": "Код расформирован",
        }[outer])
    return result


async def check_code(client: httpx.AsyncClient, full_code: str) -> dict[str, Any]:
    while (remaining := _PACING.remaining_seconds("mobile_check")) > 0:
        await asyncio.sleep(remaining)
    _PACING.record_rate_limit("mobile_check", retry_after_seconds=REQUEST_INTERVAL)
    try:
        # Preserve the full scanned value, including GS; no token or short-KI projection.
        response = await client.post(CHECK_URL, json={"code": full_code})
    except httpx.HTTPError:
        return unavailable("Честный знак недоступен. Повторите проверку позже.")
    try:
        raw: Any = response.json()
    except ValueError:
        raw = response.text
    if not response.is_success:
        result = unavailable(
            "Честный знак ограничил частоту запросов. Повторите проверку позже."
            if response.status_code == 429
            else "Честный знак недоступен. Повторите проверку позже."
        )
    else:
        result = interpret_check(raw)
    result.update(raw_response=raw, http_status=response.status_code)
    return result
