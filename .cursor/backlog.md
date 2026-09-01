# Autopilot backlog — уверенная выкатка + ЧЗ на уже оклеенные

> Цель заказчика: **выкладывать с 99% уверенностью**. Сегодня включить модуль ЧЗ
> «уже оклеенные» на бою **только для ФФ ПакХаб** (`vb7220047@gmail.com`,
> tenant `a69067c1-e6b3-458c-93d1-e5121aaa4966`) и **только после того, как все проверки зелёные**.

## Почему это делается (контекст, читать перед началом)

11.08.2026 на бой ушло шесть выкаток. Гейт был зелёный каждый раз, и при этом:
воркер лежал 40 минут, 1638 заказов не синхронизировались, клиенту в кабинет WB
насыпались пустые поставки. **Все поломки были на границе — с Wildberries, со схемой
БД, с топологией контейнеров, с памятью сервера.** Юнит-тесты проверяют середину,
которая не ломалась.

Три конкретных примера, которые задают требования к работе:

1. Признак ПВЗ читался из полей `canPvz` / `isPvz` — **таких полей в ответе WB нет**.
   Тесты были зелёные, потому что наш эмулятор отдавал те же несуществующие имена.
   Мок подтверждал неверное допущение. Настоящее поле — `isPickupPointShipmentAllowed`.
2. `SYNC_STATUS_BATCH_SIZE = 500` при том, что `POST /api/v3/orders/status` отбивал
   такие пачки. Мок съедал любой размер, поэтому тест не падал.
3. `supplyId` приходит в ответе `/api/v3/orders` и выбрасывался. Тест не падает —
   никто не утверждал, что его надо читать.

Вывод: **эмулятор не является источником истины. Источник истины — официальная
документация WB и живой ответ WB.**

## Правила для исполнителей

- Каждая проверка WB сверяется с **официальной документацией Wildberries**
  (https://dev.wildberries.ru/), а не с нашим эмулятором и не с комментариями в коде.
  Если код и документация расходятся — прав документ, расхождение фиксируется в отчёте.
- Сквозные сценарии гоняются **в реальном браузере по кнопкам, без заглушек** на фронте.
- Ничего не включать на бою до зелёного полного прогона.
- Не возвращать ПВЗ-гейт в `fbs_supply_validator_service` и отказ `insufficient_unpacked`
  в `fbs_picking_service` — это намеренные боевые изменения.
- Новых чипов и плашек в интерфейсе не добавлять — заказчик их не любит, объяснять текстом.

## Контракт КИЗ-бэклога

> **Контракт (читает orchestrator):**
> - Задача = строка таблицы; **id — первая ячейка**.
> - **Закрыто** = файл `.cursor/state/<id>.done` (создаёт orchestrator после verifier). **Таблицу не редактируем.**
> - **Заблокировано** = `.cursor/state/<id>.blocked` (3 фейла подряд).
> - **depends_on** — id-предшественники; задача runnable, когда все они `.done`.
> - **files** — что задача правит; две задачи с пересечением `files` **не** идут параллельно.
> - **gate** — команда проверки (зелёная = задача готова к `.done`).
> - Изоляция: каждый builder в `git worktree .cursor/wt/<id>`, коммит там.

## Активная задача: `tasks/fbs-kiz-manual-binding/TASK.md`

**Читать ТЗ целиком перед первой правкой.** Ветка `feat/fbs-kiz-manual-binding`.
Фронтенд (`frontend/`) в бэклог НЕ входит — его делает владелец сам. Ничего в `frontend/` не трогать.

Общий гейт бэка: `cd backend && ruff check . && mypy . && pytest -n auto`

## Задачи

| id | depends_on | files | gate | task |
|----|-----------|-------|------|------|
| WB-01 | - | docs/wb-api-contract.md | test -s docs/wb-api-contract.md | По официальной документации WB описать КАЖДЫЙ используемый нами метод: путь, категория прав, лимит частоты, максимальный размер пачки, все поля запроса и ответа с типами, семантика пагинации. Минимум: `/content/v2/get/cards/list`, `/api/v3/orders`, `/api/v3/orders/new`, `/api/v3/orders/status`, `/api/v3/supplies`, `/api/v3/supplies/{id}/orders`, `/api/v3/stocks/{warehouseId}`, `/api/v3/warehouses`, `/api/v3/offices`. Для каждого — что именно мы проверяем и почему. Это входной документ для WB-02. |
| WB-02 | WB-01 | backend/tests/contract/test_wb_contract.py | pytest backend/tests/contract -q | Контрактные тесты против ЖИВОГО WB настоящим ключом тестового селлера. Проверять форму, а не логику: существование полей, типы, предельный размер пачки (граница принимается / за границей отбивается), семантика курсора пагинации, наличие `supplyId` и `isPickupPointShipmentAllowed`. Ключ только из переменной окружения, в репозиторий не класть, в лог не печатать. Без ключа тесты пропускаются с внятным сообщением, а не падают. |
| WB-03 | WB-02 | backend/tests/contract/test_emulator_matches_wb.py | pytest backend/tests/contract -q | Сверка эмулятора с реальностью: для каждого метода из WB-01 сравнить набор и имена полей, которые отдаёт `wb_emulator`, с тем, что отдаёт живой WB. Расхождение = падение теста. Именно это поймало бы историю с `canPvz`. |
| WB-04 | WB-03 | .github/workflows/ci.yml | act -n -W .github/workflows/ci.yml \|\| true | Вшить контрактные тесты в CI отдельной обязательной ступенью ПЕРЕД деплоем. В выводе ступени печатать список проверенных методов и их лимиты, чтобы в логе CI было видно, что именно сверено. Деплой не стартует, пока ступень красная. |
| FLAG-01 | - | backend/app/core/settings.py | cd backend && ruff check . && mypy . | Ввести признак включения модуля ЧЗ «уже оклеенные» с разбором по арендаторам: выключен по умолчанию, включается точечно списком tenant_id. Значение читается из окружения, меняется без пересборки образа. |
| FLAG-02 | FLAG-01 | backend/app/api/fbs_orders.py | cd backend && pytest tests -k kiz -q | Закрыть признаком все точки входа модуля: пока выключен — эндпоинты недоступны и поведение ровно прежнее, никаких следов в ответах. Покрыть тестами оба состояния. Работа ведётся на ветке `feat/fbs-kiz-manual-binding`, её сначала свести с текущим `main`. |
| FLAG-03 | FLAG-02 | frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx | npm run build && npm run test:unit | Спрятать интерфейс модуля под тот же признак: выключен — экран выглядит как до правки. Признак приезжает с бэкенда, не хардкодится на фронте. |
| MIG-01 | FLAG-03 | backend/alembic/versions | cd backend && alembic heads | Накатить миграцию модуля ЧЗ на КОПИЮ боевой базы и убедиться, что `alembic heads` возвращает одну голову и подъём проходит с текущей боевой версии схемы. Миграция на реальных данных ещё ни разу не применялась — это единственное, что тяжело откатить. |
| ROLL-01 | WB-04,MIG-01 | docs/rollout-chz-pakhab.md | test -s docs/rollout-chz-pakhab.md | Регламент включения: выкатить код с выключенным признаком, убедиться по проверке после деплоя что всё живо, затем включить ТОЛЬКО для арендатора ПакХаб `a69067c1-e6b3-458c-93d1-e5121aaa4966`, наблюдать смену, порядок отката — переключение признака, а не откат деплоя. Что смотреть в логах и в базе, чтобы понять, что пошло не так. |

<!--
ПОРЯДОК ДЛЯ ОРКЕСТРАТОРА
Дорожка E2E снята 31.08.2026 вместе с браузерными тестами.
Дорожка FLAG независима от WB по файлам, но её MIG-01 обязан пройти до ROLL-01.
ROLL-01 — последняя, зависит от концов обеих дорожек.

ЧЕГО НЕ ДЕЛАТЬ
Не писать тест-кейс на каждую кнопку — такой набор разрастается, начинает падать
от каждой правки и его отключают. Ни один из багов 11.08 он бы не поймал.
Нужны немногие глубокие сквозные пути плюс жёсткие контрактные проверки по краям.
-->
| KIZ-01 | - | backend/alembic/versions,backend/app/models/fbs_order.py,backend/app/models/marking_code.py,backend/app/models/packaging_task.py | cd backend && ruff check . && mypy . && pytest | Миграция по §4.1–4.3 ТЗ: в `fbs_order_markings` добавить `tenant_id` (FK, NOT NULL, backfill из `fbs_orders`), `source` (default `operator`), `created_by_user_id`, `created_at`; партиальный уникальный индекс `(tenant_id, kind, value) WHERE meta_status <> 'rejected'`; в `marking_codes` — `source` (default `pool`); в `packaging_task_lines` — `qty_marking_external` (int, default 0). Проверить upgrade и downgrade. |
| KIZ-02 | KIZ-01 | backend/app/services/fbs_kiz_service.py,backend/app/api/fbs_kiz.py | cd backend && ruff check . && mypy . && pytest | Новый сервис + роутер. `GET /operations/fbs-orders/kiz/lookup` по §5.1: толерантный матч стикера (`sticker_code` → `wb_barcode` → `partA+partB`), ограничение по `supply_id`, ответ с `current_kiz` и `needs_confirmation`, 404 `sticker_not_found`, 409 `order_frozen`. Тесты в `backend/tests/test_fbs_kiz.py`. |
| KIZ-03 | KIZ-02 | backend/app/services/fbs_kiz_service.py,backend/app/api/fbs_kiz.py | cd backend && ruff check . && mypy . && pytest | `POST /kiz/validate` по §5.2 — проверка пары без сохранения: дубль по `fbs_order_markings` и `marking_codes`, заморозка заказа. Ничего не пишет в БД (покрыть тестом). |
| KIZ-04 | KIZ-03 | backend/app/services/fbs_kiz_service.py,backend/app/api/fbs_kiz.py | cd backend && ruff check . && mypy . && pytest | `POST /kiz/commit` по §5.3: каждая пара своей транзакцией, построчный результат; без `confirmed` на заказе с КИЗ → `needs_confirmation`; создание `MarkingCode(source='external_fbs', status='applied', packaging_task_line_id=…)` + событие `applied`; `FbsOrderMarking(source='operator')`; отправка в WB и синк статусов переиспользуют логику `scan_order_metadata`; инкремент `qty_marking_external`. Тест частичного успеха обязателен. |
| KIZ-05 | KIZ-04 | backend/app/services/fbs_kiz_service.py,backend/app/api/fbs_kiz.py | cd backend && ruff check . && mypy . && pytest | `DELETE /operations/fbs-orders/{order_id}/kiz` по §5.4: WB `delete_marketplace_order_meta` → гашение `FbsOrderMarking` → `MarkingCode.status='void'` + событие `voided` → декремент `qty_marking_external`. При ошибке WB не менять ничего (покрыть тестом). |
| KIZ-06 | KIZ-01 | backend/app/services/marking_code_service.py,backend/app/services/packaging_task_service.py,backend/app/services/fbs_workspace_service.py | cd backend && ruff check . && mypy . && pytest | **Принцип §1.4 ТЗ.** `assert_packaging_line_marking_done` сравнивает `qty_marking_printed + qty_marking_external` с `qty_done(line)`; `_lines_needing_marking` и печать-всего вычитают `qty_marking_external`; `_build_marking_pool` исключает заказы с уже привязанным sgtin. Обязательный тест — сценарий 150/100/50 из §1.4. |
| KIZ-07 | KIZ-04,KIZ-06 | backend/app/services/marking_code_service.py,backend/app/api/marking_codes.py | cd backend && ruff check . && mypy . && pytest | Аудит по §4.3: найти все выборки `marking_codes`, показывающие инвентарь/разбивку по статусам, и добавить фильтр `source = 'pool'`, чтобы внешние коды не искажали отчётность пула. В PR — список проверенных мест файл:строка, правки только там, где нужно. |
