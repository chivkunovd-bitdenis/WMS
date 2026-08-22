ФИЧ: 11

## Фичи

### 1. Общая денежная ячейка и печать счёта

Оператор видит ставки и суммы в одном формате: RUB, две цифры после запятой, знак сторно и правое выравнивание; действие печати может честно называться «Печать счёта».

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts`

Зависит от: нет.

Проверка: `MoneyCell` отдельно показывает положительную сумму, ноль, сторно и «—» без сигнальной окраски; `PrintAction` с `what="счёт"` в панели имеет подпись «Печать счёта».

### 2. Единый выбор календарного месяца

Оператор выбирает месяц в одном переиспользуемом поле, которое сохраняет выбранное значение при загрузке и объясняет ошибку формата, границы или недоступность.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/PeriodPicker.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/index.ts`

Зависит от: нет.

Проверка: компонент принимает и отдаёт `YYYY-MM`, корректно показывает label «Месяц», ошибку и disabled-состояние, не очищая значение при состоянии загрузки родителя.

### 3. Финансовый фундамент: профили, версии тарифов и журнал начислений

Система получает единственный tenant-изолированный источник для реквизитов ФФ и селлера, версионных тарифов с единицами `document`, `item`, `liter_day` и неизменяемых строк начислений/сторно. Для хранения сразу закрепляются `service_code='storage_liter_day'` и источник `storage_measurement`, без параллельных таблиц тарифов или начислений.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/__init__.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/<revision>_billing_financial_core.py`

Зависит от: нет; это обязательный 09-A из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/ARCH-CROSS.md`.

Проверка: миграция создаёт только общий набор billing-таблиц; ограничение уникальности не допускает второе начисление для одного исходного события, а сторно ссылается на исходную строку и не изменяет её.

### 4. API реквизитов и версионных тарифов

Администратор ФФ может сохранить один профиль плательщика селлера и профиль получателя ФФ, создать общую или персональную ставку с датой начала; сервер проверяет ИНН, обязательные поля, tenant-границы, допустимую единицу и конфликт будущих периодов. Новая ставка закрывает прежнюю версию, а не переписывает историю; нулевая ставка остаётся явной бесплатной работой.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/main.py`

Зависит от: 3.

Проверка: администратор сохраняет валидные реквизиты и ставку, а неверный ИНН, пересечение с будущей версией и обращение к селлеру другого tenant возвращают понятную ошибку и не меняют сохранённые данные.

### 5. Реквизиты селлера в существующем диалоге S-18

Администратор открывает строку селлера и в раскрываемом блоке «Реквизиты для счетов» вводит юридическое наименование, ИНН и необязательный КПП; после сохранения видит подтверждение, а ошибка остаётся над полями без технического кода. Новый маршрут и колонка в списке не появляются.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-seller-profile.spec.ts`

Зависит от: 4.

Проверка: сценарий `S-31-TC-001` сохраняет корректные реквизиты через диалог; сценарий `S-31-TC-009` показывает ошибку контрольного числа ИНН и подтверждает, что ранее сохранённый профиль не затёрт.

### 6. Тарифы ФФ в существующих настройках S-19

Администратор переключается на «Тарифы ФФ», сохраняет реквизиты ФФ и новую общую либо персональную ставку, видит только действующие версии и открывает историю отдельно. Существующие «Склад и сотрудники» и ставка упаковщика остаются без регрессии.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-tariffs.spec.ts`

Зависит от: 1, 4.

Проверка: сценарии `S-31-TC-002` и `S-31-TC-003` через UI создают тариф и следующую версию без пересчёта старой; `S-31-TC-010`, `S-31-TC-011` исключают двойное сохранение и пересечение периодов, а `S-19-TC-001` подтверждает доступность прежней вкладки настроек.

### 7. Операционные начисления при финальной приёмке и отгрузке

После первого финального факта приёмки или отгрузки ФФ→МП система атомарно пишет одну строку журнала со снимком действовавшего тарифа, фактическим количеством, датой и исполнителем. Повтор не дублирует начисление; отсутствие тарифа создаёт видимую `unpriced`-строку и не останавливает склад. Внутренняя отгрузка в эту карточку не входит.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/inbound_intake_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/marketplace_unload_status.py`

Зависит от: 3, 4.

Проверка: завершённая приёмка и marketplace-отгрузка создают по одному начислению с правильной единицей, количеством и исполнителем; повтор финального действия не создаёт дубль, а закрытый документ без тарифа остаётся выполненным и имеет `unpriced` в журнале.

### 8. Автоматическое формирование неизменяемых счетов

Ежедневный идемпотентный запуск после 02:30 МСК и действие повтора используют один алгоритм: для закрытого месяца создают один счёт на селлера с агрегированными строками и снимками реквизитов, либо записывают ровно одну понятную блокирующую причину. Счёт не формируется при `unpriced`, отсутствии профилей или незакрытом хранении; отмена создаёт окончательный статус `cancelled`, не меняя счёт и не создавая повторную отмену.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/tasks/billing_tasks.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py`

Зависит от: 3, 4, 7 и межкарточный результат 08-B — зафиксированные `StorageStatement`, публикующие `storage_liter_day` в общий ledger по контракту `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/ARCH-CROSS.md`.

Проверка: сценарии `S-31-TC-006`, `S-31-TC-013`, `S-31-TC-014`, `S-31-TC-015` подтверждают один полный счёт при двух параллельных запусках, понятную остановку при незакрытом хранении и идемпотентную отмену; позднее сторно попадает только в следующий счёт (`S-31-TC-016`).

### 9. Маршрут и общий каркас «Расчётов»

В меню ФФ появляется один доступный только администратору пункт «Расчёты» и маршрут `/app/ff/billing`; экран имеет две вкладки, сохраняющие выбранный месяц и селлера. Рядовой сотрудник и селлер не получают финансовый маршрут или суммы.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/layouts/AuthedAppLayout.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`

Зависит от: 2, 8.

Проверка: администратор открывает `/app/ff/billing`, меняет вкладку и сохраняет контекст фильтра; у селлера и складского сотрудника пункт отсутствует, а прямой маршрут не показывает финансовые данные.

### 10. Реестр начислений в «Расчётах»

Администратор сверяет за выбранный месяц операции или объём по исполнителям: видит фактические документ, количество, ставку и сумму, а только требующие действия проблемы — «Нет тарифа». Поиск и фильтры не дают старым данным выглядеть актуальными при ошибке; пустота, загрузка и ошибка объясняют следующий шаг.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts`

Зависит от: 1, 2, 8, 9.

Проверка: `S-31-TC-004` проверяет фильтр, строки и сохранение контекста вкладок; `S-31-TC-005` переключает режим по исполнителям и подтверждает отсутствие денежных колонок; `S-31-TC-012` показывает начисление без тарифа без блокировки выполненной складской операции.

### 11. Реестр, просмотр, печать и отмена счёта

Администратор видит за закрытый месяц только номер, период, селлера, дату, сумму и статус счёта, а блокирующие причины ведут к единственному исправляющему действию. В диалоге он раскрывает исходные документы, печатает HTML-представление и подтверждённо отменяет выставленный счёт; отменённый счёт остаётся доступным для печати и истории.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`

Зависит от: 1, 2, 8, 9.

Проверка: `S-31-TC-007` открывает счёт, раскрывает документы и запускает печать без UI-управления в печатном виде; `S-31-TC-008` требует подтверждение отмены, а повторное действие не меняет историю и не создаёт вторую отмену.

## Порядок

Сначала независимо и параллельно выполняются 1, 2 и 3: первые два куска добавляют ui-kit, а 3 — обязательный финансовый контракт 09-A. После 3 последовательно идут 4 и 7; настройка должна существовать до того, как финальная складская операция сможет снять тариф.

Фичи 5 и 6 можно выполнять параллельно после 4: они меняют разные frontend-экраны. Между 7 и 8 должен быть завершён межкарточный результат 08-B; это обязательный барьер, иначе счёт сможет выйти без хранения за тот же месяц. После 8 можно делать 9, затем 10 и 11 параллельно: обе используют общий экран, поэтому при фактическом редактировании одного `FfBillingScreen.tsx` их нужно отдать одному исполнителю последовательно либо заранее разделить этот экран на независимые компоненты.

Итоговая зависимость: `1‖2‖3 → 4 → (5‖6‖7) → 08-B → 8 → 9 → (10‖11)`.

## Что осталось за бортом

- Исторический backfill начислений до явно заданной даты включения биллинга: контракт прямо запрещает автоматическую загрузку прошлого периода.
- Внутренняя отгрузка, паллеты, вес, ступени, минимумы и одновременный фикс с поштучной ставкой: это не входит в закрытый набор первой волны.
- НДС, счёт-фактура, УПД, акт, ЭДО, PDF-движок, экспорт, платежи, задолженность и отправка счёта селлеру: нужен отдельный бухгалтерский или интеграционный контур.
- Селлерский финансовый кабинет и доступ сотрудника склада к тарифам или суммам: они исключены текущим контрактом.
- Внешний поиск юридического лица по ИНН, адреса и банковские реквизиты селлера, несколько плательщиков и договоры: в контракте для них нет сценария.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.
