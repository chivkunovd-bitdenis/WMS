# Стенд для видео по ФБС: эмулятор WB на Railway — 31.08.2026, ~13:30 MSK

Прод не тронут: он как ходил в `https://marketplace-api.wildberries.ru`, так и ходит.

## Что развёрнуто

Новый сервис Railway **`wb-emulator`** в проекте `loyal-wonder`, ветка
`chore/wb-emulator-railway-dockerfile`, файл `wb_emulator/Dockerfile.railway`.
Публичного адреса у него нет — только внутренняя сеть Railway.

Отдельный Dockerfile понадобился потому, что Railway отвергает инструкцию `VOLUME`:
`dockerfile invalid: docker VOLUME at Line 18 is not supported, use Railway Volumes`.
Исходный `wb_emulator/Dockerfile` и `docker-compose.emulator.yml` не менялись.

Переменные сервиса: `PORT=8000`, `RAILWAY_DOCKERFILE_PATH=wb_emulator/Dockerfile.railway`,
`WB_EMULATOR_DB_PATH=/data/wb_emulator.sqlite`, `WB_EMULATOR_ADMIN_TOKEN` (в скретчпаде),
`WB_EMULATOR_TOKEN_MAP` — три токена `stage-token-a|b|c`.

Сервис **WMS** переведён на эмулятор:
`WILDBERRIES_MARKETPLACE_API_BASE=http://wb-emulator.railway.internal:8000`
(было `https://marketplace-api.wildberries.ru` — этим значением возвращать назад).

Проверено изнутри контейнера WMS: `GET /health` эмулятора → `200`.

## Что засеяно

Эмулятор: `python -m wb_emulator.seed.load_seed` → `seller_a 5, seller_b 4, seller_c 5`.
Склад продавца — `501001 «Emulator Seller Warehouse»`.

WMS, арендатор **«WMS Staging»** `9c31f3f4-…`, админ `staging-admin@example.com`:

- склад «Тестовый» `307c0ccd-…`
- селлер **«Эмулятор WB»** `50110328-…`, WB-токен `stage-token-a` (content/supplies/marketplace)
- привязка `501001 → Тестовый`, `is_active`, `served`, публикация остатков выключена
- пять товаров с остатком по 10 шт в зоне «Без ячеек»

| Артикул | nmId | chrtId | ЧЗ | Сценарий |
|---|---|---|---|---|
| EMU-NORMAL-B2C | 123456789 | 111001 | нет | обычный |
| EMU-KIZ-REQUIRED | 123456790 | 111002 | **да** | обязательный Честный знак |
| EMU-KIZ-OPTIONAL | 123456791 | 111003 | нет | ЧЗ необязателен |
| EMU-B2B-LEGAL | 123456792 | 111004 | нет | юрлицо (`is_legal`) |
| EMU-CAN-PVZ-TRUE | 123456793 | 111005 | нет | сдача через ПВЗ (`can_pvz`) |

Импорт заказов: `orders_received 10, orders_created 5, orders_upserted 10`.
В базе стенда пять новых заказов `510001…510005`, все `mapped` + `reserved`,
дедлайн 05.09. Старые `990000001…7` в статусе `delivered` — мусор прошлых прогонов.

## Что эмулятор умеет (для видео)

Заказы: `/orders/new`, `/orders`, `/orders/status`, отмена.
Поставки: создать, добавить заказ, сдать (`/deliver`), грузоместа (`/trbx` CRUD).
Печать: `POST /orders/stickers`, `GET /supplies/{id}/barcode`,
**`POST /supplies/{id}/trbx/stickers` — QR коробов**.
Остатки: `PUT/POST /stocks/{warehouseId}`. Склады и офисы продавца.
Админка: `POST /__admin/orders` (докинуть заказы), `POST /__admin/orders/{id}/wb-event`
(двинуть статус со стороны WB), `POST /__admin/faults` (сломать WB намеренно).

## Известное ограничение

`GET /api/v3/supplies` (список поставок) в эмуляторе не реализован — есть только
создание и чтение одной поставки. При опросе это даёт одну строку в логе
`wb supplies list fetch failed … upstream_error`; импорт заказов при этом
отрабатывает полностью. На путь «создать поставку → набить → напечатать → сдать»
не влияет, но в логах будет шуметь.

## Как вернуть стенд на настоящий WB

```
railway variables --service WMS --set "WILDBERRIES_MARKETPLACE_API_BASE=https://marketplace-api.wildberries.ru"
```
Сервис `wb-emulator` можно оставить — он ни на что не влияет, пока переменная не смотрит на него.

---

# Догон: Честные знаки засеяны — 31.08.2026, ~15:00 MSK

Сеял штатным импортом `marking_code_service.import_marking_codes` — тем же путём,
которым оператор загружает файл кодов, а не вставкой в таблицы. Файл
`stage-kiz-emulyator.csv`, автор загрузки — `staging-admin@example.com`.

Формат КИЗ взят из парсера сервиса: `01<GTIN14>21<серийник>`, где GTIN14 — это
ноль плюс EAN-13 штрихкод товара, серийник не короче 13 символов.

```
принято: 100   пропущено: 0

пул «Куртка демо обычная»          gtin 02000000000011  принято 20
пул «Куртка демо с ЧЗ»             gtin 02000000000012  принято 20
пул «Куртка демо ЧЗ необязателен»  gtin 02000000000013  принято 20
пул «Куртка демо юрлицо»           gtin 02000000000014  принято 20
пул «Куртка демо ПВЗ»              gtin 02000000000015  принято 20
```

`count_available_for_product` по каждому из пяти товаров → **20 доступных**.

Поставка со скриншота владельца `WB-GI-2F66EF14FBB2`: `picked 1/1`,
`stickers_ready 1`, `packed 0` — то есть подбор пройден, дальше упаковка с ЧЗ.

Экран руками не открывал — боевой учётки стенда у меня нет.
