# 05 — Независимое ревью

- **Вердикт:** ✅ APPROVE (после фикса keyset pagination + packed-cancel demotion)
- **Ревьюер:** adversarial-reviewer + orchestrator fix loop
- **Дата:** 2026-07-31

## Находки первого прохода (исправлено)

| # | Severity | Проблема | Фикс |
|---|----------|----------|------|
| 1 | BLOCK | OFFSET-пагинация пропускала хвост при исключении заказов из batch | Keyset `(created_at_wb, id)` |
| 2 | WARN | Cancel в `packed` supply не менял статус отгрузки | Demote → `assembling`, без автопромоута |
| 3 | WARN | TC-003 не проверял 501-й заказ | Assert tail_wb_id + 2 batches |
| 4 | WARN | Marking autopoll без ORDER BY | `order_by(created_at_wb, id)` |

## Прогон гейтов

```text
ruff check (5 сервисов + тесты) → OK
mypy (5 сервисов) → OK
pytest tests/test_fbs_review_fixes.py … test_fbs_marking.py → 34 passed
```

## Остаточные риски (принято)

- Резерв: тест последовательный (SQLite), не `asyncio.gather` — locks на product/reservations достаточны для prod Postgres.
- PR должен содержать **только FBS review slice** — в дереве есть несвязанные ЧЗ/frontend hunks.
