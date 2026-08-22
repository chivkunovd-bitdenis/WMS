# DEV · 05-prod-slow · TableLoadMore

## Изменённые файлы

Кодовые файлы атома в этой проверке не изменялись: реализация уже присутствует в рабочей копии и соответствует контракту. Проверены:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/TableLoadMore.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/UiKitShowcase.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершился в доступном окружении без вывода; процесс остановлен. Результат не подтверждён.
- `python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений в соседних экранах: `MarkingPrintDialog.tsx`, `WbProductPickerDialog.tsx`, `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`, `SellerInboundDraftScreen.tsx`. Файлы атома в сообщениях проверки отсутствуют; baseline не изменялся.
- `npm run test:unit` — не запущен: `vitest: command not found`.

Ревью-сценарии атома проверены по коду: состояние `hasNext=false` скрывает элемент; доступное состояние показывает единственную кнопку «Показать ещё»; `loading` блокирует кнопку, показывает спиннер и «Загружаем…»; ошибка выводит `ErrorNotice` над доступным повторным действием. Showcase содержит все четыре состояния и интерактивный сценарий с защитой от повторного вызова.

## Не реализовано

Буквально не подтверждены зелёные tsc и unit-гейты из-за отсутствующих/зависших инструментов в окружении. Исправление чужих нарушений `ui_guard.py` и установка зависимостей не входят в разрешённые файлы и атомарную задачу.
