# BLG-C02: узкое исследование журнала исходящих запросов WB

Стадия: `S03 DOMAIN_RESEARCH`
Роль: `pipeline-ba`
Дата исследования: `2026-08-21`
Вердикт автора: `RESEARCH_READY`
Область: существующий внешний HTTP-контракт WMS -> Wildberries; без изменения API WB,
складского процесса, UI, данных, production и release.

## 1. Вывод

Для расследования интеграционных сбоев нужен отдельный структурированный event на каждую
фактическую попытку HTTP-вызова к WB. Минимально полезный и безопасный event содержит метод,
разрешённый WB-host, нормализованный route template, HTTP-статус либо тип transport-ошибки,
длительность, номер попытки и внутренний `request_ref`. Он не содержит полный URL, query string,
headers, request/response body, токен, cookie, код маркировки, sticker/QR payload или текст
исключения.

Стандартный INFO-лог `httpx` недостаточен для бизнес-требования. Он не пишет headers и body, но
пишет полный URL и свободный текст, не даёт WMS-корреляцию, не различает logical operation и retry,
не ограничивает журнал только WB-hosts и не создаёт outcome при transport-ошибке без ответа.
Поэтому включение глобального logger `httpx` не считается готовым безопасным журналом.

Проверка конкретной реализации, emulator/MockTransport proof, нагрузка, доступ к журналу и release
остаются стадиям `S04`, `S11`, `S15`, `S20`, `S23` и `S26-S28`. S03 не разрешает deploy.

## 2. Источники и версии

| ID | Источник | Версия и дата | Уровень | Что подтверждает |
|---|---|---|---|---|
| SRC-01 | `docs/product/backlog-queue.json`, карточка `BLG-C02` | snapshot controller, 2026-08-21 | official | Нужны method/address/status, маскирование секретов, поиск конкретного запроса и отдельное разрешение на release. |
| SRC-02 | `docs/BACKLOG-2026-08-19-CHAT-RU.md:32` | repository record, 2026-08-19 | observed | Кандидат находился в `.worktrees/picklist-size`; заявлены `logging_setup.py`, method/address/status, token test и API/worker wiring. |
| SRC-03 | [WB API: общая информация](https://dev.wildberries.ru/ru/openapi/api-information) | current public OpenAPI, accessed 2026-08-21 | official | Токен передаётся в `Authorization`; описаны 4xx/5xx, `429` и числовые rate-limit headers. |
| SRC-04 | [WB API: FBS](https://dev.wildberries.ru/ru/openapi/orders-fbs) | HTTP paths v3, current public OpenAPI, accessed 2026-08-21 | official | FBS endpoints содержат order/supply IDs в path/body; metadata содержит SGTIN/UIN/IMEI/GTIN; `409` расходует лимит как 10 запросов. |
| SRC-05 | [HTTPX logging](https://www.python-httpx.org/logging/) | current HTTPX docs, accessed 2026-08-21 | official | INFO event имеет форму `HTTP Request: METHOD full-URL HTTP/version status`; network details идут отдельным logger `httpcore`. |
| SRC-06 | [HTTPX event hooks](https://www.python-httpx.org/advanced/event-hooks/) | current HTTPX docs, accessed 2026-08-21 | official | Client hooks являются штатной точкой для logging/monitoring request и response. |
| SRC-07 | [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) | current cheat sheet, accessed 2026-08-21 | official | Access tokens, session IDs, passwords, keys и sensitive personal data нельзя писать напрямую; значения нужно удалять, маскировать или санитизировать. |
| SRC-08 | [OpenTelemetry HTTP client semantics](https://opentelemetry.io/docs/specs/semconv/http/http-spans/) | stable HTTP client attributes, accessed 2026-08-21 | official | Базовые поля: method, server address, status, error type, resend count; sensitive URL content подлежит scrubbing; рекомендуется event/span на wire attempt. |
| SRC-09 | `backend/app/services/wildberries_client.py`, `wildberries_fbs_client.py`, `fbs_stock_sync_service.py` | checkout `a0427e890c35da5a05147114f4302dc2987d3a88`, observed 2026-08-21 | observed | В текущем checkout есть 22 прямые точки HTTP-вызова WB и три разрешённых WB-host settings. |
| SRC-10 | `backend/app/services/wildberries_errors.py` | checkout `a0427e890c35da5a05147114f4302dc2987d3a88`, observed 2026-08-21 | observed | Текущий error logger может писать до 500 символов raw WB response body; это отдельный канал утечки, который должен попасть в security review. |
| SRC-11 | uncommitted `.worktrees/picklist-size` at `8259901bdf3c7ea70f908b37635de7fc21eaf4ef`, files `backend/app/core/logging_setup.py` and `backend/tests/test_outbound_http_logging.py` | observed 2026-08-21; file SHA-256 `8392dd8b19519fde94481b8b63527389b629ac9d8374c20f71eecae380c6911b` and `9c74ee6e044b1c283db48cbea309719339a8e416a9dd3161d38aeb3428d12dce` | observed | Кандидат поднимает глобальный `httpx` logger до INFO, default-on, подключает API и Celery и тестирует только отсутствие `Authorization`/token в одной успешной mock-операции. Это наблюдение, не durable Git artifact и не release proof. |

У публичной страницы WB нет отдельного номера релиза документа. Для неё версия фиксируется как
`current public OpenAPI as accessed 2026-08-21`; версии endpoint отражены в самих paths (`v1-v3`).

## 3. Граница внешнего контракта

В область BLG-C02 входят вызовы только к allowlist hosts:

- `content-api.wildberries.ru`;
- `supplies-api.wildberries.ru`;
- `marketplace-api.wildberries.ru`;
- явно разрешённый local emulator host в тестовом окружении с `environment=emulator`.

Логирование произвольного `httpx`-трафика WMS не входит в задачу. Redirect на host вне allowlist
должен завершаться безопасным outcome, а не расширять область сбора данных.

Каталог, FBS/FBO, остатки, резервы, маркировка, печать, отгрузка, отмены и возвраты не меняют
бизнес-поведение. Они применимы только как типы WB-вызовов, payload которых запрещено писать.
Competitor workflows/screens и seller instruction не применимы: BLG-C02 не создаёт новый домен,
модуль или операторский процесс.

## 4. Allowlist структурированного события

Один event создаётся после каждой фактической попытки отправки. При retry сохраняется один
`operation_ref`, новый `request_ref` на wire attempt и возрастающий `attempt`.

```json
{
  "event": "wb.http.client.completed",
  "occurred_at": "2026-08-21T00:00:00Z",
  "provider": "wildberries",
  "environment": "local|emulator|staging|production",
  "component": "api|worker",
  "operation_ref": "opaque-local-operation-ref",
  "request_ref": "wbreq-uuid",
  "tenant_ref": "opaque-internal-ref-or-null",
  "seller_ref": "opaque-internal-ref-or-null",
  "local_entity_ref": "opaque-internal-ref-or-null",
  "operation": "controlled-low-cardinality-name",
  "http_method": "GET|POST|PUT|PATCH|DELETE",
  "server_address": "allowlisted-wb-host",
  "route_template": "/api/v3/orders/{orderId}/cancel",
  "attempt": 1,
  "duration_ms": 123,
  "status_code": 204,
  "outcome": "http_completed|http_rejected|rate_limited|upstream_error|transport_error|redirect_blocked",
  "error_type": null,
  "rate_limit_remaining": 19,
  "rate_limit_retry_seconds": null
}
```

Rules for fields:

1. `route_template` comes from a controlled registry near WMS endpoint constants. Raw path is not
   a fallback. Unknown route becomes `unknown`, with a metric/security signal.
2. `operation`, `outcome` and `error_type` are enums to keep cardinality bounded and prevent log
   injection. Arbitrary exception text is forbidden.
3. `tenant_ref`, `seller_ref` and `local_entity_ref` are internal opaque references, never names,
   emails or marketplace credentials. Their access and retention are decided at S11/S26.
4. `status_code=null` is valid when no response was received. `error_type` is one of
   `timeout|connect|dns|tls|cancelled|protocol|other`.
5. Only numeric WB response headers `X-Ratelimit-Remaining`, `X-Ratelimit-Retry`,
   `X-Ratelimit-Limit`, `X-Ratelimit-Reset` may be separately allowlisted. No raw header map.
6. Logging failure must not change the WB request result or warehouse transaction.

## 5. Denylist

The event must never contain:

- `Authorization`, cookies, API/JWT/session tokens, passwords, encryption keys or connection URLs;
- full URL, query string, URL credentials, raw request/response headers;
- request body, response body or their excerpts;
- SGTIN/CIS, UIN, IMEI, GTIN, customs declaration, barcode, sticker, QR/ZPL/PDF/image payload;
- raw order/supply/warehouse IDs embedded in a path; use route template and local correlation;
- customer data, product titles, seller names, email, phone or address;
- exception message, `repr(request)`, `repr(response)` or stack data that repeats URL/body;
- newline/control characters from external values.

The existing `log_wb_client_error(... wb_response_body=%r)` path (SRC-10) must be included in the
same negative security tests or removed from the new structured lane. Testing only the new success
event cannot prove that WB diagnostics are safe end to end.

## 6. HTTP outcome mapping

| Signal | Safe interpretation | Required event data |
|---|---|---|
| `2xx` | HTTP exchange completed; not proof of full business success | status, duration, attempt |
| `3xx` | Unexpected for configured API host; redirect policy is explicit | status and `redirect_blocked` or controlled resend |
| `400/413/422` | Request/contract rejection | status; no body |
| `401/403` | Authentication/access rejection | status; never token/header |
| `404` | Route or object not found | status and route template |
| `409` | Business conflict; WB counts it as 10 requests in Marketplace category | status and numeric remaining limit when present |
| `429` | Rate limited | status plus numeric retry/reset fields when present |
| `5xx` | WB unavailable/internal error | status and retry attempt |
| no response | DNS/connect/TLS/timeout/protocol failure | `status_code=null`, enum `error_type`, duration |

Pagination produces one event per page request without cursor/query values. Batch calls produce one
HTTP event for the batch; a `2xx` does not imply every item succeeded. Sanitized business counters
(`requested_count`, `accepted_count`, `rejected_count`) may be a separate allowlisted application
event only after endpoint-specific contract cases exist. Partial response bodies are never logged.

## 7. Candidate assessment

Observed candidate (SRC-11) has useful intent but does not yet satisfy the card:

- positive: API and Celery entrypoints are considered; default HTTPX INFO omits headers/body; one
  mock test proves the sample token and word `Authorization` are absent on a successful GET;
- gap: free-form HTTPX message instead of structured allowlist;
- gap: full URL is recorded, including path/query values;
- gap: logger is global for all HTTPX traffic, not WB-host scoped;
- gap: no correlation ref, tenant/seller/local operation, duration or retry attempt;
- gap: no event contract for timeout/DNS/TLS/cancel, redirects, `409`, `429`, `5xx`, pagination or
  partial batch success;
- gap: no negative tests for marking bodies, response body, query secrets, raw exception text,
  existing `wb_response_body`, worker duplicate setup or non-WB traffic;
- gap: `default=True` activates logging as soon as the artifact runs. Whether activation must be
  config-gated until owner-authorized S26/S27 is a Product/Release decision, not an S03 assumption.

## 8. Machine capability matrix

All applicable rows are processed. `ready_for_contract` means research is complete and the row is
handed to the named later stage; it does not mean implementation exists.

```json
{
  "schema_version": "1.0",
  "task_id": "BLG-C02",
  "stage": "S03",
  "as_of": "2026-08-21",
  "unprocessed_applicable_rows": 0,
  "rows": [
    {"id":"AUTH","applicable":true,"status":"ready_for_contract","sources":["SRC-03","SRC-07"],"decision":"Authorization and every credential are denylisted","owner_stage":"S15"},
    {"id":"METHOD_HOST_ROUTE","applicable":true,"status":"ready_for_contract","sources":["SRC-04","SRC-08","SRC-09"],"decision":"Log method, allowlisted server and route template, never raw path fallback","owner_stage":"S11"},
    {"id":"URL_PRIVACY","applicable":true,"status":"ready_for_contract","sources":["SRC-05","SRC-07","SRC-08"],"decision":"Full URL, query and URL credentials are forbidden","owner_stage":"S15"},
    {"id":"HTTP_STATUS","applicable":true,"status":"ready_for_contract","sources":["SRC-03","SRC-04","SRC-08"],"decision":"Record nullable numeric status and typed HTTP outcome","owner_stage":"S15"},
    {"id":"TRANSPORT_ERRORS","applicable":true,"status":"ready_for_contract","sources":["SRC-08"],"decision":"No-response failures use a closed error_type enum without exception text","owner_stage":"S15"},
    {"id":"RATE_LIMIT","applicable":true,"status":"ready_for_contract","sources":["SRC-03","SRC-04"],"decision":"429 and allowlisted numeric rate-limit headers are observable; 409 weight is tested","owner_stage":"S15"},
    {"id":"RETRIES","applicable":true,"status":"ready_for_contract","sources":["SRC-08"],"decision":"One event per wire attempt with operation_ref, request_ref and attempt","owner_stage":"S15"},
    {"id":"PAGINATION","applicable":true,"status":"ready_for_contract","sources":["SRC-04","SRC-09"],"decision":"One event per page; cursor and query values are not logged","owner_stage":"S15"},
    {"id":"BATCH_PARTIAL","applicable":true,"status":"ready_for_contract","sources":["SRC-04"],"decision":"HTTP completion is distinct from business/item success; no response body logging","owner_stage":"S15"},
    {"id":"MARKING_PRINT","applicable":true,"status":"ready_for_contract","sources":["SRC-04","SRC-07"],"decision":"Marking IDs and printable payloads are denylisted in every success/error path","owner_stage":"S15"},
    {"id":"CORRELATION","applicable":true,"status":"ready_for_contract","sources":["SRC-01","SRC-08"],"decision":"Engineer lookup uses request_ref plus controlled internal refs","owner_stage":"S11"},
    {"id":"TENANT_SELLER_ACCESS","applicable":true,"status":"ready_for_product_decision","sources":["SRC-01","SRC-07"],"decision":"Opaque refs only; reader roles and retention require explicit Product/Release contract","owner_stage":"S11"},
    {"id":"API_WORKER","applicable":true,"status":"ready_for_contract","sources":["SRC-02","SRC-11"],"decision":"Same event schema and no duplicate handlers in API and worker","owner_stage":"S15"},
    {"id":"VOLUME_OUTAGE","applicable":true,"status":"ready_for_contract","sources":["SRC-03","SRC-08"],"decision":"Bounded-cardinality fields, no success sampling until forensic requirement changes, logger failure cannot break operation","owner_stage":"S15"},
    {"id":"CURRENT_ERROR_BODY","applicable":true,"status":"ready_for_security_review","sources":["SRC-10","SRC-07"],"decision":"Existing raw response-body logging is in the negative-test and remediation scope","owner_stage":"S04"},
    {"id":"EMULATOR_PROOF","applicable":true,"status":"ready_for_cases","sources":["SRC-06","SRC-09"],"decision":"Use MockTransport/local emulator and egress guard; no live WB call required","owner_stage":"S15"},
    {"id":"RELEASE_ACTIVATION","applicable":true,"status":"ready_for_release_decision","sources":["SRC-01","SRC-11"],"decision":"Default-on versus config-gated activation is decided before S26; S03 grants no release authority","owner_stage":"S26"},
    {"id":"COMPETITOR_WORKFLOW","applicable":false,"status":"not_applicable_verified","sources":["SRC-01"],"decision":"Infrastructure logging change has no competitor/operator screen or workflow","owner_stage":"S03"},
    {"id":"LIVE_SANDBOX","applicable":false,"status":"not_applicable_verified","sources":["SRC-06","SRC-09"],"decision":"Contract can be proven with deterministic emulator; live marketplace call is prohibited for this task","owner_stage":"S23"}
  ]
}
```

## 9. Non-blocking questions routed forward

1. `S11 Product`: кто имеет право читать журнал и по каким `tenant_ref/seller_ref` фильтрам?
2. `S11 Product`: какой срок хранения и какой интерфейс/CLI является понятным способом найти
   `request_ref`? До решения журнал нельзя считать операционно доступным.
3. `S11/S26 Product + Release`: журнал включается только явным config flag после release review или
   автоматически в owner-authorized artifact? Research recommendation: config-gated activation.
4. `S15/S23`: достаточно ли хранить числовые rate-limit поля для `409/429`, или они идут только в
   metrics? В обоих вариантах raw headers запрещены.

Эти вопросы не блокируют S03: для каждого есть безопасная граница и стадия-владелец. Они блокируют
соответствующее Product/Release утверждение, если останутся без решения.

## 10. Required proof for later stages

- positive events for `2xx`, `409`, `429`, `5xx` and no-response timeout;
- retry/pagination produce separate attempts with stable operation correlation;
- API and worker emit the same schema once, without duplicate lines;
- searches for canary token, `Authorization`, query secret, SGTIN/CIS, UIN/IMEI/GTIN, response
  body and newline injection return zero matches across success and error logs;
- non-WB HTTP request does not produce `wb.http.client.*`;
- logger/storage failure does not change the business HTTP outcome;
- tests use MockTransport/local emulator under deny-by-default egress guard;
- release evidence names exact SHA, config decision, log sink/access policy and monitoring signal.

No live WB/Ozon call, production read, secret access or credential-page action was used in S03.
