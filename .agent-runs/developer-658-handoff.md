# WMS-658: передача разработчика

Продуктовая реализация сохранена локальным коммитом
`77abb8e3daece5ca4b3b8eed7580c0afe612cb1f`
(`WMS-658: реализация импорта и расследования`) поверх тестового контракта
`6a5ff0e39ea05d0503908a7ca1cb9139018db24d`. Ветка
`codex/night1007-658` не опубликована и `main` не менялся.

## Что перенесено

- три серверных пути импорта КИЗ используют общий атомарный механизм: допустимый
  новый код связывает товар и включает `requires_honest_sign`; дубликат,
  неправильный seller/tenant и откат не оставляют флаг или лишние сущности;
- для PDF сохранены происхождение и обязательность исходного артефакта, а печать
  результата принимает только коды указанного `import_batch_id` в запрошенном
  порядке; отсутствующий обязательный артефакт не заменяется новым кодом;
- добавлены миграции provenance, сервис правил WB (`needKiz` или официальный
  родитель «Одежда»), read-only dry-run/apply backfill и интеграция со штатной
  синхронизацией карточек;
- диалог загрузки показывает каталог выбранного селлера независимо от текущего
  флага ЧЗ и даёт печатать точный результат импорта;
- `marking_import_audit_service` читает только данные и сохранённые артефакты.
  При `final_print_pdf=None` он возвращает `final_print_pdf` в `evidence_gaps`.
  Если payload DataMatrix совпал, но финальный PDF имеет другой визуальный
  макет, он возвращает `first_divergence=final_print_layout` и соответствующий
  evidence gap. Аудит не создаёт коды, пулы или связи.

## Файлы продуктового коммита

- `backend/alembic/versions/20261005_0658_marking_code_artifact_provenance.py`
- `backend/alembic/versions/20261005_0658b_import_artifact_provenance.py`
- `backend/app/api/marking_codes.py`
- `backend/app/api/seller_catalog.py`
- `backend/app/models/marking_code.py`
- `backend/app/services/marking_code_service.py`
- `backend/app/services/marking_import_audit_service.py`
- `backend/app/services/marking_label_artifact_service.py`
- `backend/app/services/seller_fulfillment_catalog_service.py`
- `backend/app/services/wb_honest_sign_service.py`
- `backend/app/services/wildberries_product_import_service.py`
- `backend/app/services/wildberries_product_sync_service.py`
- `frontend/src/screens/shared/MarkingImportDialog.tsx`

## Проверки

В `backend` прошли:

```sh
PY=/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python
"$PY" -m pytest -n 0 \
  tests/test_wms658_marking_import_contract.py \
  tests/test_wms658_normalized_identity_regression.py \
  tests/test_wms658_wb_honest_sign_contract.py -q --tb=short
```

Результат: **48 passed, 9 skipped**. Пропущены только маркированные сценарии
конкуренции с реальным PostgreSQL: в текущем запуске использовалась SQLite,
конфигурацию подключения не читали и не меняли.

Также прошли Ruff и mypy по десяти затронутым backend-модулям и двум миграциям,
а `git diff --check` был чист перед продуктовым коммитом.

Фронтенд-проверки `vitest`, `tsc` и `npm run build` не запускались: в worktree
нет исполняемых `node_modules/.bin/vitest` и `node_modules/.bin/tsc`.
Зависимости не устанавливались, `npm ci` не выполнялся.

## Оставшиеся границы

Реальный инцидент 04.10.2026 не закрыт: исходный PDF и фактический конечный
PDF/PNG отсутствуют. Реализация честно отмечает их отсутствие как evidence gap,
не восстанавливает их и не считает синтетические тестовые PDF доказательством.
Не проводились production-операции, миграции на стенде, внешняя загрузка,
изменение секретов, browser-приёмка, физическая печать, независимое ревью,
аналитическая приёмка, CI, push, merge или deploy. Ручной C23 и read-only
подтверждение текущих production-данных для R10/R11 остаются следующими этапами.
