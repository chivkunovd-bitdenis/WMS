# ORDER 033 — Wave 2 FBS Packaging / Print Acceptance

Полоса: обычная  
Экран: FBS — Упаковка и печать  
Задачи: FBS-09, FBS-10, FBS-11, FBS-12, FBS-21  
Стадия: 4 — продуктовая проверка в живом браузере; artifact-only фиксация результата  
Статус: SCREEN_APPROVED для экранного сценария FBS packaging/print на локальном стенде  
Commit: 7c727134e6984d496b6791fec5e46f8b76bf0492  
Находки: Стоп 0 / Тормоз 0 / Хвост 2  
Раунд правок: 0  
Блокеры: Docker daemon/WB emulator недоступен; один дополнительный rerun теста ЧЗ остановлен инфраструктурно из-за `No space left on device`

## Проверенный сценарий

Локальный URL: `http://127.0.0.1:5181/app/ff/fbs`  
Backend: `http://127.0.0.1:19010`, `/health` вернул `200`  
Логин: CDP-mock `localStorage.wms_token_ff=live-smoke-token`, `/api/auth/me` как `live@example.com` / `fulfillment_admin`  
Браузер: внешний видимый Google Chrome `151.0.7922.138`, управление через Chrome DevTools Protocol на `9224`; Playwright/headless не использовался как приемка  
Скрипт приемки: `/tmp/wms_wave2_fbs_live_gate_cdp.mjs`

В Chrome пройден маршрут: FBS-заказ -> `Печать всего` -> предпросмотр/конструктор -> QR заказа с `copies=3` -> меню строки `Перепечатать` -> режим коробов `Без распределения` на 2 короба -> QR короба WMS -> `Передать в WB` -> `Печать QR поставки`.

Скриншоты live-gate, все `2730x1478`:

- `/tmp/wms-wave2-fbs-live-gate-01-packing-controls.png`
- `/tmp/wms-wave2-fbs-live-gate-02-print-all-constructor.png`
- `/tmp/wms-wave2-fbs-live-gate-03-order-qr-preview-copies.png`
- `/tmp/wms-wave2-fbs-live-gate-04-reprint-dialog.png`
- `/tmp/wms-wave2-fbs-live-gate-05-boxes-without-distribution.png`
- `/tmp/wms-wave2-fbs-live-gate-06-box-qr-preview.png`
- `/tmp/wms-wave2-fbs-live-gate-07-supply-qr-preview.png`

## 6а mapping

| Правило 6а / gate | Факт |
|---|---|
| Работать в своем worktree | Итоговый tracked artifact создан в `/Users/deniscivkunov/Projects/WMS/.worktrees/wave2-fbs-packaging-print-20260815`, ветка `iteration/wms-wave2-fbs-packaging-print-20260815`; ошибочный временный файл вне worktree удален, в commit не попадает. |
| Не трогать чужие worktree и integration/main | Merge не выполнялся; integration/main не менялись. |
| Продуктовая приемка только через живой внешний браузер | Пройден видимый Google Chrome через CDP; Playwright/headless, API/curl и чтение кода не засчитывались как приемка. |
| Проверять реализованный экран, а не будущий дизайн | Проверен существующий экран `FBS — Упаковка и печать` после commit `7c727134e6984d496b6791fec5e46f8b76bf0492`. |
| Артефакты должны позволять восстановить результат | Есть commit SHA, URL локального стенда, CDP-скрипт, 7 PNG-скриншотов и список прокликанных действий. |
| Тесты — технический слой, не замена браузеру | Тесты перечислены ниже отдельно; статус приемки опирается на live Chrome gate. |
| Не пересекаться с чужим scope | UI/бизнес-код в artifact-only проходе не менялся; FBS-01 файлы не трогались. |

## Task mapping

| Задача | Приемочное подтверждение |
|---|---|
| FBS-09 | QR товара/заказа открыт через кнопку `QR`; QR короба WMS открыт в блоке коробов; QR поставки WB открыт после `Передать в WB`. Скриншоты 03, 06, 07. |
| FBS-10 | Перед печатью показан стандартный предпросмотр с выбором копий; поле копий выставлено в `3`. Скриншоты 02, 03, 07. |
| FBS-11 | Меню строки заказа содержит `Перепечатать`, действие открывает reprint-dialog без нового массового запуска. Скриншот 04. |
| FBS-12 | В блоке коробов включена галка `Без распределения`, введено количество `2`, созданы короба, товар по коробам не распределялся, QR короба доступен. Скриншоты 05, 06. |
| FBS-21 | `Печать всего` доступна на этапе упаковки и открывает ленту печати через общий `MarkingPrintDialog`; повторный расход ЧЗ проверяется техническими тестами и reprint-контрактом, не браузерной имитацией принтера. Скриншот 02. |

## Тесты

- `python3 -m ruff check .` в `backend/`: `All checks passed!`
- `python3 -m mypy .` в `backend/`: `Success: no issues found in 258 source files`
- `WMS_TEST_DATABASE_URL=sqlite+aiosqlite:////tmp/wms_wave2_final_84244_pytest.sqlite python3 -m pytest tests/test_fbs_packing_box.py tests/test_fbs_shipment_deliver_gate_unit.py -q`: `12 passed in 3.43s`
- `npm run test:unit -- FfFbsSupplyWorkspace.test.ts`: `1 file passed`, `2 tests passed`, `416ms`
- `npm run build`: passed; Vite собрал `11998 modules` за `2.30s`, осталось стандартное warning про chunks > 500 kB
- Дополнительный точечный FBS order-print-tape тест: `tests/test_fbs_box_clear_and_workspace_extras.py::test_order_print_tape_assigns_codes_to_requested_orders` — `1 passed in 4.56s`
- Дополнительный точечный ЧЗ reprint invariant rerun: `tests/test_marking_write_off_invariants.py::test_reprint_does_not_change_available_count` — `1 failed, 1 error in 8.80s` из-за инфраструктуры: `sqlite3.OperationalError: database or disk is full` и `No space left on device` при записи `.pytest_cache`

## Находки

Стоп: 0. Экранный путь FBS-09/FBS-10/FBS-11/FBS-12/FBS-21 в live Chrome пройден.  
Тормоз: 0. Нет продуктовой находки, которая мешает операторскому сценарию упаковки/печати.  
Хвост: 2. Docker/WB emulator недоступен, поэтому стенд использовал CDP-mock FBS data поверх локального backend/Vite; диск почти заполнен (`~122 MiB` свободно), из-за этого один дополнительный rerun ЧЗ-теста упал инфраструктурно.

## Границы

В этом artifact-only проходе UI, backend business code и тесты не менялись. Запрещенные FBS-01 файлы `backend/app/services/fbs_stock_sync_service.py` и `backend/app/services/fbs_stock_availability_service.py` не трогались.

Модель: пользователь запросил `gpt-5.5 high`; текущая Codex-сессия не дает мне технически подтвердить переключение модели, поэтому фиксирую ограничение как runtime-ограничение среды.
