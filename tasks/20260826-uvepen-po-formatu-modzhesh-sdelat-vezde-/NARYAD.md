# Наряд · 20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-

**Полоса:** обычная
**Тип:** экран
**Заведён:** 26.08.2026

## Просили дословно

> увепен по формату ? моджешь сделать? везде глде мы шк короьов делаем

## Экраны

- `S-03` — FBS
- `S-12` — Отгрузки на МП
- `S-17` — Приёмка
- `S-20` — Сортировка
- `S-22` — Операционная приёмка

## Границы правки

- `backend/app/services/box_barcode_service.py`
- `backend/app/services/warehouse_box_service.py`
- `backend/app/services/inbound_intake_box_service.py`
- `backend/app/services/fbs_packing_box_service.py`
- `backend/tests/test_box_barcode_service.py`
- относящиеся к генерации коробов проверки в существующих backend-тестах
- `tasks/20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-/`
- `docs/evidence/20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-/`

## Статус

- [x] арх-решение — не требуется (единое правило существующих коробов)
- [x] контракт
- [x] разработка — код и целевые тесты; общий backend-гейт красный на базовых ошибках
- [ ] критик исполнения
- [ ] судья в живом браузере
- [x] доказательства — автоматические проверки и полный backend-прогон
- [ ] влито

## Текущий блокер

Релизная готовность не подтверждена: полный backend-гейт содержит 69 ошибок Ruff,
19 ошибок mypy и 6 упавших тестов вне изменённой зоны. Живой браузер и вливание
не выполняются до зелёного обязательного гейта.
