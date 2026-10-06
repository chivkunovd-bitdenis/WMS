# WMS-684 + WMS-586 — передача разработчика

Последний законченный шаг: исправлена пагинация PDF по follow-up review 77efb37d и опубликованному до кода контракту 49ba6eb0c121c7f75e1b5a7f0668b35f315ca061. Все 36 адресных backend-проверок прошли; ветка ожидает повторного независимого ревью и продуктовой приёмки.

## Цикл WMS-586: строка выше страницы (07.10.2026)

Меняются только `backend/app/services/inbound_acceptance_act_service.py` и этот handoff. Frozen-тесты, требования и прежние исправления стикера/даты/номера сохранены.

Вместо исключения `acceptance_act_pdf_row_too_tall` строка продолжается на следующих страницах в исходных колонках. Размещаемый префикс определяется фактическим результатом `insert_textbox`, с предпочтением границы строки/слова. Остаток передаётся следующей странице без удаления исходных символов. Уже напечатанные поля, включая номер строки и количества, повторно не выводятся. Итого формируется существующим кодом после полного завершения строк. Размер шрифта товара остаётся 7,5 pt. На страницах продолжения одной строки заголовки не вставляются между фрагментами текста, что сохраняет порядок извлечения имени из PDF.

Проверки выполнялись последовательно существующим `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python`, без установки зависимостей:

```sh
cd backend
python -m ruff check app/services/inbound_acceptance_act_service.py
python -m mypy app/services/inbound_acceptance_act_service.py
python -m pytest -n0 -p no:cacheprovider tests/test_wms586_acceptance_act_contract.py tests/test_wms586_review_regression_contract.py tests/test_wms684_586_scope_contract.py -q --tb=short
```

Ruff и mypy прошли. Pytest: **36 passed**, 6 существующих предупреждений об устаревших API/типах PyMuPDF. Новый реальный HTTP-контракт подтверждает 200 вместо 500, полный текст всех 64 строк/255 символов, корректные план/факт/разницу и единственное итого. Прежние контракты проверяют пятистрочное имя, 321 товар, данные/даты/права, отсутствие записей при повторных/одновременных скачиваниях и границы изменений.

Дополнительная диагностическая проба реального генератора с подменой только чтения синтетического документа: длинное имя между двумя обычными товарами, 64 и 128 явных строк, в обоих случаях 255 символов. Получено 3 и 4 страницы соответственно; весь текст извлекается, количества каждой строки и итог 15/12/−3 присутствуют один раз, все текстовые координаты внутри страницы, пустых страниц нет. Растры начала/конца продолжения и последней страницы просмотрены через `view_image`: нет обрезания и наложений. Локальные синтетические образцы — `.agent-runs/developer-586-pagination-{64,128}.pdf` и соответствующие PNG; это вспомогательные файлы, не сохранённые в Git доказательства независимого ревью. Для восстановления проверки используется frozen HTTP-контракт из коммита 49ba6eb0.

Полный локальный suite/build, независимое ревью, приёмка, CI и deploy в этом цикле не выполнялись. Ниже сохранена история предыдущих циклов; её результаты не заменяют повторное независимое ревью пагинации.

Реализовано:

- стикер короба приёмки содержит номер короба, селлера, номер собственной приёмки и её московскую дату; исходный штрихкод, одиночная и массовая печать сохранены;
- PDF акта приёмки добавлен рядом с существующим Excel и строится из тех же плановых/фактических строк, расхождений и итогов;
- API и экран используют PDF/Excel только для завершённой приёмки; накладная, выбор строк и настройки не менялись;
- наивный `created_at`, который SQLite возвращает без временной зоны, трактуется как UTC до перевода в московскую дату.

Повторный цикл по dc5ee181:

- PDF до размещения строки измеряет результат `insert_textbox`; явные переводы строк входят в начальную оценку, строка увеличивается на фактический дефицит высоты, а невозможность разместить поле не замалчивается;
- компактный макет с реквизитами включается только при `metadata`, поэтому грузоместо и короб отгрузки остаются в исходной сетке;
- стикер без зоны трактует дату как UTC, а номер получает через `formatHumanDocumentNumber` с fallback `—`.

Проверено:

- `cd backend && pytest -n0 tests/test_wms586_acceptance_act_contract.py tests/test_wms684_586_scope_contract.py` — 34 passed;
- `cd backend && ruff check app/api/inbound_intake.py app/services/inbound_acceptance_act_service.py` — passed;
- `cd backend && mypy app/api/inbound_intake.py app/services/inbound_acceptance_act_service.py` — passed;
- `cd frontend && npx tsc --noEmit -p tsconfig.app.json` — passed;
- целевые Vitest-контракты WMS-586, WMS-684 и Chromium/PDF-проверка с декодированием Code128 — passed.
- `cd backend && pytest -n0 -p no:cacheprovider tests/test_wms586_acceptance_act_contract.py tests/test_wms586_review_regression_contract.py -q --tb=short` — 33 passed;
- `cd frontend && npx vitest run --config ../.agent-runs/vitest.tester.config.mts --maxWorkers=1 --no-file-parallelism --no-cache src/screens/ff/FfInboundRequestView.wms684.dom.test.tsx src/screens/ff/FfInboundRequestView.wms684.review-regression.dom.test.tsx` — 16 passed;
- `cd frontend && npx vitest run --config ../.agent-runs/vitest.tester.config.mts --maxWorkers=1 --no-file-parallelism --no-cache src/screens/ff/FfInboundRequestView.wms684.pdf.test.tsx` — 2 passed;
- повторные `ruff`, `mypy` для PDF-сервиса и `tsc` фронтенда — passed.

Ограничения: в этой сессии нет разрешённого браузерного средства для просмотра рабочего экрана, поэтому визуальная CUA-проверка остаётся за аналитиком. Полный suite, build, независимое ревью, приёмка, CI и deploy этим шагом не выполнялись.
