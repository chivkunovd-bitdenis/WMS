# BLG-D07 — S04 RESEARCH_CRITIC

## Паспорт

- Роль: `pipeline-reviewer`, независимый `research-critic`.
- Модельный класс: `gpt-5.6-sol`, `expensive`.
- Дата проверки: `2026-08-21`, Europe/Moscow.
- Проверенный вход: `S03-DOMAIN-RESEARCH.md`, `S03-capability-matrix.json`, официальный WB FBS
  OpenAPI, FBS guide, sandbox documentation и локальный status worker.
- Внешние операции: production/sandbox API не вызывались; секреты и авторизованные кабинеты не
  использовались.
- Verdict: `RESEARCH_REWORK`.

## Итог критика

S03 правильно нашёл основной бизнес-дефект: локальный `sorted` исключён из последующей сверки, хотя
официальная песочница показывает переходы после `sorted`. Верно зафиксированы размер запроса до 1000
ID, общий FBS rate limit 300 запросов в минуту с интервалом 200 мс и burst 20, а также риск
batch-to-single amplification.

Но исследование пока нельзя пропустить дальше. В нём неполный и внутренне противоречивый контракт
статусов, неверно посчитана цена `4XX`, а перечисленные sandbox cases являются только выпиской из
документации, не proof исполнения. Эти ошибки напрямую влияют на mapping, retry policy и расчёт
нагрузки worker.

## Блокирующие находки

### RC-01 — статусная модель не закрыта

Официальная английская FBS OpenAPI-страница перечисляет `postponed_delivery`, но S03 исключает его из
таблицы и называет только признаком старого снимка. При этом S03 добавляет `cancel_carrier` и
`canceled_by_carrier`, которые независимый поиск в доступных официальных FBS OpenAPI/guide snapshots
не подтвердил. Русская и английская страницы также расходятся по части enum и error responses.

До pass нужен один датированный, воспроизводимый contract snapshot или сохранённые точные выдержки,
которые объясняют языковой/version skew и дают полный список `supplierStatus`/`wbStatus`. Неизвестные
значения всё равно должны сохраняться как raw и не запускать необратимые действия.

Источники:

- https://dev.wildberries.ru/en/docs/openapi/orders-fbs
- https://dev.wildberries.ru/ru/openapi/orders-fbs
- https://dev.wildberries.ru/knowledge-base/articles/019d49a4-0771-7571-aea9-11d5b597f34c/zakazy-fbs

### RC-02 — неверный учёт `4XX`

S03 утверждает, что любой `4XX` считается как десять запросов. Официальная FBS документация говорит
иначе: как десять запросов учитывается ответ `409`. Нельзя переносить этот множитель на `400`, `401`,
`402`, `403` или `429` без отдельного источника. Batch-to-single fallback по-прежнему опасен: auth,
rate-limit или transport failure может превратить один batch в сотни обычных запросов, но расчёт
бюджета должен быть фактическим.

Отдельно нужно согласовать response matrix: доступные snapshots показывают `402` в английской версии
и `404` в русской, тогда как S03 фиксирует `402`, но не `404`. Без versioned snapshot этот список
нельзя объявлять исчерпывающим.

### RC-03 — sandbox cases не являются исполненным proof

Официальная песочница действительно документирует цепочку `sorted -> ready_for_pickup -> sold` и
варианты `canceled_by_client`/`defect`; лимит Marketplace sandbox — 1 запрос в секунду суммарно для
всех методов. Но S03 не запускал песочницу и не приложил emulator output. Поэтому таблица
`WB-FBS-STATUS-01..10` является test design, а не доказательством исполнения.

Для carrier statuses и `postponed_delivery` в найденной sandbox matrix нет переходов. S03 должен
явно отделить документированные переходы от непокрытых и передать в S15 executable local-emulator
cases: полный/частичный `200`, пропущенный ID, дубликат ID, неизвестный status, `400/401/402/403/404`,
`429`, timeout/`5XX`, restart/replay и batch-to-single cap. Никакой live WB вызов для rework не нужен.

Источники:

- https://dev.wildberries.ru/sandbox
- https://dev.wildberries.ru/en/openapi-other/sandbox-environment

## Проверенные области

| Область | Вердикт критика | Обоснование |
|---|---|---|
| Endpoint | pass | `POST /api/v3/orders/status` подтверждён официально. |
| Request size | pass с уточнением | `1..1000` ID подтверждены OpenAPI/guide; обязательная уникальность ID в S03 не подкреплена отдельным официальным claim. |
| Rate limit | pass | 300/min, 200 мс, burst 20 на seller account для общей группы FBS methods. |
| `4XX` accounting | rework | Вес x10 относится к `409`, не ко всем `4XX`. |
| Status enum | rework | Пропущен `postponed_delivery`; carrier cancel values не имеют воспроизводимого provenance. |
| Webhook | pass | Общий WB webhook catalog не перечисляет событие изменения статуса FBS; polling остаётся источником reconciliation. |
| Sandbox/emulator | rework | Документация есть, исполненного proof и покрытия недоступных sandbox transitions нет. |
| Stale-status edges | rework | Риски найдены, но terminal/reopen policy и executable cases не закрыты. |

## Stale-status edge cases, обязательные для следующих артефактов

1. `sorted` сейчас попадает в `STATUSES_EXCLUDED_FROM_WB_SYNC`, поэтому WMS никогда не увидит
   последующие `ready_for_pickup`, `sold`, `canceled_by_client` или `defect`.
2. Любой локальный `done`, `cancelled` или `defect` также исключается навсегда. Product должен назвать
   допустима ли поздняя коррекция WB после такого статуса; до решения нельзя считать terminal policy
   фактом внешнего контракта.
3. Worker каждый cycle снова сортирует по `created_at_wb` и ограничивается 10 000 строками. Без
   freshness ordering/cursor хвост старше лимита может не получить сверку.
4. Ответ `200` без части ID не должен обновлять их success time. Дублированный ID в ответе сейчас
   молча перезаписывается последней строкой в `by_id`, поэтому нужен отдельный invalid-response case.
5. Неизвестный raw status должен сохраняться и сигнализироваться, но не снимать резерв и не менять
   локальное состояние необратимо.
6. `last_wb_sync_at` должен означать валидную строку именно этого заказа, а не факт успешного HTTP или
   неполного seller cycle; attempt time, per-order success и full-cycle success должны различаться.

## Условие снятия blocker

Автор S03 должен:

1. исправить status enum и приложить воспроизводимый dated provenance для спорных значений;
2. заменить утверждение про все `4XX` на точное правило `409 x10` и согласовать error matrix;
3. отделить documented sandbox scenarios от executed proof;
4. передать в S15 явную emulator coverage matrix для partial/malformed responses, rate/error classes,
   неизвестных и поздно меняющихся статусов;
5. оставить `unhandled_applicable_rows: 0` только после закрытия этих строк.

После этого нужен новый независимый запуск S04. До выполнения условия `RESEARCH_PASSED` запрещён.
