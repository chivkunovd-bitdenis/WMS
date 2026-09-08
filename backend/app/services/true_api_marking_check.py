"""Read-only receiving checks with an existing True API JWT (WMS-396).

Contract: https://docs.crpt.ru/gismt/True_API/ — cises/info and cises/check.
No token issuance, retail permission API, warehouse lifecycle or stock changes.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from app.services.marketplace_provider import MarketplaceBackoff

BASE_URL = "https://markirovka.crpt.ru/api/v3/true-api"
BATCH_SIZE = 1000
REQUEST_INTERVAL = 2.0
# Existing process-local mechanism; this does not coordinate separate workers.
_PACING = MarketplaceBackoff()


def unavailable(
    reason: str = "Честный знак не подтвердил статус. Повторите проверку.",
) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "outer_status": None,
        "checked_at": datetime.now(UTC).isoformat(),
        "provider": "true_api",
    }


def short_ki(full_code: str) -> str | None:
    """Project AI01+AI21 only; never guess a serial boundary or mutate full KM."""
    code, separator, _tail = full_code.partition("\x1d")
    if (
        not separator
        or not 19 <= len(code) <= 38
        or not code.startswith("01")
        or not code[2:16].isdigit()
        or code[16:18] != "21"
    ):
        return None
    return code


def parse_crypto(data: Any, codes: list[str]) -> dict[str, bool | None]:
    unknown: dict[str, bool | None] = dict.fromkeys(codes)
    if not isinstance(data, dict) or type(data.get("result")) is not bool:
        return unknown
    result = data["result"]
    if "quantity" in data:
        if type(data["quantity"]) is int and data["quantity"] == len(codes) and "codes" not in data:
            return dict.fromkeys(codes, result)
        return unknown
    invalid = data.get("codes")
    if result is not False or not isinstance(invalid, list) or not invalid:
        return unknown
    bad: set[str] = set()
    for value in invalid:
        if not isinstance(value, str):
            return unknown
        matches = [code for code in codes if value == code or value == short_ki(code)]
        # A shortened invalid code must identify exactly one submitted full KM.
        if len(matches) != 1 or matches[0] in bad:
            return unknown
        bad.add(matches[0])
    if len(bad) >= len(codes):
        return unknown  # The all-invalid shape requires quantity, per the contract.
    return {code: code not in bad for code in codes}


def parse_info(data: Any, requested: list[str]) -> dict[str, dict[str, Any]]:
    rows = data if isinstance(data, list) else [data]
    answers: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("cisInfo"), dict):
            continue
        info = row["cisInfo"]
        key = info.get("requestedCis")
        if key not in requested or not isinstance(key, str) or info.get("cis") != key:
            continue
        if key in answers:
            duplicates.add(key)
        answers[key] = row
    return {key: row for key, row in answers.items() if key not in duplicates}


def interpret(row: dict[str, Any] | None, verified: bool | None) -> dict[str, Any]:
    answer = unavailable()
    if row is None:
        return answer
    info = row["cisInfo"]
    outer = info.get("status")
    answer["outer_status"] = outer if isinstance(outer, str) else None
    error = row.get("errorCode")
    if error is not None:
        if str(error) == "404":
            answer.update(status="problem", reason="Код не найден в Честном знаке")
        elif str(error) == "401":
            answer["reason"] = (
                "Токен Честного знака недействителен или истёк. Проверьте интеграцию селлера."
            )
        return answer
    if row.get("errorMessage"):
        return answer
    if verified is False:
        answer.update(status="problem", reason="Криптоподпись кода не подтверждена")
    elif info.get("ogvs"):
        answer.update(status="problem", reason="Код заблокирован в Честном знаке")
    elif outer == "INTRODUCED" and verified is True:
        answer.update(status="introduced", reason="Код введён в оборот, криптоподпись подтверждена")
    elif outer in {"APPLIED", "EMITTED", "RETIRED", "WRITTEN_OFF", "DISAGGREGATED"}:
        answer.update(
            status="problem",
            reason={
                "APPLIED": "Код нанесён, но не введён в оборот",
                "EMITTED": "Код выпущен, но не введён в оборот",
                "RETIRED": "Код выведен из оборота",
                "WRITTEN_OFF": "Код списан",
                "DISAGGREGATED": "Код расформирован",
            }[outer],
        )
    return answer


async def _post(client: httpx.AsyncClient, path: str, token: str, body: Any) -> Any:
    # No await between the final remaining check and reservation in this event loop.
    while (remaining := _PACING.remaining_seconds("true_api")) > 0:
        await asyncio.sleep(remaining)
    _PACING.record_rate_limit("true_api", retry_after_seconds=REQUEST_INTERVAL)
    response = await client.post(
        BASE_URL + path,
        json=body,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    # /info documents 404 bodies with per-code requestedCis. Other failures are transport errors.
    if not (path == "/cises/info" and response.status_code == 404):
        response.raise_for_status()
    return response.json()


async def check_batch(
    client: httpx.AsyncClient,
    codes: list[str],
    token: str | None,
) -> dict[str, dict[str, Any]]:
    if not token:
        return {
            code: unavailable("У селлера не настроен токен Честного знака. Проверьте интеграцию.")
            for code in codes
        }
    if len(codes) > BATCH_SIZE:
        raise ValueError("True API batch exceeds 1000 codes")
    answers = {
        code: unavailable("Не удалось выделить КИ. Отсканируйте полный код с GS-разделителями.")
        for code in codes
    }
    valid = list(dict.fromkeys(code for code in codes if short_ki(code) is not None))
    if not valid:
        return answers
    short_codes = {code: value for code in valid if (value := short_ki(code)) is not None}
    requested = list(dict.fromkeys(short_codes.values()))
    try:
        rows = parse_info(await _post(client, "/cises/info", token, requested), requested)
        crypto = parse_crypto(await _post(client, "/cises/check", token, {"codes": valid}), valid)
    except (httpx.HTTPError, ValueError) as exc:
        reason = "Честный знак недоступен. Повторите проверку позже."
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code == 401:
                reason = (
                    "Токен Честного знака недействителен или истёк. Проверьте интеграцию селлера."
                )
            elif exc.response.status_code == 429:
                reason = "Честный знак ограничил частоту запросов. Повторите проверку позже."
        answers.update({code: unavailable(reason) for code in valid})
        return answers
    answers.update({code: interpret(rows.get(short_codes[code]), crypto[code]) for code in valid})
    return answers
