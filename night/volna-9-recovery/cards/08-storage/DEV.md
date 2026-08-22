# 08-storage · screen-dev rework по повторному ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/src/screens/ff/FfStoragePage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend/tests-e2e/storage.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

В экран S-11 вместо тупикового сообщения добавлен диалог тарифа по макету и контракту:
операционный склад, обязательные ставка и дата начала, раскрываемая индивидуальная ставка
селлера, `PrimaryAction` «Сохранить» и `SecondaryAction` «Отмена». Ввод проверяется до
отправки; ошибка сервера остаётся в диалоге и показывается через `ErrorNotice`. Сохранение
отправляет общий тариф и, если раскрыто исключение, отдельную версию для пары
«селлер + склад» в `/operations/storage/tariffs`, после чего перечитывает экран.

В `S-11-TC-002` зафиксированы ввод ставки и даты и точное тело запроса. Для
`S-11-TC-012` восстановлен непустой сценарий сотрудника: он раскрывает SKU при настроенном
тарифе, но не видит ни изменение тарифа, ни фиксацию.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage` — красный только на существующих нарушениях вне файлов атома: `frontend/src/components/WbProductPickerDialog.tsx` (`0 → 646`), `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` (`2493 → 2498`) и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`1111 → 1169`). В файлах S-11 нового нарушения нет; базовая линия не обновлялась. Скрипт также сообщает улучшение `frontend/src/App.tsx` (`3492 → 3491`), этот файл в текущем rework не менялся.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный: 20 файлов, 141 тест.
- `npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002|S-11-TC-012' --reporter=line` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — инфраструктурно красный до запуска тестов: Playwright web-server не смог открыть `127.0.0.1:18000`, `operation not permitted`.
- `npx playwright test tests-e2e/storage.spec.ts --grep 'S-11-TC-002|S-11-TC-012' --list` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/frontend` — зелёный: найдены четыре целевых теста в одном файле, тестовый файл компилируется.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage` — зелёный.

## Не реализовано

- В backend этой рабочей копии отсутствует маршрут записи тарифа. Экран теперь отправляет
  `POST /operations/storage/tariffs` с `warehouse_id`, `amount`, `valid_from` и
  необязательным `seller_id`, но реальное сохранение получит 404, пока владелец backend-слоя
  не опубликует этот endpoint. Добавлять backend-файл роли `screen-dev` и списку файлов
  атома не разрешено; ложный успех через локальное состояние не создавался.
- Полный браузерный результат `S-11-TC-002` и `S-11-TC-012` не подтверждён из-за запрета
  песочницы на локальный bind. Компиляция и обнаружение целевых тестов подтверждены.
- Находки 2–6 повторного `REVIEW.md` относятся к backend-моделям, API, миграции и backend-
  тестам. Они не исправлялись ролью `screen-dev`; соседние продуктовые файлы не затрагивались.

## Находки

Секреты, ключи, токены, `.env`, персональные кабинеты и боевой production не открывались
и не использовались.
