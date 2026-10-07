# WMS-663: исправления F1/F2/F3, передача независимому ревьюеру

06.10.2026. Замена недоступного разработчика 19130. Основание —
`docs/reviews/wms663-astra-7d9e9.md`; тестовый коммит до реализации:
`17296a81e991c4f7852629ae333a2a546148f4a3`. Его публикация проверена через
`git ls-remote origin refs/heads/codex/wms662-663-priority` до правки продукта.
Тестировщик зафиксировал 4 целевых FAIL и 2 PASS защит.

Изменён только `backend/app/services/ozon_exemplar_documents_service.py`.
Текущий выбор документа заменяет набор целей прежнего запроса. При сборке
полного payload накладывается только текущий выбор текущего document writer;
история документов не переносится поверх свежего снимка при сканировании КИЗ.
GET с сохранённым снимком теперь читает status через существующий resume,
обновляет сведения экземпляров и сохраняет локальное намерение и версию.
Поля, отсутствующие в status, и требования документов сохраняются.
Результат чтения сохраняется существующим checkpoint со сверкой версии.

Последующий подтверждённый marking set допускается при validation_in_process
независимо от истории документов. Классификация результата marking не зависит
от истории выбора ГТД/РНПТ. Проверки неизвестного результата, текущего writer,
версии и запрета update_not_available остаются.

## Выполненные проверки

Из backend, Python и инструменты из постоянного WMS/backend/.venv:

```text
python -m pytest tests/test_wms663_astra_regressions.py tests/test_wms663_customs_documents_contract.py -n 1 -q --tb=short
22 passed, 1 skipped, 12 warnings in 17.93s
python -m pytest tests/test_ozon_fbs_process_contract.py tests/test_fbs_ozon_lane.py tests/test_ozon_box_assembly.py tests/test_ozon_fbs_openapi_models.py -n 1 -q --tb=short
101 passed, 12 warnings in 18.28s
ruff check .
All checks passed!
mypy .
Success: no issues found in 552 source files
git diff --check
PASS
```

SKIP — существующая PostgreSQL-гонка; в этом исправлении она не повторялась.
Ожидания новых и прежних тестов не изменены. Другие исполнители работают
в том же checkout; их файлы и результаты не включаются в этот коммит.

Требуется новое независимое Astra high ревью именно исправленного SHA.
Этот документ — передача разработчика, не вердикт ревьюера или аналитика.
Приёмка, полный CI, DOM, визуальная проверка и выпуск здесь не объявляются.
Навыки и дочерние агенты не запускались. Production, Telegram, кабинеты
учётных данных и внешние операции Ozon не использовались. Merge/deploy нет.
