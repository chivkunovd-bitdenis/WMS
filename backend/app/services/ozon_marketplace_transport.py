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
* **Публикация остатков включена и идёт методом ``/v2/products/stocks``.**
  Запрет из ТЗ от 25.08.2026 («Публикация остатков FBS запрещена в любом
  случае») был решением того дня, когда кабинет отвечал 403 и проверить метод
  было нечем. 03.09.2026 кабинет открылся, и владелец снял запрет: без
  публикации остатков Ozon не знает, сколько у нас товара, и продавать по FBS
  нельзя вообще. Метод живой: боевой ключ на пустом списке отвечает
  ``400 Request validation error: invalid ProductsStocksRequest.Stocks: value
  must contain between 1 and 100 items, inclusive``, а кандидат
  ``/v1/product/import/stocks`` мёртв (``404 page not found``).
* **Мутации не повторяются.** Идемпотентных ключей Ozon не документирует ни
  для одной мутации, поэтому повтор — забота вызывающего кода, который знает
  семантику операции. Транспорт делает ровно один запрос.
* **Здесь нет `create_supply`, `deliver_supply` и `dispatch_unload`.** Они были,
  вечно отвечали отказом — и ни разу никем не вызывались: ни одного места в коде,
  которое бы их звало, не существовало. При этом со стороны они читались как
  «эти куски Ozon не сделаны», хотя передача поставки давно живёт целиком в
  `ozon_fbs_process_service.handoff_supply` (сборка отправлений, создание
  перевозки, её состав, подтверждение, штрихкод акта и лист отгрузки), а
  «передачи отгрузки» у Ozon нет как операции вовсе. Мёртвый метод, который врёт
  про состояние модуля, хуже отсутствующего.
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

# Справочник складов продавца: по нему оператор выбирает склад Ozon вместо того,
# чтобы вводить его номер руками. Двести — потолок поля `limit` в схеме
# `v2WarehouseListV2Request`, и само поле обязательное: без него метод не
# отвечает. Десять страниц по двести — это две тысячи складов у одного продавца,
# заведомо больше, чем бывает.
WAREHOUSE_PAGE_LIMIT = 200
MAX_WAREHOUSE_PAGES = 10

UNFULFILLED_LIST_PATH = "/v4/posting/fbs/unfulfilled/list"
WAREHOUSE_LIST_PATH = "/v2/warehouse/list"
POSTING_GET_PATH = "/v3/posting/fbs/get"
ACT_BARCODE_PATH = "/v2/posting/fbs/act/get-barcode"
PRODUCTS_STOCKS_PATH = "/v2/products/stocks"
PACKAGE_LABEL_PATH = "/v2/posting/fbs/package-label"
PDF_MEDIA_TYPE = "application/pdf"

# «За один запрос можно изменить наличие для 100 пар товар-склад» — описание
# метода в официальной спецификации Ozon (swagger.json, ProductAPI_ProductsStocksV2).
# Живой кабинет подтверждает границу сам: на пустом списке отвечает «value must
# contain between 1 and 100 items, inclusive». В JSON-схеме `maxItems` не
# объявлен, поэтому пакетируем здесь, а не надеемся на валидатор.
STOCK_BATCH_SIZE = 100

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


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _stock_item(stock: Mapping[str, object]) -> dict[str, object]:
    """Один элемент `stocks` в форме, которую ждёт `/v2/products/stocks`.

    Три решения, каждое — из официальной спецификации Ozon, а не из удобства:

    * **Идентификатор ровно один.** Описание метода: «Если запрос содержит оба
      параметра — `offer_id` и `product_id`, изменения применятся к товару с
      `offer_id`. Для избежания неоднозначности используйте только один из
      параметров». Отправлять оба — это молча отдать решение Ozon; берём
      `product_id`, потому что это его собственный идентификатор карточки, и
      только при его отсутствии падаем на артикул продавца.
    * **`quant_size` не отправляется.** Он стоит в `required` схемы, но в
      `properties` его нет, а раздел «Обновления» спецификации объясняет почему:
      16.06.2025 параметр помечен устаревшим, 26.06.2025 «Удалили параметры
      `stocks.quant_size` из запроса и `result.quant_size` из ответа метода».
      Запись в `required` — мусор, оставшийся после удаления.
    * **`sku` не участвует.** В схеме метода такого поля нет вовсе: у Ozon `sku`
      и `product_id` — разные числа (живой `/v4/product/info/stocks` отдаёт по
      одной карточке `product_id: 6204279711` и `sku: 5680762790`).
    """
    warehouse_id = _positive_int(stock.get("warehouse_id"))
    if warehouse_id is None:
        raise MarketplaceProviderError(
            "ozon",
            None,
            {"reason": "warehouse_id"},
            code="ozon_stock_item_invalid",
        )
    raw_stock = stock.get("stock")
    if isinstance(raw_stock, bool) or not isinstance(raw_stock, int) or raw_stock < 0:
        raise MarketplaceProviderError(
            "ozon",
            None,
            {"reason": "stock"},
            code="ozon_stock_item_invalid",
        )
    item: dict[str, object] = {"warehouse_id": warehouse_id, "stock": raw_stock}
    product_id = _positive_int(stock.get("product_id"))
    offer_id = stock.get("offer_id")
    if product_id is not None:
        item["product_id"] = product_id
    elif isinstance(offer_id, str) and offer_id.strip():
        item["offer_id"] = offer_id.strip()
    else:
        raise MarketplaceProviderError(
            "ozon",
            None,
            {"reason": "identifier"},
            code="ozon_stock_item_invalid",
        )
    return item


_StockKey = tuple[str, str, int]


def _stock_item_key(item: Mapping[str, object]) -> _StockKey:
    """Чем отправленная строка отличается от остальных в том же пакете.

    Идентификатор в отправленной строке ровно один — так её собирает
    `_stock_item`, — поэтому и ключ строится по нему: пара «идентификатор плюс
    склад».
    """
    warehouse_id = int(str(item["warehouse_id"]))
    if "product_id" in item:
        return ("product_id", str(item["product_id"]), warehouse_id)
    return ("offer_id", str(item["offer_id"]), warehouse_id)


def _stock_row_keys(row: Mapping[str, object], *, batch_warehouses: set[int]) -> set[_StockKey]:
    """Ключи, под которыми строка ответа может опознать отправленную.

    Ozon кладёт в ответ оба идентификатора и склад (`result[].offer_id`,
    `result[].product_id`, `result[].warehouse_id` — поля из его собственной
    схемы `productv2ProductsStocksResponseResult`), но в живых ответах часть из
    них бывает пустой. Поэтому строка опознаётся по любому из идентификаторов,
    а отсутствующий склад берётся из пакета — но только если склад в пакете
    один и подставлять нечего кроме него. Иначе строка остаётся неопознанной, и
    отправленные строки честно считаются неподтверждёнными.
    """
    row_warehouse = _positive_int(row.get("warehouse_id"))
    if row_warehouse is not None:
        warehouses = {row_warehouse}
    elif len(batch_warehouses) == 1:
        warehouses = set(batch_warehouses)
    else:
        return set()
    keys: set[_StockKey] = set()
    product_id = _positive_int(row.get("product_id"))
    offer_id = row.get("offer_id")
    for warehouse_id in warehouses:
        if product_id is not None:
            keys.add(("product_id", str(product_id), warehouse_id))
        if isinstance(offer_id, str) and offer_id.strip():
            keys.add(("offer_id", offer_id.strip(), warehouse_id))
    return keys


def _row_error_texts(row: Mapping[str, object]) -> tuple[list[str], list[str]]:
    errors = row.get("errors")
    entries = [
        error
        for error in (errors if isinstance(errors, list) else [])
        if isinstance(error, dict)
    ]
    codes = [str(error.get("code") or "") for error in entries]
    messages = [str(error.get("message") or "") for error in entries]
    return [code for code in codes if code], [message for message in messages if message]


def _reconcile_stock_rows(
    batch: Sequence[Mapping[str, object]],
    rows: Sequence[object],
) -> tuple[int, list[dict[str, object]]]:
    """Сверить ответ Ozon с отправленным пакетом построчно.

    Ozon не обязан отвечать строкой на каждую отправленную пару товар-склад, и
    молчание — это не согласие. Особенно опасно молчание по нулю: пропущенный
    ноль оставляет в кабинете прежний положительный остаток, то есть товар
    продолжает продаваться, когда его нет. Поэтому подтверждённой считается
    только та строка, на которую Ozon ответил `updated: true` и которую мы
    смогли сопоставить с отправленной по идентификатору.

    Возвращает число подтверждённых строк и список неподтверждённых: и тех, что
    Ozon отклонил, и тех, про которые он промолчал.
    """
    batch_warehouses = {int(str(item["warehouse_id"])) for item in batch}
    confirmed: set[_StockKey] = set()
    rejected: dict[_StockKey, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        keys = _stock_row_keys(row, batch_warehouses=batch_warehouses)
        if not keys:
            continue
        if row.get("updated") is True:
            confirmed |= keys
            continue
        codes, messages = _row_error_texts(row)
        for key in keys:
            rejected[key] = {
                "offer_id": row.get("offer_id"),
                "product_id": row.get("product_id"),
                "warehouse_id": row.get("warehouse_id"),
                "codes": codes,
                "messages": messages,
            }
    failures: list[dict[str, object]] = []
    confirmed_count = 0
    for item in batch:
        key = _stock_item_key(item)
        if key in confirmed:
            confirmed_count += 1
            continue
        failure = rejected.get(key)
        if failure is not None:
            failures.append(failure)
            continue
        failures.append(
            {
                "offer_id": item.get("offer_id"),
                "product_id": item.get("product_id"),
                "warehouse_id": item.get("warehouse_id"),
                "codes": ["OZON_ROW_MISSING"],
                "messages": ["Ozon не ответил по этой паре товар-склад."],
            }
        )
    return confirmed_count, failures


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

    async def fetch_warehouses(self, *, client_id: str, api_key: str) -> list[dict[str, Any]]:
        """Справочник складов продавца — тот самый список, которого не было вовсе.

        Номер склада Ozon оператор до сих пор вводил руками, и опечатка
        обнаруживалась только по тому, что у продавца пропали продажи. Список
        приезжает по запросу и нигде не хранится: складов у продавца единицы, а
        второй экземпляр этого списка у нас немедленно разойдётся с кабинетом.

        Тем же ответом приходит `has_entrusted_acceptance` — включена ли у
        склада доверительная приёмка. Раньше за этим собирались лезть в кабинет
        руками (WMS-356); теперь это просто поле строки.
        """
        rows: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(MAX_WAREHOUSE_PAGES):
            payload: dict[str, object] = {"limit": WAREHOUSE_PAGE_LIMIT}
            if cursor:
                payload["cursor"] = cursor
            raw = await self.call(
                client_id=client_id,
                api_key=api_key,
                path=WAREHOUSE_LIST_PATH,
                payload=payload,
            )
            if not isinstance(raw, dict):
                break
            warehouses = raw.get("warehouses")
            if isinstance(warehouses, list):
                rows.extend(item for item in warehouses if isinstance(item, dict))
            next_cursor = raw.get("cursor")
            cursor = next_cursor if isinstance(next_cursor, str) else ""
            if not raw.get("has_next") or not cursor:
                break
        return rows

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
        """Одна этикетка — один запрос, потому что этого требует сам Ozon.

        Спецификация метода ``/v2/posting/fbs/package-label`` разрешает до
        двадцати номеров за раз, но там же предупреждает: «Если хотя бы для
        одного отправления возникнет ошибка, этикетки не будут подготовлены для
        всех отправлений в запросе». В поставке из двадцати заказов одно
        неготовое отправление оставило бы оператора без всех девятнадцати
        остальных, поэтому спрашиваем по одному.

        Отказ по конкретному отправлению не рушит остальные: он возвращается
        строкой с ``error_code``. Строка с ошибкой — это не файл и не тишина, и
        выше по стеку её видно как ошибку именно этого заказа.
        """
        rows: list[dict[str, Any]] = []
        for posting_number in posting_numbers:
            if not posting_number:
                continue
            try:
                raw = await self.call(
                    client_id=client_id,
                    api_key=api_key,
                    path=PACKAGE_LABEL_PATH,
                    payload={"posting_number": [posting_number]},
                )
            except MarketplaceProviderError as error:
                if error.is_account_blocked or error.status_code is None:
                    # Заблокированный кабинет и обрыв связи — это не свойство
                    # одного отправления, а общий отказ: следующие девятнадцать
                    # запросов дадут ровно то же самое.
                    raise
                rows.append(
                    {
                        "posting_number": posting_number,
                        "error_code": f"ozon_label_{error.status_code}",
                        "error_message": str(error.payload.get("message") or ""),
                    }
                )
                continue
            content = raw.get("file_content") if isinstance(raw, dict) else None
            if not isinstance(content, str) or not content:
                rows.append(
                    {
                        "posting_number": posting_number,
                        "error_code": "ozon_label_empty",
                        "error_message": "",
                    }
                )
                continue
            declared = raw.get("content_type") if isinstance(raw, dict) else None
            media_type = declared if isinstance(declared, str) and declared else PDF_MEDIA_TYPE
            rows.append(
                {
                    "posting_number": posting_number,
                    "file": content,
                    "content_type": media_type,
                }
            )
        return rows

    async def publish_stocks(
        self,
        *,
        client_id: str,
        api_key: str,
        stocks: Sequence[Mapping[str, object]],
    ) -> int:
        """Опубликовать остатки парами товар-склад, порциями по сотне.

        Возвращает число строк, которые Ozon подтвердил построчно. Любая
        неподтверждённая строка — отказ всей публикации: подтверждённое до неё
        число уезжает в `payload["confirmed"]`, чтобы вызывающий не приписывал
        себе чужого успеха, но и не терял настоящий.
        """
        items = [_stock_item(stock) for stock in stocks]
        if not items:
            return 0
        confirmed_total = 0
        for start in range(0, len(items), STOCK_BATCH_SIZE):
            batch = items[start : start + STOCK_BATCH_SIZE]
            raw = await self.call(
                client_id=client_id,
                api_key=api_key,
                path=PRODUCTS_STOCKS_PATH,
                payload={"stocks": batch},
            )
            rows = raw.get("result") if isinstance(raw, dict) else None
            if not isinstance(rows, list) or not rows:
                # 200 без единой строки результата — это не подтверждение. Считать
                # его успехом значит покрасить привязку в «опубликовано», когда
                # Ozon про наш остаток ничего не сказал.
                raise MarketplaceProviderError(
                    "ozon",
                    None,
                    {"sent": len(batch), "confirmed": confirmed_total},
                    code="ozon_stock_unconfirmed",
                )
            confirmed, failures = _reconcile_stock_rows(batch, rows)
            confirmed_total += confirmed
            if failures:
                raise MarketplaceProviderError(
                    "ozon",
                    None,
                    {
                        "failed": failures,
                        "sent": len(batch),
                        "confirmed": confirmed_total,
                    },
                    code="ozon_stock_rejected",
                )
        return confirmed_total

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
