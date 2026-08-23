ФИЧ: 20

## Фичи

### 1. Восстановить типовую сборку затронутых экранов

Оператор снова может открыть настройки, селлеров и выбор периода: используемые поля сохраняют те же подписи, значения и `data-testid`, но применяют актуальный API MUI; неиспользуемый импорт удалён. Это устраняет единственную причину, из-за которой фронтенд не собирается до создания бандла.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/PeriodPicker.tsx`

Зависимости: нет.

Проверка: `npm run build` в `frontend/` завершается успешно; в браузере поля реквизитов ФФ и селлера, а также выбор месяца остаются интерактивными и сохраняют прежние тестовые идентификаторы.

### 2. Хранить финансовые ставки и суммы только целыми копейками

Администратор вводит и видит рублёвую цену как прежде, а сервер хранит ставку и сумму в целых копейках, поэтому значение `4550` во всех границах модуля означает 45,50 ₽, а не 4 550 ₽. Миграция согласована с моделью и не вводит параллельный денежный формат.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09a_billing_financial_core.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_financial_core_migration.py`

Зависимости: нет.

Проверка: миграционный тест создаёт схему и подтверждает целочисленный формат копеек; тест модели и сервиса фиксирует, что 4 550 копеек форматируются как 45,50 ₽.

### 3. Разрешить новое начисление после сторно того же факта

Когда отменённая складская услуга выполнена заново, сервер создаёт новый положительный факт с тем же источником, но другим `event_kind`; исходное начисление и его сторно остаются неизменяемой историей. Повтор одного и того же события без сторно по-прежнему не создаёт дубль.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_09a_billing_financial_core.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py`

Зависимости: 2.

Проверка: тест последовательно создаёт начисление, сторно и повторный завершённый факт; в журнале есть две положительные записи и одна отрицательная, а два одинаковых положительных вызова без сторно дают одну запись.

### 4. Завершать нулевую проверенную приёмку и начислять фикс за документ

После фактической проверки с нулевым количеством оператор может закончить приёмку: документ переходит в `done`, а при действующем тарифе «за документ» появляется одно начисление. При поштучном тарифе сумма остаётся нулевой, но складской документ также не зависает.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/inbound_intake_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_inbound_intake_service_sort_be01.py`

Зависимости: 2, 3.

Проверка: сервисный тест проводит документ с нулевыми фактическими количествами через проверку и завершение, затем ожидает статус `done` и единственное документное начисление; негативный случай подтверждает отсутствие второго начисления при повторе.

### 5. Возвращать отсутствие начислений как штатную пустоту API

Для селлера без строк за период сервер отвечает пустым результатом, а не блокировкой `no_entries`; блокировками остаются только причины, которые оператор действительно способен устранить. API не предлагает повторное формирование, если для него нет исправимой причины.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_api.py`

Зависимости: 2, 3.

Проверка: API-тест запрашивает пустой месяц и ожидает штатное пустое состояние без `blocked/no_entries`; сценарий с настоящим отсутствием тарифа остаётся блокировкой с конкретной причиной.

### 6. Разделить серверные причины отсутствующих реквизитов

Сервер различает отсутствие профиля плательщика селлера и отсутствие реквизитов ФФ, чтобы ответ содержал ровно то исправляющее место, которое снимет удержание счёта. Если отсутствуют оба профиля, причины передаются раздельно, без маскировки одной другой.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py`

Зависимости: 2, 3.

Проверка: сервисные тесты отдельно создают неполный профиль селлера и неполный профиль ФФ; в каждом ответе ожидается собственный код причины и без ложного кода другой стороны.

### 7. Получать номер счёта из единого сервиса нумерации документов

Автоматический выпуск выдаёт счёту номер через `document_number_service`, а не из фрагмента UUID селлера. Номер не раскрывает технический идентификатор и не сталкивается между селлерами одного периода.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py`

Зависимости: 2, 3.

Проверка: тест формирует счета двум селлерам за один месяц и проверяет уникальные номера из общего сервиса, без UUID-префикса; повторный запуск возвращает уже созданный счёт.

### 8. Относить даты строк счёта к МСК на сервере

Детализация счёта определяет календарную дату факта по МСК, поэтому завершение в 00:30 МСК 1 сентября отображается 1 сентября, а не 31 августа UTC. Период и дата строки больше не противоречат друг другу.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py`

Зависимости: 2, 3.

Проверка: сервисный тест передаёт время на границе полуночи МСК и ожидает в строке счёта дату нового московского дня и соответствующий месячный период.

### 9. Передавать тип строки и ссылку на исходный документ в API журнала

API журнала явно отдаёт `entry_type` и для сторно сохраняет ссылку на исходный складской документ. Клиент может отличить отмену от выполненной услуги и показать её рядом с реальным источником, а не приписать работу отменившему пользователю.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_api.py`

Зависимости: 3.

Проверка: API-тест создаёт исходное начисление и сторно, затем ожидает у отрицательной строки признак сторно, исходный `source_type/source_id` и отсутствие подмены источником `billing_reversal`.

### 10. Закрепить поведение ежедневного автоматического формирования счетов

Тест запускает тело ежедневной задачи, а не только читает её расписание: задача обходит требуемых селлеров и закрытые месяцы, вызывает тот же идемпотентный сервис формирования и фиксирует результат. Сломанный обход или пропущенный commit станет красным тестом.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_tasks.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_service.py`

Зависимости: 5, 6, 7, 8.

Проверка: тест вызывает `_run_billing_invoices_daily` на данных нескольких селлеров и периодов, подтверждает созданные счета и commit, затем повторяет запуск и ожидает отсутствие дублей.

### 11. Показывать пустой месяц как пустое состояние, без ложного повтора

На вкладке «Счета» администратор видит понятное пустое состояние, если начислений за выбранный месяц нет. Кнопка «Повторить формирование» видна только при исправимой серверной причине, а не для пустоты или уже выставленного счёта.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`

Зависимости: 1, 5.

Проверка: e2e-сценарий выбирает селлера без начислений и видит штатную пустоту без действия исправления; сценарий с отсутствующим тарифом по-прежнему показывает осмысленный повтор после устранения причины.

### 12. Вести к правильным реквизитам из каждого удержания счёта

Действие в удержании из-за профиля селлера открывает нужного селлера, а удержание из-за реквизитов ФФ — настройки ФФ. Администратор попадает именно туда, где может исправить названную сервером причину.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`

Зависимости: 1, 6, 11.

Проверка: e2e отдельно моделирует обе причины и по клику проверяет маршрут к карточке селлера либо к настройкам ФФ; неверный маршрут не предлагается.

### 13. Честно отображать сторно в режиме «По исполнителям»

Режим «По исполнителям» не засчитывает сторно как выполненную работу отменившего пользователя: строка обозначена отменой и раскрывает исходный документ. Ссылка на документ остаётся доступной и для отрицательной записи.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-ledger.spec.ts`

Зависимости: 1, 9, 11.

Проверка: e2e показывает начисление и сторно разных пользователей; исполнительский итог не приписывает отрицательные штуки отменившему, а клик по сторно открывает исходный документ.

### 14. Форматировать даты начислений и счетов в МСК в интерфейсе

Экран «Расчёты» отображает даты операций, выставления и детализации в фиксированном часовом поясе МСК, независимо от часового пояса браузера администратора.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`

Зависимости: 1, 8, 11.

Проверка: компонентный тест фиксирует для UTC-времени около московской полуночи дату МСК; смена timezone среды не меняет видимый результат.

### 15. Выбирать корректный начальный месяц для каждой вкладки

При первом открытии «Начислений» выбран текущий месяц, а при первом открытии «Счетов» — последний закрытый; после ручной смены месяц пользователя сохраняется при переключении вкладок. Администратор сразу видит текущую работу, не теряя свой выбор.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`

Зависимости: 1, 14.

Проверка: компонентный тест открывает обе вкладки впервые, ожидает разные значения по контракту и затем подтверждает сохранение вручную выбранного периода.

### 16. Открывать вкладку тарифов из действий исправления

Оба действия «Открыть тарифы» ведут непосредственно на вкладку `tariffs` настроек ФФ, а не на общий раздел «Склад и сотрудники». Настройки читают параметр маршрута и открывают нужную вкладку без изменения существующего сценария зарплаты упаковщика.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`

Зависимости: 1, 11.

Проверка: e2e нажимает оба предложения открыть тарифы — из блокировки счёта и из начислений — и видит активную вкладку «Тарифы ФФ»; обычное открытие настроек остаётся на штатной вкладке.

### 17. Синхронизировать единицу расчёта с выбранной услугой тарифа

В форме тарифа смена услуги с хранения на приёмку или отгрузку автоматически устанавливает допустимую единицу `document` либо `item`; `liter_day` остаётся только у хранения. Оператор не может отправить серверу заведомо недопустимую пару.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.test.ts`

Зависимости: 1, 16.

Проверка: компонентный тест выбирает хранение, затем приёмку и отгрузку, проверяет допустимую единицу в форме и успешное формирование корректной пары; негативный случай не посылает `liter_day` для операционной услуги.

### 18. Сообщать о сетевой ошибке сохранения реквизитов и тарифа

Если сохранение профиля ФФ или тарифа не дошло до сервера, индикатор загрузки сменяется видимой ошибкой с возможностью исправить данные и повторить действие. Форма не создаёт впечатление, что настройки уже сохранены.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfSettingsScreen.test.ts`

Зависимости: 1, 17.

Проверка: компонентные тесты отклоняют запрос сохранения профиля и тарифа; в каждом случае ожидаются видимое сообщение об ошибке, восстановленная доступность кнопки и отсутствие ложного уведомления об успехе.

### 19. Сообщать о сетевой ошибке отмены счёта

При сетевом отказе после подтверждения отмены экран явно сообщает, что отмена не подтверждена, закрывает состояние ожидания и не скрывает счёт как отменённый. Администратор не повторяет опасное действие вслепую.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`

Зависимости: 1, 16.

Проверка: компонентный тест отклоняет запрос отмены после подтверждения и ожидает сообщение об ошибке, закрытый индикатор и сохранённый статус исходного счёта.

### 20. Форматировать количество и сумму исходного документа в детализации

В раскрытии строки счёта количество отображается через `QtyCell`, а сумма — через `MoneyCell`: 1 008 ₽ видны как `1 008,00 ₽` и не смешиваются с числом единиц. Формат соответствует остальным финансовым значениям экрана.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`

Зависимости: 1, 19.

Проверка: компонентный тест раскрывает документ с количеством и суммой 100800 копеек и ожидает отдельные форматированные `QtyCell` и `MoneyCell`, включая знак ₽ и две дробные позиции.

## Порядок

1. Сначала выполнить 1: до зелёной сборки нельзя надёжно проверить ни один интерфейсный атом. Она независима от серверных исправлений.
2. Затем последовательно выполнить 2 → 3: денежный формат и ключ событий — фундамент для операций и счетов.
3. После 3 атом 4 можно вести параллельно с 5, 6, 7, 8 и 9: первый исправляет закрытие приёмки, остальные — независимые границы и представление уже существующего финансового ядра.
4. Атом 10 следует после 5–8, потому что проверяет ежедневный путь на окончательной семантике пустоты, реквизитов, номера и московской даты.
5. Экранный поток по общему файлу `FfBillingScreen.tsx` выполнять строго так: 11 → 12 → 13 → 14 → 15 → 16 → 19 → 20. 11 ждёт API пустоты, 12 — причины профиля, 13 — API сторно, 14 — серверной даты; далее порядок устраняет конфликты в одном файле.
6. После 16 настройки можно вести параллельно с веткой отмены счёта: 17 → 18 работают только с `FfSettingsScreen.tsx`, а 19 → 20 — только с `FfBillingScreen.tsx`.
7. Каждая фича заканчивается своей адресной проверкой из раздела выше; в конце нужны общий `npm run build`, целевые `pytest` и пользовательские e2e-сценарии на видимые состояния.

## Что осталось за бортом

- Принятые ранее DEV-атомы 1–6 (вкладки, история тарифов, сетки таблиц и краткая подпись повтора) не возвращаются в разработку: в `REVIEW.md` они не являются незакрытыми находками.
- Новый UI-kit не выделяется: `MoneyCell`, `PeriodPicker` и расширение `PrintAction` уже существуют, а review требует только их корректного применения и типовой совместимости.
- Внешняя отправка счетов, PDF/УПД, НДС, оплаты, задолженность, backfill и кабинет селлера отсутствуют в контракте этой починки и не добавляются.
