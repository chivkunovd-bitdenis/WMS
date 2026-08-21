# S12 TASK_CUT - BLG-I02: WB verdict persistence and fail-closed dispatch

## Business meaning

Система может продолжать отгрузку, не сохранив точный ответ Wildberries о
проверке маркировки, и фактически считать отсутствие ошибки разрешением. Это
создаёт ложный зелёный статус: оператор думает, что заказ допустим к сдаче,
хотя подтверждения маркетплейса нет. Каждый вердикт Wildberries нужно хранить
вместе со временем и причиной, а dispatch, то есть передача заказа дальше,
должен разрешаться только по явно подтверждённому положительному состоянию.

## Atomic vertical implementation card

### I02-C1: Durable WB evidence before FBS dispatch

**Observable outcome.** На существующей поверхности передачи FBS-поставки
оператор видит только один честный итог для текущего tenant, seller, склада,
состава заказов и текущих значений маркировки. Команда dispatch доступна лишь
при `POSITIVE_CONFIRMED`; во всех остальных состояниях deliver в WB не
вызывается. После любого обращения к WB операторский результат читается из
сохранённого локального доказательства, а не выводится из отсутствия ошибки.

Это одна вертикальная карточка: хранение доказательств, вычисление состояния,
gate перед deliver и read-back являются одной бизнес-цепочкой. Нельзя отдать в
разработку отдельно миграцию, endpoint, worker или кнопку, если в результате
всё ещё возможен optimistic dispatch.

### Ownership and hard boundaries

- `BLG-I02` владеет append-only историей WB attempts и реальных verdict rows,
  их связью с текущей ревизией маркировки, fail-closed вычислением статуса и
  запретом deliver до успешного gate.
- `BLG-I01` владеет подтверждённым контрактом endpoint `orders/meta`,
  transport, batching, polling и обработкой ответа WB. `BLG-I02` не подменяет
  его endpoint, не изобретает transport fallback и не вызывает WB напрямую.
- `BLG-D03` владеет Product/legal oracle для `requiredMeta`, `optionalMeta` и
  обязанности передавать маркировку для конкретного товара. До его решения
  `optional` остаётся blocked, а не считается положительным автоматически.
- Работа ограничена FBS preflight и deliver. Она не меняет FBO, cancel/return,
  прямой Честный Знак, исправление КИЗ, live WB/Ozon, secrets, deploy/release
  или production data.

## Vertical behavior and persistence boundary

### 1. Attempt evidence: one record for every WB call

Для каждого вызова `orders_meta_preflight` или `supply_deliver` сохраняется
ровно один append-only attempt, включая timeout, connection error, malformed
response и ответы без body. Attempt содержит локальную identity, tenant/seller,
source operation, supply при наличии, защищённый exact request scope и hash
порядка order IDs, transport outcome, HTTP status/WB error code при наличии,
`observed_at_utc` как время получения WMS, hashes request/response, признак
body, защищённый raw payload или durable reference и версию external-contract
snapshot.

`observed_at_utc` не называется временем WB или Честного Знака. Bodyless `204`
честно сохраняется с `response_body_present=false`; timeout и connection error
также не получают выдуманный body, status или verdict.

### 2. Verdict evidence: only rows actually returned by WB

Под attempt сохраняются `0..N` append-only detail rows и только для реальных
`metaDetails[]`, которые пришли от WB. Каждая строка сохраняет external order,
порядок order/meta, key, защищённое value либо hash value, точный
case-sensitive `decision_raw`, нормализованный class и безопасную русскую
причину. Синтетическая строка для пропущенного заказа, key, bodyless ответа или
ошибки запрещена.

Новая попытка не перезаписывает ни attempt, ни detail row. Производная current
projection допустима лишь как воспроизводимый индекс поверх истории: она
ссылается на attempts/details, содержит completeness, supersession и fingerprint
текущего marking set. Она не заменяет исходное доказательство.

### 3. Current-state categories

| Operator/business state | Evidence rule | Dispatch |
| --- | --- | --- |
| `POSITIVE_CONFIRMED` | Свежий preflight в пути dispatch покрывает все запрошенные заказы и применимые ключи текущей revision; все реальные решения явно positive, attempt и rows уже committed. `optional` positive только с oracle BLG-D03. | Allowed to call deliver. |
| `NEGATIVE_CONFIRMED` | Сохранён реальный документированный negative verdict либо `409 MetaValidationFail` конкретной deliver attempt. | Blocked until correction and a new preflight. |
| `WAITING_BLOCKED` | `pending` или `deadlineExceeded`; последний технически eligible у WB всё равно не является явным положительным подтверждением. | Blocked; only bounded recheck is eligible. |
| `UNKNOWN_BLOCKED` | Unknown decision, optional without D03 oracle, missing order/key, conflicting duplicate, stale marking fingerprint, incomplete/empty/corrupt response, timeout, transport failure or HTTP error. | Blocked. |

Положительными являются только утверждённые S11 values для соответствующего key
(`filled` и документированные passed states); отрицательные сохраняются как
`NEGATIVE_CONFIRMED`; любой новый, отсутствующий или противоречивый value идёт
в `UNKNOWN_BLOCKED`. Отсутствие ошибки никогда не переходит в positive.

### 4. HTTP result semantics

| WB result | Persist before any local result | Local meaning |
| --- | --- | --- |
| `200 orders/meta` | One preflight attempt and all actually returned detail rows. Then evaluate completeness against requested scope and current marking fingerprint. | May become `POSITIVE_CONFIRMED` only if every gate predicate passes; otherwise blocked. |
| Bodyless `204 deliver` | One `DELIVER_ACCEPTED` attempt with no synthetic per-order/per-key detail rows. | WB accepted this deliver attempt; operator success is shown only after this persistence. It does not repair preflight omissions or manufacture positive verdicts. |
| `409 MetaValidationFail` | One `DELIVER_REJECTED_PARTIAL` attempt, protected raw body and only the returned problem/pending details, including an honestly empty `orders[]` if it is what WB returned. | Negative result for this deliver attempt; it blocks and never replaces a complete preflight projection or makes omitted orders positive. |
| Every other HTTP `4XX` (`400`, `401`, `402`, `403`, `404`, `429` and any future `4XX`) | One honest attempt with status/error/body if present and only real detail rows if present. Preserve rate-limit headers for `429`. | `UNKNOWN_BLOCKED`; no deliver permission. Every `4XX` receives the documented rate-limit accounting, not only `409`. |
| `5XX`, timeout, connection error, malformed response | One honest transport/result attempt, zero detail rows unless real parseable rows exist. | `UNKNOWN_BLOCKED`; no optimistic retry or deliver. |

## Dispatch gate and safe execution order

1. Resolve the active tenant/seller, supply, warehouse and its current
   tenant-owned orders and marking-set fingerprint. A changed order membership,
   KIZ or other applicable identifier invalidates prior positive evidence.
2. Use the `BLG-I01` transport to obtain current metadata in deterministic
   batches of no more than 100 order IDs, observing rate-limit/backoff rules.
3. Commit the attempt and every real returned verdict row atomically before any
   projection or permission decision. A crash after WB responds but before local
   commit must remain blocked and recoverable by read-back, never green.
4. Compute the current state from persisted evidence only. Missing, stale,
   duplicate-conflicting, waiting, negative, unknown and failed evidence all
   close the gate.
5. Invoke `supply_deliver` only from persisted `POSITIVE_CONFIRMED`. Persist
   its attempt outcome before returning success, failure or retry guidance to
   the operator. No alternate route, background retry or UI action may bypass
   this gate.

## Resources and safety constraints for S13

S13 must turn this logical card into the actual resource graph without widening
the card. It must nominate and lock the precise additive migration/model,
repository/service boundary, API/read-back surface, queue/worker path for
polling or recovery, current-projection resource, emulator fixture/reset and
existing FBS dispatch surface. S13 also owns retention and access rules for raw
payloads, transaction boundaries, idempotency/recovery identity and the exact
locks; S12 does not select table names, routes, file paths or implementation.

All storage, queries, projection reads, worker jobs and operator read-back are
tenant- and seller-scoped. A supply/order/marking value is usable only after
membership and ownership checks in the same tenant; failures do not disclose
another tenant's existence or values. Warehouse is part of the active FBS
operational context: a verdict from another warehouse/supply/order composition
cannot authorise the current dispatch. Raw payloads and full KIZ stay protected
and absent from ordinary logs and operator UI; UI receives only safe reasons,
masked identifiers where necessary and retry/block guidance.

## Operator and read-back surface

No new screen is approved by this card. On the existing FBS dispatch surface,
the state must be distinguishable as ready, negative, waiting or unknown. The
surface exposes dispatch only in `POSITIVE_CONFIRMED`; `WAITING_BLOCKED` and
`UNKNOWN_BLOCKED` may offer a safe recheck, while `NEGATIVE_CONFIRMED` identifies
only real WB-named order/key reasons to correct. After a process restart or
retry, the same state and the last relevant attempt outcome are read back from
durable history. It must never display raw WB payloads, tokens or a full KIZ.

## Mandatory dependency gates

`BLG-I01` and `BLG-D03` are mandatory downstream gates. They do not block this
S12 cut, S13 planning, S14 falsification or S15 case preparation, because this
card explicitly fails closed while their final contracts/implementations are
pending. They are, however, non-bypassable blockers before `S16
PRODUCT_APPROVED_FOR_DEV` and before `S18 DEVELOPMENT`:

- `BLG-I01` must provide the accepted versioned endpoint/transport/polling
  contract and its required implementation evidence for this card to use.
- `BLG-D03` must provide the accepted oracle table that resolves applicability
  of `requiredMeta`/`optionalMeta`; until then optional remains
  `UNKNOWN_BLOCKED`.
- No local mapping, feature flag, mocked green status or manual DB action may
  erase, resolve or work around either dependency edge.

If either dependency is still open at S16, Product must issue the controller's
blocked/waiting outcome with the exact dependency named. There is no Product
approval before Dev and no workspace/development dispatch until both gates have
the required evidence.

## Required downstream outputs

### S13 ARCHITECT_PLAN

Produce a resource graph and sequencing for append-only attempts/details,
additive migration, tenant/seller/warehouse isolation, protected payload
retention, current marking fingerprint/completeness rules, atomic persistence,
crash recovery, idempotent deliver, bounded polling/rate-limit protection,
read-back/API surface and exact file/resource locks. Preserve the I01/D03 gates.

### S14 ARCHITECT_FALSIFICATION

Independently try to produce false green or an unauthorised deliver using stale
or changed KIZ, partial/empty `409`, duplicate conflict, omitted order/key,
unknown decision, `deadlineExceeded`, `pending`, bodyless/error response,
crash between WB response and commit, tenant/seller/warehouse cross-read and
retry/concurrency. Any such route requires replan, not a local exception.

### S15 CASE_FACTORY

Create direct and breaker cases with WB emulator or separately authorised
sandbox (never production) for every documented SGTIN decision, other-key
positive/negative decisions, unknown and unapproved optional, missing and
duplicate details, stale/current-revision changes, `200`, bodyless `204`,
partial/empty `409`, every `4XX`, `5XX`, `429`, timeout, connection error,
malformed body, batches over 100, tenant/seller/warehouse isolation, restart
read-back and idempotent retry. Every blocked category must prove absence of a
deliver call and absence of synthetic verdict rows.

### S16 and S18

S16 receives the complete S11/S12/S13/S14/S15 package and must not approve the
card until BLG-I01 and BLG-D03 gates are demonstrably closed. S18 then implements
the whole vertical card: durable database evidence, service/API/worker paths,
gate and operator read-back, without live marketplace calls, release or deploy.

## Explicit exclusions

This S12 artifact approves no application code, schema/migration choice, route,
worker schedule, UI redesign, test execution, commit, push, release, deploy,
secret access, live WB/Ozon request, sandbox call or production data operation.

## Handoff

**Next stage:** `S13 ARCHITECT_PLAN`, role `solution-architect`. The task is
critical and has an external contract, so S13/S14/S15 are required before the
dependency-gated S16. The current controller has no S12 blocker; the future
blocker is explicitly preserved for S16/S18 until `BLG-I01` and `BLG-D03` are
accepted.
