# DEV · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

В существующей зоне статуса заказа сохранены единые `StatusChip` и `TextCell` для вердикта WB, включая русскую причину отказа и сообщение о недоступной сдаче. Дополнительно нейтрализован статус упакованной поставки: worklist поставок не содержит агрегированного WB-вердикта, поэтому экран больше не обещает «Готова к сдаче» до проверки заказов.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный `npx` не вернул диагностик или код завершения в доступное время, поэтому зелёным не считаю.
- `python3 scripts/ui/ui_guard.py` — красный из-за двух новых нарушений в несвязанных файлах `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; для изменённого `FfFbsOrdersScreen.tsx` новых нарушений нет, показатели улучшились.
- `npm run test:unit` — красный: `vitest: command not found`, frontend-зависимости отсутствуют.
- Целевые Playwright-сценарии — не запущены: локальная Playwright-зависимость/стенд не доступна в этом окружении.
- `git diff --check` — без ошибок форматирования.

## Не реализовано

- Находки 1–4 из `REVIEW.md` относятся к backend и исправляются в соответствующих доменных слоях; они не входят в разрешённые файлы этого экранного атома.
- Находка 6 относится к `FfFbsSupplyWorkspace.tsx` и не входит в разрешённые файлы этого атома.
- Полный агрегированный WB-вердикт для строк поставок не может быть добавлен буквально: тип `FbsSupplyWorklistItem` и API-файлы находятся вне разрешённой границы. Поэтому исправлен только ложноположительный текст `Готова к сдаче`.
