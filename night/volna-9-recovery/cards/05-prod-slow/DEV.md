# DEV · 05-prod-slow · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

Код экрана не менялся: реализация в
`/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
уже буквально соответствует контракту атома: в ветке `statusGroup === 'new'`
есть четыре заголовка с `width` 210 / 135 / 180 / 140 и
`whiteSpace: 'nowrap'`; колонки «Статус» в этой ветке нет. Ранее
привязанный e2e-кейс `S-03-TC-016` проверяет те же CSS-свойства.

## Гейты

- ЗЕЛЁНЫЙ: из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend` выполнено
  `npx tsc --noEmit -p tsconfig.app.json` — код завершения 0.
- КРАСНЫЙ, существующая baseline-находка вне границ атома: из корня выполнено
  `python3 scripts/ui/ui_guard.py` — код завершения 1. Выводит превышения
  baseline для `src/components/MarkingPrintDialog.tsx`,
  `src/components/WbProductPickerDialog.tsx`,
  `src/screens/v2/FfFbsOrdersScreen.tsx`,
  `src/screens/v2/FfFbsSupplyWorkspace.tsx` и
  `src/screens/v2/SellerInboundDraftScreen.tsx`. Baseline не обновлялся;
  контракт атома запрещает несвязанное дробление экранов.
- ЗЕЛЁНЫЙ: из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend` выполнено
  `npm run test:unit` — 20 файлов, 142 теста, код завершения 0.
- НЕ ЗАПУЩЕН ДО СЦЕНАРИЯ: из
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend` выполнено
  `npx playwright test tests-e2e/ff-fbs-orders.spec.ts --grep 'fbs orders: search keeps list, selected drawer stays stable and Excel downloads'`.
  Playwright не смог поднять свой локальный e2e API: песочница запретила bind
  `127.0.0.1:18000` (`operation not permitted`). Полный backend-regress,
  `ruff check .` и `mypy .` не запускались согласно ограничению атома.

## Не реализовано

- Живой browser review `S-03-TC-016` и два обязательных снимка в
  `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docs/evidence/05-prod-slow/`
  не выполнены: это отдельная роль product browser review; дополнительно
  технический e2e не смог стартовать из-за запрета песочницы на локальный
  порт. Признаков дефекта в коде контракта не найдено.
