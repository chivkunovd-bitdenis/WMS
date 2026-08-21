# BLG-I08 — S03 DOMAIN_RESEARCH: безопасная диагностика ключей WB

Дата снимка внешнего контракта: **2026-08-21**
Роль: `pipeline-ba`
Охват: существующая интеграция WB, только диагностика наличия, срока и пригодности ключа для нужной категории API. Создание, просмотр, замена, отзыв и ротация ключей; кабинеты учётных данных; live-проверки реальных ключей; production и deploy не исследовались и не выполнялись.

Машинная матрица: [`S03-wb-auth-capability-matrix.json`](S03-wb-auth-capability-matrix.json).

## Вывод

Безопасный статус нельзя свести к одному флагу «ключ есть». Для каждого селлера, реально используемой WMS capability (`content`, `supplies`, `marketplace`) и окружения нужно отдельно хранить: настроен ли секрет, результат последней проверки нужного домена, время проверки, время последнего успеха, срок по локально разобранной JWT metadata и последнюю безопасную категорию ошибки.

`GET /ping` нужного домена — официальный неразрушающий probe. `200` подтверждает, что запрос дошёл, токен валиден для URL и его категория совпадает с сервисом. Но WB прямо предупреждает: `/ping` **не проверяет доступность сервиса**. Для фактической готовности capability сильнее успешный реальный вызов этой capability; его время можно использовать как `last_success_at`, не создавая дополнительную нагрузку.

Любой неуспешный исход меняет текущий `state` и `checked_at`, но не очищает и не заменяет исторический `last_success_at`. Это правило одинаково для отсутствия или некорректного секрета, локального истечения срока, `401`, `403`, `429`, transport/DNS/timeout, `5xx` и malformed upstream response. Только новый доказанный успех заменяет `last_success_at` своим временем; sandbox-успех никогда не обновляет production-историю.

Значения `Authorization` и `X-Client-Secret`, любые части или маски токена, JWT identifiers (`id`, `sid`, `asid`, `for`), битовая маска категорий, request headers и произвольные raw request/response данные запрещены во всех диагностических sinks: persistence, cache/queue, logs, traces, metrics, exception text, API, UI/analytics, support payload и pipeline evidence. Оператор видит только allowlisted normalized status, безопасный incident reference и время. Управление ключом остаётся вне операторского сценария.

## Версия и официальные источники

| ID | Источник | Версия/дата источника | Уровень |
|---|---|---|---|
| WB-API-INFO | [Документация WB API: проверка подключения](https://dev.wildberries.ru/docs/openapi/api-information) | доступ 2026-08-21; OpenAPI без номера версии на странице | `official` |
| WB-AUTH-ERRORS | [Ошибки авторизации WB API и их решение](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-1936-7d84-a59d-41bcac098903/oshibki-avtorizatsii-wb-api-i-ikh-reshenie) | обновлено 2026-04-03 | `official` |
| WB-ERROR-CODES | [Расшифровка кодов ошибок WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-2cb0-781d-8921-deaf4a014a58/rasshifrovka-kodov-oshibok-wb-api) | обновлено 2026-04-06 | `official` |
| WB-JWT | [Декодирование и проверка токенов WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-1540-76f6-befe-726633dc11be/dekodirovanie-i-proverka-tokenov-wb-api) | обновлено 2026-04-03 | `official` |
| WB-SECURITY | [Безопасность данных продавца при работе с WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-1160-7ecf-91e9-abb10256bd0e/bezopasnost-dannykh-prodavtsa-pri-rabote-s-wb-api) | обновлено 2026-04-03 | `official` |
| WB-AUTH-SYSTEM | [Система авторизации WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-0d73-71e9-be3e-b2c44567470c/sistema-avtorizatsii-wb-api) | обновлено 2026-04-03 | `official` |
| WB-SANDBOX | [Ограничения тестового контура WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-24e3-7642-801f-e1f18c5fe708) | обновлено 2026-04-03 | `official` |
| WB-CATEGORIES | [Категории данных WB API](https://seller.wildberries.ru/instructions/ru/kz/material/wb-api-data-categories?recommended=true) | обновлено 2026-05-18 | `official` |
| WB-TOKEN-LIFECYCLE | [Как создать, обновить или удалить токен WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-01c8-7cba-95ca-1b95904886b7/kak-sozdat-obnovit-ili-udalit-token-wb-api) | обновлено 2026-04-03 | `official` |
| WB-STATUS | [Журнал событий WB API](https://dev.wildberries.ru/knowledge-base/articles/019d49a1-347a-7905-9c96-10ce8436b0e4/zhurnal-sobytii-wb-api) | обновлено 2026-04-03 | `official` |

Локальная граница WMS подтверждена чтением `backend/app/api/wildberries_integration.py`, `backend/app/services/wildberries_credentials_service.py`, `backend/app/services/wildberries_errors.py`, `frontend/src/screens/v2/WildberriesScreen.tsx` и `frontend/screens.registry.json` на base SHA `69c271678782d7dcfa39df97cd905cbee1678727`. Это `observed`, не доказательство внешнего поведения WB.

## Внешний контракт

### 1. Наличие и срок

- Обычный токен WB действует 180 дней. В JWT документированы `iat` и `exp`; тип находится в `acc`, категории — в `s`, тестовый признак — в `t`.
- JWT payload можно разобрать **только на backend** без передачи секрета в браузер или сторонний decoder. До успешного ответа WB это metadata claim, а не доказательство активности или отсутствия отзыва.
- Статус `EXPIRED` допустим, если `exp <= now` или WB вернул allowlisted причину `token expired`. Отзыв, смену владельца и блокировку кабинета нельзя надёжно различить только локальным JWT.
- Отсутствие зашифрованного значения означает `NOT_CONFIGURED`; это локальный факт, запрос к WB не нужен.

### 2. Probe по capability и окружению

| Capability WMS | Окружение | Endpoint `/ping` | Статус поддержки и provenance |
|---|---|---|---|
| `content` | `production` | `GET https://content-api.wildberries.ru/ping` | `official`: явно указан в WB-API-INFO |
| `content` | `sandbox` | `GET https://content-api-sandbox.wildberries.ru/ping` | `official`: явно указан в WB-API-INFO |
| `marketplace` | `production` | `GET https://marketplace-api.wildberries.ru/ping` | `official`: явно указан в WB-API-INFO |
| `marketplace` | `sandbox` | не установлен | `not_documented_for_ping`: sandbox base host опубликован в WB-SANDBOX, но `/ping` отсутствует в таблице WB-API-INFO; URL не выводится по шаблону |
| `supplies` | `production` | `GET https://supplies-api.wildberries.ru/ping` | `official`: явно указан в WB-API-INFO |
| `supplies` | `sandbox` | не установлен | `not_documented_for_ping`: sandbox base host опубликован в WB-SANDBOX, но `/ping` отсутствует в таблице WB-API-INFO; URL не выводится по шаблону |

Ни один production или sandbox endpoint в этом исследовании не вызывался. Строки фиксируют опубликованный контракт, а не разрешение на сетевую проверку. Для Marketplace и Supplies нельзя автоматически приписать `/ping` к известному sandbox base host: до появления официального источника такой probe имеет статус `not_documented_for_ping`.

Ответ успеха документирован как JSON с `TS` и `Status: OK`. Probe принимает `Authorization: Bearer <token>` только на backend. Максимум — 3 запроса за 30 секунд отдельно для каждого варианта `/ping`; WB предупреждает, что автоматизация может вызвать временную блокировку. Следствие для WMS: кэш не менее 30 секунд, single-flight на `tenant + seller + capability`, ручной refresh с debounce, без polling-цикла и с соблюдением `Retry-After`/backoff при `429`.

`/ping` не доказывает право записи. Нельзя выполнять искусственную POST/PATCH/DELETE операцию ради health-check. Право записи подтверждается либо безопасной проверяемой metadata после серверного разбора, либо результатом реальной разрешённой бизнес-операции. Пока такого доказательства нет, UI показывает `WRITE_ACCESS_UNKNOWN`, а не «всё работает».

### 3. Нормализация ошибок

| Наблюдение | Безопасный код WMS | Что можно сказать оператору | Что нельзя утверждать |
|---|---|---|---|
| секрет отсутствует | `NOT_CONFIGURED` | «Подключение WB не настроено. Передайте ответственному за интеграции.» | что WB недоступен |
| `exp <= now` или allowlisted `token expired` | `EXPIRED` | «Срок ключа истёк. Нужен ответственный сотрудник.» | что ключ отозван |
| `401`, причина не доказана | `AUTH_REJECTED` | «WB не принял ключ. Повтор операции не поможет до проверки подключения.» | «ключ точно отозван» или «кабинет заблокирован» |
| `403` на нужном методе | `INSUFFICIENT_ACCESS` | «Ключ работает, но не хватает категории или права операции.» | какая именно настройка неверна без подтверждённой detail/category |
| `429` | `CHECK_DELAYED` | «Проверка временно отложена из-за лимита WB.» | что ключ неисправен |
| transport/DNS/timeout | `NETWORK_UNAVAILABLE` | «Не удалось связаться с WB; сохранено время последнего успешного подключения.» | что ключ просрочен |
| HTTP `5xx` или malformed response | `WB_UNAVAILABLE` | «WB временно не отвечает корректно; сохранено время последнего успешного подключения.» | что ключ неисправен |
| `200 /ping` | `CONNECTED` | «Подключение этой категории подтверждено» + время | что write-операции разрешены или весь WB доступен |
| проверка старше Product TTL | `STALE` | «Статус давно не проверялся» + `last_success_at` | что прежний успех актуален сейчас |

WB документирует два формата error body. Внутренний адаптер может разобрать `detail`, `requestId`, `code`, но наружу допускаются только allowlisted normalized code, безопасный incident reference и время. Произвольный `detail` нельзя показывать напрямую: внешний текст не является стабильным UI-контрактом и может содержать нежелательные данные.

### 4. Роли и tenant-граница

- Статус вычисляется и хранится отдельно по `tenant_id + seller_id + capability`; результат одного селлера нельзя переиспользовать для другого.
- Оператор имеет read-only доступ только к бизнес-статусу и инструкции. Он не видит поля ввода, secret metadata или действия удаления/замены.
- Создание и удаление токена WB официально относится к владельцу профиля. В WMS исправление адресуется роли «ответственный за интеграцию/владелец кабинета», а не оператору склада.
- `last_checked_at`, `last_success_at`, `expires_at`, `retry_after_at` — ISO 8601 UTC. В интерфейсе время локализуется, но API сохраняет timezone.
- Сохраняется источник успеха: `ping` либо `business_call`. Успешный business call сильнее probe для конкретной capability.

### 5. Переходы `last_success_at` и recovery

- Ключ истории: `tenant_id + seller_id + capability + environment`; успех другого селлера, capability или окружения не переносится.
- Любая неуспешная проверка обновляет только текущий `state`, `checked_at`, безопасный `incident_ref` и при необходимости `retry_after_at`. Предыдущее значение `last_success_at` и его `success_source` сохраняются без изменений, включая `null`, если успеха ещё не было.
- Время неуспешной проверки никогда не записывается в `last_success_at`. В UI исторический успех показывается рядом с текущей ошибкой именно как прошлый факт, а не как признак текущей работоспособности.
- Recovery — следующий валидный `200 /ping` либо разрешённый успешный business call — переводит текущий state в `CONNECTED`, очищает текущую безопасную ошибку и заменяет `last_success_at` временем этого успеха.
- `STALE` вычисляется по Product TTL и не меняет ни `checked_at`, ни `last_success_at`.

## Минимальный безопасный response contract для следующих стадий

Это исследовательская граница, не утверждённый Product/API contract:

```json
{
  "capabilities": [
    {
      "capability": "marketplace",
      "environment": "production",
      "configured": true,
      "state": "CONNECTED",
      "checked_at": "2026-08-21T00:00:00Z",
      "last_success_at": "2026-08-21T00:00:00Z",
      "success_source": "ping",
      "expires_at": "2026-09-15T12:00:00Z",
      "write_access": "unknown",
      "retry_after_at": null,
      "incident_ref": null
    }
  ]
}
```

Разрешённый диагностический payload ограничен normalized state/code, `configured`, capability/environment, безопасным `incident_ref` и timestamps. Запрещённые данные: `token`, token mask/fragment/fingerprint, `Authorization`, `X-Client-Secret`, JWT/JWT payload, `id`, `sid`, `asid`, `for`, category bitmask, request headers/body, raw response headers/body/detail, upstream URL/query/path/object identifiers и любые производные, позволяющие восстановить credential material.

Запрет действует сквозным образом для persistent storage, cache, queue/event payloads, logs/audit logs, traces/spans, metric values/labels, exception message/stack/context, API response, UI state/DOM/analytics, support export/ticket и pipeline receipt/evidence/screenshots. Внутренний адаптер может разобрать только allowlisted причину и обязан немедленно отбросить raw payload до выхода из своего процесса; исключения формируются уже из sanitized normalized result.

## Applicability audit обязательных lanes S03

| Lane из PIPELINE-RU | Применимость | Результат |
|---|---|---|
| официальная API-документация, версия и дата | да | источники и snapshot date зафиксированы |
| инструкции продавцу и оператору | да | владелец управляет токеном; оператор получает read-only диагноз |
| FBS/FBO и полный автомат статусов | нет | задача не меняет статусы заказов/поставок; исследуется только auth capability |
| каталог, заказы, остатки, резервы, маркировка, печать, отгрузка, отмены, возвраты | узко | покрыто через три используемых WMS capability; бизнес-контракты методов не меняются |
| pagination | нет | `/ping` не пагинируется |
| rate limits, batch, partial success, retries, webhooks/polling | частично | rate limit/retry/cache покрыты; batch/partial/webhooks к одиночному probe неприменимы |
| боли пользователей | да | повтор бесполезных действий устранён разделением auth/permission/transient состояний |
| competitor workflows/screens | нет | это не новый домен/модуль; сравнение UI относится к S09, не к внешнему контракту |
| безопасность, роли, tenant, селлер и склад | да | no-secret response, seller/tenant isolation и read-only operator boundary зафиксированы; warehouse неприменим к ключу |
| объёмные и аварийные режимы | да | single-flight/cache, `429`, network, `5xx`, stale/last-known-success покрыты |
| окружения и endpoint provenance | да | production и sandbox перечислены отдельно; неподтверждённые `/ping` не выводятся из base host |
| emulator test design | да | машинные `test_design_not_executed` rows покрывают ошибки, recovery, stale и no-leakage; исполнение остаётся за S15 |
| исторический успех и recovery | да | единый preserve-rule задан для всех failure outcomes и отдельного success recovery |
| сквозная redaction | да | credential/raw-upstream denylist применён ко всем storage, observability, API/UI/support/evidence sinks |

Необработанных применимых capability rows: **0**.

## Вопросы для S04 и следующих стадий

1. **Non-blocking, S04:** официальная общая статья относит отсутствие права записи к `403`, но локальный WMS-код содержит наблюдение, что отдельные Marketplace write-методы возвращали `401` с `read-only` detail. Критик должен потребовать emulator contract cases для обоих вариантов; UI должен нормализовать их в `INSUFFICIENT_ACCESS`, не полагаясь только на HTTP-код.
2. **Non-blocking, S04/S13:** текущий WMS имеет отдельные слоты и fallback между content/supplies/marketplace. Следует проверять эффективный секрет той же логикой resolution, которой пользуется конкретная capability, иначе зелёный статус может относиться не к реально используемому ключу.
3. **Non-blocking, S09/Product:** Product задаёт TTL для `STALE`, окно `EXPIRING_SOON` и кому виден incident reference. Исследование не подменяет это решение.
4. **Required later, S15:** исполнить без реальных ключей machine-readable emulator cases из матрицы. В S03 они имеют только статус `test_design_not_executed`; это не sandbox/emulator proof.

## Решение S03

`RESEARCH_READY`: rework S03 закрывает environment provenance, machine-readable emulator design, all-failure preservation/recovery и end-to-end redaction. Production/sandbox API, live credentials и credential pages не использовались. Это рекомендация автора, а не само-приёмка; обязателен новый независимый S04.
