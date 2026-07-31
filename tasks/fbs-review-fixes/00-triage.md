# 00 — Триаж

- **Задача (одной строкой):** Исправить 4 находки независимого ревью PR #103 (FBS autopoll/packaging): отмена вешает отгрузку, PACKED без валидации КИЗ, оверселл резерва, потеря заказов в статус-синке >500.
- **Тип:** `bug`
- **Размер:** `M` (4 связанных backend-фикса + тесты)
- **GitHub Issue:** нет (tasks/fbs-review-fixes/TASK.md)
- **Стоит ли делать сейчас / зачем:** критично — отгрузка может навсегда застрять в ASSEMBLING; остальное — data integrity / синк.

## Маршрут (bug M, см. `.dev/PROCESS.md` §1)
- [x] 0 триаж (этот файл)
- [ ] 1 анализ + арх-коучинг
- [ ] 🔒 ГЕЙТ 1: арх + стек (меняется поведение сервисов — да)
- [ ] 3 тест-дизайн (+ маппинг на TC-ID)
- [ ] 4 код (вертикальный срез backend)
- [ ] 5 независимое ревью + прогон гейтов
- [ ] 6 док (кратко в TASKLOG)

## Что затрагивает
- `backend/app/services/fbs_cancellation_service.py` — отмена
- `backend/app/services/fbs_packaging_integration_service.py` — упаковка/промоушен
- `backend/app/services/wb_marketplace_orders_service.py` — резерв, статус-синк
- `backend/app/services/fbs_autopoll_service.py` — синк маркировки в автопросе
- `backend/tests/test_fbs_*` — регресс + TC-NEW-FBS-FIX-*
