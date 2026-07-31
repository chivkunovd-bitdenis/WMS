# 01 — Анализ + арх-коучинг

## Продуктовая часть
- **Проблема/цель:** после мержа FBS autopoll+packaging отгрузка может «зависнуть» при отмене заказа; резерв может перепродаться; старые заказы перестают синкаться; PACKED может встать до проверки КИЗ WB.
- **Ожидаемое поведение:** отменённый заказ уходит из отгрузки, упаковка пересчитывается, отгрузка двигается дальше или возвращается в черновик; резерв атомарен; все нетерминальные заказы рано или поздно синкаются; PACKED только при валидном КИЗ.
- **Границы:** находка #5 (WB до commit) — только запись в анализ, не кодим. Мелочи (мёртвый код deliver_supply, BackgroundJob) — вне scope.
- **MVP:** не противоречит `docs/MVP_DECISIONS_RU.md` (FBS import-only, термин «отгрузка»).

## Техническая часть

### Как устроено сейчас
1. **Отмена** (`fbs_cancellation_service.py:34-40`): `NON_CANCELLABLE` не включает ASSEMBLING/IN_SUPPLY/PACKED. При отмене — только `_release_reservation`, `supply_id` не трогается, `PackagingTaskLine.qty_total` не уменьшается → `is_task_complete()` ложь навсегда.
2. **Промоушен PACKED** (`fbs_packaging_integration_service.py:77-86`): `_supply_requires_marking` проверяет наличие sgtin, не `check_status`. Синк статусов маркировки — только ручной API (`fbs_marking_service.sync_order_marking_statuses`).
3. **Резерв** (`wb_marketplace_orders_service.py:287-319`): `available_qty_for_fbs_reserve` без `FOR UPDATE`; ветка existing order без `IntegrityError`-ретрая (в отличие от insert нового заказа `:433-443`).
4. **Статус-синк** (`wb_marketplace_orders_service.py:475-521`): `LIMIT 500` + `ORDER BY created_at_wb DESC`; `TERMINAL_FBS_STATUSES` не включает SORTED → sorted забивают выборку.

### Варианты и рекомендации

| # | Варианты | Рекомендация (Agent) |
|---|----------|----------------------|
| 1 | A) убрать из отгрузки + пересчёт упаковки B) запретить отмену в отгрузке C) error-state | **A** — отмена на WB неизбежна |
| 2 | A) PACKED ждёт check_status=ok B) достаточно наличия C) ok + синк в автопросе | **C** — ok + синк в status-autopoll |
| 3 | FOR UPDATE на резервах + IntegrityError retry | единственный путь |
| 4 | пагинация + исключить sorted из очереди синка | оба |

## 🎓 Вопросы (решены Agent в continuous mode)
1. Что делать с пустой отгрузкой после отмены последнего заказа? → **вернуть supply в `draft`, packaging_task_id оставить (задание можно переиспользовать) или обнулить task — см. 02-arch-decision**
2. PACKED без ok КИЗ? → **ждём ok, синк в автопросе**
3. sorted в синке? → **исключить из выборки (финал для FF)**
