# Наряд · 20260826-davay-esche-vnedrim-sistemu-esli-u-nas-n

**Полоса:** обычная
**Тип:** существующий FBS-процесс
**Экран:** S-03 `/app/ff/fbs`

## Просили дословно

> Давай ещё внедрим систему. Если у нас нет как бы остатков, ну мы их списываем,
> пускай они лучше в минус уходят, потому что ноль — это некорректно.

## Границы правки

- `backend/app/services/inventory_service.py`
- `backend/app/services/fbs_packaging_integration_service.py`
- `backend/app/services/fbs_shipment_service.py`
- `backend/app/services/fbs_cancellation_service.py`
- `backend/app/models/fbs_shipment_reversal_ledger.py`
- `backend/app/cli/reconcile_fbs_unlinked_shipments.py`
- `backend/alembic/versions/20260826_0103_fbs_shipment_movement_link.py`
- `backend/tests/test_fbs_packaging_integration.py`
- `backend/tests/test_fbs_packaging_fulfillment.py`
- `backend/tests/test_fbs_shipment_warehouse_sc.py`
- `backend/tests/test_fbs_review_fixes.py`
- `backend/tests/test_reconcile_fbs_unlinked_shipments.py`
- `tasks/20260826-fbs-writeoff-on-shipment/TASK.md`
- `tasks/20260826-davay-esche-vnedrim-sistemu-esli-u-nas-n/CONTRACT.md`
- `tasks/20260826-davay-esche-vnedrim-sistemu-esli-u-nas-n/NARYAD.md`

Фронтенд и формат API не меняются.

## Статус

- [x] арх-решение — не требуется, меняется существующий FBS-процесс
- [x] контракт
- [x] разработка
- [x] ревью
- [x] проверки
- [ ] commit и push
- [ ] влито и проверено на проде
