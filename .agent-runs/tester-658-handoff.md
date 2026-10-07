# WMS-658: передача тестового контракта

Тестовый контракт сохранён коммитом `6a5ff0e39ea05d0503908a7ca1cb9139018db24d`
(`WMS-658: контракт тестов`) поверх проверенного `origin/etalon`
`4b298efc95be7b4b6b7fe5665be9f3671f1fe747`.

В коммите только контрактные тесты: backend C1–C22, включая проверки
нормализованной идентичности и WB Honest Sign, и frontend C4. Продуктовый код,
CI/guards и AGENTS/CLAUDE не менялись. В качестве read-only источника прежних
тестов использована только ветка `night/wms-658-5beb52da`.

## Обязательный RED до продукта

Выполнено из `backend` текущего checkout:

```sh
PY=/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python
"$PY" -m pytest -n 0 \
  tests/test_wms658_marking_import_contract.py::test_c22_incident_audit_is_read_only_and_reports_first_divergence \
  -q --tb=short
```

Результат на чистом etalon: **RED, 1 failed** за 0.84 s. Ожидаемая причина —
`ModuleNotFoundError: app.services.marking_import_audit_service`: на etalon нет
read-only аудита импорта. Это не ошибка фикстуры и не подмена результата
синтетическим успехом.

C22 требует, чтобы аудит конкретного импорта:

1. при `final_print_pdf=None` вернул `final_print_pdf` в `evidence_gaps`, не
   объявляя отсутствие файла успешным сравнением;
2. при одном DataMatrix, но пересобранном визуальном макете, вернул
   `first_divergence == "final_print_layout"` и `final_print_layout` в
   `evidence_gaps`;
3. сохранил read-only границу: коды и пулы до и после каждого вызова равны;
4. при удалённой строке `MarkingCodeImportFile` отметил одновременно
   `source_pdf` и `final_print_pdf` как пробелы доказательств.

Сценарий использует управляемый байтовый источник PDF только вместо внешнего
object storage. Он не утверждает, что расследовал инцидент 04.10.2026: для
этого по R11 остаются нужны точный импорт, исходный файл и фактический конечный
PDF/PNG.

## Выполненные проверки контракта

```sh
cd backend
PY=/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python
"$PY" -m pytest --collect-only -q \
  tests/test_wms658_marking_import_contract.py \
  tests/test_wms658_normalized_identity_regression.py \
  tests/test_wms658_wb_honest_sign_contract.py
"$PY" -m ruff check \
  tests/test_wms658_marking_import_contract.py \
  tests/test_wms658_normalized_identity_regression.py \
  tests/test_wms658_wb_honest_sign_contract.py
git diff --check
```

Результаты: **PASS** — pytest обнаружил 57 backend-сценариев; **PASS** — Ruff;
**PASS** — `git diff --check` перед коммитом.

Для прозрачности: целевой mypy на трёх новых backend-файлах пока **RED** с 16
ошибками ровно по отсутствующим на etalon продуктовым API (`build_import_result_pdf`,
`find_marking_code_by_cis_identity`, `marking_catalog` и др.). Скрывать их
`type: ignore` или ослаблять ожидания нельзя: эти ошибки подтверждают, что
контракт требует ещё не перенесённую реализацию.

Проверка frontend-контракта командой
`npx vitest run src/screens/shared/MarkingImportDialog.wms658.test.ts` не
запустилась: в checkout отсутствует пакет `vitest`; `npx tsc --noEmit -p
tsconfig.app.json` также не доступен без установленного TypeScript. Зависимости
не устанавливались, поскольку это не входит в контракт тестировщика. После
переноса продукта разработчик должен установить штатное окружение проекта и
прогнать frontend-тест, `tsc`, а затем backend PASS-команды на точном SHA.
