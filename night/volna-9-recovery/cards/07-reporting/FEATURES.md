ФИЧ: 7

## Фичи

### 1. Починить тестовый writer движений для обязательного склада

Пользователь отчёта снова получает проверяемый backend-контракт движений: тестовый
сценарий создаёт каждое движение с фактическим складом, поэтому обязательное
`warehouse_id` не ломает подготовку данных и адресный набор отчётов проходит.

**Файлы:**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movements_report.py`

**Зависит от:** ничего.

**Проверка:** выполнить `pytest tests/test_inventory_movements_report.py`; сценарий
`test_inventory_movements_summary_groups_and_period_filter` создаёт движения для
`wid1`/`wid2` без `NOT NULL constraint failed: inventory_movements.warehouse_id` и
сохраняет проверки фильтра по складу.

### 2. Не выдавать неполное перемещение за ноль в CSV операций

Оператор, выгружающий группировку «По операциям», видит ту же проблему неполной
transfer-пары, что и в таблице: отсутствующая сторона остаётся тире, а строка
явно несёт признак ошибки, а не подставленный ноль. Корректные операции и их
порядок не меняются.

**Файлы:**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py`

**Зависит от:** ничего.

**Проверка:** адресный pytest создаёт единственное `stock_transfer_out` в выбранном
складе, сверяет таблицу и CSV и подтверждает, что CSV не содержит `0,3,-3` как
обычную корректную строку; для полной пары и обычных операций экспорт по-прежнему
повторяет таблицу.

### 3. Публиковать признак операционного склада в API складов

Клиенты обоих порталов получают от `/warehouses` не эвристику по названию, а
авторитетный признак `is_operational` для каждого склада. Создание и переименование
склада не меняют этот признак и не меняют остальные поля ответа.

**Файлы:**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/warehouses.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_catalog.py`

**Зависит от:** ничего.

**Проверка:** pytest создаёт обычный склад и читает `GET /warehouses`; в ответе есть
булево `is_operational: true`. Отдельно проверяется, что read-модель не теряет
признак, если имя склада меняется.

### 4. Фильтровать склады отчёта ФФ только по API-признаку

Оператор ФФ видит в фильтре отчёта только склады с `is_operational=true`. Склад с
`is_operational=false` не появляется даже после штатного переименования в «Архив»;
угадать его назначение по префиксу имени экран больше не пытается.

**Файлы:**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`

**Зависит от:** фича 3.

**Проверка:** Playwright подменяет ответ `/api/warehouses` двумя физически разными
складами, включая переименованный неоперационный `Архив` с
`is_operational=false`; на `/app/ff/reports` этот склад не доступен в селекторе, а
при одном оставшемся операционном складе сам селектор скрыт.

### 5. Фильтровать склады отчёта селлера только по API-признаку

В портале селлера действует та же граница: селлер не может выбрать служебный склад
в отчёте после его переименования, а доступный физический срез остаётся только в
рамках своего seller_id.

**Файлы:**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts`

**Зависит от:** фича 3.

**Проверка:** Playwright возвращает из `/api/warehouses` обычный склад и
переименованный `Архив` с `is_operational=false`, затем селлер открывает
`/app/seller/reports`. Служебный склад не появляется в отчётном выборе, фильтр
селлера по-прежнему скрыт, а страница не показывает данные другого селлера.

### 6. Снимать скелетон таблицы после отмены старой страницы

Если оператор нажал «Вперёд», а до ответа сменил поиск или склад, новый срез
загружается как рабочая таблица, а не остаётся бесконечно под скелетоном. Поздний
ответ отменённой страницы по-прежнему не может перезаписать свежие строки.

**Файлы:**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`

**Зависит от:** ничего.

**Проверка:** сценарий `S-33-TC-008` удерживает ответ второй страницы, меняет поиск
на `fresh-slice` и подтверждает появление `Fresh filtered result` без скелетона;
после освобождения старого ответа таблица всё ещё не содержит `Stale page result`.

### 7. Зафиксировать блокировку отчёта без права доступа

Сотрудник ФФ без `inventory` и пользователь портала селлера без `can_products`,
открыв прямую ссылку на отчёт, получают понятное состояние «Нет доступа», а не
данные или пустой отчёт. Реестр S-33 описывает это ограничение всеми шестью
обязательными полями: что блокируется, условие, место проверки, видимое состояние,
разблокировку и бизнес-причину.

**Файлы:**

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/docs/blockers/S-33.md`

**Зависит от:** ничего.

**Проверка:** два адресных Playwright-сценария открывают прямые маршруты
`/app/ff/reports` и `/app/seller/reports` под ролями без соответствующего права и
проверяют видимое сообщение об отказе и отсутствие отчётных данных. Проверка
`docs/blockers/S-33.md` подтверждает отдельную шестипольную запись для этой
блокировки без расхождения с UI и серверным ограничением.

## Порядок

Сначала можно независимо и параллельно выполнить фичи 1, 2, 3, 6 и 7: они не
используют результат друг друга и затрагивают разные слои или файлы. После фичи 3
параллельно выполняются фичи 4 и 5, поскольку обе опираются на обязательное поле
`is_operational` в ответе API. Если один исполнитель берёт общий
`ff-reports.spec.ts`, он выполняет фичи 4 и 6 последовательно в указанном порядке,
не смешивая их критерии при проверке.

## Что осталось за бортом

- Уже принятые ui-kit-компоненты `ReportMetricStrip`, `MovementFlowChart` и
  `WarningNotice`, ширины колонок, визуальный вес пагинации и исправленная ошибка
  таблицы не возвращаются в разработку: повторный `REVIEW.md` признал их закрытыми.
- Новые виды отчётов, финансовые показатели, маркетплейсные данные и изменения
  моделей хранения не входят в этот rework: повторно режутся только пять
  незакрытых находок `REVIEW.md`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, production
  `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
