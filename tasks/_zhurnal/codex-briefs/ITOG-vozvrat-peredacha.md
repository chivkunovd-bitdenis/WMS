# Итог: сторож возврата после передачи поставки WB

Дата проверки: 29.08.2026.

## Что изменено

В `reverse_fbs_shipment_if_needed` добавлена проверка факта передачи поставки по
`fbs_supplies.delivered_at`. Поставка ищется по текстовому
`order.wb_supply_id` в пределах арендатора; пустой `order.supply_id` для этого
не используется.

Старое условие `supplier_status == "complete"` сохранено как дополнительное.
Сторож блокирует возврат, если поставка уже передана либо статус поставщика всё
ещё равен `complete`. При блокировке он пишет предупреждение в лог, проставляет
`ledger.reversed_at`, не создаёт складского движения и возвращает `False`.

Параметр `skip_if_supplier_complete`, передача `actor_user_id` в складское
движение и разбор многопозиционных заказов Ozon через
`ledger.ozon_positions_json` не изменялись.

## Проверенные сценарии

- Переданная поставка, `supplier_status == "cancel"`, пустой `order.supply_id`:
  возврат заблокирован по текстовому `wb_supply_id`, функция вернула `False`,
  новое движение не создано, `reversed_at` заполнен.
- Непереданная поставка с пустым `delivered_at`: товар вернулся на остаток для
  статусов `new` и `confirm`.
- Прежний случай `supplier_status == "complete"`: возврат по-прежнему
  блокируется даже без связанной поставки.
- Адресный файл Ozon прошёл без регрессии.

## Ворота

Из каталога `backend/` выполнено:

```text
ruff check .
All checks passed!

mypy .
Success: no issues found in 390 source files

python3 -m pytest tests/test_fbs_writeoff_sold_and_reversal_guard.py tests/test_fbs_ozon_lane.py -q
39 passed in 30.54s
```

Полный `pytest` не запускался согласно ограничению задачи. Выкатка и изменение
боевых данных не выполнялись.
