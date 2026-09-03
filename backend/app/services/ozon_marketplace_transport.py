"""Живой HTTP-транспорт к Ozon Seller API за общей границей провайдера.

До этого модуля единственным настоящим запросом к Ozon во всём бэкенде была
проверка пары Client-Id/Api-Key (``ozon_client.py``); все десять мест, где
создаётся ``OzonMarketplaceProvider``, сидели на ``FakeMarketplaceTransport``.
Здесь появляется вторая, боевая реализация того же протокола.

Три решения, которые стоит объяснить, а не выводить из кода:

* **Бинарные ответы приводятся к тому же виду, что и JSON.** У трёх методов
  печати Ozon в спецификации объявлен бинарный тип (``application/pdf``,
  ``image/png``), но приложен пример с полями ``file_name``/``file_content``/
  ``content_type``. Спецификация сама себе противоречит, а живого отправления,
  на котором это можно разрешить, в кабинете нет. Поэтому транспорт принимает
  оба варианта и отдаёт наверх один: словарь с base64 в ``file_content``. Кто
  бы из двух ни оказался прав, разбор выше по стеку не меняется.
* **Публикация остатков запрещена.** Это решение из ТЗ
  (``tasks/ozon-integration-20260825/FBS-PROCESS.md``, раздел 9): «Публикация
  остатков FBS запрещена в любом случае». Метода публикации нет ни в нашей
  копии спецификации, ни в коде, и витрину покупателя мы вслепую не трогаем.
* **Мутации не повторяются.** Идемпотентных ключей Ozon не документирует ни
  для одной мутации, поэтому повтор — забота вызывающего кода, который знает
  семантику операции. Транспорт делает ровно один запрос.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.settings import settings as app_settings
from app.services.marketplace_provider import MarketplaceProviderError

# Ozon отдаёт максимум сто отправлений за страницу (ограничение поля `limit`
# в схеме posting.v4.PostingFbsUnfulfilledListRequest).
UNFULFILLED_PAGE_LIMIT = 100
# Потолок обхода: сто страниц по сто — десять тысяч отправлений за один проход.
# Дальше это уже не «опрос», а выгрузка, и она должна быть отдельной задачей.
MAX_UNFULFILLED_PAGES = 100
# Окно выборки несобранных отправлений по времени сборки. Фильтр `cutoff`
# обязателен: без него Ozon отвечает пустым списком.
CUTOFF_WINDOW_PAST_DAYS = 30
CUTOFF_WINDOW_FUTURE_DAYS = 30

UNFULFILLED_LIST_PATH = "/v4/posting/fbs/unfulfilled/list"
POSTING_GET_PATH = "/v3/posting/fbs/get"
ACT_BARCODE_PATH = "/v2/posting/fbs/act/get-barcode"

_JSON_MEDIA_TYPES = frozenset({"application/json", "text/json", "application/problem+json"})


def _error_payload(response: httpx.Response) -> dict[str, object]:
    """Keep Ozon's own ``code``/``message`` so callers can tell 403/7 from 403/anything."""
    try:
        parsed = response.json()
    except (json.JSONDecodeError, ValueError):
        return {"body": response.text[:500]}
    if isinstance(parsed, dict):
        return dict(parsed)
    return {"body": parsed}


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


def _media_type(response: httpx.Response) -> str:
    return (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()


def _binary_envelope(response: httpx.Response) -> dict[str, object]:
    """Present a raw PDF/PNG body exactly like Ozon's own file envelope."""
    disposition = response.headers.get("Content-Disposition") or ""
    file_name = ""
    for part in disposition.split(";"):
        cleaned = part.strip()
        if cleaned.lower().startswith("filename="):
            file_name = cleaned.split("=", 1)[1].strip().strip('"')
    return {
        "file_name": file_name,
        "file_content": base64.b64encode(response.content).decode("ascii"),
        "content_type": _media_type(response) or "application/octet-stream",
    }


class HttpxOzonMarketplaceTransport:
    """The single live adapter; one instance may serve many sellers of one tenant."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (base_url or app_settings.ozon_seller_api_base).rstrip("/")
        self._timeout = timeout_seconds or app_settings.ozon_api_timeout_sec
        self._client = client

    async def _request(
        self,
        *,
        client_id: str,
        api_key: str,
        path: str,
        payload: Mapping[str, object],
    ) -> httpx.Response:
        headers = {
            "Client-Id": client_id,
            "Api-Key": api_key,
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}{path}"
        try:
            if self._client is not None:
                return await self._client.post(
                    url,
                    headers=headers,
                    json=dict(payload),
                    timeout=self._timeout,
                )
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                return await client.post(url, headers=headers, json=dict(payload))
        except (httpx.HTTPError, TimeoutError, OSError) as exc:
            raise MarketplaceProviderError(
                "ozon",
                None,
                {"path": path},
                code="transport_error",
            ) from exc

    async def call(
        self,
        *,
        client_id: str,
        api_key: str,
        path: str,
        payload: Mapping[str, object],
    ) -> object:
        response = await self._request(
            client_id=client_id,
            api_key=api_key,
            path=path,
            payload=payload,
        )
        if response.status_code >= 400:
            error_payload = _error_payload(response)
            if response.status_code == 429:
                retry_after = _retry_after_seconds(response)
                if retry_after is not None:
                    error_payload["retry_after_seconds"] = retry_after
            raise MarketplaceProviderError("ozon", response.status_code, error_payload)
        if not response.content:
            return {}
        if _media_type(response) in _JSON_MEDIA_TYPES:
            try:
                return response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise MarketplaceProviderError(
                    "ozon",
                    response.status_code,
                    {"path": path},
                    code="ozon_invalid_json",
                ) from exc
        return _binary_envelope(response)

    async def fetch_orders(self, *, client_id: str, api_key: str) -> list[dict[str, Any]]:
        """Walk every unfulfilled posting page; the caller upserts them as they are."""
        now = datetime.now(tz=UTC)
        request_filter: dict[str, object] = {
            "cutoff_from": (now - timedelta(days=CUTOFF_WINDOW_PAST_DAYS)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "cutoff_to": (now + timedelta(days=CUTOFF_WINDOW_FUTURE_DAYS)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }
        rows: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(MAX_UNFULFILLED_PAGES):
            payload: dict[str, object] = {
                "filter": request_filter,
                "limit": UNFULFILLED_PAGE_LIMIT,
                # Штрихкоды и финансовые данные Ozon добавляет в ответ только
                # по явной просьбе: без этого нет ни штрихкода отправления,
                # ни цены.
                "with": {"barcodes": True, "financial_data": True},
            }
            if cursor:
                payload["cursor"] = cursor
            raw = await self.call(
                client_id=client_id,
                api_key=api_key,
                path=UNFULFILLED_LIST_PATH,
                payload=payload,
            )
            if not isinstance(raw, dict):
                break
            postings = raw.get("postings")
            if isinstance(postings, list):
                rows.extend(item for item in postings if isinstance(item, dict))
            next_cursor = raw.get("cursor")
            cursor = next_cursor if isinstance(next_cursor, str) else ""
            if not raw.get("has_next") or not cursor:
                break
        return rows

    async def fetch_statuses(
        self,
        *,
        client_id: str,
        api_key: str,
        order_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        """Read each posting back by number: only this method carries the substatus."""
        rows: list[dict[str, Any]] = []
        for posting_number in order_ids:
            if not posting_number:
                continue
            try:
                raw = await self.call(
                    client_id=client_id,
                    api_key=api_key,
                    path=POSTING_GET_PATH,
                    payload={"posting_number": posting_number, "with": {}},
                )
            except MarketplaceProviderError as error:
                # Отправление могло исчезнуть из кабинета; остальные читаем.
                if error.status_code == 404:
                    continue
                raise
            if isinstance(raw, dict) and isinstance(raw.get("result"), dict):
                rows.append(raw["result"])
        return rows

    async def fetch_order_labels(
        self,
        *,
        client_id: str,
        api_key: str,
        posting_numbers: Sequence[str],
    ) -> list[dict[str, Any]]:
        _ = client_id, api_key, posting_numbers
        raise MarketplaceProviderError(
            "ozon",
            None,
            {},
            code="ozon_label_pdf_unsupported",
        )

    async def publish_stocks(
        self,
        *,
        client_id: str,
        api_key: str,
        stocks: Sequence[Mapping[str, object]],
    ) -> None:
        _ = client_id, api_key, stocks
        raise MarketplaceProviderError(
            "ozon",
            None,
            {},
            code="ozon_stock_publish_disabled",
        )

    async def dispatch_unload(
        self,
        *,
        client_id: str,
        api_key: str,
        document_id: str,
    ) -> None:
        _ = client_id, api_key, document_id
        raise MarketplaceProviderError(
            "ozon",
            None,
            {},
            code="ozon_unload_dispatch_unsupported",
        )

    async def create_supply(
        self,
        *,
        client_id: str,
        api_key: str,
        name: str,
        posting_numbers: Sequence[str],
    ) -> dict[str, Any]:
        _ = client_id, api_key, name, posting_numbers
        raise MarketplaceProviderError(
            "ozon",
            None,
            {},
            code="ozon_supply_created_locally",
        )

    async def deliver_supply(
        self,
        *,
        client_id: str,
        api_key: str,
        supply_id: str,
    ) -> None:
        _ = client_id, api_key, supply_id
        raise MarketplaceProviderError(
            "ozon",
            None,
            {},
            code="ozon_supply_created_locally",
        )

    async def fetch_supply_qr(
        self,
        *,
        client_id: str,
        api_key: str,
        supply_id: str,
    ) -> bytes:
        """Штрихкод перевозки — ближайший аналог QR поставки WB, и он PNG."""
        if not supply_id.isdigit():
            raise MarketplaceProviderError(
                "ozon",
                None,
                {"supply_id": supply_id},
                code="ozon_carriage_id_invalid",
            )
        raw = await self.call(
            client_id=client_id,
            api_key=api_key,
            path=ACT_BARCODE_PATH,
            payload={"id": int(supply_id)},
        )
        if not isinstance(raw, dict):
            return b""
        content = raw.get("file_content")
        if not isinstance(content, str) or not content:
            return b""
        try:
            return base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise MarketplaceProviderError(
                "ozon",
                None,
                {},
                code="ozon_invalid_file",
            ) from exc
