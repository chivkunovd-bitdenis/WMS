# 05 — Независимое ревью — fbs-wb-emulator

**Вердикт: APPROVE with WARNINGS**

Дата: 2026-08-02  
Ветка: `feat/fbs-wb-emulator`  
База проверки: pytest `wb_emulator/tests/` (36 passed), анти-косяк из `TASK.md`.

## Что проверено

| # | Анти-косяк | Результат |
|---|------------|-----------|
| 1 | Поля ответов = то, что читает `wildberries_client.py` (camelCase) | OK для orders / supplies / stickers / meta (контракт-тесты) |
| 2 | `WILDBERRIES_MARKETPLACE_API_BASE` подхватывается | OK в `docker-compose.emulator.yml` на `api`, `celery_worker`, `celery_beat` |
| 3 | Прод-compose чист от эмулятора | OK — в `docker-compose.prod.yml` нет `wb-emulator` / env на emulator |
| 4 | Стикеры — валидный PNG | OK — magic bytes в media + full-cycle тестах |
| 5 | SQLite на volume | OK — `wb_emulator_data` + `WB_EMULATOR_DB_PATH=/data/...` |

## EMU-050 (закрытый инцидент)

1. Первая сдача: create был `GET /__admin/orders` — в ТЗ нужен **`POST`**. Исправлено (`833e848`).
2. При merge: дубль стора (`seed/orders_store.py` vs `services/orders_store.py`) и риск двух `/orders/new`. Сведено к одному `services/orders_store.py` (`317c69e`).

## WARNINGS (не блокеры v1 happy-path)

1. **Полный цикл «через WMS UI»** (автопрос → экран FBS → deliver) против живого compose — не прогонялся в этой сессии; есть контракт эмулятора + `test_full_cycle.py`. Рекомендуется smoke на стенде с overlay.
2. Seed баркодов — шаблон `seed/order_templates.json`; привязка к реальному каталогу селлера для `mapping=mapped` зависит от содержимого фикстуры на стенде.

## Закрыто в EMU-070/080
- `GET /api/v3/warehouses` и `/offices` — списки в форме клиента.
- Full-cycle pytest + `03/04/05/06` артефакты.

## Не трогали

- `backend/app/**` ради эмулятора не меняли в EMU-* коммитах (только новый сервис + test compose).
- `docker-compose.prod.yml` не меняли.
