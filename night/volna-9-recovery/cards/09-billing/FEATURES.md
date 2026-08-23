ФИЧ: 7

## Фичи

### 1. Сохранять новую тарифную ставку в целых копейках

Оператор по-прежнему вводит ставку в рублях с двумя знаками, но API отделяет это входное значение от выходного значения в копейках и до записи переводит его в `int`. Поэтому создание тарифа, включая `0,00 ₽`, возвращает `201`, не передаёт `Decimal` в целочисленное поле и в ответе остаётся сумма в копейках.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_api.py`

Зависимости: нет.

Проверка: отправить `POST /billing/tariffs` со ставками `0.00` и `45.00`; оба запроса возвращают `201`, в базе и API-ответе получаются соответственно `0` и `4500` копеек, а отрицательная и трёхзнаковая дробная ставка по-прежнему отклоняются валидацией.

### 2. Дооценивать ранее неоценённые начисления в копейках

Когда оператор добавляет покрывающий тариф, ранее сохранённое начисление без ставки получает снимок ставки и сумму целыми копейками: для документной услуги — за один документ, для поштучной и литр-дневной — по точному количеству. Историческая строка больше не получает `Decimal` в поля `rate` и `amount` и не ломает `flush`.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_configuration_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_configuration_api.py`

Зависимости: 1.

Проверка: создать неоценённую строку журнала, затем тариф, покрывающий дату факта; после `flush` у строки целые `rate` и `amount` в копейках, она перестаёт быть `unpriced`, а `mypy` не сообщает ошибки на присваивании этих полей.

### 3. Исправить контракт MoneyCell: вход — целые копейки

Общий UI-kit форматирует параметр денежной ячейки как сумму в минорных единицах (копейках), сохраняя два знака, неразрывный пробел и обычное отображение сторно. Это единый фундамент для тарифов, начислений и счетов; `4500` отображается как `45,00 ₽`, а `null` — как «—».

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/ui-kit/Cells.test.ts`

Зависимости: нет.

Проверка: unit-тесты `formatMoney`/`MoneyCell` фиксируют `4500 → 45,00 ₽`, `-60000 → -600,00 ₽`, `0 → 0,00 ₽` и `null → —`; существующая таблица тарифов, передающая API-значение без деления, показывает ставку корректно.

### 4. Показывать и печатать счета из копеек без повторного пересчёта

Экран «Расчёты» передаёт денежные поля ledger и счёта в исправленный `MoneyCell` как копейки; HTML-печать форматирует те же минорные единицы, а раскрытая детализация не делит сумму второй раз. E2E-макеты используют фактический API-контракт (`1200`, `1494000`, `8`, `1455200`), поэтому проверяют сумму для оператора, а не старый рублёвый fixture.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`

Зависимости: 3.

Проверка: при ответе ledger/счёта в копейках таблица начислений, карточка счёта, раскрытая строка и всплывшая печать согласованно показывают, например, `63000` как `630,00 ₽`; в UI и печати нет значения, завышенного в 100 раз.

### 5. Открывать именно реквизиты, которые снимают профильную блокировку

Кнопка проблемы `missing_seller_profile` открывает диалог указанного селлера и его блок «Реквизиты для счетов», а `missing_ff_profile` ведёт на `/app/ff/settings?tab=tariffs`, где находится блок реквизитов ФФ. Администратор после перехода видит нужные поля, а не только корректный URL.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/v2/SellersScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/tests-e2e/billing-invoices.spec.ts`

Зависимости: нет.

Проверка: в браузерном сценарии обе причины выводятся из API списка счетов; нажатие для селлера открывает его диалог и раскрытые поля реквизитов, а действие для ФФ активирует вкладку «Тарифы ФФ» с реквизитами. Обычное открытие `/app/ff/settings` по-прежнему остаётся на вкладке сотрудников.

### 6. Закрепить в описании и API-тесте два профильных кода блокировки

Эксплуатационное описание `S-31` называет оба фактических кода `missing_ff_profile` и `missing_seller_profile`, их отдельные действия и способы снятия. Серверный API-тест фиксирует именно эти возвращаемые причины, чтобы документ и контракт не вернулись к несуществующему `missing_profile`.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_invoice_api.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/docs/blockers/S-31.md`

Зависимости: нет.

Проверка: тесты API отдельно получают `missing_ff_profile` при отсутствии реквизитов ФФ и `missing_seller_profile` при отсутствии плательщика-селлера; в `S-31.md` для каждого кода есть шесть обязательных полей: что блокируется, условие, серверная проверка, видимое сообщение, действие снятия и бизнес-причина.

### 7. Выбирать начальные месяцы начислений и счетов по Москве

Начальный период вкладок вычисляется в часовом поясе `Europe/Moscow`: «Начисления» открывают текущий московский месяц, «Счета» — предшествующий, включая границу месяца. Уже вручную выбранные периоды вкладок не изменяются.

Файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/frontend/src/screens/ff/FfBillingScreen.test.ts`

Зависимости: нет.

Проверка: unit-тест передаёт `2026-08-31T21:30:00Z` и получает сентябрь для начислений и август для счетов; тест также сохраняет раздельно вручную выбранные месяцы вкладок.

## Порядок

1. Сначала выполнить 1, затем 2: второе исправление опирается на единый переход рублёвого ввода в целые копейки.
2. Параллельно с этой backend-цепочкой можно выполнить 3 и 6: их файлы не пересекаются с 1–2 и друг с другом.
3. После 3 выполнить 4, поскольку экран и печать зависят от исправленного контракта `MoneyCell`.
4. Затем последовательно выполнить 5 и 7. Обе фичи независимы по поведению, но затрагивают один и тот же `FfBillingScreen.tsx`; это исключает конфликт двух исполнителей. Их также нельзя вести параллельно с 4, который меняет тот же экран и E2E-файл.
5. Итоговая пользовательская проверка денег проходит после 1–4: создание тарифа, дооценка строки, список начислений, счёт и печать должны использовать один и тот же формат копеек.

## Что осталось за бортом

- Нет: перепланирование ограничено шестью незакрытыми находками `REVIEW.md`; ранее принятые атомы карточки в разработку не возвращаются.
- Внешняя среда Playwright не входит в исправление: если ей снова запрещён bind `127.0.0.1:18000`, это фиксируется как инфраструктурное ограничение после запуска адресных сценариев, а не обходится изменением продукта.
