# S-04 — stock-sync Ozon

Проверенный срез: API существующей привязки склада выдаёт `marketplace` и
`external_warehouse_id`; существующая таблица stock-sync показывает нейтральный
Chip WB/Ozon и безопасные статусы Ozon. Обязательный wave0-тест последней
физической единицы уже находится в
`backend/tests/test_fbs_stock_models.py::test_one_physical_unit_cannot_be_allocated_to_wb_and_ozon`.
Добавленный в этой лане `test_ozon_binding_api_output_keeps_provider_identity`
проверяет только поля provider identity в API привязки.

- `pytest backend/tests/test_fbs_stock_models.py backend/tests/test_marketplace_foundation.py -q`: 24 passed, exit 0.
- `ruff check --ignore RUF100 backend/app/api/fbs_sellers.py backend/tests/test_fbs_stock_models.py`: exit 0.
- `npx tsc --noEmit -p tsconfig.app.json`, unit `fbsApi.test.ts` и `npm run build`: exit 0.

BLOCKED: В существующем интерфейсе нет разрешённого диалога создания Ozon-привязки, а текущая запись привязки и публикация остатка жёстко WB-only; без запрещённой правки общего provider adapter/transport нельзя добавить выбор Ozon или публикацию по правилам.

Реальные запросы к Ozon и живые mutation остатков не выполнялись. Доказательство в живом браузере не записано: установленный browser skill не содержит обязательный `browser-client.mjs`, а второй запуск Playwright не получил собственный сервер — `localhost:18000` занят неизвестным процессом.
