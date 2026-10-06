# WMS-675 · Функциональное восстановление инцидента на private PostgreSQL

Результат: **1 PASS**, `test_bambook_exact_31_recovers_26_once`, 06.10.2026. Проверен тестовый SHA `afb35e33de98f04956d7b13fdba6dc12e4612df3`; база общего product-кандидата `acd0523e9986e89149959319c74fd355c659d22e` (исправленный classifier662). Отдельная ветка `codex/wms675-incident-regression-20261006`. Контракт до первого запуска: `1f49257d66f64a17fec5b70cb4a55156213382c4`.

## Что реально выполнено

Своя PostgreSQL16.14, новая БД `wms_test_675_incident_20261006_01`, собственный кластер в этом worktree. Server identity проверен SQL: `wms_test_675_incident_20261006_01|wms_test|127.0.0.1|55475`; другие mutating DB/production не использовались. Схему строил стандартный `backend/tests/conftest.py`, основу данных — готовая seed662. Новые fixture tenant/seller/warehouse/product/order IDs изолированы; реальные posting/SKU/offer/qty/status сохранены. История прихода сведена к сохранённому net balance, incident expense0; 31 сохранённый ledger recipe перенесён с remap локальных ID. Старые11 facts/22 charges созданы настоящим billing service до восстановления.

Основание: сохранённые `fresh-read-position-classification.json`,31 `live-ozon-run-20261006-attempt1/posting-*.json` и `accounting-refresh-20261006-attempt1/{orders_positions_reserves,ledger,balances_locations,operation_facts,billing_entries}.csv`. Нового live-аудита не было. HTTP MockTransport отвечает очищенными настоящими cards только на `/v3/posting/fbs/get`; production transport/provider/classifier настоящие. Иное внешнее HTTP запрещено тестом. Подменён лишь внешний stock-publish dispatch в тестовой среде; обычные intentions создаются, seller scope проверен. В production runtime overrides/monkeypatch/suppression отсутствуют.

Реальные `ozon_targets` → `make_observation` → `save_observations` → supply/order/product locks → `conduct_supply` → commit. `prepare_shipment_sources`, `write_off_order`, inventory/ledger/reservations/billing не подменены. Проверки результата открывают новые DB-сессии после commit. Второй вызов повторно читает все31 cards и запускает тот же сервис.

| Проверено | Фактический результат теста |
|---|---|
| Positive26 | 9 pickup_point +6 on_way_to_city delivering,11 delivered/received,qty1 |
| Исключения | 4 cancelled (включая2 cancelled_after_ship=true),1 awaiting; расход/биллинг0 |
| Расход и ledger | 26 новых shipment movements по -1; completed26; reversal0 |
| SKU1586484429 | 458→454, расход4 |
| SKU1697770458 | 285→277, расход8 |
| SKU1586466682 | 389→384, расход5 |
| SKU1695128938 | 536→534, расход2 |
| SKU1589998415 | 202→195, расход7 |
| SKU1695134284 awaiting | 239→239, расход0 |
| Резерв | position16→1, legacy0; остался только awaiting |
| Биллинг | facts11→26, charges22→52; ровно1 fbs_order+1 packing на positive order; quantities1; старые IDs/quantity/amount и22 line IDs сохранены |
| Документ/отмены | draft остаётся draft, delivered_at null из-за awaiting; исключённые статусы сохранены |
| Повтор | Те же movement IDs/fact IDs/charge IDs/line IDs, остатки/резервы/ledger quantities без изменений; новая дельта0 |

## Команда и вывод

Из `backend`, существующий venv; `WMS_TEST_DATABASE_URL=postgresql+asyncpg://wms_test@127.0.0.1:55475/wms_test_675_incident_20261006_01`. JWT использован только искусственный test value, secret/broker settings явно пустые; боевые ключи не читались.

```sh
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -s -o addopts='' tests/test_wms675_recovery_scenario.py
```

```text
WMS675 isolated database: wms_test_675_incident_20261006_01 127.0.0.1:55475
WMS675 recovery verified: expense=26 reserve=16->1 facts=11->26 charges=22->52 existing IDs preserved; repeat expense/facts/charges delta=0; SKU deltas=4/8/5/0/2/7
1 passed, 6 warnings in 3.44s
```

Шесть предупреждений — deprecation Starlette422/Swig, не failures. Targeted ruff: All checks passed. Полный CI/прочие suites не запускались и не объявлены PASS.

## Предыдущие попытки и предел приёмки

До PASS были4 ошибки подготовки/чтения моей test fixture, переданные ведущему по мере обнаружения: `1f49257d6` — inet address возвращал /32; `052d076c5` — пропущен обязательный deadline_at; `905ecadef` — пропущен reserve_status; `21bb4068b` — physical/billing_quantity нужно читать из BillingLedgerLine, не Entry. Исправления только теста, отдельные commits до успешного запуска; бизнес-ожидания26/16→1/11+15/22+30/повтор0 не ослаблялись. Продуктовый service defect этим прогоном не обнаружен.

Для общей интеграции: новый тест и этот proof/requirements; ранее опубликованный план/progress `ced5a713e56d3bb4fe2c310d3813306f08446ce2` остаётся источником штатного послерелизного пути (в точной исходной базе acd0523e документы плана ещё старые). Здесь их не меняли: владение только incident test/proof/requirements.

**Принята функциональная проверка на testDB; actual production recovery NOT_PERFORMED.** После общего CI/выпуска и команды ведущего нужен свежий exact external proof + current ledger/reserve/billing, новый расчёт missing и штатное проведение только остатка. Обычная публикация остатков остаётся частью application поведения; caps не меняются, точные внешние значения/число публикаций не доказаны. Этот тест не проверяет реальные bindings/caps/внешнюю публикацию и не заменяет production readback.
