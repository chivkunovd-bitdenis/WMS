# WMS-658 F4: передача разработчика

Продуктовый commit: `441ce28536837b70a3e6fc8b6d4b1e6121f264b2`.
База frozen contract: `a9443e3f3ceee39f3dae04d72bc3cf61fc75a1dd`.
Review: `3df33bab7`. Прочитаны AGENTS.md, актуальный origin/etalon,
developer skill, актуальный review и tester handoff
`ambiguous-source-test-contract-final.txt`. Работа только в
`codex/night1007-658`, исходное дерево чистое.

Изменён только `backend/app/services/marking_import_audit_service.py`.
Извлечение source evidence выполняется постранично существующим extractor,
поэтому его file-wide dedup не удаляет второй макет того же полного CIS на
другой странице. Все кандидаты объединяются по полному исходному payload;
разные сигнатуры оставляют `source_to_artifact_layout`. Одинаковые повторные
сигнатуры на разных страницах не создают неоднозначность сами по себе.
Если extractor не возвращает все повторные области внутри одной страницы,
проверка числа decoded occurrences оставляет evidence gap. Аудит не выдаёт
первую область за полностью проверенный источник. Все операции с PDF в памяти.

Штатный import dedup, полный payload, flags, WB nmID guard и печать не менялись.
Frozen tests, requirements, guards/CI и incidentreport из `4be907b` не менялись;
их diff перед коммитом пуст. Чужие worktree не использовались.

## Фактические проверки

До правки выполнен только новый frozen F4 test на базе `a9443e3f3`:
**RED, 1 failed**, 2.76 s. Падение на строке 1151:
`assert 'source_to_artifact_layout' in report['evidence_gaps']`, фактически `[]`.
Все предварительные assertions двух страниц, полного payload, разных
артикулов и одной parsed строки прошли. Декодер завершился без timeout.

После правки выполнен один адресный набор **6 PASS, 0 skip**, 3.73 s,
SQLite в памяти, один worker. Команда из backend:

```sh
PYTHONDONTWRITEBYTECODE=1 WMS_TEST_DATABASE_URL=sqlite+aiosqlite:///:memory: \
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest \
  -n 0 -p no:cacheprovider -q --tb=short -o faulthandler_timeout=60 \
  tests/test_wms658_marking_import_contract.py::test_c22_audit_reports_ambiguous_layouts_for_same_cis_in_one_source_pdf \
  tests/test_wms658_marking_import_contract.py::test_c22_audit_accepts_unchanged_label_cropped_from_supplier_page \
  tests/test_wms658_marking_import_contract.py::test_c22_incident_audit_is_read_only_and_reports_first_divergence \
  tests/test_wms658_marking_import_contract.py::test_c22_audit_reports_source_to_saved_label_substitution \
  tests/test_wms658_marking_import_contract.py::test_c22_audit_reports_raster_final_label_substitution \
  tests/test_wms658_wb_honest_sign_contract.py::test_c19_c20_backfill_rejects_raw_nmid_that_does_not_belong_to_product
```

Ruff изменённого audit service — PASS. Mypy того же файла
(`--cache-dir=/dev/null`) — PASS. `git diff --check` — PASS.
Новых dependencies, широких прогонов, frontend/full build и агентов не было.

## Ограничения

Синтетические проверки не закрывают реальный инцидент 04.10. Исходный PDF и
фактический конечный print PDF/PNG по сохранённому incidentreport недоступны,
их нельзя считать сравнёнными или восстановленными. Сам отчёт не изменён.
Новая независимая перепроверка, приёмка и CI этого SHA остаются следующими
этапами. Production/database mutations, секреты, внешние API, merge/deploy
не выполнялись.
