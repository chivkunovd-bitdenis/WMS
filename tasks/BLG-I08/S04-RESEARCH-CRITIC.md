# BLG-I08 — S04 RESEARCH_CRITIC

## Паспорт

- Роль: `pipeline-reviewer`, независимый `research-critic`.
- Модельный класс dispatch: `gpt-5.6-sol`, `expensive`.
- Дата проверки: `2026-08-21`, Europe/Moscow.
- Вход: `S03-WB-AUTH-STATUS-RESEARCH.md`, `S03-wb-auth-capability-matrix.json` и
  официальные WB API/knowledge-base страницы, найденные независимо.
- Внешние операции: production и sandbox API не вызывались; реальные ключи, кабинеты учётных
  данных, secrets, deploy и production не затрагивались.
- Verdict: `RESEARCH_REWORK`.

## Итог критика

Основа S03 верна: `/ping` является неразрушающей проверкой доставки запроса, валидности токена/URL и
совпадения категории с сервисом, но не проверкой доступности самого сервиса. Также правильно
разделены `401`, `403`, `429`, `5xx` и transport/DNS/timeout; transient-ошибки не объявляются
поломкой ключа, а `200 /ping` не доказывает write-доступ.

Пропустить research дальше пока нельзя. Машинная матрица объявляет ноль необработанных применимых
строк, хотя не покрывает официально опубликованный sandbox-вариант Content `/ping`, не содержит
исполняемой emulator matrix и не задаёт полную политику сохранения `last_success_at` и удаления
credential/raw-response данных из всех диагностических sinks.

## Блокирующие находки

### RC-01 — неполная environment/endpoint matrix

Официальная таблица WB Connection Check перечисляет для Content два адреса:
`content-api.wildberries.ru/ping` и `content-api-sandbox.wildberries.ru/ping`. Для Marketplace и
Supplies в этой таблице указаны только production-варианты. S03 перечисляет три production host и
не фиксирует ни Content sandbox, ни явный статус sandbox-поддержки для Marketplace/Supplies.

До pass машинная матрица должна иметь строки `capability + environment + endpoint + provenance`:
официальный Content sandbox и явные `not_documented_for_ping`/`unverified` для остальных сочетаний,
если отдельный официальный источник не докажет их. Это исследование endpoint contract, а не
разрешение вызвать sandbox. Live/sandbox вызовы для rework не нужны и запрещены текущим scope.

Источник:

- https://dev.wildberries.ru/docs/openapi/api-information

### RC-02 — emulator cases не являются capability rows

S03 перечисляет будущие проверки одной prose-строкой, но машинная matrix не содержит ни одного
emulator row и поэтому не может честно утверждать `unprocessed_applicable_rows: []`. Нужны
детерминированные case rows со статусом `test_design_not_executed`, ожидаемым normalized state и
инвариантами для: missing, malformed, expired, unknown/revoked `401`, wrong-category `403`, read-only
`401/403`, `429` с отсутствующими/валидными retry headers, timeout/DNS, `5xx`, recovery, stale и
no-leakage. Отдельно нужно проверить, что endpoint-specific `/ping` contract документирует
`200/401/429`, а `403` относится к permission failure нужного business method, если нет более узкого
официального доказательства.

Исполненное доказательство остаётся стадией S15; S03 обязан передать полный test design, не выдавая
его за выполненный sandbox/emulator proof.

### RC-03 — семантика `last_success_at` не закрыта

S03 явно сохраняет последний успех при network/`5xx`, но не задаёт правило для последующего
`401`/`403`, `429`, локального `EXPIRED` и malformed response. Исторический `last_success_at` нельзя
очищать или заменять временем неуспешной проверки: текущий `state` и `checked_at` меняются отдельно,
а последний доказанный успех сохраняется по `tenant + seller + capability + environment` до нового
успеха. UI должен показывать его именно как исторический факт рядом с текущей ошибкой, не как
признак актуальной работоспособности.

До pass это правило должно появиться и в prose, и в machine row, вместе с recovery case.

### RC-04 — запрет утечки не охватывает все auth material и sinks

S03 запрещает `Authorization`, token/JWT identifiers и raw response в UI/analytics receipt, но не
делает явным сквозной запрет для application logs, persistence, traces, metrics, exception text и
support payload. Кроме того, текущая официальная схема WB для сервисных/basic tokens использует
`X-Client-Secret`; это такой же credential material и он отсутствует в denylist S03.

До pass контракт должен разрешать наружу только normalized code, безопасный incident reference и
timestamps. `Authorization`, `X-Client-Secret`, bearer/token fragments, decoded JWT identifiers,
request headers, raw body/detail/response и URL/query/object identifiers не должны сохраняться,
логироваться, трассироваться, попадать в метрики, exception text, API/UI или pipeline evidence.
Разбор allowlisted причины допустим только внутри адаптера с немедленным отбрасыванием raw payload.
Никакого чтения или live-проверки credentials для этой правки не требуется.

Источники:

- https://dev.wildberries.ru/knowledge-base/articles/019d49a1-1160-7ecf-91e9-abb10256bd0e/bezopasnost-dannykh-prodavtsa-pri-rabote-s-wb-api
- https://dev.wildberries.ru/knowledge-base/articles/019d49a1-bd37-76b4-931d-fa5fa437b85e

## Проверенные области

| Область | Вердикт критика | Обоснование |
|---|---|---|
| `/ping` semantics | pass с rework по host matrix | `200` доказывает reachability/token/URL/category, но не service health и не write access. |
| `401` | pass | Authentication rejection; expiry допустим только по `exp` или allowlisted reason, отзыв не выводится без доказательства. |
| `403` | pass | Недостаточно категории/прав; не смешивается с broken token. |
| `429` | pass с emulator row | Отдельный delayed/rate-limit state, retry headers требуют cases. |
| `5xx` и network | pass с emulator rows | Разные transient states, оба сохраняют last-known success. |
| Last success | rework | Нет явного preserve-rule для всех failure transitions и recovery. |
| Token redaction/raw response | rework | Нет полного sink coverage и `X-Client-Secret` в denylist. |
| Sandbox/emulator | rework | Пропущен Content sandbox `/ping`; case list не представлен machine rows. |

## Условие снятия blocker

Автор S03 должен:

1. добавить environment/endpoint rows для Content, Marketplace и Supplies с точным official,
   `not_documented_for_ping` или `unverified` provenance;
2. добавить machine-readable emulator case rows и явно отделить test design от executed proof;
3. зафиксировать сохранение исторического `last_success_at` при любом неуспешном исходе и recovery;
4. расширить denylist на `X-Client-Secret` и все storage/log/trace/metric/exception/API/UI/evidence sinks;
5. оставить `unprocessed_applicable_rows: []` только после закрытия этих строк.

После rework нужен новый независимый запуск S04. До этого `RESEARCH_PASSED` запрещён.
