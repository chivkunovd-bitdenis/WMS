# BLG-I02 - S04 RESEARCH_CRITIC

## Паспорт повторного review

- Роль: `pipeline-reviewer`, независимый `research-critic`.
- Проверенный rework commit: `8b30c37aca8c51e06a8702ba14e36cfedfde2387`.
- Модельный класс dispatch: `gpt-5.6-sol`, `expensive`.
- Дата повторной проверки: `2026-08-21`, Europe/Moscow.
- Вход: `S03-EXTERNAL-CONTRACT.md`, предыдущий S04 verdict, controller packet и rework diff.
- Независимая внешняя сверка: публичные страницы WB FBS OpenAPI и журнала изменений открыты
  без авторизации в видимом браузере; Marketplace production и sandbox API не вызывались.
- Секреты, кабинеты учётных данных, deploy и application code не затрагивались.
- Verdict: `RESEARCH_PASSED`.

## Итог

Rework закрывает все четыре блокирующие находки предыдущего S04. Контракт теперь разделяет одну
обязательную запись результата попытки и `0..N` реально возвращённых verdict rows. Поэтому
bodyless `204`, transport/error outcomes и частичный `409 MetaValidationFail` сохраняются без
вымышленных `meta_key` или `decision`.

Текущий официальный FBS OpenAPI независимо подтверждает, что `409` возвращает только заказы, чьи
идентификаторы не прошли или ещё не завершили проверку. S03 сохраняет такой ответ append-only как
отрицательный результат конкретной попытки и не заменяет им полную preflight-проекцию. Живой DOM
также подтверждает актуальное правило `all 4XX x10`, а журнал изменений связывает `metaDetails`,
deliver validation и удаление legacy `meta` с FBS-записью от `31.03.2026`, DOM id `note-500`.

Исследование достаточно для перехода к Product-контракту S11. Оно не выполняет live-вызовы, не
использует секреты и не выдаёт будущий emulator proof за уже полученное доказательство.

## Независимая проверка blocker

### RC-01 - `409 MetaValidationFail` как partial append-only result: закрыто

В live-схеме `PATCH /api/v3/supplies/{supplyId}/deliver` поле `data.orders[]` описано как массив
заказов, чьи идентификаторы маркировки не прошли или ещё не завершили validation. Схема не обещает
полный набор положительных заказов или всех ключей поставки; официальный пример допускает пустой
`orders[]` при `code=MetaValidationFail`.

Разделы 3.2, 5.1, 5.2 и 6 S03 теперь требуют сохранить attempt, raw body и только реально
вернувшиеся detail rows, заблокировать эту попытку и не удалять, не заполнять и не заменять
отсутствующие строки. Семантики replacement больше нет.

### RC-02 - attempt outcome и `0..N` detail rows: закрыто

Раздел 5 задаёт два append-only уровня:

- ровно один attempt outcome для каждого preflight/deliver вызова, включая timeout, connection
  error, malformed response и bodyless HTTP response;
- ноль или больше detail rows только для фактических элементов `metaDetails[]` от WB.

Для `204` S03 сохраняет только `DELIVER_ACCEPTED` на attempt-level, оставляет response body
отсутствующим и прямо запрещает synthetic per-key `CONFIRMED_ALLOW`. Для no-body failures
`http_status`, response hash/payload и detail rows имеют честную nullable/zero cardinality.

### RC-03 - rate-limit accounting: закрыто

На текущей публичной странице
`https://dev.wildberries.ru/en/docs/openapi/orders-fbs` в видимом DOM для обоих затронутых методов
воспроизведено правило: `One request with 4XX response codes is counted as 10 requests.`

Поисковый индекс той же страницы ещё показывал старую формулировку только про `409`, поэтому он не
использован как текущий оракул. S03 правильно фиксирует более новый live-контракт `all 4XX x10` и
сохраняет runtime-защиту по фактическим `X-Ratelimit-*` headers.

### RC-04 - provenance release note от 31.03.2026: закрыто

Публичный журнал `https://dev.wildberries.ru/en/release-notes?id=188` содержит FBS-запись
`Changes in FBS Orders Methods` от `03/31/2026`; её DOM id равен `note-500`. Запись сообщает о
validation при deliver, добавлении `metaDetails` в `POST /api/marketplace/v3/orders/meta` и
удалении deprecated `meta` 30 апреля. Запись от `03/26/2026` относится к Seller User Management.

Source row S03 теперь ссылается на канонический журнал, правильную дату и правильное содержание.

## Проверка сохранённых решений и safety

- Полный текущий набор `decision` независимо воспроизведён в live-схеме.
- `deadlineExceeded` остаётся WB-eligible, но validation может позднее пройти или упасть; S03
  сохраняет Product question и блокирует dispatch до S11.
- `gtin.required` и `expiration.required` всё ещё ошибочно находятся под положительным заголовком,
  хотя описание говорит `Validation failed`; fail-closed mapping S03 на `BLOCK` корректен.
- Неизвестный `decision` сохраняется raw и получает `UNKNOWN_BLOCK`, а не optimistic allow.
- Внешние API, sandbox, production, токены и кабинеты не использовались; raw КИЗ и секреты в
  review artifact не записывались.

## Closure matrix

| Область | Результат | Основание |
|---|---|---|
| Attempt vs verdict rows | pass | Один attempt плюс `0..N` только реальных detail rows. |
| `409 MetaValidationFail` | pass | Append-only partial negative result, без replacement или synthesis. |
| Bodyless `204` | pass | Только `DELIVER_ACCEPTED`, без per-key decisions. |
| Rate limit | pass | Текущий live DOM подтверждает `all 4XX x10`. |
| Release-note provenance | pass | `31.03.2026`, `note-500`, FBS change; 26.03 исключена. |
| Safety and factuality | pass | Live calls/secrets отсутствуют, unknown и ambiguous states fail-closed. |

## Остаточные обязательства следующих стадий

1. S11 должен явно утвердить блокировку `deadlineExceeded` и Product policy для optional marking.
2. S13 должен определить retention защищённого raw payload, atomic persistence, current marking
   revision и crash recovery между внешним ответом и локальным commit.
3. S15 должен материализовать emulator cases для enum, omissions, duplicates, stale revision,
   timeout/`429`/`5xx`, `409 MetaValidationFail` и bodyless `204`.

Эти пункты уже переданы владельцам следующих стадий и не являются открытыми S03 research gaps.
Дополнительных S04 blocker нет.
