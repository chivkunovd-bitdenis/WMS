# DEV · 02-verdikt-screen

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-supply.spec.ts` — S-03-TC-007 дополнен явной проверкой нейтрального `background.paper` (`rgb(255, 255, 255)`) и прозрачной левой границы у строк с принятым и отклонённым WB-вердиктом.

`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` проверен: K7 уже реализован в исходной ветке — `markingReady` отсутствует, фон строки зависит только от активности сканера и печати, левая граница — только от активности сканера.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npm run test:unit -- src/screens/v2/FfFbsSupplyWorkspace.test.ts` — 1 файл, 3 теста.
- КРАСНЫЙ, вне атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && python3 scripts/ui/ui_guard.py` сообщает новые нарушения в `src/components/WbProductPickerDialog.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; эти файлы не входят в S-03 и не менялись.
- НЕ ЗАПУЩЕН ДО СЦЕНАРИЯ ИЗ-ЗА СРЕДЫ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'one blocked order prevents whole-supply delivery'` — webServer не может привязаться к `127.0.0.1:18000` (`operation not permitted`).
- Перед запуском тестов был удалён только воспроизводимый кэш `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/.mypy_cache` (~210 МБ), чтобы устранить `ENOSPC`; исходники и артефакты других карточек не затрагивались.

## Не реализовано

- Визуальный e2e-прогон S-03-TC-007 не завершён: среда запрещает привязку тестового webServer к `127.0.0.1:18000`.
- Новых правок `FfFbsSupplyWorkspace.tsx` нет, поскольку требуемая логика K7 уже буквально присутствовала в рабочей ветке; добавлена регрессия, фиксирующая отсутствие зелёной заливки и границы.
