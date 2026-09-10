# WMS-325 — настройки, реквизиты, тарифы и счета

Реализован следующий ограниченный срез WMS-325. **Это не независимая приёмка и не закрытие всей WMS-325/415/416.** Source commit: `d3103aa8e0aff0b76e1840f21f997d9ee6387072`, `WMS325: audit tenant settings, billing profiles, tariffs and invoices`. Ветка `feat/wms056-audit-trail`, постоянный checkout `/Users/deniscivkunov/Projects/WMS/.worktrees/wms056-audit-trail`.

## Исходная база и владение

Перед работой проверены pwd, чистота Git и HEAD `1207deba53e7937eb09011dc2dff8355b6e9ca3f`. Прочитаны применимые AGENTS, текущая карточка WMS-325 и разделы 5–7 инвентаризации координатора `docs/reviews/wms325-mutation-inventory-20260910.md`, включая соседние границы seller/catalog. Для разрешённых writers сравнен текущий координатор `496df7affba3ed5259d6a5da722e55803af9e33c`: отличий от этой ветки не было. Дополнительно проверен рабочий diff координатора в этих файлах: пусто. **Импортированных дельт координатора в этой волне нет.**

Изменены только пять сервисов: tenant_settings_service, billing_configuration_service, billing_tariff_matrix_service, billing_invoice_service, billing_invoice_v2_service; константы разрешённых document_type в существующей модели DocumentEvent и перечень этих типов в существующем history API; один новый файл целевых тестов. Модель billing и схема БД не менялись. Новый API или расширение прав не потребовались.

Замороженный срез `96799065`: inbound/MP/print writers, соответствующие модели/API, тесты и его report не изменены — проверено diff относительно `1207deba`. Не выполнялись merge/reset, дочерние агенты, правки канона, inventory/stock/warehouse/catalog/products/chat/mobile/418 или WMS-111/112. Клиентские данные, секреты, кабинеты учётных данных, отправка email и платёжные шлюзы не использовались.

## Реализованное покрытие

В существующую таблицу DocumentEvent добавляются события существующих типов `data_changed`, `document_created`, `status_changed`. Пять новых значений **document_type** обозначают уже существующие объекты, не новые доменные сущности или журналы.

| Writer | Факт и адрес истории |
| --- | --- |
| `tenant_settings_service.update_tenant_settings` | before/after address_storage_enabled, separate_marking_print_enabled, fbs_shipment_cutoff_time. `tenant_settings`, document_id=tenant.id |
| `billing_configuration_service.save_profile` | Создание и правка реквизитов ФФ или селлера: seller_id, legal_name, inn, kpp, bank_name, bik, settlement_account, correspondent_account после существующей нормализации/валидации. `billing_profile`, document_id=profile.id |
| `billing_configuration_service.create_tariff` | Новая версия, закрытие прежнего периода, billing_enabled_from: version_id, seller_id, warehouse_id, service_code, unit, amount_kopecks, valid_from/valid_to. `billing_tariff`, document_id=tenant.id |
| `billing_tariff_matrix_service.save_tariff_matrix` | Снимки разрешённых полей версий, включённость услуг, revision и billing_enabled_from. Для версии: ID, seller/product/employee scope IDs, service_code, unit, enabled, rate_kopecks, UTC-интервал. `billing_tariff_matrix`, document_id=tenant.id |
| `billing_invoice_service.form_invoice` | Только успешно созданный legacy-счёт: invoice_id, seller_id, origin=legacy, status, period, total_amount_kopecks. `billing_invoice`, document_id=invoice.id |
| `billing_invoice_service.cancel_invoice` | Переход существующего issued → cancelled с прежним и новым состоянием; повторная отмена — без события |
| `billing_invoice_v2_service.create_invoice_v2` | Только реально созданный V2-счёт после успешной записи строк и idempotency-связи: invoice_id, seller_id, origin=v2, status, creation_mode, период и итог в копейках. Повтор существующего idempotency key возвращает прежний счёт без нового события |
| `billing_invoice_v2_service.cancel_invoice_v2` | Автор текущей отмены через audit-контекст; issued_by_user_id остаётся автором выпуска, не подменяется |

`storage_statement_service.create_storage_tariff` прочитан, но не изменён: он вызывает save_tariff_matrix. Новое покрытие поэтому действует для общей и индивидуальной ставки хранения **одним** событием матрицы, без дублирования в wrapper. Повтор сохранения тех же версий/сервисов не создаёт новый факт.

Реквизиты селлера в этом срезе — существующий BillingProfile, который меняется через `/billing/profiles/sellers/{seller_id}`. Создание Seller, аккаунтов и магазинов относится к другим writers и этим патчем не объявляется покрытым.

## Сохранённые контракты

Payload строится только из явных перечисленных полей. Нет model_dump, сериализации входящего request, invoice.lines, manual description, snapshot всего профиля из счёта, расчётных токенов, idempotency key/hash, файлов или иных произвольных текстов. Юридическое наименование и банковские реквизиты — именно разрешённые поля существующего profile writer, не извлечение данных из неизвестного payload.

Каждая новая запись проходит через неизменённый record_document_mutation. Автор и снимок имени берутся из контекста после аутентификации с существующей tenant-проверкой. Переданный actor_user_id/body не является источником автора. System-контекст сохраняется как source=system без пользовательского снимка. No-op пропускается по равным проекциям; отвергнутые изменения не пишут факт успешного действия.

Сохранены существующие SQL-блокировки, проверки, ставки, округления, интервалы, revision increments, биллинговая дата начала, дооценка ledger, выпуск/отмена/idempotency счетов и границы commit. Новых row locks, NOWAIT, commit или финансовых OperationFact/BillingLedgerEntry ради истории нет. Вызов существующего переноса остатков при выключении адресного хранения не изменён. Упаковка, навигационные гейты и складские движения вне нового diff.

Запись истории находится в транзакции операции. Существующие savepoints изолируют ошибку аудита; новая политика fail-soft не вводилась. Откат внешней транзакции удаляет и событие. При отказе хранилища истории операция может завершиться без истории — это сохранённый контракт, не обещание абсолютной полноты.

History API по-прежнему использует require_fulfillment_admin. Добавлены только пять допустимых document_type, необходимые для чтения нового покрытия. Проверка пользователя-селлера на каждом новом типе возвращает 403; иной tenant не видит события.

## Выполненные проверки

Собственная изолированная native PostgreSQL: кластер wms325-settings-pg-*, БД wms325_settings_synthetic, Unix socket, порт 55468, TCP отключён. Все организации, пользователи, реквизиты, тарифы и счета — синтетические. Последовательные pytest-процессы, без xdist; максимум один тестовый процесс одновременно. Coordinator DB/fixtures и живые данные не использовались. После проверок PostgreSQL остановлен; созданный кластер перенесён в Trash.

**17 новых проверок прошли** за 13.05s: [focused-pytest.txt](focused-pytest.txt). Покрыты:

- HTTP-authenticated настройки, три поля, no-op и очистка cutoff time; попытка передать другой actor в body не меняет автора; admin-only и tenant-изоляция истории.
- Создание/нормализация/изменение/повтор/отклонение профиля ФФ и селлера; снимок имени сохраняется после переименования.
- Legacy-тариф: создание двух версий и закрытие прежнего периода без изменения прежней ставки; отказ пересечения не даёт факт; лишних ledger/OperationFact нет.
- Матрица: первая/следующая версия, закрытие старого интервала, no-op, оба направления enabled, откат ошибочной смешанной пачки и сохранение количества версий.
- Storage wrapper: общая и seller-ставка дают одно системное событие; повтор — без события.
- V2 invoice: HTTP-создание, idempotent retry; отмена от другого валидного пользователя того же synthetic tenant через сервисный контекст; последующие HTTP-отмены не создают дубликатов; issued_by_user_id и сумма сохранены. Ручной текст и ключ повторного запроса отсутствуют в журнале.
- Legacy invoice: создание/повтор/отмена/повторная отмена, сумма и количество ledger-строк сохранены.
- Пять настоящих PostgreSQL trigger-failures при INSERT в document_event: настройки, profile, legacy tariff, matrix, V2 invoice успешно сохраняют бизнес-результат без события и без нового финансового факта.
- Четыре проверки outer rollback: profile, tariff, invoice cancellation, settings; событие существует внутри транзакции и отсутствует после rollback вместе с изменением данных.

**29 существующих целевых проверок прошли** за 22.09s: [scoped-regressions.txt](scoped-regressions.txt). Запущены только:

- tests/test_billing_configuration_api.py;
- tests/test_billing_invoice_api.py;
- tests/test_billing_invoice_v2_duplicates.py;
- tests/test_billing_invoice_cross_format_duplicates.py;
- tests/test_billing_invoice_v2_api.py::test_manual_invoice_v2_preview_save_retry_and_cancel;
- tests/test_tenant_settings.py::test_tenant_settings_get_and_patch.

Этот прогон сохраняет проверки границ сумм/дооценки, непротиворечивости тарифов, отсутствия двойного выставления источников и существующих операций счетов. Полный набор не запускался. Прежний результат inbound/MP `47 passed, 1 old fixture failure` остаётся в предыдущем report без изменений; старое ожидание не ослаблялось и здесь не перегонялось.

Scoped Ruff: `All checks passed!`. Scoped mypy: `Success: no issues found in 8 source files`. Mypy запускался с `--follow-imports=silent`, проверяя семь изменённых production-файлов и новый тест без диагностики нетронутых импортов. `git diff --check` прошёл. Итоговый production-diff прочитан полностью: вставки аудита, import существующего helper/projection и разрешённые значения document_type; финансовые выражения и ветвления не переписаны.

Использованы `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/{pytest,ruff,mypy}`; pytest — из backend, с WMS_TEST_DATABASE_URL только собственного кластера. Новые тесты: `backend/tests/test_wms325_settings_billing_mutations.py`. Файлы Ruff/mypy: app/models/document_event.py, app/api/document_events.py, app/services/tenant_settings_service.py, app/services/billing_configuration_service.py, app/services/billing_tariff_matrix_service.py, app/services/billing_invoice_service.py, app/services/billing_invoice_v2_service.py и новый файл тестов.

## Открытые границы

Это конкретные writers разделов 5–7, а не универсальный аудит любых изменений Tenant/Seller/billing-таблиц. Автоматическое создание/дозаполнение выключенной матрицы через ensure_disabled_tariff_matrix, журнал причин отказа выставления BillingRunIssue, соседние административные writers и все paths вне перечисленных функций не расширены. Прочие пробелы полной инвентаризации WMS-325 — seller/account creation и делегирование магазинов, каталог/настройки вне перечисленных полей, маркировка/шаблоны, чат, импорты и остальные контуры — остаются за рамками этой волны. Чужие статусы приёмки не менялись.

CI, браузер, staging/production, миграции, merge и deploy в этом срезе не выполнялись. Срез сохранён для отдельного независимого review и интеграции координатором; весь WMS-325 не объявляется завершённым.
