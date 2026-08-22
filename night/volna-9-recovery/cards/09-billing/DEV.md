# 09-billing · screen-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/PeriodPicker.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md`

Компонент сохраняет контролируемое значение `YYYY-MM` при любых перерисовках родителя,
передаёт новое значение через `onChange`, поддерживает границы `min`/`max`, disabled-состояние
и текст ошибки. Для ошибки добавлена доступная связь поля с подсказкой через `aria-invalid` и
`aria-describedby`. Экспорт `PeriodPicker` и `PeriodPickerProps` уже присутствовал в
`frontend/src/ui-kit/index.ts`, поэтому файл экспорта не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не запущен: в окружении отсутствует `frontend/node_modules/.bin/tsc` (exit 127).
- `python3 scripts/ui/ui_guard.py` — красный по пяти несвязанным существующим монолитным экранам: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/ff/FfSettingsScreen.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Нарушений в изменённом `PeriodPicker.tsx` не указано; базовую линию не обновлял.
- `npm run test:unit` — не запущен: команда `vitest` отсутствует в окружении (exit 127).
- `git diff --check` — зелёный.

## Не реализовано

Пунктов контракта, относящихся к `PeriodPicker`, которые не удалось реализовать буквально, нет.
