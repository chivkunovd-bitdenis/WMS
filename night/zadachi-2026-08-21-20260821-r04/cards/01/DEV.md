## Изменённые файлы

Экранные файлы не изменялись. Для карточки 01 отсутствует обязательный `tasks/<slug>/CONTRACT.md`; кроме того, в `frontend/screens.registry.json` у S-14 поле `files` пустое. Изменение экранов без контракта нарушило бы ограничения роли `screen-dev`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный: обнаружены новые нарушения в существующих файлах `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не относятся к разрешённым файлам карточки 01 и не изменялись.
- `npm run test:unit` (из `frontend/`) — не запустился: `vitest: command not found`.

## Не реализовано

- Экранная часть карточки 01 не реализована буквально: входной экранный контракт отсутствует, а точные колонки, действия и состояния для S-05/S-14 не определены.
- S-14 нельзя изменять по реестру: его список `files` пуст.
- Артефакты карточки описывают backend-сверку статусов Wildberries, но реализация backend запрещена ролью `screen-dev`.
