# WMS-658: C9 PostgreSQL и граница C19 live preflight

Проверено на SHA `a9cc021f90c9412875c79cef75836fab228a8df7`.

## C9: PostgreSQL-конкуренция

Выполнена ровно адресная команда из `backend`:

```sh
WMS_TEST_DATABASE_URL=postgresql+psycopg_async://deniscivkunov@127.0.0.1:5432/wms_test_658_identity_20261006 \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n 0 -q \
  tests/test_wms658_normalized_identity_regression.py::test_postgresql_workers_share_one_code_pool_and_link_for_identity_variants \
  --junitxml=.agent-runs/wms658-c9-pg.xml
```

Результат: **9 passed**, 0 skip, 4.02 s. Это девять параметризованных пар
конкурирующих import-путей и вариантов нормализованной идентичности КИЗ.
Фактическая JUnit-квитанция сохранена рядом:
`wms658-c9-pg-20261007.xml`.

## C19/R10: live read-only preflight

Требование нуждается в текущих `SellerWildberriesImportedCard.raw_json`,
`Product.wb_nm_id`, tenant/seller, `nmID`, `subjectID`, `needKiz` и актуальной
WB связи `subjectID -> parentID/parentName` с родителем «Одежда», после чего
должен быть сформирован точный dry-run список apply/skipped с причинами.

Существующий `build_backfill_plan` — сервисная функция, а не отдельный
read-only CLI/runbook. Найденный штатный вызов `fetch_category_catalog` в
seller-catalog/sync получает seller credential-token; sync имеет запись и не
является разрешённым read-only preflight. Отдельного обычного deployment
transport, который одновременно задаёт подтверждённую tenant/seller область,
открывает локальные raw-карточки и вызывает WB справочник без sync/записи,
в проекте не найдено.

Поэтому C19 live preflight **не запускался**: отсутствует готовый
авторизованный read-only путь и точная область tenant/seller. Не создавались
инструменты, не читались/не управлялись credentials, не выполнялись WB-вызовы,
backfill apply, remote sync или production-записи.
