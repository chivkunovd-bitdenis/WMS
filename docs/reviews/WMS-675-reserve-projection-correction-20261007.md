# WMS-675 · точечная сверка stale reserve projection

## Наблюдаемый факт и продуктовый вывод

После фактического recovery из receipt `f0411289b` external/ledger accounting
согласованы: 26 positive posting проведены, 5 cancelled не списаны,
`missing_delta=0`, а реальные строки `fbs_order_reservations` и
`fbs_order_product_reservations` для scope отсутствуют. Однако у 14 Ozon
positions заказов `done` оставалось `FbsOrderProduct.reserved_quantity=1`.

Это **не реальный резерв и не недоступный остаток**: расчёт свободного stock
`fbs_reserved_by_product` читает только две таблицы reservation rows. Но это
не безобидное отображение: поле отдаётся в FBS worklist API/UI и его
ненулевое значение блокирует штатный CLI merge duplicate products с причиной
`fbs_product_reservations_present`. Поэтому состояние должно быть
синхронизировано, но без нового расхода, billing или внешнего handoff.

## Минимальный штатный путь

Подходящая граница уже существует: `update_fbs_order_reservation(...,
reserve=False)`. До исправления она возвращалась сразу, когда фактических
reservation rows уже не было, и потому не очищала денормализованный position
projection. Минимальная корректировка очищает `reserved_quantity` и ставит
обычный `reserve_status=released` только в этом stale случае. Она не меняет
inventory movement, balance, ledger, billing, `conduct_supply`, targets или
marketplace transport; при реальных reservation rows сохраняется прежний
ветвящийся путь удаления.

Regression `test_release_reconciles_stale_ozon_position_projection_without_reservation_rows`
сначала был RED на deployed `4c` (position оставался `1`), затем PASS. Он
также повторяет release и доказывает идемпотентность, отсутствие real
reservation rows и неизменность availability (`reserved=0`).

## Операционный порядок после verified deploy этого fix

1. Новый read-only preflight ограничивает scope 14 order IDs с `status=done`,
   одним Ozon position и stale `reserved_quantity=1`; подтверждает ноль строк
   и количества в обеих reservation tables, journal 31/26, ledger completed
   26/no reversal, `missing_delta=0`, а также baseline facts/charges/stock.
2. В одной application transaction получить существующие
   `lock_order_batch_packaging_rows`, затем `lock_handoff_batch_products` для
   только этих 14 IDs. Reload orders/positions и reservation rows `FOR UPDATE`.
   Любое изменение состава, nonzero real reservation, incomplete ledger или
   nonzero missing delta останавливает correction без write.
3. Для каждого из этих 14 orders вызвать только
   `update_fbs_order_reservation(session, order, reserve=False)` и обычный
   `session.commit()`. Не вызывать `conduct_supply`, `save_observations`,
   billing, sync-statuses, Ozon ship/approve/deliver/create или SQL UPDATE.
4. Отдельная read-only session проверяет: 14 position projections=0; обе
   reservation tables=0; stock/ledger/facts/charges и 31 journal/targets
   неизменны; `missing_delta=0`. Повтор того же service path не меняет данные.

Это не новый продукт, runner или ещё одна WMS-662 recovery chain. До verified
deploy code commit к production не применяется.
