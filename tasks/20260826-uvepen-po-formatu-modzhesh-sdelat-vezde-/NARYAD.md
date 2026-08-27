# Наряд · 20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-

**Полоса:** обычная
**Тип:** экран
**Заведён:** 26.08.2026

## Просили дословно

> увепен по формату ? моджешь сделать? везде глде мы шк короьов делаем

## Экраны

- `S-12` — Отгрузки на МП
- `S-17` — Приёмка
- `S-20` — Сортировка
- `S-22` — Операционная приёмка

## Границы правки

- `backend/app/services/box_barcode_service.py`
- `backend/app/services/warehouse_box_service.py`
- `backend/app/services/inbound_intake_box_service.py`
- `backend/tests/test_box_barcode_service.py`
- `frontend/tests-e2e/ff-inbound-boxes.spec.ts`
- `frontend/tests-e2e/ff-inbound-box-intake.spec.ts`
- относящиеся к генерации коробов проверки в существующих backend-тестах
- `tasks/20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-/`
- `docs/evidence/20260826-uvepen-po-formatu-modzhesh-sdelat-vezde-/`

## Строго вне границ

- FBS-короба и их внутренний формат `FBS-*`.
- Получение от WB, хранение и печать QR грузомест FBS.
- Получение от WB, хранение и печать общего QR FBS-поставки.

## Статус

- [x] арх-решение — не требуется (единое правило существующих коробов)
- [x] контракт
- [x] разработка — 18-символьный формат и физический 203-dpi regression
- [x] критик исполнения — `CODE_REVIEW_PASSED` после печатного rework
- [x] судья в живом браузере — `PRODUCT_BROWSER_APPROVED`
- [x] доказательства — полный backend/frontend-гейт и живые скриншоты
- [ ] влито

## Текущее состояние

Полный backend-гейт зелёный: Ruff, mypy, `1054 passed, 5 skipped`.
Production build и полный Playwright зелёные: `202 passed, 7 skipped`.
Код, полные гейты, финальный review и независимый живой браузер зелёные.
Остаются Git commit/push, PR/CI, вливание и production deploy.
