# 00 — Триаж

- **Задача (одной строкой):** добавить на вкладку FBS «Новые» фильтр по складам селлера и выкатить срочно на прод.
- **Тип:** `feature`
- **Размер:** `S`
- **GitHub Issue:** нет; срочный прямой запрос пользователя в Codex 2026-08-12.
- **Стоит ли делать сейчас / зачем:** да; оператору нужно быстро сужать новые FBS-заказы до конкретного склада, чтобы не смешивать сборку разных складских привязок.

## Маршрут (из типа+размера, см. `.dev/PROCESS.md` §1)
- [x] 0 триаж (этот файл)
- [x] 1 анализ + арх-коучинг
- [x] 🔒 ГЕЙТ 1: арх + стек
- [x] 2 контракт (пропуск для S)
- [x] 3 тест-дизайн (+ маппинг на TC-ID)
- [x] 4 код (вертикальный срез)
- [ ] 5 независимое ревью + прогон гейтов
- [ ] 🔒 ГЕЙТ 2 приёмка (опц.)
- [ ] 6 док → `docs/`

## Что затрагивает (первая прикидка)
- backend API: `backend/app/api/fbs_orders.py`;
- backend service: `backend/app/services/fbs_worklist_service.py`;
- frontend FF portal: `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`, `frontend/src/screens/v2/fbsApi.ts`;
- tests: backend worklist regression and Playwright FBS orders scenario;
- no DB migration, no new WB calls, no secret handling.
