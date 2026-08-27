# Волна 5: сотрудники и выплаты за выполненные действия

## 0. Статус, порядок и ровная граница

Это исполняемый контракт Волны 5 модуля «Расчёты». Нормативный источник
продукта — `tasks/billing-module-20260825/TASK.FINAL.md`, §§ 9–11, особенно
§§ 10.4 и 11.2, и сценарии приёмки 31–36. Волна не начинает разработку, пока
независимый reviewer не подтвердит исполнимость именно этого пакета, а Волны
3 и 4 не получат собственные `PRODUCT_BROWSER_APPROVED` и опубликованные tip.
Она не принимает и не исправляет заодно их экран, счета, тарифную матрицу или
старые документы.

Работа выполняется только в постоянном worktree
`/Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826` на
ветке `codex/billing-module-20260826`. Это обычная полоса. До первой правки
исполнитель сверяет фактический pushed tip Wave 4 и единственный Alembic head
`20260827_0114_billing_invoice_v2`; если 0114 ещё не принят или head иной,
статус `BLOCKED`, а не угадывание parent миграции.

После независимого `CONTRACT_ACCEPTED` и после принятия Wave 4 открыть ровно
один наряд следующей командой. У `/app/ff/billing` нет отдельного S-ID в
реестре, поэтому его точная граница задаётся только `--files`: это не даёт
наряду автоматически захватить чужой экран «Настройки».

```bash
python3 scripts/naryad.py new "Волна 5 модуля «Расчёты»: вкладка сотрудников, неизменяемые выплаты и сверка упаковки" --lane обычная --files backend/app/models/billing.py,backend/app/models/operation_fact.py,backend/app/models/packaging_task.py,backend/app/models/user.py,backend/app/models/__init__.py,backend/app/services/operation_fact_service.py,backend/app/services/packaging_task_service.py,backend/app/services/staff_packaging_billing_service.py,backend/app/services/staff_earning_service.py,backend/app/services/billing_staff_report_service.py,backend/app/api/billing.py,backend/app/api/billing_staff_report_schemas.py,backend/app/api/staff_accounts.py,backend/alembic/versions/20260827_0115_staff_earnings.py,backend/tests/test_operation_facts.py,backend/tests/test_packaging_tasks.py,backend/tests/test_staff_packaging_billing.py,backend/tests/test_staff_users.py,backend/tests/test_billing_financial_core_migration.py,backend/tests/test_staff_earning_service.py,backend/tests/test_billing_staff_report_api.py,backend/tests/test_billing_staff_report_service.py,backend/tests/test_billing_tariff_matrix.py,frontend/src/screens/ff/FfBillingScreen.tsx,frontend/src/screens/ff/FfBillingScreen.test.ts,frontend/tests-e2e/billing-staff-report.spec.ts,frontend/tests-e2e/ff-staff-packaging-billing.spec.ts,frontend/tests-e2e/billing-seller-report.spec.ts,frontend/tests-e2e/billing-invoices.spec.ts,docs/evidence/billing-05-employees/STAFF-EARNINGS-PROOF.md,docs/evidence/20260827-volna-5-modulya-raschety-vkladka-sotrudn/BILLING-STAFF-1600.jpg,docs/evidence/20260827-volna-5-modulya-raschety-vkladka-sotrudn/BILLING-STAFF-FINANCE-OFF-1280.jpg,docs/evidence/20260827-volna-5-modulya-raschety-vkladka-sotrudn/VERDICT.md,tasks/billing-05-employees/TASK.md
```

`frontend/src/ui-kit/**`, экран настроек, тарифная матрица,
route-конфигурация, `App.tsx`, screen registry, Wave 3/4 product code, legacy
invoice/storage UI, baseline-guards, secrets, staging и production в эту волну
не входят. Исключение внутри указанной boundary только одно: минимальные
additive поля `User`/`PackagingTask` и их completion writer требуются для
долговечного configured-zero и employee snapshot упаковки; они не меняют
экран настроек, его колонки или flow.
Если требуемого UI-kit primitive нет, developer останавливает этот наряд:
отдельная общая prerequisite проходит свой наряд, review, commit/push и только
затем Wave 5 открывается заново. Локальные MUI-аналоги таблицы, фильтра,
кнопки, dropdown, chip или switch запрещены.

Миграция только добавляющая: `0115` имеет единственный parent `0114`, не
переписывает 0110–0114. Она добавляет staff journal, composite unique
`PackagingTask(tenant_id, id)`, employee/history snapshots и configured-state,
но не меняет ни существующую сумму упаковки, ни тарифы, операции, ledger или
invoices. Никаких mass-reprice, реконструкции старой истории или смены
активной ставки задним числом.

## 1. Цель и явные нецели

Администратор ФФ на существующей вкладке «Сотрудники» экрана
`/app/ff/billing` за произвольный московский период видит, какие конкретные
действия выполнил каждый сотрудник и какая сумма полагается за эти действия.
Он может открыть отдельную детализацию, увидеть отсутствие ставки и сверить
упаковку с уже существующим расчётом по завершённым упаковочным заданиям.

Не входят: изменение ставок в самом отчёте, создание/отмена счетов,
чекбоксы, начисления селлеру, пересчёт архивной упаковки, расширение ролей,
новый маршрут, экспорт, выплата
денег, платёжная ведомость, удаление сотрудника и какая-либо новая
автоматизация. Допустим только узкий server-side completion path: explicit
сохранение уже введённой ставки (включая 0), configured-state и имени в
`PackagingTask`; это не меняет настройку ставки или её UI. Упаковка остаётся
отдельной ставкой и не переносится в матрицу.

## 2. Экран: только существующий каркас и UI-kit

На `FfBillingScreen` появляется третья верхняя вкладка **«Сотрудники»** между
«Селлеры» и «Выставленные счета». Это не новый route и не переделка имеющихся
двух вкладок. При переходе на неё используются те же `ScreenHeader`,
`FilterBar`, `MoscowDateRangeInput`, `SecondaryAction`, `PreferenceSwitch`,
`ReportMetricStrip`, `DataTable`, `TextCell`, `MoneyCell`, `StatusChip`,
`ErrorNotice`, `TableSkeletonBody` и штатный контейнер таблицы, которые уже
приняты для `/app/ff/billing`.

* Период: сегодня, 7 дней, 30 дней, текущий месяц, прошлый месяц и валидный
  произвольный диапазон максимум 366 дней. Сервер интерпретирует его в Москве
  как `[date_from, date_to + 1 день)`; UI не подменяет серверную валидацию.
* Фильтры: текстовый поиск по сохранённому имени сотрудника и select
  сотрудника «Все сотрудники». Сортировка summary разрешена только по
  `employee_name`, `operation_count`, `item_quantity`, `missing_rate_count` и
  `net_total_kopecks`, с явными `sort_by`/`sort_direction`; сервер задаёт
  устойчивый tie-breaker `employee_id_or_snapshot_key`. Дата действия всегда
  является устойчивым вторичным ключом detail cursor.
* Состояние «Финансы» — самостоятельная настройка
  `tenant_id:user_id:billing:employees:finance` в `localStorage`. Она не
  наследует значение «Селлеров», не даёт нового права и не утечёт между
  тенантами/пользователями.
* Summary в finance-off имеет ровно: «Сотрудник», «Операций», «Штук»,
  «Показать операции». В finance-on добавляет перед действием «Нет ставки» и
  «К выплате». Верхняя полоса содержит не более четырёх значений: сотрудников,
  операций, штук и «К выплате» только finance-on.
* Нажатие «Показать операции» открывает отдельный detail block под summary,
  а не раскрывающуюся самодельную таблицу. В finance-off: дата/время,
  документ, действие, физическое количество, результат/сторно и штатный
  переход в исходный документ. В finance-on добавляются расчётная единица,
  ставка и сумма. Нет чекбоксов, действий счета, кнопки «Выставить счёт» или
  invoice-history ни в одном режиме.
* Нулевая, но подтверждённо настроенная ставка показывается как `0,00 ₽` и
  не считается «Нет ставки». Отсутствующая/неподтверждённая ставка видна как
  компактный `StatusChip` «Нет ставки», с нулевой суммой; это не молчаливый
  ноль и не ошибка всего отчёта.
* Пока запрос идёт, summary/detail показывают штатные skeleton; empty —
  понятный `EmptyState`; ошибка detail остаётся заметной через `ErrorNotice`
  и не стирает последнюю успешную summary. Новый запрос отменяет старый и
  дополнительно игнорирует опоздавший ответ через request-id/alive guard.
  `Загрузить ещё` добавляет только следующую страницу и не дублирует строки.

Никакого микрошрифта, изменения ширины существующих seller/invoice колонок,
глобального горизонтального scroll, перестановки шапки или «заодно» правки
старых экранов. Горизонтальная прокрутка допустима только в штатном
`DataTable`-контейнере. Ставки не редактируются на этой вкладке; отчёт лишь
показывает snapshot фактического действия и не трактует employee rates
`inbound/picking/marketplace_outbound/return` как источник оплаты упаковки.

## 3. Данные: неизменяемая выплата и единственный источник упаковки

Добавляется только `StaffEarningEntry`, tenant-safe immutable journal для
неупаковочных фактов. У него минимум:

```text
id, tenant_id
source_kind: operation_fact | packaging_task_snapshot
operation_fact_id nullable, packaging_task_id nullable
employee_user_id nullable, employee_history_key, employee_name_snapshot
operation_code, service_code
occurred_at
physical_quantity, billing_quantity, billing_unit
tariff_version_v2_id nullable, rate_kopecks nullable, amount_kopecks
missing_rate boolean
reversal_of_id nullable
idempotency_key
created_at
```

Табличные checks требуют ровно один source reference и согласованный
`source_kind`; `operation_fact` допускает только `inbound`, `picking`,
`marketplace_outbound`, `return` и их reversal-коды, `packaging_task_snapshot`
зарезервирован только для read-model reconciliation и не является вторым
writer-источником. Добавляются composite tenant FK/проверки к
`OperationFact`, `PackagingTask` и `BillingTariffVersionV2`, `amount` в
копейках без float, неотрицательные physical/billing quantity, nullable rate
только при `missing_rate=true`, один reversal link в пределах tenant и
уникальные индексы:

* `(tenant_id, id)` для composite references;
* `(tenant_id, idempotency_key)` unique;
* `(tenant_id, operation_fact_id)` unique для `source_kind=operation_fact`;
* `(tenant_id, packaging_task_id)` unique для
  `source_kind=packaging_task_snapshot`;
* `(tenant_id, employee_history_key, occurred_at, id)` и
  `(tenant_id, employee_user_id, occurred_at, id)` для быстрых
  summary/detail.

`employee_history_key` — обязательный, неизменяемый UUID исходного actor,
но не FK к живой учётной записи; он остаётся ключом grouping/detail после
удаления `User`. `StaffEarningEntry` не хранит редактируемую ссылку на текущую
карточку сотрудника как источник отображения. При создании `operation_fact`
центральный writer обязан получить `actor_name_snapshot` из уже
загруженного/tenant-scoped `User.email`; тот же строковый снимок копируется в
earning. Поэтому удаление `User` (FK становится `NULL`) не меняет историческое
имя или `employee_key`. Старые факты без достоверного actor snapshot не
«восстанавливаются» по догадке: они показывают только безопасное «Сотрудник
недоступен» и не смешиваются с одноимённым новым сотрудником.

### Упаковка — особое, не дублируемое правило

`PackagingTask.billing_units_packed`, `billing_rate_kopecks`,
`billing_rate_configured`, `billing_earned_kopecks`, `completed_by_user_id` и
`completed_at`, выставленные существующим
`staff_packaging_billing_service.finalize_task_billing`, остаются единственным
источником оплаты упаковки. Wave 5 не пересчитывает их из тарифа, не применяет
employee `BillingTariffVersionV2`, не меняет `finalize_task_billing` и не
создаёт независимую денежную строку из `OperationFact` упаковки.

`billing_staff_report_service` объединяет два строго разделённых источника:

1. `StaffEarningEntry` только для неупаковочных `OperationFact`;
2. завершённый `PackagingTask` напрямую как `packaging_task_snapshot` read
   row, с его текущим неизменяемым snapshot и с employee name, сохранённым в
   materialized `StaffEarningEntry`-reference только если он уже существует.

Если implementation materializes reference `packaging_task_snapshot` ради
единого журнала, она обязана создавать/читать её единственным идемпотентным
reconciliation writer, копировать **ровно** четыре snapshot-поля задания и
никогда не использовать её сумму как источник: canonical sum всегда читается
из `PackagingTask`. При несовпадении `units/rate/configured/earned`, при
отсутствии task, foreign tenant или повторном source запись помечается
`integrity_error` и не участвует в total; API не скрывает проблему. Это
защищает от двух выплат за одно действие и делает расхождение проверяемым.

Для `OperationFact.operation_code in ('packing_completed', 'packing_reversal')`
staff-earning writer не создаёт строку вообще. Его idempotency/unique checks
также отвергают попытку записать тот же факт как operation earning и packing
reconciliation. Один документ с разными актёрами остаётся несколькими
`OperationFact`; каждый начисляется только своему snapshot actor.

## 4. Расчёт ставок, reversal и граница истории

Для нового неупаковочного `OperationFact` с actor service ищется tenant-scoped
employee `BillingTariffVersionV2` по exact `employee_user_id`, `service_code`
и полуоткрытому timestamp-интервалу факта. Ставка и её версия копируются в
earning в момент факта. Тариф не редактирует уже созданный earning; новая
версия дооценивает только ещё не созданный/непроценённый фактический факт
после валидации его interval, но не меняет историю.

Если актёр отсутствует (системное действие), такая операция не порождает
выплату. Если актёр есть, но applicable employee rate отсутствует, earning
создаётся с `missing_rate=true`, `rate_kopecks=null`, `amount_kopecks=0`,
снимком имени, физическим количеством и причиной «Нет ставки». Подтверждённый
ноль — отдельный случай `missing_rate=false`, rate/amount `0`.

Reversal создаёт отдельный immutable earning с тем же сотрудником и snapshot
ставкой либо явной причиной отсутствия ставки; он указывает на earnings
исходного fact через `reversal_of_id`, имеет отрицательную signed сумму в
отчётном read-model и не переписывает исходник. Цепочки tenant-scoped,
acyclic; duplicate/cross-tenant/malformed reversal fail closed, не давая
исказить итог. `physical_quantity` остаётся физическими штуками, а
`billing_quantity`/unit не подменяют её.

История до cutover `OperationFact` не создаёт вымышленных выплат. Для неё
report пуст там, где нет надёжного employee actor/snapshot; legacy
`BillingLedgerEntry` селлерских начислений никогда не трактуется как зарплата.
Backfill 0115 разрешён только для существующих post-cutover
`OperationFact` и завершённых `PackagingTask`, и обязан быть идемпотентен;
он не меняет их source rows и фиксирует deterministic cutover test.

## 5. API, RBAC, период, поиск, сортировка и курсор

Только `fulfillment_admin` получает новые endpoints. `fulfillment_staff`,
селлер, `shift_lead`, неавторизованный и другой tenant получают прежний
deny/404/403 без суммы, имени или cursor из чужого тенанта. `billing.py`
содержит только router/RBAC wiring; Pydantic shapes в
`billing_staff_report_schemas.py`, чтобы не раздувать router и не менять
back-guard baseline.

Обязательные read-only endpoints:

* `GET /api/billing/staff-report/summary` — `date_from`, `date_to`, optional
  `employee_id`, `search`, `include_finance`, `sort_by`, `sort_direction`.
  Возвращает server-side rows и totals, не сумму загруженной detail страницы.
* `GET /api/billing/staff-report/employees/{employee_key}/details` — те же
  filter bounds/finance, `limit=1..100`, signed `cursor`. `employee_key` —
  opaque serialization persistent `employee_history_key`, а не lookup живого
  `User`; поэтому он открывает сохранённый snapshot удалённого сотрудника.
  Чужой/неизвестный key возвращает 404.

Формат physical response не содержит `rate_kopecks`, `amount_kopecks`,
`net_total_kopecks`, missing-rate money metadata, employee tariff version или
другие денежные поля. Finance-on добавляет только явно описанные money/missing
rate fields. Состав операций и пагинация обоих режимов идентичны. Все значения
денег — integer kopecks, dates/datetimes ISO, display name — snapshot.

Cursor HMAC-подписан и связывает tenant, employee snapshot key, exact Moscow
period, search, employee filter, finance mode, sort, direction, last stable
tuple `(occurred_at, source_kind, source_id, id)`. Tampered cursor, cursor
другого employee/tenant/filter/finance/sort и malformed order дают named 422;
offset pagination запрещена. Navigation target source документа возвращается
сервером как стабильный typed target, а не угадывается UI.

## 6. Автоматические проверки и test traceability

В `TASK`/PR перед dev фиксируются минимум следующие применимые тест-кейсы:

| TC-ID | Applies | Проверяемый результат |
|---|---:|---|
| TC-NEW-005 | Y | Given один документ с inbound/picking/outbound fact разных actor, When admin открывает period, Then summary/detail начисляют каждый action только его сотруднику; negative: system actor не получает earning. |
| TC-NEW-006 | Y | Given packaging task завершён со snapshot rate/units/earned, When report/reconciliation читается повторно, Then показанная упаковка равна `staff_packaging_billing_service`; negative: packing OperationFact не создаёт вторую выплату. |
| TC-NEW-007 | Y | Given employee без ставки и employee с explicit zero, When finance-on, Then первый виден «Нет ставки» и не ломает total, второй виден как 0,00 ₽ без ошибки; finance-off omits all money. |
| TC-NEW-008 | Y | Given fact/earning имеет employee snapshot, When живой User удалён, Then history открывается по snapshot name; negative: foreign tenant cannot read its employee key/cursor. |
| TC-NEW-009 | Y | Given 53 mixed staff entries over Moscow boundary and reverse chain, When admin searches/sorts/loads next page, Then signed cursor yields all rows once, totals are server-side and page has no global overflow. |

Backend unit/service/API tests обязаны покрыть: interval exact boundary (включая
конец года/Москва), actor snapshots, four non-packaging services, two actors
одного документа, system actor, zero/missing rate, rate version snapshot,
reversal sign/link, idempotent repeated writer/backfill, no packing earning,
packing direct reconciliation equality and mismatch fail-closed, duplicate
source/FK tenant integrity, deleted user snapshot, tenant/RBAC, finance field
absence, search/filter/sort, cursor tamper/filter/tenant mismatch, 1/100
limit, OpenAPI refs and migration PostgreSQL upgrade `0110→…→0115`, downgrade
и re-upgrade with one head.

Frontend unit tests cover all tab labels/state keys, columns in both finance
modes, no invoice controls, date shortcuts, request abort/request-id, empty,
loading, error preserving summary, `Load more`, known zero vs missing rate and
stable source navigation. E2E contains the TC IDs above and passes through UI,
not direct HTTP: admin selects period/search/employee, switches finance,
opens detail, loads next page, validates no invoice action; it also checks
regular employee/seller denial plus seller-report and invoice regressions.

Required technical gates after implementation:

```bash
cd backend && ruff check . && mypy . && pytest
cd frontend && npm run test:unit && npm run build && npm run test:e2e
python3 scripts/ci/back_guard.py
python3 scripts/ci/check_migrations.py
python3 scripts/ui/ui_guard.py
node scripts/ui/invariants.js
```

Any inherited red test is red status, not a waived success. No generated
screenshots, database or baseline side-effect is staged unless listed in the
наряд and independently reviewed.

## 7. Обязательное живое browser-доказательство

После code review независимый Product Browser Agent открывает видимый browser
с реальной local fixture/role `fulfillment_admin`, а не Playwright/headless/API
и не пересказ developer. Он руками проходит: finance-on и finance-off,
today/7/30/current/previous/arbitrary Moscow period, employee search/filter,
sort, detail/load-more, zero rate, missing rate, deleted snapshot, packaging
row, source navigation, error and empty retry. Проверка ограничена новым
billing screen: настройки и тарифная матрица не открываются и не меняются.

На ширинах **1600 px и 1280 px** судья фиксирует `document.scrollWidth <=
clientWidth`, отсутствие пересечений/обрезания, видимые подписи, правильные
колонки и отсутствие глобального overflow; допустима только внутренняя
прокрутка `DataTable`. Реальные скриншоты сохраняются по путям из наряда,
`STAFF-EARNINGS-PROOF.md` перечисляет команды/версии/fixtures/результаты,
`VERDICT.md` содержит URL, роль, клики, видимые состояния, widths и ровно один
verdict `PRODUCT_BROWSER_APPROVED`, `PRODUCT_REWORK_REQUIRED` или
`PRODUCT_BROWSER_BLOCKED`.

## 8. Сдача и стоп-условия

Только после `BA_READY`, `PRODUCT_APPROVED_FOR_DEV`, `DEV_DONE`,
`CODE_REVIEW_PASSED`, `PRODUCT_BROWSER_APPROVED`, всех зелёных gates,
committed evidence и push можно сообщать «Wave 5 готова в ветке». Это не merge
в `main`, не CI proof и не deployment. Перед этим исполнитель проверяет
`git status`, diff и origin SHA; чужие `baseline-dirty.txt`, Wave 3/4
незавершённые files и любой несвязанный diff не добавляются.

`BLOCKED` обязателен, если не принят contract/Wave 3/Wave 4, нет единого head
0114, не хватает existing UI-kit primitive, найдено несоответствие упаковки,
невозможно безопасно получить живое browser evidence или требуется путь вне
literal наряд. Нельзя «починить заодно», расширить роль, изменить старые
экраны, создать вторую копию проекта или подменить ручное browser принятие
зелёными тестами.
