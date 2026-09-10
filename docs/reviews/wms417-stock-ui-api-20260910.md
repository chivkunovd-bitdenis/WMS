# WMS-417 / WMS-338 / WMS-060 — завершение трёх UI/API-замечаний

Работа выполнена только в `/Users/deniscivkunov/Projects/WMS/.worktrees/wms338-stock-min-formula`,
ветка `feat/wms338-stock-min-formula`, от чистого `21c4600213418befc1df0dfc7f104e52ed8c82f8`.
Координатор явно расширил владение на эти три файла и scoped tests/report.
Прочитаны изменения abb2beba и 40a3216b: WMS-111/112 оспорены/приостановлены,
не развиваются, не интегрируются и не выпускаются этим исполнителем. Cancel worker
не возобновлялся; новых агентов нет. Канон и handoff остаются у координатора.

## Изменение поведения

1. Действующий файл `frontend/src/screens/ff/products-fbs/FfProductsFbsPage.tsx`
   передаёт bulk PUT как `{product_ids, rule: body}`. Поля units_mode и
   units_by_warehouse сохранены. Одиночный запрос сохраняет прежний контракт.
2. Действующий диалог находится в
   `frontend/src/screens/ff/products-fbs/FbsStockDialog.tsx`, не в components.
   Увеличение определяется сравнением введённых и сохранённых чисел независимо
   от прежнего режима. Возврат из процентов к прежнему/уменьшенному cap после
   падения free не блокируется; новое или увеличенное значение сверх free
   остаётся запрещённым. Изменено одно условие в существующем MUI-диалоге.
3. `backend/app/api/fbs_sellers.py`: GET stock-pool получает free_stock через
   bulk get_rule_views — тот же источник, которым через get_rule_view пользуется
   PUT summary. pool_limit/available_for_this_binding отражают физический free;
   суммы сохранённых потолков остаются информационными и не вычитаются из него.
   Список товаров и фильтры каталога не менялись.

## Исполненные проверки

- Сначала реальный HTTP bulk-сценарий запущен с `--runxfail`: 1 passed.
  Только после этого снят strict xfail в test_wms417_stock_http_contract.py.
- `uv run pytest -q tests/test_wms417_stock_http_contract.py
  tests/test_fbs_warehouse_binding.py tests/test_wms417_stock_review.py`:
  **34 passed**, без xfail/skip. Тест выполняет saveRule, извлечённый из настоящего
  TSX, и передаёт его JSON в настоящий ASGI API. Single и bulk дают200 и сохраняют
  режим/числа после перечитывания.
- Расширенный HTTP round-trip проверяет cap5+3 при физическом наличии2 и обычном
  резерве1. GET и PUT возвращают free1, потолки остаются5+3. Возврат в штуки
  принимается сервером; увеличение сверх наличия возвращает409.
- `npm run test:unit -- src/screens/ff/products-fbs/FbsStockDialog.test.ts`:
  **5 passed**. Из действующего диалога извлекаются и исполняются его условия,
  проверяются прежний/уменьшенный cap, новый/увеличенный cap сверх free и допустимое
  увеличение. Это выполнение клиентского условия, не браузерный тест.
- `uv run ruff check .`: PASS. `uv run mypy .`: PASS, 436 source files.
- `npx tsc --noEmit -p tsconfig.app.json`: PASS; `npm run build`: PASS.
  Build сообщил только предупреждение о крупных chunks. Новый тест добавлен
  после старта сборки, поэтому отдельно повторён tsc для включения этого файла.
- Scoped ESLint диалога, нового теста и страницы: у страницы прежние ошибки
  react-refresh/only-export-components на64/80 и предупреждение dependency
  sellerKey на186. Тот же запуск на содержимом файла из21c46002 воспроизвёл
  ровно эти два errors/один warning. Новых lint findings нет; общий ESLint этого
  файла не объявляется зелёным. Несвязанный перенос экспортов не выполнялся.

Отдельный PostgreSQL-прогон:
`WMS_TEST_DATABASE_URL=postgresql+psycopg:///wms417_stock_ui_20260910 uv run pytest -q tests/test_wms417_stock_http_contract.py`
дал **3 passed**. После завершения synthetic DB удалена. Новых изменений
блокировок в этом продолжении нет; повтор полного concurrency-набора не требовался.
Полный pytest не запускался.

## Файлы и сохранность

- frontend/src/screens/ff/products-fbs/FfProductsFbsPage.tsx
- frontend/src/screens/ff/products-fbs/FbsStockDialog.tsx
- frontend/src/screens/ff/products-fbs/FbsStockDialog.test.ts
- backend/app/api/fbs_sellers.py
- backend/tests/test_wms417_stock_http_contract.py
- docs/reviews/wms417-stock-ui-api-20260910.md
- docs/reviews/wms417-stock-review-followup-20260910.md — ссылка на это продолжение

Изменения c14abc46 и21c46002 сохранены. Новых таблиц/журналов/счётчиков, страниц,
тем и фильтров WB/Ozon нет. WMS-418 принадлежит root в отдельном worktree;
его код не тронут. Упаковка не меняется, формула min(cap,free) сохранена.
Тестовые данные только синтетические; клиентские stock/financial операции,
секреты/ключи/квота не использовались и не изменялись ради тестов.

## Граница приёмки

Три конкретных межслойных дефекта из отчёта21c46002 устранены в коде и проверены
тестами. Это не закрывает независимое review/CI/browser/live acceptance.
CUA вернул browsers=[], у нативного Chrome доступен лишь заголовок окна, без
элементов управления; getScreenshot ответил «Screenshot unavailable». Чужое
окно отмен не использовалось и не изменялось. Кнопки WMS не нажимались.

Нужен ручной проход на согласованном стенде из итогового SHA: одиночный и
массовый редактор, проценты→штуки с прежним cap выше free, отказ увеличения,
перечитывание GET/PUT и отсутствие потери WB/Ozon значений. Интеграцию с WMS-418
проводит координатор узкими изменениями, не перезаписью файлов. Выпуск пакета,
содержащего спорный111/112, запрещён; исполнитель не делает merge/deploy.
