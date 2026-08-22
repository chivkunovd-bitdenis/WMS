# DEV · 05-prod-slow · TableLoadMore

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

Продуктовые файлы атома не изменялись: ревью не содержит замечаний к
`TableLoadMore`, а текущая реализация уже соответствует контракту. Проверены:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/TableLoadMore.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/frontend/src/ui-kit/UiKitShowcase.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный из-за новых нарушений в
  чужих файлах: `MarkingPrintDialog.tsx`, `WbProductPickerDialog.tsx`,
  `FfFbsOrdersScreen.tsx`, `FfFbsSupplyWorkspace.tsx`,
  `SellerInboundDraftScreen.tsx`. Файлы атома в выводе отсутствуют; базовая
  линия не менялась.
- `npm run test:unit -- --run` (из `frontend/`) — не запущен: команда завершилась
  с `sh: vitest: command not found`; зависимости тестового раннера отсутствуют.

Проверены сценарии контракта: без следующего курсора элемент скрывается;
доступное состояние показывает единственное действие «Показать ещё»; при
загрузке показаны «Загружаем…» и спиннер, а повторный клик блокируется; при
ошибке `ErrorNotice` расположен над вновь доступным действием. Витрина ui-kit
демонстрирует скрытое, доступное, загружаемое и ошибочное состояния, а её
интерактивный пример считает вызовы и не допускает повторного запуска во время
загрузки.

## Не реализовано

Нет продуктовых пунктов, не реализованных буквально в пределах этого атома.
Зелёный `ui_guard.py` и unit-тесты не подтверждены из-за нарушений вне
разрешённых файлов и отсутствующего `vitest`; исправление чужих экранов,
изменение baseline или установка зависимостей не входят в атом.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой
кабинет Wildberries не читались и не затрагивались.
