# DEV · 06-picking-list-order · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx` — `busy` теперь явно блокирует Escape; длинное тело модального документа имеет ограниченную высоту и прокрутку.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/FilterBar.tsx` — `ChoiceFilter` получил недоступное состояние с объясняющей подсказкой и корректным `aria-disabled`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Cells.tsx` — причина блокировки `CheckCell` доступна через подсказку на обёртке, которая принимает события у disabled-контрола.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/UiKitShowcase.tsx` — витрина показывает недоступный фильтр с причиной; при `busy` кнопка закрытия получает причину и блокируется.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт этого атома.

`PrintAction` со значением `стикеры заказов` и экспорты `ModalFrame`, `ChoiceFilter`, `CheckCell` уже присутствовали в разрешённых файлах и не требовали изменений в этой переделке.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локального `tsc` нет; `npx` не смог скачать пакет из-за недоступности `registry.npmjs.org` (`ENOTFOUND`).
- `python3 scripts/ui/ui_guard.py` — красный только из-за двух существующих нарушений вне атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не менялась.
- `npm run test:unit` — красный: локальный `vitest` отсутствует (`sh: vitest: command not found`).
- `git diff --check` — зелёный.

## Не реализовано

- Находки 1–5 из `REVIEW.md` относятся к `FfFbsPickList.tsx`, `FbsPrintPreviewDialog.tsx`, API, backend-сервису и тестам экрана. Эти файлы вне слоя и границы атома 1, поэтому не менялись.
- Изолированный unit-тест нового примитива не добавлен: в данной рабочей копии нет установленного раннера `vitest`, а ревьюер не назвал тест ui-kit как разрешённый дополнительный файл.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
