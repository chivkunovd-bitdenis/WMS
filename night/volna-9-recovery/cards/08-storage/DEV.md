# DEV · 08-storage · атом 7 · повторная разработка по ревью

## Что реализовано

- `GET /operations/storage/statements` — признак настроенного тарифа теперь считается по выбранным операционным складам; для администратора персональная ставка одного селлера не подменяет общую ставку склада.
- `POST /operations/storage/statements/{statement_id}/fix` — фиксация выбирает только тарифы того же склада и селлера, сохраняет эффективную ставку с достаточной точностью и по-прежнему публикует один неизменяемый набор `BillingLedgerEntry`.
- `GET /operations/storage/statements/{statement_id}/print` — A4-снимок берёт литро-дни, эффективную ставку и сумму из неизменяемого ledger, поэтому документ согласован с начислением при старте или смене тарифа внутри месяца.
- `storage_statement_service` — склад добавлен в область выбора общей и индивидуальной версии тарифа; эффективная ставка одной ledger-строки хранится с точностью 12 знаков после запятой.
- Финансовая модель 09-A очищена от преждевременных `BillingInvoice` и `BillingRunIssue`, для которых в миграции не было таблиц. Эти сущности остаются за атомом 09-B.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/billing.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/__init__.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0094_billing_financial_core.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_statement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_billing_models.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- `20260822_0094` — в создаваемую таблицу `billing_tariff_versions` добавляет nullable `warehouse_id` с внешним ключом на `warehouses`, обязательность склада для `storage_liter_day`, раздельную уникальность общих и персональных ставок внутри склада и сохранение прежней уникальности глобальных тарифов других услуг. Точность `billing_ledger_entries.rate` увеличена до `Numeric(28, 12)` для арифметически согласованной эффективной ставки одной строки.
- Миграция остаётся добавляющей: удаления таблиц или колонок нет.

## Тесты

- `backend/tests/test_storage_statement_service.py` — проверены два одновременных запроса фиксации, единственность ledger-строки, неизменность повторной печати после нового обмера, отказ для проблемного и текущего черновика, нулевой statement, отсутствие подходящего тарифа, изоляция тарифа другого склада, неприменимость персональной ставки как общей и согласованность A4 с начисленными литро-днями при неполном тарифном месяце.
- `backend/tests/test_billing_models.py` — проверены складские и глобальные уникальные индексы тарифа, точность ledger-ставки и отсутствие преждевременных ORM-таблиц 09-B.
- `backend/tests/test_storage_movement_scope.py` — назначенный ревьюером миграционный регресс включён в целевой прогон; исправление правильного `down_revision = 20260821_0093` уже находилось в текущем HEAD.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/models/billing.py app/models/__init__.py app/services/storage_statement_service.py app/api/storage.py alembic/versions/20260822_0094_billing_financial_core.py tests/test_storage_statement_service.py tests/test_billing_models.py tests/test_storage_movement_scope.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/models/billing.py app/models/__init__.py app/services/storage_statement_service.py app/api/storage.py` — успешно: `Success: no issues found in 4 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_statement_service.py tests/test_billing_models.py tests/test_storage_movement_scope.py` — успешно: `14 passed in 3.64s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/check_migrations.py` — не запущен: в этой рабочей копии отсутствует `scripts/ci/check_migrations.py`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && alembic heads` — успешно: единственная голова `20260822_0097 (head)`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && git diff --check` — успешно, ошибок пробелов нет.
- `back_guard.py` не применялся: атом не добавляет новый роут; самого файла в этой рабочей копии также нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && git add <файлы атома> && git commit -m "fix(storage): align fixed statements with warehouse ledger"` — среда запретила запись в общий Git-каталог: `Unable to create .../.git/worktrees/lane-2-08-storage1/index.lock: Operation not permitted`. Изменения остались в рабочей копии и не закоммичены.

Обычный целевой вызов `mypy` без `--follow-imports=silent` дополнительно был выполнен и дошёл до несвязанных импортов. Он нашёл четыре существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; в четырёх затронутых модулях ошибок не показал. Полный backend-регресс не запускался по ограничению атома.

## Не реализовано

- Находки ревью 1 и 7 относятся к `frontend/` и роли `screen-dev`; backend-dev их не менял.
- API создания и изменения тарифа не добавлялся: это отдельный следующий атом и не входит в «зафиксировать документ и опубликовать ledger-строку».
- `BillingInvoice` и `BillingRunIssue` не реализованы: по `ARCH-CROSS.md` они принадлежат следующему этапу 09-B и не должны регистрироваться ORM до своей миграции.

## Находки

- В репозитории отсутствуют предписанные скрипты `scripts/ci/check_migrations.py` и `scripts/ci/back_guard.py`; цепочка миграций вместо первого дополнительно проверена безопасной командой `alembic heads` без подключения к БД.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не использовались.

## Блокеры

Функциональных блокеров кода нет. Публикация результата заблокирована файловыми правами среды на общий Git-каталог; commit и push не созданы. Отсутствие репозиторного migration-checker явно зафиксировано выше.
