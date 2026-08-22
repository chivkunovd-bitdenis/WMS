ФИЧ: 11

## Фичи

### 1. Зафиксировать селлера и склад в факте движения

Оператор получает исторически устойчивый отчёт: у каждого нового движения сохраняются владелец товара и фактический операционный склад на момент проведения, а старая история один раз заполняется по доступным связям. После проверки полноты `warehouse_id` становится обязательным; для неразрешимой старой привязки остаётся признак legacy-данных, а не подстановка догадки. Миграция также создаёт составные индексы для срезов tenant/seller/warehouse по времени.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/models/inventory_movement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movement_reporting_dimensions.py`

Зависит от: завершённых стабилизационных карточек волны `03 → 01 → 04-A` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/ARCH-CROSS.md`.

Проверка: применить миграцию к истории с товарами разных селлеров и ячейками разных складов; убедиться, что новые поля, backfill и индексы созданы, `warehouse_id` заполнен и обязателен для новых строк, а неуверенная историческая привязка помечена как legacy вместо изменения факта.

### 2. Записывать измерения вместе с каждым новым движением

При любой штатной корректировке остатка сервис в той же транзакции записывает в `InventoryMovement` `seller_id` товара и `warehouse_id` ячейки. Тем самым будущая перепривязка товара или ячейки не меняет отчётную историю. Контракт предназначен и для будущей пары transfer из 04-D; сама реализация transfer в эту карточку не входит.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/inventory_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_service_reporting_dimensions.py`

Зависит от: фичи 1.

Проверка: провести движение, затем изменить текущую связь товара с селлером или ячейки со складом; созданная строка журнала сохраняет исходные `seller_id` и `warehouse_id`.

### 3. Добавить WarningNotice в ui-kit

Экран может показать одно заметное, но неблокирующее предупреждение — например, об устаревшем импорте Wildberries или legacy-истории — тем же языком и отступами, что у существующей ошибки, без использования статусного чипа для всего экрана.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx`

Зависит от: нет.

Проверка: unit-тест рендерит `WarningNotice` с текстом и `testId`; в DOM виден MUI Alert с severity `warning`, а текст доступен читателю экрана.

### 4. Добавить четырёхзонную полосу показателей в ui-kit

Экран получает переиспользуемый `ReportMetricStrip`: одну outlined-полосу из четырёх равных зон с правым выравниванием чисел, единицей «шт.», табличными цифрами, `—` для неприменимого сравнения и скелетами во время загрузки, без вложенных карточек.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.test.tsx`

Зависит от: нет.

Проверка: unit-тест проверяет четыре обычных показателя, нулевое значение, `null` как «—» с пояснением и загрузочный скелет вместо устаревших чисел.

### 5. Добавить дневной график потоков в ui-kit

Экран получает `MovementFlowChart` с видимой легендой и текстовым описанием: приход и расход идут сплошными линиями, прошлый расход — пунктиром только при включённом сравнении. Компонент отдельно показывает пустой период и скелет, поэтому график не имитирует нулевые данные при загрузке.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx`

Зависит от: нет.

Проверка: unit-тест подтверждает легенду и доступное описание серий, отсутствие пунктирной серии при выключенном сравнении, текст «За выбранный период движений нет» для пустого набора и скелет при загрузке.

### 6. Отдать защищённую сводку и дневной поток отчёта

Сервер вводит read-only `GET /reports/overview`: он валидирует период не длиннее 366 дней, принудительно ограничивает селлера его `seller_id`, проверяет `inventory` у сотрудника ФФ и `can_products` у селлера. Ответ одновременно возвращает текущий физический остаток только по `is_operational`, внешний приход/расход без полных transfer-пар, сравнение с предыдущим равным интервалом, дневные серии, `generated_at`, свежесть источника и признаки предупреждений. Внутренние перемещения не увеличивают верхние показатели.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_overview.py`

Зависит от: фича 2 и завершённая 04-D, которая записывает transfer-пары по контракту 07-A.

Проверка: API-тесты проверяют московское умолчание на стороне клиента не требуется, полуоткрытые даты, отказ при 367 днях, изоляцию tenant/селлера, права ролей, исключение transfer-пары из внешних итогов, отдельный текущий остаток и «—» при нулевом расходе прошлого периода.

### 7. Отдать постраничную таблицу товаров и операций

Сервер вводит `GET /reports/inventory` с фиксированными `group_by=product|operation`, белым списком сортировок и страницами по 50 строк. В товарном срезе возвращаются видимые колонки отчёта, в операционном — приход, расход и нетто; при фильтре склада внутренние стороны transfer показываются отдельными строками. Неполная transfer-пара возвращает фактически записанные значения и флаг ошибки, а не достраивается эвристикой.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py`

Зависит от: фича 6.

Проверка: API-тест создаёт более 50 агрегатов и получает корректные границы страницы; проверяет две разрешённые группировки, поиск по названию/артикулу/SKU/ШК, отсутствие служебных складов, отдельные transfer-строки при выборе склада и ошибку целостности для неполной пары.

### 8. Выгружать текущий срез честным CSV

Сервер вводит `GET /reports/inventory/export.csv`: файл потоково повторяет фильтры, группировку, порядок и агрегированные колонки таблицы, не содержит канала, номеров документов, Excel-разметки или чужих данных. Для пустого среза и периода свыше 366 дней экспорт не создаётся с понятной доменной ошибкой.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py`

Зависит от: фича 7.

Проверка: API-тест сравнивает заголовки и строки CSV с ответом таблицы для одинаковых параметров, подтверждает фильтрацию по области роли и отсутствие выдачи при пустом срезе.

### 9. Открыть один отчёт в обоих порталах и зарегистрировать S-33

Пользователь с допустимой ролью видит пункт «Отчёты» и маршрут своего портала: ФФ — `/app/ff/reports`, селлер — `/app/seller/reports`. В реестре появляется один экран `S-33` с двумя маршрутами и единым контрактом зон; при отсутствии права меню и маршрут недоступны. Новая маршрутизация не добавляет вкладок или каталогов отчётов.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/layouts/AuthedAppLayout.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json`

Зависит от: фича 8.

Проверка: Playwright открывает пункт меню как администратор ФФ и как селлер с `can_products`, попадает на соответствующий URL и не видит у селлера селектор чужого селлера; аккаунт без права не получает пункт и не открывает маршрут.

### 10. Показать общий срез, фильтры и состояния верхней части экрана

На едином экране оператор сразу видит шапку «Остатки и движения», фильтры периода/склада/селлера/поиска/сравнения, четыре показателя, график и время актуальности. Выбор фильтра немедленно запрашивает новый единый срез; пока он загружается, блоки показывают скелеты, а не прошлые числа. Экран показывает из ответа `WarningNotice` о свежести WB и legacy-данных только для ФФ, а при сбое сводки оставляет будущую таблицу доступной и предлагает повторить загрузку.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts`

Зависит от: фичи 3, 4, 5, 6 и 9.

Проверка: Playwright меняет период и поиск через UI и видит синхронно обновлённые показатели и график; отдельно проходит загрузку, пустой период, отсутствие базы сравнения, устаревший внешний импорт и повтор после ошибки сводки. Селлерский сценарий подтверждает, что фильтр селлера и техническое предупреждение отсутствуют.

### 11. Показать таблицу, группировку, пагинацию и скачивание CSV

Нижняя часть того же экрана использует `DataTable`: переключатель «По товарам / По операциям» меняет только табличный запрос, а верхняя сводка не перезагружается. Отображаются фиксированные колонки, серверная строка «1–50 из N», пустое и ошибочное состояния таблицы; `PrimaryAction` «Скачать CSV» доступен лишь при строках, а клиент скачивает серверный CSV вместо HTML-файла `.xls`.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts`

Зависит от: фичи 10.

Проверка: Playwright переключает обе группировки, переходит на вторую страницу, проверяет неизменность верхних показателей, видит объяснение недоступного CSV при пустом периоде и получает файл с MIME CSV при нажатии «Скачать CSV».

## Порядок

Сначала обязательная волновая цепочка `03 → 01 → 04-A`, затем фича 1 и фича 2 образуют 07-A. После фичи 2 карточка 04-D обязана начать записывать transfer-пары по новому контракту; только после её завершения можно начинать 07-B, то есть фичу 6.

Фичи 3, 4 и 5 независимы друг от друга и от backend-фундамента, поэтому их можно выполнять параллельно. После 04-D backend-фичи 6 → 7 → 8 идут последовательно. Затем фронтенд идёт 9 → 10 → 11; фича 10 также ждёт все три ui-kit-фичи. Параллельная работа в одной и той же `FfReportsPage.tsx` не допускается.

## Что осталось за бортом

- Продажи, выручка, прибыль, комиссии, счета, задолженность и стоимость хранения не входят в операционный отчёт; деньги остаются границей карточки 09-billing.
- Оборачиваемость, неликвид, прогнозы и рекомендации требуют дневных снимков и согласованных формул, которых контракт первой волны не даёт.
- PDF, Excel, рассылки, сохранённые шаблоны, конструктор отчётов, документная детализация и фильтр единственного маркетплейса не входят в контракт.
- Материализованная витрина не создаётся до измеренного превышения p95 `/reports` выше 2 секунд семь дней подряд при не менее 100 реальных запросах.
- В контракте не определён точный источник и порог устаревания `source_freshness`; до реализации его нужно брать из уже существующего локального статуса импорта, не вызывая внешний API.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
