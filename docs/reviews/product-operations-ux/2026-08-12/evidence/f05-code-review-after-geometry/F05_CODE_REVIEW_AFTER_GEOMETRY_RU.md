# F05 Code Review After Geometry Rework

Дата проверки: 2026-08-13.
Роль: isolated Code Review Agent.
Verdict: `CODE_REVIEW_PASSED`.

## Scope

Проверялась текущая реализация F05 "Единая карточка приёмки для ФФ и селлера" после geometry rework seller fact-card:

- `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`
- `frontend/src/screens/v2/SellerDocumentsScreen.tsx`
- `frontend/src/screens/v2/sellerInboundDocumentUi.test.ts`
- `frontend/src/utils/inboundOperationType.ts`
- `frontend/tests-e2e/seller-inbound-fact-card-geometry.spec.ts`

Секреты, Railway variables, внешние панели, production/staging не открывались и не менялись.

## Repo State

Обязательные pre-checks выполнены:

- `git rev-parse --show-toplevel` -> `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`
- прочитан `AGENTS.md`
- прочитан `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`
- `git status --short --branch` показал грязное рабочее дерево с большим числом чужих изменений вне F05 scope

Заявленный rework SHA `d0d3faee804d103ce7a409e475154239d4ff079a` существует, но не является предком текущей ветки. На момент проверки HEAD двигался чужими docs-коммитами; текущий HEAD после тестов был `a189c472f7241cd02a0711b6ebbe9e46148f7247`.

По пяти scoped F05 files разница между `d0d3faee804d103ce7a409e475154239d4ff079a` и текущим HEAD отсутствует:

```text
git diff --stat d0d3faee804d103ce7a409e475154239d4ff079a..HEAD -- <F05 scoped files>
# no output
```

В рабочем дереве scoped F05 files также не имели unstaged diff. Тесты запускались в текущем грязном worktree; вне scope были незакоммиченные изменения, включая `frontend/src/apps/seller/SellerApp.tsx` и `frontend/tests-e2e/inbound-boxes-helpers.ts`.

## Review Evidence

1. Seller fact card at 1280px.

   Fact-card рендерится отдельной веткой для `status !== draft`: `SellerInboundDraftScreen.tsx` lines 523-531 and 917-1191. Таблица fact-card использует fixed layout, `width: 100%`, `maxWidth: 100%`, `minWidth: 0`, `overflowX: hidden`, процентный `colgroup`, и содержит обязательные колонки `Заявлено`, `Факт`, `Расхождение`: lines 998-1039. Значения `Заявлено`, `Факт`, `Расхождение` и метка `Добавлено ФФ` выводятся в строках 1138-1174.

   Target Playwright spec проверяет этот же пользовательский путь на 1280px: создаёт completed inbound, открывает seller documents, кликает seller row, проверяет отсутствие draft controls, проверяет `Заявлено`/`Факт`/`Недостача 1`, `Добавлено ФФ`, `Излишек 1`, затем меряет `documentScrollWidth`, `bodyScrollWidth`, `containerScrollWidth`, right edge `Расхождение`, совпадение количества header/body cells и минимальную ширину name column: `seller-inbound-fact-card-geometry.spec.ts` lines 36-141.

2. No extra fact-card controls or technical UI.

   В completed fact-card нет draft form и нет кнопок `Добавить товары`, `Сохранить`, `Передать на склад`, `Удалить`; они находятся только в draft branch lines 620-916. E2E закрепляет отсутствие этих controls after completion: spec lines 79-85. Новых chips на completed fact-card нет; summary оформлен как compact bordered summary boxes, а status `Chip` остаётся только в draft branch lines 673-677.

3. Human-readable statuses.

   `SellerDocumentsScreen.tsx` maps inbound raw statuses `receiving`, `sorting`, `done`, `primary_accepted`, `verifying`, `verified`, `posted` into Russian user labels and hides unknown raw backend strings behind `Статус уточняется`: lines 51-70. `SellerInboundDraftScreen.tsx` uses the same pattern for fact-card status: lines 91-119. Unit test covers known statuses and unknown raw fallback: `sellerInboundDocumentUi.test.ts` lines 11-31.

4. Draft controls absent after completion.

   `isDraft` gates all editable draft controls. Completed statuses render `seller-inbound-fact-card`, not `seller-inbound-draft-form`: `SellerInboundDraftScreen.tsx` lines 523-531, 620-916, 917-1191. E2E asserts absent draft form and absent add/save/submit/delete controls after completion: spec lines 79-85.

## Tests Run

```text
npm run test:unit -- sellerInboundDocumentUi.test.ts
Result: passed, 1 file, 4 tests.
```

```text
npx playwright test tests-e2e/seller-inbound-fact-card-geometry.spec.ts --workers=1 --reporter=line
Result: passed, 1 test, Chromium, 19.5s.
```

```text
npm run build
Result: passed. Vite emitted only the existing chunk-size warning.
```

## Findings

No blocking findings in the scoped F05 implementation.

Residual risk: the worktree was not clean and HEAD moved during review. The scoped F05 files match `d0d3faee804d103ce7a409e475154239d4ff079a`, but the executed tests used the current dirty worktree, not a pristine checkout of `d0d3fae`.

## Matrix Update

`ITERATION_FEATURE_CARDS_RU.md` was not updated because it already had pre-existing unrelated modifications in the worktree. Updating and committing it would risk capturing another agent's changes.
