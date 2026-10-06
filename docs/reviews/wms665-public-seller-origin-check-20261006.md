# WMS-665 / WMS-517 — правильный публичный origin seller portal

Проверено 06.10.2026 только чтением production-конфигурации и публичными HTTP
запросами. Сервисы, DNS, прокси, Git, данные и настройки не менялись; браузер,
авторизация и выпуск токена не использовались.

## Результат

Правильный публичный origin существующего WMS seller portal:

`https://wms.sellerfocus.pro`

Рабочая ссылка существующего экрана вывода:

`https://wms.sellerfocus.pro/seller/honest-sign/withdrawals`

Сообщённый Виталию адрес
`https://sellerfocus.pro/seller/honest-sign/withdrawals` ведёт на другой сайт —
корневой landing SellerFocus — и закономерно возвращает 404 на `/seller/*`.
Добавлять новый экран или второй префикс `/seller` для исправления адреса не
нужно.

## Источник маршрутизации

На production портами 80/443 управляет контейнер `wb-finance-caddy-1`. Его
read-only mount указывает на `/root/wb-finance/Caddyfile`. В фактически
загруженной конфигурации:

- `sellerfocus.pro, www.sellerfocus.pro` отдают статический landing из
  `/var/www/landing`;
- `wms.sellerfocus.pro` целиком проксируется на `172.18.0.1:8088`;
- порт `172.18.0.1:8088` слушает `docker-proxy` WMS web;
- внутренний `/opt/wms/deploy/Caddyfile.http` обрабатывает `/seller*` через
  `try_files {path} /seller/index.html`.

Это согласуется со штатным production workflow, где публичный smoke использует
`https://wms.sellerfocus.pro`, и с repository-конфигурацией
`docker-compose.wms-host-8088.yml`.

## Фактический GET и отличие от неправильного origin

Публичные GET и HEAD дали одинаковый результат по методам:

| Origin и путь | GET | HEAD | Содержание |
|---|---:|---:|---|
| `sellerfocus.pro/` | 200 | 200 | старый landing, Last-Modified 05.04.2026 |
| `sellerfocus.pro/seller/` | 404 | 404 | seller portal здесь не смонтирован |
| `sellerfocus.pro/seller/honest-sign/withdrawals` | 404 | 404 | тот же неверный origin |
| `wms.sellerfocus.pro/` | 200 | 200 | WMS fulfillment SPA |
| `wms.sellerfocus.pro/seller/` | 200 | 200 | seller SPA |
| `wms.sellerfocus.pro/seller/honest-sign/withdrawals` | 200 | 200 | seller SPA fallback для существующего маршрута |

GET `/seller/` и GET `/seller/honest-sign/withdrawals` на правильном origin имеют
одинаковый SHA-256 тела
`6be7d0dce40241d4ab587224bae957f116678fd6709339cce87038ec2f7923e8` и
`Cache-Control: no-cache, no-store, must-revalidate`. Тот же SHA получен прямым
GET с production-host на внутренний upstream `172.18.0.1:8088` для обоих путей.
Это доказывает, что edge и внутренний WMS Caddy отдают один seller SPA, включая
deep-link, а не только отвечают на HEAD.

## Граница проверки

HTTP 200 подтверждает доставку SPA по правильному адресу, но не подтверждает
роль Виталия, доступ AVpack, ЭЦП, период продаж, состав КИЗ или production submit.
Для этого пользователь должен войти обычным способом на правильном origin; в
этом проходе чужая сессия не искалась и не использовалась. Отдельный read-only
аудит `8ed232e4` остаётся источником по существующему экрану и границам WMS-517.
