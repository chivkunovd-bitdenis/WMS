# 05 — Ревью + прогон

## Независимое ревью
- **Ревьюер:** Codex subagent `019ff50d-d342-71b1-babf-7b9e099a78be`.
- **Вердикт:** блокеров нет.
- **Что учтено после ревью:** выбранный склад теперь сбрасывается на «Все склады», если после refresh/sync backend больше не возвращает его в `warehouse_options`.
- **Оставшийся осознанный риск:** в режиме «Все селлеры» общий физический WMS-склад остаётся одной опцией. Это соответствует текущему фильтру по `warehouse_id`; если нужен строго WB-склад конкретного селлера, надо отдельным запросом добавить фильтр по `wb_warehouse_id` + seller.

## Прогон проверок
- backend style: `cd backend && python -m ruff check .` — green.
- backend types: `cd backend && python -m mypy .` — green.
- backend regression: `python -m pytest backend/tests/test_fbs_worklist_query_count.py` — `3 passed`.
- frontend build: `cd frontend && npm run build` — green.
- frontend e2e: `cd frontend && npm run test:e2e -- ff-fbs-orders.spec.ts` — `4 passed` on the main-based hotfix branch.

## Итог
Критерий TC-S17-025 закрыт на backend и browser UI. Миграций и secret-действий нет.
