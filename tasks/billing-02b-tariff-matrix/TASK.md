# Волна 2Б: тарифная матрица

## 0. Как работать и открыть наряд

Работа выполняется только в worktree
`/Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826`, ветка
`codex/billing-module-20260826`. База — принятая волна 2А:
`60f82566e9adc65706b00ebb679c6725062801e6`. До независимого review этого
пакета наряд и product code не открываются/не меняются.

После `ACCEPTED` открыть ровно такой наряд:

```bash
python3 scripts/naryad.py new "Волна 2Б модуля «Расчёты»: тарифная матрица на экране Настройки ФФ" --screens S-19 --lane обычная --files backend/app/models/billing.py,backend/app/models/__init__.py,backend/app/models/packaging_task.py,backend/app/services/billing_tariff_matrix_service.py,backend/app/services/billing_configuration_service.py,backend/app/services/billing_ledger_service.py,backend/app/api/billing.py,backend/alembic/versions/20260826_0112_billing_tariff_matrix.py,backend/tests/test_billing_tariff_matrix.py,backend/tests/test_billing_configuration_api.py,backend/tests/test_billing_ledger_service.py,backend/tests/test_billing_invoice_service.py,backend/tests/test_billing_invoice_api.py,backend/tests/test_staff_packaging_billing.py,frontend/src/screens/ff/FfSettingsScreen.tsx,frontend/src/screens/ff/FfSettingsScreen.test.tsx,frontend/src/api.ts,frontend/tests-e2e/ff-billing-tariff-matrix.spec.ts,frontend/tests-e2e/billing-ledger.spec.ts,frontend/tests-e2e/billing-invoices.spec.ts,docs/evidence/billing-02b-tariff-matrix/OPERATION-FACTS-PROOF.md
```

Только перечисленные файлы разрешены для реализации. `frontend/src/ui-kit/**`,
существующий экран начислений/счетов, route-конфигурация, legacy storage UI,
`docs/backend-guard-baseline.json`, 2А и будущие волны в границы не входят.
Если необходим иной файл или пересекается ownership S-19 — `BLOCKED` с точным
узким amendment; не расширять список молча. Миграция только добавляющая,
`20260826_0112` продолжает единственный head 2А. Никаких production/staging,
секретов, Ozon или UI-kit правок.

## 1. Цель и бизнес-результат

Администратор ФФ на существующем экране «Настройки ФФ» получает одну компактную
панель «Тарифы» после сотрудников. Он может одной операцией сохранить включение
услуг, ставки за документ/единицу, индивидуальные товарные исключения и
версионные ставки сотрудников. Это даёт будущим волнам честную конфигурацию
денег без нового экрана, нового маршрута, отчёта, счёта или автоматической
рассылки.

## 2. Дословные требования владельца и UI-граница

> «Только существующие components from `frontend/src/ui-kit`; никакой custom
> table/filter/dropdown/button/tab; не менять соседние стандартные
> settings/billing screens or flows «заодно»; no new route; точная geometry at
> 1600px, headers/columns/overflow/loading/error/empty/disabled; live browser
> by separate Terra judge, separate Terra ui-critic, ui_guard, unit/type/build/
> targeted Playwright + billing-ledger/invoices regressions, invariants
> screenshots/evidence. Не править ui-kit в этой волне без отдельного owner
> decision.»

Нормализованный критерий: меняется только зона панели S-19; используются
`ScreenHeader`, `DataTable`, `FilterBar`, `EmptyState`, `TableSkeletonBody`,
`ErrorNotice`, `StatusChip`, `PrimaryAction`, `SecondaryAction`, `ActionGroup`,
`MoneyCell` из уже существующего UI-kit. Нельзя собирать локальные аналоги этих
элементов или трогать сами их реализации. API для матрицы добавляется к
существующему `/billing`, не создаёт URL экрана и не меняет старые ответы без
нового параметра.

## 3. Что уже существует и обязательно переиспользуется

- 2А `OperationFact` — принятый источник будущего тарифицирования; 2Б не
  реконструирует историю до cutover и не меняет recovery.
- `BillingTariffVersion`, `BillingLedgerEntry`, `BillingInvoice`,
  `billing_configuration_service`, `billing_ledger_service` и `/billing` —
  legacy configuration/readers. Ограничение
  `uq_billing_ledger_source_event` не ослабляется и не переименовывается.
- `BillingTariffVersion` остаётся единственным дневным тарифом
  `storage_liter_day`; storage API/экран и его месячные документы не
  переписываются.
- `staff_packaging_billing_service` и snapshot упаковки в `PackagingTask`
  остаются единственным источником зарплаты за упаковку.
- S-19 — `/app/ff/settings`, `FfSettingsScreen`; в ней уже есть header,
  складская панель и блок сотрудников. Панель тарифов идёт после блока
  сотрудников; `FfBillingScreen` и его route не меняются.

## 4. Нормативные входы и запреты

Приоритет: этот TASK, `BACKGROUND.md`, `CASES.md`, `S-19.md`, принятые 2А
package/evidence, `tasks/billing-module-20260825/TASK.FINAL.md`, `AGENTS.md`,
`CLAUDE.md`, `docs/product/NARYAD_RU.md`, `docs/product/UX_CANON_RU.md` и
`frontend/screens.registry.json`. Указанный в старом 2А package путь
`docs/process/KANON_ZADACHI_RU.md` отсутствует в текущем checkout; он не
заменяется выдуманным локальным каноном.

Запрещено: новый route или tab экрана, UI/API/legacy rewrite 2А, 3–5, правки
соседних Settings/Billing flow, удаление/изменение старых версий, пересчёт уже
выписанных ledger/invoice строк, ослабление уникальностей, внутридневное
хранение, silent default при отсутствии tenant configuration, частичное
сохранение матрицы, UI-kit/refactor «заодно» и baseline update.

## 5. Данные, API и поведение

### Data layer

Добавить `BillingTariffVersionV2` только для non-storage услуг. В ней нужны
tenant-safe область (`seller_id` nullable для common/seller scope, `product_id`
только для товарного override, `employee_user_id` только для employee scope),
`service_code`, `unit` (`document`/`item`), `enabled`, ставка в копейках,
`valid_from_at`/`valid_to_at` в UTC и snapshots, необходимые для истории.
Проверки исключают смешанные scope и product override без seller/item-unit;
tenant FK/сервисная проверка отклоняют foreign seller/product/employee. Уникальные
timestamp indexes на область+service+unit+`valid_from_at` обязательны. Сервис
блокирует поток версий и отклоняет пересекающиеся интервалы; он закрывает только
предыдущую версию, никогда не редактирует использованную.

В `BillingLedgerEntry` добавляется nullable v2-FK, сохраняя legacy
`tariff_version_id`, старые строки и `uq_billing_ledger_source_event` буквально
без ослабления. В `PackagingTask` добавляется только
`billing_rate_configured`: историческое ненулевое packaging rate = configured,
исторический ноль = «нет ставки/не подтверждено»; новый явный ноль возможен
только через настроенную версию. Packaging money не дублируется в employee
matrix.

Миграция: создаёт V2 и ограничения; копирует legacy non-storage тарифы без
разрыва/наложения, переводя `valid_from` в московскую полночь и включительный
`valid_to` в исключающую следующую московскую полночь; проставляет nullable V2
ссылки только там, где это безопасно, legacy FK оставляет; добавляет
`billing_rate_configured`. Новые `packing` и `return` выключены, legacy
`inbound`/`marketplace_outbound` сохраняют действие. Storage остаётся в
`BillingTariffVersion` с московскими днями, не V2.

### API layer

Только `fulfillment_admin` читает/сохраняет matrix через существующий `/billing`.
GET возвращает полный tenant-scoped draft и immutable active/history rows; POST/PUT
получает всю matrix c optimistic revision. Сохранение выполняет validation,
interval closure и запись одной DB transaction: любой invalid foreign scope,
overlap, unit/product mismatch, integer overflow или stale revision делает 4xx
и сохраняет **ноль** изменений. Повтор того же draft не создаёт версий.
OpenAPI/Pydantic contracts и API tests обязательны. Seller/staff/other tenant
получают 403/404 без утечки matrix.

### Screen layer S-19

Панель «Тарифы» после «Сотрудники»: одна таблица seller services
(Приёмка/Упаковка/Отгрузка/Возврат, с включением, unit, rate, Moscow start и
product exceptions) и отдельная компактная таблица employee rates
(приёмка/подбор/отгрузка/возврат); «Упаковка» в employee block только text/link
к уже существующей ставке пользователя. «Хранение» только ссылка на его
существующий экран. Для `document` product exception недоступен с объяснением;
service disabled остаётся visible «Не тарифицируется» для будущего отчёта.
Нет custom tabs/dropdowns/filters/buttons/tables: только описанный existing
UI-kit/MUI composition. Нет нового route или нового URL-поведения; существующие
ссылки на Settings не превращаются в отдельный экран.

## 6. Точные границы реализации и зависимости

| Слой | Разрешённые файлы | Результат |
|---|---|---|
| Models/migration | `backend/app/models/billing.py`, `backend/app/models/__init__.py`, `backend/app/models/packaging_task.py`, `backend/alembic/versions/20260826_0112_billing_tariff_matrix.py` | additive V2, v2-FK, configured marker, single head |
| Service | `backend/app/services/billing_tariff_matrix_service.py`, `billing_configuration_service.py`, `billing_ledger_service.py` | atomic tenant-scoped save, interval resolver, non-storage reader/writer bridge |
| API | `backend/app/api/billing.py` | admin-only matrix Pydantic/OpenAPI contract |
| Backend tests | named six billing/staff test files in §0 | matrix, migration, tenant/RBAC, legacy ledger/invoice regressions |
| S-19 | `frontend/src/screens/ff/FfSettingsScreen.tsx`, `.test.tsx`, `frontend/src/api.ts` | compact panel only; existing UI-kit imports only |
| Browser | `frontend/tests-e2e/ff-billing-tariff-matrix.spec.ts`, `billing-ledger.spec.ts`, `billing-invoices.spec.ts` | visible matrix plus old screens unchanged |
| Evidence | `docs/evidence/billing-02b-tariff-matrix/OPERATION-FACTS-PROOF.md` | commands, exits, PostgreSQL and browser proof |

Dependency is exactly accepted 2А SHA `60f82566e9adc65706b00ebb679c6725062801e6`.
If a missing source needs another file, stop for amendment instead of broadening.

## 7. Что остаётся неизменным

2Б не строит seller/staff reports, finance switch, new invoice flow, automatic
invoice stop, invoice print, storage arbitrary-period calculation or employee
earning ledger. Existing Billing screen, invoice cancellation/history, storage
screen/API and staff packaging billing retain routes, response compatibility and
workflow. Old non-storage reader/writer switches to V2 only behind the migration
contract; historical ledger/invoice values and legacy references remain
readable. Existing user/seller/warehouse permissions do not widen.

## 8. Тесты, гейты, PostgreSQL и browser proof

Сначала CASES red tests, затем minimal implementation. Обязательны targeted
backend tests, billing ledger/invoice regressions, frontend unit/type/build,
targeted Playwright, `ui_guard`, backend ruff/mypy/full pytest,
`check_migrations`, exactly one Alembic head, `back_guard`, diff check и полный
frontend e2e. PostgreSQL proof: upgrade 2А→0112, V2 indexes/FKs/checks,
legacy backfill intervals, overlap/atomic rollback, tenant rejection, DST and
Moscow boundaries, unchanged `uq_billing_ledger_source_event`.

На 1600px отдельный Terra ui-critic сверяет канон и отдельный Terra judge в
живом browser вручную проходит admin success/disabled/error/empty/loading;
им не может быть автор реализации. Сохранить screenshots и `ui_guard`/
invariants output в evidence. Красный любой тест, включая старый, закрытие
запрещает. После двух разных безрезультатных подходов к одной проблеме —
`BLOCKED`.

## 9. Отчёт, review, commit и push

После независимого review и browser verdict сохранить отдельные product,
tests/evidence commits; push `origin codex/billing-module-20260826`; проверить
clean status. До этого допустимы только статусы «контракт готов к независимому
review»/`BLOCKED`, не «реализовано» или «принято».

```text
Полоса: обычная
Экран: S-19 — Настройки ФФ
Стадия: <номер и название>
Статус: <результат>
Base SHA: 60f82566e9adc65706b00ebb679c6725062801e6
Commit: <SHA или нет>
Доказательства: <путь или нет>
Раунд правок: 0 | 1 | 2
Блокеры: <список или нет>
```
