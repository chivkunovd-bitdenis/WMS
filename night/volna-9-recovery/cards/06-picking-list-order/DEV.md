# DEV · 06-picking-list-order · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md`

В `ff-fbs-supply.spec.ts` добавлены пользовательские браузерные сценарии, которые открывают лист через видимую кнопку рабочего места, а не изолированный компонент: `S-03-TC-001` проверяет серверный порядок и диапазоны, `S-03-TC-002` — локальную отметку и отсутствие перенумерации после фильтра, `S-03-TC-003` — передачу полного канонического набора заказов при пустом результате фильтра, `S-03-TC-006` — пустую поставку, `S-03-TC-007` — блокировку повторной печати, кнопки закрытия и Escape во время подготовки.

Исправления первых трёх находок ревью уже находятся в текущем сохранённом коммите `e60b085d998a470c986e0ca8614bae11ffde6a9f`: `FfFbsPickList` подключён к `FfFbsSupplyWorkspace`, оба полных маршрута печати используют серверный порядок, предпросмотр строит пару `WB → WMS № K`, а Честный знак берётся из сохранённого изображения или формируется как DataMatrix, но не печатается текстом КИЗ.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — **красный на существующих файлах вне разрешённого слоя атома**. Ошибки: `frontend/src/ui-kit/Cells.tsx:89` — MUI 9 не принимает `inputProps`; `frontend/src/ui-kit/ModalFrame.tsx:32-33` — MUI 9 не принимает `disableEscapeKeyDown`, параметр `reason` не используется. В изменённом e2e-файле ошибок не найдено.
- `python3 scripts/ui/ui_guard.py` из корня — **красный на существующих соседних файлах**: `frontend/src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`) и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Базовая линия не обновлялась. По слою карточки guard сообщает улучшения в `FfFbsPickList.tsx` и `FfFbsSupplyWorkspace.tsx`.
- `npm run test:unit` из `frontend/` — **зелёный**: 21 файл, 149 тестов пройдены.
- `npx eslint tests-e2e/ff-fbs-supply.spec.ts` из `frontend/` — **зелёный**.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-00(1|2|3|6|7)' --list` — **зелёный**: Playwright обнаруживает все 5 сценариев.
- Живой запуск тех же 5 Playwright-сценариев — **заблокирован средой** до выполнения тестов: webServer не может открыть `127.0.0.1:18000`, ошибка `[Errno 1] operation not permitted`.

## Не реализовано

- Буквально зелёные `tsc` и `ui_guard.py` недостижимы без правок файлов вне разрешённой границы этого атома; конкретные внешние ошибки перечислены в разделе «Гейты».
- Живой Playwright-прогон не завершён из-за запрета среды на локальный bind порта. Сценарии добавлены, компилируются, перечисляются Playwright и проходят ESLint, но их браузерный результат в этой среде не заявляется как зелёный.
- Новый e2e-слой и этот отчёт локально реализованы, но не сохранены новым commit: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`). Восстановимый HEAD остаётся `e60b085d998a470c986e0ca8614bae11ffde6a9f`; незакоммиченный diff необходимо сохранить оркестратору с доступом на запись к общему Git-каталогу.
