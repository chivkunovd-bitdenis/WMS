ВЕРДИКТ: НАХОДКИ 5

# Ревью · 06-picking-list-order

Вердикт: CHANGES_REQUESTED.

## Находки

1. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx:82-103` — полная печать вызывает `order-print-tape`, но физически строит только пары PNG WB + номер WMS и полностью игнорирует возвращённые `codes` / `printed_codes`. При заказе с Честным знаком сервер назначит код, пометит его напечатанным и привяжет к WB, а оператор не получит этикетку ЧЗ. Цена — необратимо израсходованный код без физической маркировки товара; состав существующей ленты, который контракт запрещает менять, потерян.

2. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx:78-104` — `window.open` вызывается только после GET листа, POST ленты и ответа WB, когда жест клика уже потерян; при блокировке popup ветка `if (!w) return` молча завершается. В обычном браузере с запрещёнными асинхронными всплывающими окнами коды ЧЗ уже будут списаны/привязаны сервером, но ни окна печати, ни ошибки оператор не увидит. Цена — операция учтена как печать без любого физического результа.

3. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py:101-110` — ручка канонизирует переданное подмножество, но не проверяет, что для `include_order_qr=true` клиент прислал весь текущий состав поставки. Если во второй вкладке добавить заказ между свежим GET на `FfFbsPickList.tsx:78` и POST на `:82`, сервер напечатает старое подмножество с номерами уже нового полного листа. Цена — лента короче поставки, а `S-03-TC-008` и явное правило FEATURES «сервер принимает только полный состав» не выполнены. Существующую построчную печать с `include_order_qr=false` можно сохранить, но сейчас сервер не различает эти два режима.

4. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx:68-75,131-136,213-218` — добавленный предпросмотр сортирует и печатает по `asset.order_number`, но `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py:196-205,1537-1550` и `map_print_asset` не возвращают ни `order_number`, ни `wb_order_id` в активе. При запуске существующей печати стикеров из workspace карточка покажет `Стикер WB №—` и `WMS № —`, а в физическую печать условие на `:134` вообще не добавит служебную этикетку. Цена — заявленная в FEATURES пара `WB → WMS № K` и единый порядок в общем предпросмотре фактически не работают.

5. `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts:4-32` — фронтовые тесты проверяют только перекладку уже готовых диапазонов и ключи отметок; в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_packaging_integration.py:1304-1388` проверяется JSON-порядок, но не физический состав ленты. Ни одного обещанного Playwright-сценария `S-03-TC-001…007` в изменениях нет. Этот набор остаётся зелёным, если фронт списывает ЧЗ без печати, popup не открывается, подмножество заказов принимается как «полная» лента или предпросмотр получает пустые номера. Цена — находки 1–4 не ловятся заявленными гейтами.

## Проверено и нормально

- Все файлы реализации входят в явно переданный список карточки; `night/`, `tests/cases/` и `docs/blockers/` считались стадийными артефактами, а не выходом за границы.
- `get_picking_list` и `_orders_in_canonical_order` используют одинаковый ключ товарной группы и стабильную развязку `wb_order_id`, затем `order.id`; диапазоны непрерывны, tenant-фильтр сохранён.
- Фильтры и отметки на фронте не перенумеровывают строки; состояния загрузки, пустоты и busy имеют предписанные тексты и блокировки.
- Точечные backend-проверки прошли: `4 passed` для канонического порядка/листа и `1 passed` для endpoint-повтора; `git diff --check` чист. Frontend-зависимостей в checkout нет, поэтому TypeScript/Vitest не запускались.
