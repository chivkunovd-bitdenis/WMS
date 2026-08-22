# DEV · 02-verdikt-screen · атомарная правка строки по WB-вердикту

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts`

В рабочем коде атом выполнен: строка больше не использует `success.light` или
`success.main` из `metadata.verdict.delivery_allowed`; фон и левый бордер
зависят только от активности сканера и состояния печати. Регрессионный кейс
S-03-TC-007 проверяет одинаковый нейтральный фон принятой и заблокированной
строк.

## Гейты

Команды запускались из этой рабочей копии:

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npm run test:unit` — зелёный, 20 файлов и 149 тестов.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && python3 scripts/ui/ui_guard.py` — красный код 1 из-за двух новых нарушений вне атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для целевого `FfFbsSupplyWorkspace.tsx` нарушений не добавлено, guard отметил улучшения. Baseline не изменялся.

Полный e2e не запускался: по инструкции карточки запускались только тесты
атома и относящиеся к нему регрессии.

## Не реализовано

Буквально не закрыт только общий gate `ui_guard.py`: он блокируется двумя
предсуществующими для этой атомарной правки нарушениями в несвязанных файлах.
Исправление или изменение baseline выходит за разрешённые файлы карточки.
