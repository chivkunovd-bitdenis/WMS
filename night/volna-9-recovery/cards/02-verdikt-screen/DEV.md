## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/tests-e2e/ff-fbs-orders.spec.ts`

Атомарная фича реализована в существующей зоне статуса: серверный вердикт отображается через `StatusChip`, причина отказа и текст недоступности — через `TextCell`. Новая колонка и заливка строки не добавлены. Сценарий покрывает S-03-TC-001, S-03-TC-002, S-03-TC-003 и S-03-TC-006.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — результат не удалось надёжно зафиксировать: команда не вывела диагностику, а окружение завершило запуск без доступного кода результата.
- `python3 scripts/ui/ui_guard.py` — красный: файл `scripts/ui/ui_guard.py` отсутствует в этой рабочей копии (ошибка `can't open file .../frontend/scripts/ui/ui_guard.py` при запуске из корня через имеющийся сценарий проверки).
- `npm run test:unit` — красный: `vitest: command not found`, зависимости frontend не установлены.

## Не реализовано

Пунктов контракта для этого атомарного куска, которые не удалось реализовать буквально, нет. Полная локальная проверка ограничена отсутствующим `ui_guard.py`, неустановленным `vitest` и недоступным надёжным результатом `tsc`; базовую линию `ui_guard.py` не изменял.
