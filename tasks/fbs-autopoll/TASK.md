# TASK — fbs-autopoll: постоянный автоопрос новых заказов FBS

- **Эпик:** FBS — см. `../fbs-marketplace-orders/SPEC.md` и `DESIGN.md`. Гейт 1 эпика ✅, под-задача наследует.
- **Тип / размер:** feature / S
- **Зависит от:** `fbs-orders-intake` (модели FbsOrder, синк заказов должен быть готов)
- **Слои:** backend: `app/tasks` + Celery Beat расписание, `app/services` (переиспользуем `wb_marketplace_orders_service`)

## Описание (для Composer)

Постоянный фоновый автоопрос новых заказов FBS для каждого селлера с валидным WB-токеном категории «Маркетплейс». Интервал опроса (2–5 мин) — из конфига. Задача идемпотентна, не создаёт задвоений.

**Архитектура:** Celery Beat запускает на расписании фоновую задачу `poll_fbs_orders_all_sellers` (один раз за цикл). Она читает список активных селлеров с токеном, затем для каждого вызывает `POST /operations/fbs-orders/sync` (существующий эндпоинт из `fbs_orders.py`). Отдельный beat-job синкит статусы активных заказов (`POST /operations/fbs-orders/sync-statuses`). Оба джоба логируют результаты и ошибки (сетевые/квоты WB — не фатальны, продолжаем цикл).

**Точки интеграции:**
- Используем существующий сервис `wb_marketplace_orders_service.list_orders()` для чтения заказов из WB API
- Используем существующий эндпоинт `POST /operations/fbs-orders/sync` (фbs_orders.py::sync_fbs_orders)
- Используем существующий эндпоинт `POST /operations/fbs-orders/sync-statuses` (fbs_orders.py::sync_fbs_order_statuses)
- Переиспользуем паттерн из существующих wildberries_*_sync задач (app/tasks/background_jobs.py)

## Scope
- Celery Beat beat-schedule для регулярного опроса (интервал из `settings.CONF_FBS_POLL_INTERVAL_SEC` или 180 сек по умолчанию)
- Фоновая задача: итерация по всем активным селлерам → вызов синк-эндпоинтов
- Логирование попыток, успехов, ошибок (без прерывания цикла на сетевых ошибках)
- Периодический синк статусов (отдельный beat-job, например, раз в 10 мин)

## Out of scope
- Вебхуки (только поллинг)
- Ручная кнопка «Синхронизировать сейчас» (может быть в фазе 2)
- Обработка лимитов WB (логируем, но не замедляем опрос на этапе v1)
- Отмены и возвраты

## Арх-подход (реальные ручки/файлы)

**Backend:**
- Новый файл `app/tasks/fbs_autopoll.py`:
  - Функция `poll_fbs_orders_all_sellers()` — итерирует селлеров, вызывает `POST /operations/fbs-orders/sync` для каждого
  - Функция `sync_fbs_order_statuses_all_sellers()` — синк статусов активных заказов
  - Оборачивание в Celery-таск (если используем Celery; иначе фоновый job через `background_job_service`)
- Новая запись в `app/tasks/background_jobs.py::BEAT_SCHEDULE` для обеих задач (интервалы: sync_orders каждые 180 сек, sync_statuses каждые 600 сек)
- Используем класс `FbsOrderSyncBody` и `FbsOrderSyncStatusesBody` из `fbs_orders.py`
- Логирование: `logger.info()` на старт, `logger.error()` на сбой

**Конфигурация:**
- `settings.CONF_FBS_POLL_INTERVAL_SEC` (default: 180, пересчитывается в beat расписание)
- `settings.CONF_FBS_STATUSES_SYNC_INTERVAL_SEC` (default: 600)

**HTTP внутри приложения:**
- Используем httpx или встроенный клиент для вызова своих эндпоинтов (зависит от паттерна в проекте)
- Endpoints: 
  - `POST /operations/fbs-orders/sync` (FbsOrderSyncBody → FbsOrderSyncOut)
  - `POST /operations/fbs-orders/sync-statuses` (FbsOrderSyncStatusesBody → FbsOrderSyncStatusesOut)

## Критерии приёмки (DoD)

- [ ] Celery Beat расписание настроено; beat процесс запускается с проектом
- [ ] Задача `poll_fbs_orders_all_sellers` вызывает синк по каждому активному селлеру
- [ ] Задача `sync_fbs_order_statuses_all_sellers` вызывает синк статусов для каждого селлера
- [ ] Логи: на каждом цикле пишется начало, результат (N заказов синкировано), ошибки сетевые не прерывают итерацию
- [ ] Конфигурация интервалов из settings (или .env)
- [ ] Тесты: моки синк-эндпоинтов, проверка итерации по селлерам, обработка ошибок

## Test coverage (в описание PR — требование CI)

| TC-ID | Title | Applies (Y/N) | Notes |
|-------|-------|---------------|-------|
| TC-NEW-FBS-AUTOPOLL-001 | Успешный опрос заказов для одного селлера | Y | Given: 1 активный селлер с токеном, 5 новых заказов на WB / When: запуск фоновой задачи poll_fbs_orders / Then: синк-эндпоинт вызван, 5 заказов в БД с status=new, логи OK |
| TC-NEW-FBS-AUTOPOLL-002 | Итерация по нескольким селлерам | Y | Given: 3 активных селлера / When: запуск poll_fbs_orders_all_sellers / Then: sync вызван 3 раза, каждому продавцу свой пакет заказов |
| TC-NEW-FBS-AUTOPOLL-003 | Сетевая ошибка одного селлера не прерывает цикл | Y | Given: 3 селлера, второй возвращает HTTP 500 / When: запуск опроса / Then: логируется ошибка продавца №2, но селлеры №1 и №3 обработаны полностью; статус джоба = success |
| TC-NEW-FBS-AUTOPOLL-004 | Идемпотентность: повторный опрос одного заказа | Y | Given: заказ wb_order_id=12345 уже в БД (status=new) / When: опрос повторен / Then: заказ обновлён (upsert), не создана копия, версия увеличена |
| TC-NEW-FBS-AUTOPOLL-005 | Синк статусов: заказ перешёл в sorted на WB | Y | Given: заказ в статусе in_delivery, WB вернул status=sorted / When: sync_fbs_order_statuses_all_sellers / Then: wb_status обновлён на sorted, фронтенд видит актуальный статус |

## Где тесты

backend: `cd backend && pytest tests/services/test_fbs_autopoll.py` (или `tests/tasks/test_fbs_autopoll.py`, в зависимости от структуры)

## Гейт перед PR

```bash
cd backend && ruff check . && mypy . && pytest
```
