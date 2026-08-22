# Screen-dev · 02-verdikt-screen · переделка атома 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/screens/v2/fbsApi.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/frontend/src/utils/metaStatus.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

`frontend/src/screens/v2/fbsApi.ts` и `frontend/src/utils/metaStatus.ts` проверены по контракту и замечаниям ревью. Их производственный код уже содержит серверный `readonly delivery_allowed`, шесть фиксированных подписей, контрактные тоны, русские причины и безопасный блокирующий fallback, поэтому повторная правка не потребовалась.

Добавлена регрессия клиентской границы для обоих ответов S-03: worklist и workspace сохраняют полученный серверный вердикт, а отсутствующее поле превращается в `Нет ответа WB` с запретом передачи. Типовой тест через `@ts-expect-error` закрепляет запрет присваивать новое значение серверному `delivery_allowed`. Словарь дополнительно проверен на приоритет непустой причины и безопасную обработку отсутствующей или неизвестной подписи.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — зелёный.
- `python3 scripts/ui/ui_guard.py` из корня — красный на предсуществующих отклонениях вне файлов атома 3: `src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`), `src/screens/v2/FfFbsSupplyWorkspace.tsx` (`экран-монолит 2493 → 2497`) и `src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Базовая линия не обновлялась; эти файлы не исправлялись, потому что текущий атом разрешает только клиентский API, словарь и тесты этого слоя.
- `npm run test:unit` из `frontend/` — зелёный: 20 файлов, 149 тестов прошли.
- Целевая проверка сценариев ревью `pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_clears_stale_filled_verdict tests/test_fbs_shipment_deliver_gate_unit.py::test_delivery_sync_error_invalidates_stale_filled_verdict` из `backend/` — зелёная: 3 теста прошли (параметры пустого batch и ошибки WB плюс сбой синхронизации перед передачей).

## Не реализовано

- Зелёный `ui_guard.py` получить в границах атома 3 нельзя: каждое показанное нарушение находится в соседнем экранном коде, который контракт этого запуска запрещает менять. Базовую линию флагом `--update` не сдвигал.
- Backend-находки ревью не переписывались ролью `screen-dev`: они уже исправлены зависимыми атомами в текущем `HEAD` и подтверждены тремя целевыми регрессионными тестами.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.
