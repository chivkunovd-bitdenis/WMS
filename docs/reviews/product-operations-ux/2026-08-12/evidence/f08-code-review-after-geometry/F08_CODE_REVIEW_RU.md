# F08 Code Review After Geometry Rework

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Code Review Agent.
Статус: `CODE_REVIEW_PASSED`.

Код не редактировался. Проверка выполнена как review diff после geometry rework.

## Scope

Проверены только файлы из scope:

- `frontend/src/screens/v2/SellerProductsStockScreen.tsx`
- `frontend/src/screens/v2/FfProductsCatalogScreen.tsx`
- `frontend/tests-e2e/seller-stock-directions.spec.ts`

Также прочитаны обязательные правила:

- `AGENTS.md`
- `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`

## Что проверено

1. Diff по seller stock screen после rework.
2. Diff по FF catalog screen после rework.
3. Diff e2e-сценария `seller-stock-directions.spec.ts`.
4. Точечный поиск по `Лимит`, `seller-fbs-limit`, `Включить всем`, raw status/code labels и техническим словам в scope.
5. `git diff --check` по трем scope-файлам.

Полный headed/browser QA не запускался в этом review-проходе: по gate-протоколу Code Review не заменяет независимый Browser Product QA. Dev already reported headed QA passed; этот review проверяет кодовую границу и покрытие.

## Findings

Blockers не найдено.

Seller table после rework остается в утвержденной compact-модели:

- отдельная колонка `Лимит` не возвращена;
- UI-control `seller-fbs-limit-*` удален из screen code;
- bulk `Включить всем` отсутствует;
- массовое действие осталось только fail-closed: `Пауза публикации всем`;
- FBS switch больше не создает FBS-пул и disabled при `stock_fbs <= 0`;
- visible statuses пользовательские: `FBS-пул не выделен`, `Публикуется в WB`, `Публикация на паузе`, `Не удалось отправить остаток в WB`;
- raw status labels вроде `pending`, `confirmed`, `conflict`, `directions_exceed_stock` не выводятся в UI.

CRUD направлений в seller Drawer соответствует F08 rework:

- create идет через `POST /products/{productId}/stock-directions`;
- edit идет через `PATCH /products/stock-directions/{directionId}` и не создает новую строку;
- delete защищен confirm-dialog, cancel не вызывает DELETE;
- форма edit/create очищается после success;
- длинные название товара, направление и комментарий ограничены `noWrap` или line clamp, подробности не выносятся в таблицу.

Geometry rework выглядит scoped and intentional:

- seller table переведена на `tableLayout: fixed`, процентный `colgroup`, compact cell padding и `overflowX: hidden`;
- identity-поля и длинные штрихкоды не должны расширять таблицу;
- FBS publication cell стал one-control compact cell вместо switch + limit + chip/status stack;
- FF catalog получил fixed layout, compact columns, no-wrap identity fields;
- FF distribution popover получил `maxWidth: calc(100vw - 32px)` и `overflowX: hidden`, что прямо закрывает прошлый global overflow риск;
- FF catalog остается read-only для направлений: create/edit/delete controls там не появились.

Риска явного конфликта с F22 safe sync в этом diff не найдено:

- отсутствие FBS-пула не дает включить per-row publication switch;
- bulk enable не возвращен;
- UI не добавляет `Лимит`, raw JSON, raw status code или technical chip;
- FBS-пул остается источником публикации, а не общий FF/FBO остаток.

Остаточные замечания не блокируют Code Review:

- В типе `WbCatalogRow` остаются поля `fbs_stock_limit` и `fbs_published_amount`, но они не выводятся пользователю. Это контракт данных строки, не возврат UI-лимита.
- Code Review не доказывает реальную headed geometry после rework. Это обязанность следующего Browser Product QA gate.

## Test Review

`frontend/tests-e2e/seller-stock-directions.spec.ts` покрывает основные F08 действия и geometry regression:

- создает seller, товар и физический остаток через inbound flow;
- открывает seller products screen;
- проверяет отсутствие `Лимит` и `seller-fbs-limit-*`;
- проверяет отсутствие bulk `Включить всем`;
- создает FBS-направление;
- создает reserve-направление;
- редактирует reserve через PATCH;
- переводит reserve в FBS-пул;
- проверяет human error вместо raw `directions_exceed_stock`;
- проверяет cancel delete без DELETE;
- подтверждает delete ровно одним DELETE;
- проверяет пересчет `FBS`, `резервы`, `Свободный FBO`;
- снимает geometry metrics: global scroll width, body/document scroll width, table scroll width, table container width, row height.

Coverage достаточно для Code Review. Независимый Browser Product QA все равно должен руками открыть UI и подтвердить реальную 1280 geometry по протоколу.

## Commands

Read-only / targeted:

```bash
git diff -- frontend/src/screens/v2/SellerProductsStockScreen.tsx
git diff -- frontend/src/screens/v2/FfProductsCatalogScreen.tsx
git diff -- frontend/tests-e2e/seller-stock-directions.spec.ts
rg -n "Лимит|seller-fbs-limit|Включить всем|pending|confirmed|conflict|error|nmID|nm_id|WB nm|Технический|debug|internal|undefined|null|NaN" frontend/src/screens/v2/SellerProductsStockScreen.tsx frontend/src/screens/v2/FfProductsCatalogScreen.tsx frontend/tests-e2e/seller-stock-directions.spec.ts
git diff --check -- frontend/src/screens/v2/SellerProductsStockScreen.tsx frontend/src/screens/v2/FfProductsCatalogScreen.tsx frontend/tests-e2e/seller-stock-directions.spec.ts
```

`git diff --check` по scope-файлам прошел без whitespace errors.

## Verdict

`CODE_REVIEW_PASSED`

Можно запускать независимый Browser Product QA для F08 после geometry rework.
