# Проверка исправления закрытия поставки и повторной печати QR

Дата: 2026-08-26.

## Что проверено

- `assembling + WB done=true` переводит поставку в `done`.
- `done=false` не меняет локальный этап поставки.
- Для `assembling` дополнительная проверка поставки не повторяет пакетный запрос статусов заказов.
- Обычная синхронизация заказов для `in_delivery` сохранена.
- Сбой чтения карточки поставки не ломает прежнюю синхронизацию заказов.
- Кнопка QR читает QR поставки и существующих грузомест, но не вызывает создание грузомест.
- Повторное нажатие остаётся операцией чтения/повторной печати.
- Если одно готовое изображение стало недоступно, остальные QR остаются доступны для печати.
- После импорта существующего грузоместа WB таблица показывает ненулевой счётчик коробов.

## Автоматические проверки

- `ruff check` по четырём изменённым backend-файлам: PASS.
- `pytest -q tests/test_fbs_tracking.py tests/test_fbs_supply_from_orders.py::test_supply_worklist_groups_active_orders_by_supply`: 8 passed.
- `pytest -q tests/test_fbs_autopoll.py tests/test_fbs_shipment_pvz.py tests/test_fbs_tracking.py tests/test_fbs_supply_from_orders.py::test_supply_worklist_groups_active_orders_by_supply`: 35 passed.
- `npm run build`: PASS.
- `npx playwright test tests-e2e/ff-fbs-orders.spec.ts`: 8 passed до добавления проверки частичного preview.
- Два финальных QR-сценария Playwright после этой правки: 2 passed.
- Независимое read-only ревью итогового diff: PASS.

## Ограничения доказательства

Полный backend-набор ранее показал два не связанных с этой правкой падения: устаревший экспорт
OpenAPI и тест с фиксированной датой 15.08.2026, которая на момент запуска уже была в прошлом.
Живой интерфейс с этим diff на production не проверялся и не развёртывался.
