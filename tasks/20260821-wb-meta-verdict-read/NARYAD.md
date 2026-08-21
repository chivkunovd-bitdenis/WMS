# Наряд · 20260821-wb-meta-verdict-read

**Полоса:** обычная  
**Экран:** S-03 (`/app/ff/fbs`) и backend API/data  
**Тип:** продолжение существующей FBS/WB интеграции, архитектурная стадия не требуется

## Просьба

Читать фактические вердикты WB по метаданным FBS через официальный `POST /api/marketplace/v3/orders/meta`, пакетами не более 100 заданий, с ограниченным retry на 429, сохраняя реальные `metaDetails`/`decision` и безопасно сверяя локальное состояние.

## Контракт

- **Экран:** операторский экран сохраняет текущий способ показа ошибки внешнего WB и не падает при ошибке чтения.
- **API и данные:** существующий автополлер `sync_marking_statuses_for_assembling_supplies` вызывает `POST /api/marketplace/v3/orders/meta` с `{\"orders\":[...]}`, максимум 100 ID в пачке; использует официальные `metaDetails` (`key`, `value`, `decision`, `reason`), не подменяет их выдуманным enum; удалённый WB код не удаляет локальную строку и не обнуляет `marking_code_id`.
- **Тесты:** проверяются граница 100/101, ограниченный 429 retry, официальные decisions (`filled`, `required`, `pending`, `optional`), исчезнувший WB-код и сохранность локальной привязки.

## Источник

[WB API: Получить метаданные сборочных заданий](https://dev.wildberries.ru/docs/openapi/orders-fbs) и [обновление WB API за март 2026](https://dev.wildberries.ru/news/302): `POST /api/marketplace/v3/orders/meta`, `metaDetails`, максимум 100 ID.

## Границы

- `backend/app/services/wildberries_fbs_client.py`
- `backend/app/services/fbs_marking_service.py`
- `backend/app/services/fbs_autopoll_service.py`
- `backend/tests/test_wildberries_marketplace_fbs_client.py`
- `backend/tests/test_fbs_marking.py`
- `backend/tests/test_fbs_autopoll.py`

Не делаем живых записей в WB, не открываем кабинеты секретов, не меняем UI/схему/формат API сверх необходимого.
