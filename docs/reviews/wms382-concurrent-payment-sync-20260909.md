# WMS-382: конкурентный зачёт подписки, 09.09.2026

Исправлен подтверждённый review-дефект в `subscription_payment_service.sync_pending_payment`: поздний запрос со старым Tenant мог затереть продление за P1+P2 датой только за P1. Новых таблиц, статусов, журналов и API нет.

Прочитан единственный caller `POST /subscription/sync`: авторизация, `get_user_by_id` и `_tenant_of` только читают пользователя/tenant в общей AsyncSession. `SessionLocal` использует `expire_on_commit=False`. Перед внешним GET завершается read-транзакция; сохраняются только tenant ID и пары локального/провайдерского ID платежей. HTTP-ответы собираются вне транзакции. Затем короткая блокировка Tenant и `populate_existing` читают актуальную дату; платежи перечитываются с блокировкой и tenant-фильтром только среди ещё pending/waiting_for_capture. Уже учтённый результат повторно не применяется. Дата и статусы фиксируются вместе.

Новый регрессионный тест воспроизводит точную последовательность с двумя независимыми сессиями PostgreSQL: A проверяет P1 и приостановлен в mock HTTP; создан P2; B проверяет P1+P2 и фиксирует два месяца; после этого отпущен A. На старом service тест упал именно на дате: `2026-10-16` вместо +60 дней от `2026-09-16`. После исправления проходит: +60 дней, оба платежа succeeded с paid_at, поздний A возвращает activated=false. Во всех трёх mock GET проверено отсутствие активной транзакции вызывающей сессии. На SQLite конкурентный тест явно пропускается, а не выдаётся за доказательство PostgreSQL-блокировок.

Использована только отдельная новая локальная БД `wms382_sync_20260909_01`, PostgreSQL `127.0.0.1:5432`, local role `deniscivkunov`, psycopg. HTTP полностью подменён и credentials тестовые. Реальные оплаты/запросы/ключи не использовались. Runtime: `/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python`.

Проверки из `backend` с `WMS_TEST_DATABASE_URL=postgresql+psycopg://deniscivkunov@127.0.0.1:5432/wms382_sync_20260909_01`:

- Старый service: `python -m pytest -q tests/test_subscription_payment.py::test_overlapping_payment_sync_preserves_both_paid_months` — 1 failed, проверка потерянных 30 дней.
- Исправленный: `python -m pytest -q tests/test_subscription_payment.py` — **9 passed**, 6.46 секунды; только прежние SWIG deprecation warnings.
- `python -m ruff check app/services/subscription_payment_service.py tests/test_subscription_payment.py` — passed.
- `python -m mypy app/services/subscription_payment_service.py --follow-imports=silent --cache-dir=/dev/null` — passed, 1 source file.

После успешных проверок закончилось место для первого сохранения отчёта/commit. Попытка удалить только собственную тестовую БД получила `Connection refused` от локального PostgreSQL; удаление не выполнено, сервер самостоятельно не перезапускался. После освобождения root воспроизводимых артефактов продолжено сохранение. Новых тестов после этого не запускалось; чужие базы и файлы не чистились.

Полный pytest, браузер и реальные платежи не запускались. Изменены только service, профильный тест и этот отчёт. Чужие auth/Ozon-правки не включаются. Push и общий выпуск выполняет root отдельно; локальное исправление не является доказательством деплоя.
