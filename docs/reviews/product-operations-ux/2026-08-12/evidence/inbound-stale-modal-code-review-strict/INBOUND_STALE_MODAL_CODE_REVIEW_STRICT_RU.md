# Inbound stale modal fix — strict code review

Дата: 2026-08-14

Роль: Inbound Stale Modal Fix Strict Code Review Agent

Repo: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`

Verdict: `CODE_REVIEW_PASSED`

## Scope

Проверял только узкую починку stale discrepancy modal и минимально связанный inbound-контекст:

- `frontend/src/screens/ff/FfInboundRequestView.tsx`
- `frontend/tests-e2e/inbound-receiving-v2.spec.ts`
- `frontend/tests-e2e/ff-inbound-print-waybill.spec.ts`

Не выполнял commit, push, staging, deploy, Railway или операции с секретами.

## Findings

Findings: none.

## Проверка по чек-листу

1. Диалог закрывается на confirm и не может остаться stale после успешного завершения.

   В `completeReceiving()` состояние `finishConfirmOpen` сбрасывается до POST:
   `frontend/src/screens/ff/FfInboundRequestView.tsx:1407-1427`.
   Сам dialog управляется только `open={finishConfirmOpen}`:
   `frontend/src/screens/ff/FfInboundRequestView.tsx:2898-2904`.
   Поэтому после клика `ff-inbound-discrepancy-confirm` старый dialog уходит до сетевого ответа и не может висеть поверх уже проведённого документа.

2. Failed POST оставляет видимый human error path, а не silent failure.

   При `!res.ok` код выставляет человекочитаемую ошибку через `setError(scanErrorMessageRu(await readApiErrorMessage(res)))` и выходит без `loadDetail()`:
   `frontend/src/screens/ff/FfInboundRequestView.tsx:1416-1419`.
   При исключении выставляется fallback `Не удалось завершить приёмку.`:
   `frontend/src/screens/ff/FfInboundRequestView.tsx:1422-1424`.
   Ошибка рендерится в верхнем alert `ff-inbound-doc-error`:
   `frontend/src/screens/ff/FfInboundRequestView.tsx:1568-1571`.
   Экран приёмки остаётся доступен для повторной попытки.

3. Non-discrepancy completion не сломан.

   Путь без расхождений по-прежнему вызывает `completeReceiving()` напрямую:
   `frontend/src/screens/ff/FfInboundRequestView.tsx:1450-1456`.
   Так как `finishConfirmOpen` уже false, новый ранний сброс состояния не меняет бизнес-путь. E2E дополнительно проверяет, что после direct-complete dialog отсутствует и статус становится `В сортировке`:
   `frontend/tests-e2e/inbound-receiving-v2.spec.ts:1073-1078`.

4. E2E защищают stale modal blocker.

   В основном regression-сценарии с расхождением после confirm добавлена проверка нулевого количества `ff-inbound-discrepancy-dialog`, затем проверяется статус `В сортировке`:
   `frontend/tests-e2e/inbound-receiving-v2.spec.ts:127-137`.
   Во втором целевом сценарии печати проведённой накладной та же защита стоит перед дальнейшими проверками:
   `frontend/tests-e2e/ff-inbound-print-waybill.spec.ts:65-73`.

5. Широких unrelated edits именно у stale-modal fix не обнаружено.

   В текущем worktree есть большой dirty inbound/product context: только по трём проверенным файлам `981 insertions(+), 75 deletions(-)`.
   Этот review не принимает и не отклоняет весь этот объём. Узкая stale-modal delta в коде — перенос `setFinishConfirmOpen(false)` на начало `completeReceiving()`; тестовая delta для blocker — assertions `toHaveCount(0)` в двух целевых e2e-сценариях.

## Локальные проверки

В рамках этого review тесты заново не запускались. Зафиксированы уже переданные main thread проверки:

- `cd frontend && npm run build` passed.
- `E2E_API_PORT=18321 E2E_WEB_PORT=55321 E2E_DB_FILE=e2e-inbound-modal-fix-... E2E_API_ORIGIN=http://127.0.0.1:18321 npx playwright test tests-e2e/inbound-receiving-v2.spec.ts tests-e2e/ff-inbound-print-waybill.spec.ts --project=chromium --grep "scan, manual edit, finish with discrepancy|conducted inbound waybill"` -> `2 passed`.

## Итог

Verdict: `CODE_REVIEW_PASSED`
