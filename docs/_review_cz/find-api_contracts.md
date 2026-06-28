# Ревью API-контрактов (ЧЗ-модуль) — диапазон 4e82c6b..HEAD

## Резюме
Найдено 6 находок: 0 CRITICAL, 1 HIGH, 3 MEDIUM, 2 LOW. Самое важное:
(1) HIGH — N+1 в `/pending-marking`: запрос `count_available_for_product` в цикле по каждой строке + полное отсутствие пагинации, риск тяжёлого ответа;
(2) MEDIUM — `/pools/{id}/codes` отдаёт ВСЕ коды пула без limit/offset (выгрузка десятков тысяч строк).
В целом контракты типизированы хорошо: почти у всех эндпоинтов есть `response_model`, ошибки сервиса маппятся в 4xx (дефолт 422, не 500), 201/204 для create/delete шаблонов проставлены.

---

## [HIGH] N+1 запрос + отсутствие пагинации в ленте «pending-marking»
- **Где:** `backend/app/services/marking_code_service.py:2381` (`list_pending_marking_lines`), вызывается из `backend/app/api/marking_codes.py:1104` (`@router.get("/pending-marking")`)
- **Доказательство:**
```python
rows: list[PendingMarkingRow] = []
for line, task, product, loc in (await session.execute(stmt)).all():
    qty_need = qty_need_pack(line)
    printed = int(line.qty_marking_printed)
    if printed >= qty_need or qty_need < 1:
        continue
    available = await count_available_for_product(session, tenant_id, product.id)  # N+1
    rows.append(PendingMarkingRow(... marking_available_count=available ...))
return rows
```
А `count_available_for_product` сам по себе делает несколько запросов:
```python
async def count_available_for_product(session, tenant_id, product_id) -> int:
    product = await get_product(session, tenant_id, product_id)            # запрос 1
    pool_ids = await _pool_ids_for_product(session, tenant_id, product_id) # запрос 2
    ...
    res = await session.execute(stmt)                                      # запрос 3 (COUNT)
```
- **Проблема:** на каждую pending-строку (а их может быть много при большой очереди упаковки) делается 3 дополнительных round-trip в БД. Это классический N+1: при N строк → ~3N запросов. Плюс сам эндпоинт `/pending-marking` не имеет `limit/offset` — `list_pending_marking_lines` грузит все строки всех задач в статусах draft/in_progress по тенанту. Это и нагрузка на БД, и риск тяжёлого ответа (нарушение требования к ленте иметь пагинацию, см. DESIGN — ленты/очереди).
- **Фикс:**
  1. Заменить вызов в цикле на батч: собрать `product_id` всех строк и один раз посчитать доступные коды по продуктам (один `GROUP BY product_id` запрос), затем мапить в строки.
  2. Добавить `limit`/`offset` (`Query(ge=1, le=200)` / `Query(ge=0)`) в эндпоинт и прокинуть в сервис, возвращать `total` как в `/ledger`.

---

## [MEDIUM] `/pools/{pool_id}/codes` — нет пагинации (выгрузка всей таблицы кодов пула)
- **Где:** `backend/app/api/marking_codes.py:709` (`list_marking_pool_codes`), сервис `marking_code_service.py:1830` (`list_pool_codes`)
- **Доказательство:**
```python
@router.get("/pools/{pool_id}/codes", response_model=list[PoolCodeOut])
async def list_marking_pool_codes(... status: Annotated[str | None, Query()] = None):
    ...
    rows = await mc_svc.list_pool_codes(session, user.tenant_id, pool_id, status=status)
    return [PoolCodeOut(...) for r in rows]
```
```python
async def list_pool_codes(session, tenant_id, pool_id, *, status=None) -> list[PoolCodeRow]:
    ...
    stmt = (select(MarkingCode, MarkingCodeImport.document_number, User.email)
            .outerjoin(...).where(MarkingCode.tenant_id == tenant_id,
                                  MarkingCode.pool_id == pool_id)
            .order_by(MarkingCode.created_at.desc()))
    if status is not None:
        stmt = stmt.where(MarkingCode.status == status)
    # НЕТ .limit()/.offset()
```
- **Проблема:** пул на один GTIN может содержать десятки тысяч кодов (импортируются пачками). Эндпоинт без `limit/offset` отдаёт их все за один запрос — риск выгрузки всей таблицы и тяжёлого JSON. Сам SQL корректен (join-ы, без N+1), проблема именно в отсутствии лимита. Нарушение требования к ленте кодов иметь пагинацию.
- **Фикс:** добавить `limit: Annotated[int, Query(ge=1, le=200)] = 50` и `offset: Annotated[int, Query(ge=0)] = 0`, прокинуть в `list_pool_codes` (`.limit(limit).offset(offset)`), вернуть форму страницы (`rows` + `total`), как сделано для `/ledger`.

---

## [MEDIUM] `auto_emit_limit` валидируется только снизу — нет верхнего предела
- **Где:** `backend/app/services/seller_marking_credentials_service.py:209` (валидация), `backend/app/api/marking_credentials.py:169` (парсинг тела)
- **Доказательство:** сервис:
```python
if auto_emit_limit is not SKIP:
    if isinstance(auto_emit_limit, int):
        if auto_emit_limit < 1:
            raise SellerMarkingCredentialsError("invalid_auto_emit_limit")
        limit_value = auto_emit_limit   # верхней границы нет
```
API (тоже без верхней границы):
```python
elif isinstance(value, int):
    auto_emit_limit = value
```
- **Проблема:** `auto_emit_limit` — лимит авто-эмиссии кодов (фича авто-introduce/эмиссии в DESIGN). Принимается любое целое >= 1, включая, например, 2_000_000_000. Это поле управляет объёмом авто-выпуска КМ — отсутствие разумного потолка делает «лимит» небезопасным (можно фактически снять ограничение опечаткой/злонамеренно). Аналог требования к `copies` — числовые поля должны иметь верхний предел.
- **Фикс:** ввести разумный потолок (например, `1 <= auto_emit_limit <= 100000`) и валидировать на входе (pydantic `Field(ge=1, le=100000)` либо явная проверка) с кодом `invalid_auto_emit_limit` → 422.

---

## [MEDIUM] Неполный маппинг ошибок credentials → возможен 500 вместо 422
- **Где:** `backend/app/api/marking_credentials.py:204` (`_patch_and_respond`), пропущенный код в `seller_marking_credentials_service.py:206`
- **Доказательство:** хендлер маппит лишь часть кодов:
```python
except SellerMarkingCredentialsError as exc:
    if exc.code in (
        "empty_patch", "token_empty", "invalid_token_type",
        "invalid_marketplace", "invalid_signing_method",
        "invalid_edo_route", "invalid_auto_emit_limit",
    ):
        raise HTTPException(status_code=422, detail=exc.code) from exc
    raise   # любой иной код -> необработанное исключение -> 500
```
А сервис умеет бросать и `invalid_auto_introduce`:
```python
if not isinstance(auto_introduce, bool):
    raise SellerMarkingCredentialsError("invalid_auto_introduce")
```
- **Проблема:** код `invalid_auto_introduce` отсутствует в whitelisted-наборе хендлера, поэтому при его возникновении сработает `raise` → 500 (Internal Server Error) на клиентскую ошибку, что нарушает контракт «ошибки клиента → 4xx». На текущем пути API сам валидирует `auto_introduce` как bool (строка 162), поэтому сервисная ветка трудно достижима именно через этот эндпоинт — но маппинг хрупкий: любой новый/иной сервисный код валидации даст 500. Требует подтверждения практической достижимости (сейчас прикрыто верхним слоем), severity снижен до MEDIUM.
- **Фикс:** добавить `"invalid_auto_introduce"` в набор маппинга; лучше — заменить хрупкий явный список на правило вида «все коды с префиксом `invalid_`/`*_empty` → 422» либо дать базовому `SellerMarkingCredentialsError` атрибут `http_status`.

---

## [LOW] Создание ресурсов возвращает 200 вместо 201
- **Где:** `backend/app/api/marking_codes.py:1296` (`POST /codes/{code_id}/defect` создаёт reprint-request) и `backend/app/api/marking_codes.py:485` (`POST /import` создаёт пулы/коды)
- **Доказательство:**
```python
@router.post("/codes/{code_id}/defect", response_model=MarkingDefectOut)   # нет status_code=201
async def report_marking_code_defect(...):
    req = await mc_svc.create_defect_reprint_request(...)
    return MarkingDefectOut(request_id=str(req.id), ...)
```
- **Проблема:** эндпоинт фактически создаёт новый объект (`MarkingReprintRequest`, возвращает его `id`), но отвечает 200, а не 201 Created. Аналогично `/import` создаёт пулы/коды и отвечает 200. Шаблоны печати при этом корректно отдают 201 (`create_print_template`, строка 973). Непоследовательность контракта. Severity LOW (функционально не критично).
- **Фикс:** для `/codes/{code_id}/defect` добавить `status_code=status.HTTP_201_CREATED`. Для `/import` — оставить 200 допустимо (это batch-операция со сводкой), либо привести к единому стилю осознанно.

---

## [LOW] Нет верхнего предела на число units в layout и число файлов импорта
- **Где:** `backend/app/api/marking_codes.py:276` (`PrintLayoutOut.units`), `print_template_service.py:80` (`parse_layout`); и `marking_codes.py:451` (цикл по `files`)
- **Доказательство:** layout:
```python
class PrintLayoutOut(BaseModel):
    units: list[PrintLayoutUnitOut]    # нет max_length
```
```python
units_raw = data.get("units")
if not isinstance(units_raw, list) or not units_raw:
    raise PrintTemplateServiceError("invalid_layout_json")
for item in units_raw:        # число units не ограничено
    ...
    if not isinstance(copies, int) or copies < 1 or copies > 10:  # copies ограничены, units — нет
```
импорт:
```python
for upload in files:          # размер каждого файла ограничен _MAX_UPLOAD_BYTES, кол-во файлов — нет
```
- **Проблема:** `copies` на блок ограничены (1..10) — хорошо; блоки в whitelist `LAYOUT_BLOCKS` — хорошо. Но длина списка `units` не ограничена: можно прислать раскладку с миллионом units (DESIGN: раскладка — это «лента блоков на одну единицу», реально ≤ единиц блоков). Аналогично, число загружаемых файлов в `/import` и `/import/preview` не ограничено (размер каждого — да, ограничен). Это потенциальный DoS/раздувание памяти. Severity LOW (нужен аутентифицированный клиент с правами).
- **Фикс:** ограничить `units` (`Field(max_length=...)`, например ≤ 20) в `PrintLayoutOut` и/или в `parse_layout`; ограничить число файлов в импорт-эндпоинтах (например ≤ 20) с 413/422.

---

## Что проверено и признано корректным
- `response_model` есть практически у всех эндпоинтов (`marking_codes.py`, `marking_credentials.py`, `notifications.py`); ORM/dict наружу без схемы не отдаётся. Исключения-«сырые» dict: `POST /read-all` → `dict[str,int]` (тривиальный `{"marked": n}`) — приемлемо.
- `copies` в `PrintMarkingCodesIn` валидируется `Field(ge=1, le=10)`, `duplicate_copies` — `Field(ge=1, le=2)`; copies на блок в layout — 1..10. Нулевые/отрицательные/огромные значения отсекаются.
- `/ledger` имеет полноценную пагинацию (`limit` ge=1 le=200, `offset` ge=0) и возвращает `total`.
- `/notifications` имеет `limit` (ge=1 le=200) + отдельный `unread_count`.
- `list_pools` (сервис) — без N+1: counts/products/consumption считаются батч-функциями (`_pool_status_counts`, `_products_by_pool`, `_pool_consumption_7d_batch`).
- `list_pool_codes` SQL — join-ами, без N+1 (проблема только в отсутствии лимита, см. выше).
- Маппинг ошибок `_http_from_mc_error`: дефолт 422 (не 500), not-found-коды → 404, `unsupported_file_type` → 415, превышение размера → 413. Внутренние ошибки клиента не улетают в 500 (кроме узкого случая credentials выше).
- `DELETE /print-templates/{id}` → 204; `POST /print-templates` → 201 — корректные коды.
- Валидация формата: `gtin` (E2e) `max_length=32`, `product_barcode`/`cis_*` имеют min/max длины, даты credentials парсятся через `date.fromisoformat` с 422 при ошибке.
