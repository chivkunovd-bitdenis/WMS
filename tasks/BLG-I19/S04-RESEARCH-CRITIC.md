# BLG-I19 — S04 RESEARCH_CRITIC

## Паспорт

- Роль: `pipeline-reviewer`, независимый `research-critic`.
- Модельный класс: `gpt-5.6-sol`, `expensive`.
- Дата проверки: `2026-08-21`, Europe/Moscow.
- Проверенный вход: `S03-WB-RATE-LIMIT-RESEARCH.md`,
  `S03-wb-rate-limit-capability-matrix.json`, текущая публичная FBS OpenAPI-страница WB,
  официальная статья о rate limits и release notes по `metaDetails`.
- Внешние операции: production/sandbox API не вызывались; секреты, токены и кабинеты учётных
  данных не использовались.
- Verdict: `RESEARCH_REWORK`.

## Итог критика

S03 правильно установил основную форму интеграции: FBS не документирует batch-delete, поэтому
массовое снятие выполняется как очередь одиночных `DELETE`; чтение принимает до 100 `orderId` и
делит с удалением квоту 300 запросов в минуту, интервал 200 мс и burst 20. Верно названы
`X-Ratelimit-Retry`, конечный retry, неоднозначный результат timeout/`5xx`, обязательный read-back
до повторного `DELETE`, отсутствие idempotency key и durable partial progress.

Но исследование пока нельзя пропустить дальше. Текущая canonical OpenAPI отличается от принятого в
S03 снимка в расчёте `4XX`, а контракт не закрывает главную бизнес-единицу задачи: один `orderId`
может содержать массив до 100 `sgtin`, тогда как `DELETE` удаляет значение ключа целиком и не умеет
снимать один выбранный код. Без этого WMS может считать успешно обработанным один код после операции,
которая фактически сняла у WB весь набор кодов заказа.

## Блокирующие находки

### RC-01 — текущий множитель относится ко всем `4XX`

На публичной canonical FBS OpenAPI-странице, открытой 2026-08-21, блоки получения и удаления
идентификаторов маркировки говорят: один запрос с кодами ответов `4XX` учитывается как 10 запросов.
S03 ограничивает этот расход только ответом `409` и поэтому недооценивает влияние `400`, `401`,
`402`, `403`, `404`, `429` и других `4XX` на общую seller-account квоту get/delete.

До pass нужно обновить prose и capability matrix, зафиксировать датированный current snapshot и
передать в S13/S15 единое правило: любой документированный `4XX` этой группы расходует 10 единиц,
а limiter учитывает фактические headers и не предполагает, что terminal-ошибка бесплатна для
соседних элементов.

Источник: https://dev.wildberries.ru/docs/openapi/orders-fbs

### RC-02 — DELETE снимает весь ключ, а progress описан только по заказу

Текущий контракт позволяет передать в `PUT /api/v3/orders/{orderId}/meta/sgtin` от 1 до 100 кодов,
но `DELETE /api/v3/orders/{orderId}/meta?key=sgtin` принимает только `orderId` и один `key`. Параметра
конкретного КИЗ в DELETE нет: удаляется значение `sgtin` целиком. S03 хранит state machine по
`orderId` и один hash ожидаемого КИЗ, хотя business meaning требует прогресс по каждому коду.

До pass S03 должен явно выбрать и доказать одну из двух семантик:

1. операция разрешена только для полного снятия всех известных `sgtin` заказа; тогда каждый код
   получает связанный per-code outcome, а `204`/read-back подтверждает отсутствие всего ожидаемого
   набора, включая защиту от неизвестных или конкурентно добавленных кодов;
2. требуется снятие подмножества; тогда одиночного DELETE недостаточно, а delete-all + повторный PUT
   оставшихся кодов является отдельной неатомарной операцией с crash window, read-back, rollback/
   manual-repair contract и двумя разными rate-limit groups. Это требует явного Product/Architecture
   решения, а не может быть скрыто внутри retry worker.

Источник: https://dev.wildberries.ru/docs/openapi/orders-fbs

### RC-03 — sandbox pacing пропущен из исполнимого контракта

Canonical FBS OpenAPI отдельно указывает для песочницы максимум 1 запрос в секунду суммарно для всех
методов Маркетплейса. S03 откладывает sandbox/emulator на S15/S23, но не передаёт этот предел и
описывает только production/token profiles. Live sandbox по-прежнему не требуется и не разрешён;
однако emulator/contract cases должны доказать отдельный sandbox limiter, чтобы тестовый прогон не
использовал production pacing 200 мс.

Источник: https://dev.wildberries.ru/docs/openapi/orders-fbs

## Подтверждённые области

| Область | Вердикт критика | Обоснование |
|---|---|---|
| FBS DELETE | pass с rework семантики | Endpoint одиночный, `204` без тела; batch-delete не найден. |
| Production rate limit | pass | Общая get/delete группа: 300/мин, 200 мс, burst 20 на аккаунт продавца. |
| `4XX` accounting | rework | Current canonical page указывает x10 для всех `4XX`, а не только `409`. |
| `429` headers | pass | `X-Ratelimit-Retry` задаёт минимальную паузу; повтор раньше запрещён. |
| Timeout/`5xx` | pass | Outcome неоднозначен; read-back предшествует повторному DELETE и local clear. |
| Batch read | pass | `POST /api/marketplace/v3/orders/meta`, не более 100 ID, та же get/delete квота. |
| Read-back schema | pass с dependency | Current `metaDetails` содержит `key`, `value`, `decision`; точное сравнение revision остаётся у BLG-I02. |
| Idempotency | pass | Idempotency key и гарантия ответа на повторный DELETE не документированы. |
| Partial progress | rework | По заказам описан верно, но обязательный per-code outcome отсутствует. |
| Sandbox/emulator | rework | Не передан общий sandbox limit 1 запрос/с для Marketplace. |

## Условие снятия blocker

Автор S03 должен:

1. заменить `409 x10` на актуальное правило `all 4XX x10` во всех артефактах и cases;
2. зафиксировать delete-all семантику `sgtin` и определить полный набор per-code outcomes;
3. если допускается снятие подмножества кодов, оформить это как отдельный неатомарный внешний
   contract с read-back/recovery либо вынести на явный Product/Architecture blocker;
4. добавить sandbox pacing 1 запрос/с в capability matrix и будущие emulator cases;
5. оставить `unprocessed_applicable_rows: 0` только после закрытия этих строк.

После rework требуется новый независимый запуск S04. До него `RESEARCH_PASSED` запрещён.
