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
классифицированный WB-host, нормализованный route template, HTTP-статус либо тип transport-ошибки,
длительность, номер попытки и внутренний `request_ref`. Нулевая утечка является сквозным
инвариантом: ни новый event, ни существующий `log_wb_client_error`, ни API/worker exception,
access/task log, trace, metric label или тестовое evidence не могут содержать raw URL/path,
object ID, headers, request/response body, credential либо свободный текст WB/исключения.

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
| SRC-03 | [WB API: общая информация](https://dev.wildberries.ru/ru/openapi/api-information) | current public OpenAPI, accessed 2026-08-21 | official | Токен передаётся в `Authorization`; описаны 4xx/5xx, token-bucket, агрегация лимитов и rate-limit headers. |
| SRC-04 | [WB API: FBS](https://dev.wildberries.ru/ru/openapi/orders-fbs) | HTTP paths v3, current public OpenAPI, accessed 2026-08-21 | official | FBS endpoints содержат order/supply IDs в path/body; metadata содержит SGTIN/UIN/IMEI/GTIN; `409` расходует лимит как 10 запросов. |
| SRC-05 | [HTTPX logging](https://www.python-httpx.org/logging/) | current HTTPX docs, accessed 2026-08-21 | official | INFO event имеет форму `HTTP Request: METHOD full-URL HTTP/version status`; network details идут отдельным logger `httpcore`. |
| SRC-06 | [HTTPX event hooks](https://www.python-httpx.org/advanced/event-hooks/) | current HTTPX docs, accessed 2026-08-21 | official | Client hooks являются штатной точкой для logging/monitoring request и response. |
| SRC-07 | [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) | current cheat sheet, accessed 2026-08-21 | official | Access tokens, session IDs, passwords, keys и sensitive personal data нельзя писать напрямую; значения нужно удалять, маскировать или санитизировать. |
| SRC-08 | [OpenTelemetry HTTP client semantics](https://opentelemetry.io/docs/specs/semconv/http/http-spans/) | stable HTTP client attributes, accessed 2026-08-21 | official | Базовые поля: method, server address, status, error type, resend count; sensitive URL content подлежит scrubbing; рекомендуется event/span на wire attempt. |
| SRC-09 | `backend/app/services/wildberries_client.py`, `wildberries_fbs_client.py`, `fbs_stock_sync_service.py` | checkout `a0427e890c35da5a05147114f4302dc2987d3a88`, observed 2026-08-21 | observed | В текущем checkout есть 22 прямые точки HTTP-вызова WB и три разрешённых WB-host settings. |
| SRC-10 | `backend/app/services/wildberries_errors.py` | checkout `a0427e890c35da5a05147114f4302dc2987d3a88`, observed 2026-08-21 | observed | Текущий error logger может писать до 500 символов raw WB response body; это отдельный канал утечки, который должен попасть в security review. |
| SRC-11 | uncommitted `.worktrees/picklist-size` at `8259901bdf3c7ea70f908b37635de7fc21eaf4ef`, files `backend/app/core/logging_setup.py` and `backend/tests/test_outbound_http_logging.py` | observed 2026-08-21; file SHA-256 `8392dd8b19519fde94481b8b63527389b629ac9d8374c20f71eecae380c6911b` and `9c74ee6e044b1c283db48cbea309719339a8e416a9dd3161d38aeb3428d12dce` | observed | Кандидат поднимает глобальный `httpx` logger до INFO, default-on, подключает API и Celery и тестирует только отсутствие `Authorization`/token в одной успешной mock-операции. Это наблюдение, не durable Git artifact и не release proof. |
| SRC-12 | [Система авторизации WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-0d73-71e9-be3e-b2c44567470c/sistema-avtorizatsii-wb-api) | updated 2026-04-03, accessed 2026-08-21 | official | Четыре типа токенов, Bearer-схема, category/read-write/type проверки и граница `401` против `403`. |
| SRC-13 | [Работа с токенами для партнёрских сервисов](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-bd37-76b4-931d-fa5fa437b85e) | current public guide, accessed 2026-08-21 | official | Сервисный токен требует `X-Client-Secret`; перечислены `401` secret failures и `403` missing/mismatched/not-allowed constraints. |
| SRC-14 | [Расшифровка кодов ошибок WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-2cb0-781d-8921-deaf4a014a58/rasshifrovka-kodov-oshibok-wb-api) | updated 2026-04-06, accessed 2026-08-21 | official | Общая семантика `402`, `406`, `451`, `429` и 5xx; response body остаётся чувствительным внешним материалом. |
| SRC-15 | [Лимиты запросов WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-28ca-7735-bf2f-98210695abc7/limity-zaprosov-wb-api) | updated 2026-04-03, accessed 2026-08-21 | official | Token bucket, лимиты по типам токенов, отсутствие Remaining на `429`, числовые Retry/Limit/Reset. |
| SRC-16 | [Ограничения тестового контура WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-24e3-7642-801f-e1f18c5fe708) | updated 2026-04-03, accessed 2026-08-21 | official | Официальные content/marketplace/supplies sandbox hosts, test-token-only и ограничения тестового контура. |
| SRC-17 | [Песочница WB API](https://dev.wildberries.ru/sandbox) | current public matrix, accessed 2026-08-21 | official | Content/Marketplace имеют суммарный предел 1 rps, Supplies FBW — 1 rps на метод; sandbox-отличия ответов и данных. |
| SRC-18 | [WB API: работа с товарами](https://dev.wildberries.ru/ru/openapi/work-with-products) | current public OpenAPI, accessed 2026-08-21 | official | Используемый WMS `PUT /api/v3/stocks/{warehouseId}` документирует `402` и `406`; `406` означает блокировку обновления остатков. |
| SRC-19 | [WB API: общение с покупателями](https://dev.wildberries.ru/ru/openapi/user-communication) | current public OpenAPI, accessed 2026-08-21 | official | `451` относится к файлу, не прошедшему модерацию, в другом API; текущие BLG-C02 вызовы его не используют. |

У публичной страницы WB нет отдельного номера релиза документа. Для неё версия фиксируется как
`current public OpenAPI as accessed 2026-08-21`; версии endpoint отражены в самих paths (`v1-v3`).

## 3. Граница внешнего контракта

В область BLG-C02 входят три явных класса host. Классификация выполняется до отправки и попадает в
`environment`; совпадение по суффиксу или произвольный `*.wildberries.ru` запрещены.

Production allowlist:

- `content-api.wildberries.ru`;
- `supplies-api.wildberries.ru`;
- `marketplace-api.wildberries.ru`;

Official sandbox allowlist (только как контракт, live-вызов в этой задаче запрещён):

- `content-api-sandbox.wildberries.ru`;
- `marketplace-api-sandbox.wildberries.ru`;
- `supplies-api-sandbox.wildberries.ru`.

Deterministic test class: фиксированный local `MockTransport` или emulator endpoint с
`environment=emulator`, который не резолвится и не перенаправляется в сеть. Emulator host не
маскируется под `sandbox`: `sandbox` означает только официальный WB host из списка выше.

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
  "environment": "emulator|sandbox|staging|production",
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
  "outcome": "http_completed|http_rejected|auth_rejected|payment_required|operation_blocked|rate_limited|upstream_error|transport_error|redirect_blocked",
  "error_type": null,
  "rate_limit_remaining": 19,
  "rate_limit_retry_seconds": null,
  "rate_limit_limit": null,
  "rate_limit_reset_seconds": null
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
5. Only parsed non-negative numeric WB response headers `X-Ratelimit-Remaining`,
   `X-Ratelimit-Retry`, `X-Ratelimit-Limit`, `X-Ratelimit-Reset` may be separately allowlisted.
   Missing or malformed values become `null`; raw strings and the raw header map are never logged.
6. Logging failure must not change the WB request result or warehouse transaction.

## 5. Denylist

The event must never contain:

- `Authorization`, `X-Client-Secret`, cookies, API/JWT/session tokens, service secrets, passwords,
  encryption keys or connection URLs;
- full URL, query string, URL credentials, raw request/response headers;
- request body, response body or their excerpts;
- SGTIN/CIS, UIN, IMEI, GTIN, customs declaration, barcode, sticker, QR/ZPL/PDF/image payload;
- raw order/supply/warehouse IDs embedded in a path; use route template and local correlation;
- customer data, product titles, seller names, email, phone or address;
- exception message, `repr(request)`, `repr(response)` or stack data that repeats URL/body;
- newline/control characters from external values.

The existing `log_wb_client_error(... wb_response_body=%r)` behavior (SRC-10) cannot remain as a
legacy lane outside the contract. Before BLG-C02 can pass implementation review, every call site in
API and worker execution must either use a safe structured projection or suppress the body/path/ID
entirely. The negative tests aggregate every emitted sink and require zero canary matches; testing
only the new success event is an automatic failure.

## 6. Auth contract without credential access

`Basic token` below means the WB **Base token type**, not HTTP Basic authentication. Every test uses
synthetic canary strings; implementation, review and test must not read, decode, rotate or replace a
real credential.

| WB token mode | Request headers | Official constraint | Safe observable result |
|---|---|---|---|
| Personal | `Authorization: Bearer <token>` | own/on-premise integration; category and read/write rights apply | status only; no token-derived claims |
| Service | `Authorization: Bearer <seller-service-token>` plus `X-Client-Secret` | both must belong to the same authorized service | status only; neither credential nor auth response text |
| Base | `Authorization: Bearer <token>`; no `X-Client-Secret` | limited categories and lower limits | status only; `token_type` is not logged |
| Test | `Authorization: Bearer <token>`; no `X-Client-Secret` | sandbox hosts only, generated data, lower limits | `environment=sandbox`; no token-derived claims |

`401` means token or service-secret verification did not pass: missing/malformed/expired/withdrawn
credential is one class for logging. `403` means a valid credential cannot perform the operation:
wrong category/access level, token type mismatch, missing `X-Client-Secret` for a Service token,
token and secret from different services, or `X-Client-Secret` supplied with a Personal token. The
WB `detail`, `requestId`, `origin` and any echoed external value remain forbidden even when they
would make diagnosis easier; the engineer correlates by local `request_ref`.

## 7. HTTP outcome mapping

| Signal | Safe interpretation | Required event data |
|---|---|---|
| `2xx` | HTTP exchange completed; not proof of full business success | status, duration, attempt |
| `3xx` | Unexpected for configured API host; redirect policy is explicit | status and `redirect_blocked` or controlled resend |
| `400/413/422` | Request/contract rejection | status; no body |
| `401/403` | Authentication/access/type rejection | `auth_rejected`, status; never token/header/body |
| `402` | Insufficient balance for a Catalog service; documented on current FBS/stock methods | `payment_required`, status; no body |
| `404` | Route or object not found | status and route template |
| `406` | Operation blocked; applicable to current `PUT /api/v3/stocks/{warehouseId}` | `operation_blocked`, status; no body |
| `409` | Business conflict; WB counts it as 10 requests in Marketplace category | status and numeric remaining limit when present |
| `429` | Rate limited | status plus numeric retry/reset fields when present |
| `451` | File failed moderation in User Communication API | N/A for current WMS call inventory; future unknown 4xx maps to `http_rejected` without body |
| `5xx` | WB unavailable/internal error | status and retry attempt |
| no response | DNS/connect/TLS/timeout/protocol failure | `status_code=null`, enum `error_type`, duration |

Pagination produces one event per page request without cursor/query values. Batch calls produce one
HTTP event for the batch; a `2xx` does not imply every item succeeded. Sanitized business counters
(`requested_count`, `accepted_count`, `rejected_count`) may be a separate allowlisted application
event only after endpoint-specific contract cases exist. Partial response bodies are never logged.

## 8. Rate-limit contract

WB applies token-bucket limits per method/group and token type. Service-token traffic is aggregated
across all seller tokens issued for the same Catalog service. Base and Test token limits are lower
and aggregated within the corresponding token type. This affects pacing, but the event must not
contain token type, token identity or a credential fingerprint.

Parsing is strict and total:

- on non-`429`, `X-Ratelimit-Remaining` may be parsed as a non-negative integer; absence is accepted
  as `null` and does not turn the HTTP result into a logging failure;
- on `429`, official docs say `X-Ratelimit-Remaining` is absent; `null` is the expected value, not a
  parser defect;
- `X-Ratelimit-Retry` and `X-Ratelimit-Reset` are non-negative numeric seconds, while
  `X-Ratelimit-Limit` is a non-negative numeric burst count;
- whitespace-normalized decimal integer values are accepted. Empty, signed-negative, fractional,
  non-ASCII numeric, overflow and arbitrary strings become `null`; no raw value is retained;
- Retry/Limit/Reset missing independently on `429` remain `null`. Retry policy uses a bounded local
  fallback decided in S15, never the external body or malformed header.

Required deterministic rows are: all four valid; `429` without Remaining; every header absent;
each header malformed independently; negative and overflow; `409` weighted accounting; Personal,
Service, Base and Test aggregation fixtures. These are parser/contract fixtures, not live calls.

## 9. Official sandbox versus emulator

The official WB sandbox is applicable to host classification and later integration compatibility,
even though this research task authorizes no request to it. It accepts only a Test token and uses
generated data. Exact mappings are:

| Production | Official sandbox | Contract difference relevant here |
|---|---|---|
| `content-api.wildberries.ru` | `content-api-sandbox.wildberries.ru` | max 1 request/second total for Content methods |
| `marketplace-api.wildberries.ru` | `marketplace-api-sandbox.wildberries.ru` | max 1 request/second total; FBS sandbox has synthetic flows and response differences |
| `supplies-api.wildberries.ru` | `supplies-api-sandbox.wildberries.ru` | FBW sandbox max 1 request/second per method |

For BLG-C02 proof, `MockTransport` is primary: it injects exact response status, body, headers,
redirect and transport exceptions without DNS/network. A local emulator may additionally prove API
and Celery worker wiring, but runs under deny-by-default egress and fixed local host classification.
Official sandbox is a separately classified compatibility lane for S23; it is neither `N/A` nor a
substitute for deterministic leak tests, and this card gives no authority to execute it.

## 10. Candidate assessment

Observed candidate (SRC-11) has useful intent but does not yet satisfy the card:

- positive: API and Celery entrypoints are considered; default HTTPX INFO omits headers/body; one
  mock test proves the sample token and word `Authorization` are absent on a successful GET;
- gap: free-form HTTPX message instead of structured allowlist;
- gap: full URL is recorded, including path/query values;
- gap: logger is global for all HTTPX traffic, not WB-host scoped;
- gap: no correlation ref, tenant/seller/local operation, duration or retry attempt;
- gap: no event contract for auth modes, `402`, `406`, timeout/DNS/TLS/cancel, redirects, `409`,
  malformed/absent `429` headers, `5xx`, pagination or partial batch success;
- gap: no negative tests for `X-Client-Secret`, marking bodies, response body, raw path/object IDs,
  query secrets, raw exception text, existing `wb_response_body`, worker duplicate setup or non-WB
  traffic;
- gap: `default=True` activates logging as soon as the artifact runs. Whether activation must be
  config-gated until owner-authorized S26/S27 is a Product/Release decision, not an S03 assumption.

## 11. Machine capability matrix

The authoritative machine-readable matrix is
`tasks/BLG-C02/S03-capability-matrix.json` (`schema_version=1.1`). It has zero unprocessed applicable
rows. `OFFICIAL_SANDBOX` is now applicable with status `contract_documented_no_live_call`, while
`EMULATOR_PROOF` remains the deterministic evidence lane. `HTTP_451` is explicitly verified N/A for
the current call inventory rather than silently omitted.

## 12. Non-blocking questions routed forward

1. `S11 Product`: кто имеет право читать журнал и по каким `tenant_ref/seller_ref` фильтрам?
2. `S11 Product`: какой срок хранения и какой интерфейс/CLI является понятным способом найти
   `request_ref`? До решения журнал нельзя считать операционно доступным.
3. `S11/S26 Product + Release`: журнал включается только явным config flag после release review или
   автоматически в owner-authorized artifact? Research recommendation: config-gated activation.
4. `S15/S23`: достаточно ли хранить числовые rate-limit поля для `409/429`, или они идут только в
   metrics? В обоих вариантах raw headers запрещены.

Эти вопросы не блокируют S03: для каждого есть безопасная граница и стадия-владелец. Они блокируют
соответствующее Product/Release утверждение, если останутся без решения.

## 13. Required proof for later stages

- positive events for `2xx`, `402`, `406`, `409`, `429`, `5xx` and no-response timeout;
- synthetic Personal/Service/Base/Test auth fixtures cover both headers and the documented
  `401/403` token-type constraints without accessing credentials;
- valid, absent and malformed rate-limit headers cover `429` without Remaining and numeric
  Retry/Limit/Reset parsing;
- retry/pagination produce separate attempts with stable operation correlation;
- API route and Celery/background worker each traverse a real application handler into the same
  MockTransport/emulator fixture and emit the same schema once, without duplicate lines;
- the test captures and concatenates structured WB events, `log_wb_client_error`, app/httpx/httpcore
  and access logs, API exception responses, worker task/retry/failure logs, traces, metric labels and
  persisted test evidence;
- exact searches for canary `Authorization`, `X-Client-Secret`, query secret, raw URL/path/order,
  supply and warehouse IDs, SGTIN/CIS, UIN/IMEI/GTIN, sticker/body and newline injection return zero
  matches in that aggregate for success, every HTTP error and every transport error;
- non-WB HTTP request does not produce `wb.http.client.*`;
- logger/storage failure does not change the business HTTP outcome;
- tests use MockTransport/local emulator under deny-by-default egress; DNS/socket access fails the
  suite. Official sandbox hosts are classification fixtures only and receive zero requests;
- release evidence names exact SHA, config decision, log sink/access policy and monitoring signal.

No live WB/Ozon call, production read, secret access or credential-page action was used in S03.
