# DEV · 08-storage · атом 1 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.tsx` — проверки `PrintAction` переведены на фактический React-рендер для вариантов `row` и `panel`, прежних подписей и disabled-пояснений.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.test.ts` — добавлена точка входа для теста, потому что текущий `vitest.config.ts` обнаруживает только файлы `*.test.ts` и пропускал контрактный `Actions.test.tsx`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — записан отчёт роли `screen-dev`.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/ui-kit/Actions.tsx` в rework не менялся: внутреннее сопоставление `what="накладную"` → `Печать накладной` уже реализовано, публичный интерфейс компонента сохранён. В `REVIEW.md` нет находок, относящихся к `Actions.tsx`, `Actions.test.tsx` или слою этого атома.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — **красный**, код возврата 2. Все девять ошибок находятся вне разрешённых файлов атома, в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`: две ошибки устаревшего `inputProps`, три вызова `TextCell` без `value`, два вызова `StatusChip` через неподдерживаемый `children`, один вызов `ProductCell` без `sku` и ещё один вызов `StatusChip` через `children` в диалоге истории.
- `python3 scripts/ui/ui_guard.py` из корня — **красный**, код возврата 1. Храповик сообщает три новых нарушения вне разрешённых файлов атома: `src/components/WbProductPickerDialog.tsx` (646 строк), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (2498 строк), `src/screens/v2/SellerInboundDraftScreen.tsx` (1169 строк). Базовая линия не обновлялась.
- `npm run test:unit` из `frontend/` — **зелёный**: 20 файлов, 141 тест, включая 3 теста `PrintAction`.
- Целевая проверка `npm run test:unit -- src/ui-kit/Actions.test.ts` — **зелёная**: 1 файл, 3 теста.
- `git add … && git commit -m "test(storage): run PrintAction render coverage"` — **красный**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`). Результат остаётся в постоянном рабочем дереве, но не сохранён отдельным коммитом.

## Не реализовано

- Пунктов атома, которые не удалось реализовать буквально, нет: `what="накладную"` рендерит подпись «Печать накладной» в `row` и `panel`; четыре существующих варианта сохранили подписи; disabled-пояснение и блокировка сохранены.
- Глобальные `tsc` и `ui_guard.py` не доведены до зелёного состояния, потому что их ошибки находятся в файлах других атомов и соседних задач, которые роль `screen-dev` для этого атома менять запрещает.
- Сохранить rework отдельным Git-коммитом не удалось из-за запрета среды на запись в метаданные worktree; без коммита результат нельзя считать опубликованным или пригодным для передачи по SHA.
