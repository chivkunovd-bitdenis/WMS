# FBS KIZ Manual Binding: live browser verdict

Экран / фича: FBS, ручная привязка КИЗ к сборочному заданию по стикеру.

Стадия: integration merge + product browser review.

Статус: `SCREEN_APPROVED`.

Commits:
- `7abcc9a` - merge `feat/fbs-kiz-manual-binding` into `integration/wms-wave0-20260814`.
- `a7c005a` - fix: expose FBS KIZ `source` in workspace metadata.
- Evidence commit: будет добавлен отдельным commit после сохранения этого артефакта.

Тесты:
- После merge KIZ: backend pytest `750 passed, 5 skipped, 6 warnings in 1734.81s`.
- Frontend build после merge KIZ: `npm run build` passed.
- После фикса `source`: targeted pytest `backend/tests/test_fbs_kiz.py::test_fbs_kiz_commit_success_creates_records_event_and_counter` - `1 passed in 3.03s`.
- После фикса `source`: `ruff check backend/app/api/fbs_orders.py backend/app/services/fbs_worklist_service.py backend/tests/test_fbs_kiz.py` passed.
- После фикса `source`: `cd backend && mypy app/api/fbs_orders.py app/services/fbs_worklist_service.py` passed.
- Fullstack Docker script не запускался до тестов: Docker daemon недоступен (`Cannot connect to the Docker daemon`).

Браузер: внешний видимый Google Chrome 151, окно macOS, управление через DevTools CDP на `127.0.0.1:19354`. Это не headless и не in-app browser; Playwright использовался только как CDP-драйвер видимого окна.

Сценарий:
- Открыт FBS worklist, вкладка `В работе`, поставка `Live KIZ full browser supply 1786780739`.
- Открыт workspace поставки и вкладка `Упаковка и маркировка`.
- До фикса подтверждён реальный Stop: commit КИЗ проходил, но UI не показывал `· КИЗ`, потому что API workspace metadata не отдавал `source`.
- После фикса UI показывает `Напечатано 2 из 2` и два маркера `· КИЗ`.
- Через `Перепечатка` открыт диалог `Отменить КИЗ?`.
- Подтверждение отмены дало `DELETE /operations/fbs-orders/d2b312bb-6127-43aa-915d-4f65ee64d323/kiz` со статусом `204`.
- После отмены UI показывает `КИЗ отменён.`, `Напечатано 1 из 2` и один маркер `· КИЗ`.
- Fake WB readback: заказ `930000000` вернул `{}`, заказ `930000001` сохранил `sgtin = 010460043993125321E2EKIZFULL000002`.

Находки:
- Стоп 1, исправлен: workspace metadata теряла `source`, из-за чего операторский КИЗ не отличался от обычного статуса и не отображался в UI.
- Тормоз 0.
- Хвост 0.

Раунд: 2. Первый live round нашёл Stop; второй live round после фикса прошёл. Локальная QA SQLite была пересогласована с текущим dev API Fernet-key для шага отмены, потому что база была засеяна другим ключом шифрования WB-token и API получал 500 до входа в бизнес-логику отмены.

Блокеры: нет для этой фичи.
