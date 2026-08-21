# BLG-I08 - S04 RESEARCH_CRITIC

## Паспорт повторного review

- Роль: `pipeline-reviewer`, независимый `research-critic`.
- Проверенный rework commit: `349057e25df7622c4058b6d07986a14b53bbe153`.
- Модельный класс dispatch: `gpt-5.6-sol`, `expensive`.
- Дата повторной проверки: `2026-08-21`, Europe/Moscow.
- Вход: `S03-WB-AUTH-STATUS-RESEARCH.md`,
  `S03-wb-auth-capability-matrix.json`, `S03-RESEARCH-REWORK-CLOSURE.md`, предыдущий S04 verdict,
  controller packet и dispatch.
- Независимая внешняя сверка: публичные страницы WB API Connection Check, sandbox и authorization
  открыты без авторизации; production/sandbox API не вызывались.
- Credentials, secrets, credential pages, deploy, production и application code не затрагивались.
- Verdict: `RESEARCH_PASSED`.

## Итог

Rework закрывает все четыре блокирующие находки предыдущего S04. Официальная таблица WB Connection
Check явно публикует Content production и sandbox `/ping`, но для Marketplace и Supplies содержит
только production `/ping`. Отдельная официальная sandbox-страница публикует base hosts Marketplace и
Supplies, поэтому S03 корректно фиксирует эти два сочетания как `not_documented_for_ping` с
`endpoint: null` и не достраивает URL по шаблону.

Машинная матрица теперь содержит 16 детерминированных emulator cases со статусом
`test_design_not_executed`, единое правило сохранения исторического `last_success_at` для каждого
failure-класса, recovery только по новому доказанному успеху и сквозной redaction contract. Это
достаточный research handoff; исполненное emulator-доказательство по-прежнему принадлежит S15.

## Независимая проверка blocker

### RC-01 - environment/endpoint provenance: закрыто

Публичная страница `https://dev.wildberries.ru/docs/openapi/api-information` независимо подтверждает:

- Content: `content-api.wildberries.ru/ping` и `content-api-sandbox.wildberries.ru/ping`;
- Marketplace: `marketplace-api.wildberries.ru/ping` без sandbox-варианта в таблице `/ping`;
- Supplies: `supplies-api.wildberries.ru/ping` без sandbox-варианта в таблице `/ping`.

Публичная статья sandbox отдельно подтверждает base hosts
`marketplace-api-sandbox.wildberries.ru` и `supplies-api-sandbox.wildberries.ru`, но не объявляет их
вариантами Connection Check. Все шесть machine rows имеют capability, environment, endpoint или
явный `null`, provenance и `prohibited_not_executed`. Выдуманных Marketplace/Supplies sandbox
`/ping` в S03 нет.

### RC-02 - machine-readable emulator design: закрыто

JSON содержит 16 уникальных case rows: missing, malformed, expired, unknown/revoked `401`,
wrong-category `403`, read-only `401/403`, `429` без и с валидным retry header, timeout, DNS, `5xx`,
malformed success response, recovery, stale и end-to-end no-leakage. У каждой строки есть stimulus,
ожидаемый normalized state/effect и invariants; у всех execution status равен
`test_design_not_executed`.

Endpoint-specific `/ping` contract отдельно ограничен документированными `200/401/429`. `403`
привязан к permission failure business method, а не приписан `/ping` без источника. Ни sandbox, ни
local emulator фактически не исполнялись, и матрица этого не скрывает.

### RC-03 - `last_success_at` и recovery: закрыто

Prose и JSON используют один ключ истории:
`tenant_id + seller_id + capability + environment`. Missing/malformed credential, local expiry,
`401`, business-method `403`, `429`, timeout, DNS, `5xx` и malformed upstream response меняют
текущий state и `checked_at`, но сохраняют прежние `last_success_at` и `success_source`, включая
`null`.

Recovery принимает только валидный `200 /ping` shape либо успешный разрешённый business call,
заменяет историю временем нового успеха и не переносит sandbox-успех в production. `STALE` является
производным состоянием и не переписывает timestamps.

### RC-04 - credential/raw-upstream exclusion: закрыто

Официальная authorization-страница независимо подтверждает, что `X-Client-Secret` является
credential header наряду с `Authorization`. Denylist S03 охватывает оба заголовка, token/JWT
material, request headers/body, raw upstream headers/body/detail/URL/query/path/object identifiers и
производные credential data.

Запрет явно распространяется на persistent storage, cache/queue, application/audit logs, traces,
metrics, exception text/context/reporters, API/websocket, UI/browser storage/analytics, support и
pipeline/test evidence. Внутреннему adapter разрешена только allowlisted классификация с немедленным
отбрасыванием raw material. Scoped pipeline secret scan трёх S03 rework-артефактов прошёл.

## Проверки и closure matrix

| Область | Результат | Основание |
|---|---|---|
| Content sandbox `/ping` | pass | Явно опубликован в текущей WB Connection Check table. |
| Marketplace/Supplies sandbox `/ping` | pass | Base hosts известны, `/ping` не документирован и не выведен по шаблону. |
| Emulator handoff | pass | 16 unique machine rows, все `test_design_not_executed`. |
| Failure preservation | pass | Все перечисленные failure classes сохраняют timestamp/source прошлого успеха. |
| Recovery/environment isolation | pass | Только новый успех заменяет историю; sandbox не обновляет production. |
| Credential/raw-upstream redaction | pass | Материалы и все требуемые sinks входят в machine denylist. |
| Live calls / secrets | pass | Production/sandbox API, credentials и credential pages не использовались. |
| Machine integrity | pass | JSON parse/invariant checks и scoped evidence secret scan зелёные. |

## Остаточные обязательства следующих стадий

1. S09/Product должен утвердить stale TTL, expiring-soon window и видимость incident reference.
2. S13 должен связать status probe с тем же effective-secret resolution, который использует каждая
   production capability.
3. S15 должен материализовать и исполнить все 16 emulator cases без реальных ключей и live calls;
   S19 позднее обязан дать им runnable bindings.
4. Эти пункты не являются пропущенными research capability rows и не блокируют S04.

Предыдущий verdict `RESEARCH_REWORK` снят только после повторной независимой проверки rework commit.
Дополнительных S04 blocker нет.
