# Подготовка staging FBS acceptance: эмулятор WB

Проверен исходный код общего SHA `5c371f39` в `.worktrees/backlog40-stage`, 08.09.2026. Только чтение исходников/документов и запись этого отчёта. Runtime variables, ключи, учётные кабинеты, данные staging и эмулятора не читались и не менялись. Новые внешние запросы WB/Ozon не выполнялись. Браузер staging ведёт root; этот отчёт не является браузерным acceptance.

## Главный вывод

**Нельзя доказать текущий маршрут в эмулятор по имени селлера «Эмулятор WB», WB-номеру заказа или имени поставки.** В WMS нет прочитанного seller-specific переключателя эмулятора. Адрес строится из глобального `settings.wildberries_marketplace_api_base`: `backend/app/core/settings.py:55`, `backend/app/services/wildberries_fbs_client.py:78–85`, `backend/app/services/wildberries_client.py:176–184`. Токен выбирает продавца на уже выбранном сервере; он не выбирает hostname.

Поэтому нужны два независимых подтверждения:

1. Текущий **исходящий адрес именно процесса WMS API**, а для background acceptance ещё worker/beat, действительно указывает на `wb-emulator.railway.internal:8000`. Свежая разрешённая запись трассировки/HTTP access log с исходящим hostname и привязкой к этому процессу годится; наличие отдельного сервиса Railway `wb-emulator`, зелёный build или старый импорт не доказывают маршрутизацию WMS. Runtime variables читать запрещено текущим поручением, поэтому я этот способ не использовал.
2. На текущем экране/в разрешённом read-only ответе WMS подтверждены tenant, полный seller UUID, supply UUID и состав orders этого синтетического продавца. Идентификаторы исторического посева ниже помогают найти набор, но не заменяют свежую сверку.

Существующие безопасные status API не решают пункт 1: `/health` возвращает только `status:ok` (`backend/app/api/health.py:9`); `/integrations/wildberries/status` возвращает только content/supplies URL, не FBS marketplace URL (`backend/app/api/wildberries_integration.py:55–58,220–230`). `has_marketplace_token`, `marketplace_scope_ok` и даты проверки тоже не содержат маршрута. Не следует открывать управление ключами ради этой проверки.

**В пределах предоставленных данных маршрут текущего Railway staging не подтверждён.** Не утверждаю, что он боевой: текущий адрес неизвестен. Без пункта 1 нельзя обещать, что синхронизация, QR-печать, привязка/отвязка, отмена или передача пойдут именно в эмулятор.

## Где описан существующий стенд

`docs/evidence/20260831-beri-v-rabotu-ves-etot-blok-nado-dovesti/stend-fbs-emulyator-dlya-video.md`, датирован 31.08.2026. Он описывает Railway-проект `loyal-wonder`, внутренний сервис `wb-emulator`, базу `/data/wb_emulator.sqlite` и перевод сервиса WMS на `http://wb-emulator.railway.internal:8000`. Это историческое свидетельство, не свежая конфигурация.

В том же документе: tenant «WMS Staging», UUID начинается `9c31f3f4`; seller «Эмулятор WB», UUID начинается `50110328`; WB-склад `501001`, название «Emulator Seller Warehouse», привязанный склад WMS «Тестовый», `is_active/served`, публикация остатков тогда была выключена. Полных актуальных UUID seller/supply этим чтением не получено. Текущая сессия employee `denis.tsd.staging@example.com` и staging URL предоставлены root, мной не проверялись.

`wb_emulator/README.md` описывает HTTP-сервис и запуск, `docker-compose.emulator.yml:44,56,63` задаёт одинаковый marketplace host для API, worker и beat в локальном compose. Это не Railway-конфигурация. Упомянутого историческим документом `wb_emulator/Dockerfile.railway` в SHA `5c371f39` нет; из этого нельзя вывести версию уже развёрнутого сервиса.

## Существующий синтетический набор

Исторический продавец seller_a / «Эмулятор WB» соответствует пяти шаблонам в `wb_emulator/seed/order_templates.json`:

| WB order | Артикул | Сценарий |
|---|---|---|
| 510001 | EMU-NORMAL-B2C | Обычный B2C, без обязательного ЧЗ |
| 510002 | EMU-KIZ-REQUIRED | Обязательный sgtin |
| 510003 | EMU-KIZ-OPTIONAL | Необязательный ЧЗ |
| 510004 | EMU-B2B-LEGAL | Юридическое лицо / B2B |
| 510005 | EMU-CAN-PVZ-TRUE | Возможность сдачи через ПВЗ |

В исходном JSON всего 16 объектов: 14 именованных сценариев seller_a/b/c и 2 legacy-шаблона. У seller_b есть различия ПВЗ и office; у seller_c — крупногабаритный/сверхгабаритный, отменённый, близкий дедлайн и pool-KIZ. Наличие этих шаблонов в Git не доказывает их присутствия в Railway. Для текущего продавца нельзя произвольно брать seller_b/c.

Документ 31.08 фиксировал дедлайн 05.09, поэтому эти старые заказы нельзя считать сейчас новыми и актуальными; они могут быть завершены, отменены или просрочены. Историю, даты и остатки не переписывать для принятия сценария. Если подходящего активного синтетического заказа нет, сценарий на существующих данных недоступен.

## Что можно проверять после подтверждения маршрута

Для активной существующей синтетической поставки с обычным B2C (`510001`, либо найденным текущим аналогом) и без обязательного ЧЗ: открыть FBS → «В работе» → нужную поставку, сверить селлера и состав, перейти между подбором, упаковкой и коробами; проверить QR заказа и короба. Эти маршруты эмулятор реализует: `wb_emulator/routes/media_meta.py:47,67,89`, создание/состав/сдача/короба — `wb_emulator/routes/supplies.py:54–169`, batch-add — `wb_emulator/routes/marketplace_supplies.py:49`.

«Всё упаковано» в текущем UI вызывает существующий `/operations/packaging-tasks/{id}/pack-all-and-complete` (`frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx:1111`). При разрешённом выполнении это проверка факта упаковки: до/после фиксировать физические остатки, резервы и движения, они не должны измениться. Нельзя принимать упаковочный статус за разрешение перехода/передачи или восстанавливать такой gate. Передача — отдельная операция с законным единичным списанием; её не подменяет проверка галки.

До доказательства маршрута ограничиться чтением уже имеющихся данных и формы. Сам workspace GET не запрашивает WB: маршрут `backend/app/api/fbs_supplies.py:1531`, сервис `backend/app/services/fbs_workspace_service.py:89`; UI загружает его и локальное packaging task, при picking/boxes перечитывает workspace каждые 15 секунд (`FfFbsSupplyWorkspace.tsx:365–461`). Это не разрешение на новые операции; фоновые server jobs живут отдельно от открытого экрана.

## Ограничения текущего кода эмулятора для ЧЗ

1. **Положительная сверка ЧЗ не совместима с текущим строгим контрактом WMS.** `wb_emulator/routes/marketplace_orders.py:29–52` возвращает `metaDetails: []` и хранит проверку в `meta.checkStatus`. Парсер WMS сохраняет эти два источника раздельно (`wildberries_fbs_client.py:500–532`), а `_sync_order_meta_from_wb` строит returned_kinds только по metaDetails; при отсутствии вида устанавливает `unknown/check_error` (`fbs_marking_service.py:805–825`). Поэтому нельзя считать успешный PUT или напечатанный PDF доказательством принятия ЧЗ эмулятором по нынешнему контракту.
2. **Нет DELETE метаданных.** WMS отвязывает через `DELETE /api/v3/orders/{id}/meta?key=sgtin` (`wildberries_fbs_client.py:773–795`). Эмулятор имеет GET этого пути и PUT `/meta/{kind}`, но DELETE не зарегистрирован (`wb_emulator/routes/media_meta.py:105–140`). По текущему набору маршрутов ожидается 405, не успешная отвязка. Это ограничение эмулятора, не доказательство регресса WMS.
3. **Маркировка хранится в памяти процесса эмулятора**, не в SQLite: `wb_emulator/services/marking_meta.py:17–18`. После рестарта данные маркировки могут отсутствовать при сохранённых заказах/поставках.
4. **Нет списка GET /api/v3/supplies**: у `wb_emulator/routes/supplies.py` зарегистрированы POST коллекции и GET конкретного ID. Исторический документ уже фиксировал эту неполноту. Поштучные запросы не доказывают полноту фонового обхода.
5. Эмулятор охватывает Marketplace/FBS. Content API, Supplies/FBO API и специальный read-only warehouse override имеют отдельные базы (`settings.py:47–65`); подтверждение FBS-host не подтверждает изоляцию импорта карточек/реальных названий складов. Такие действия не включать в этот acceptance.

Итог: точный безопасный stage-маршрут не установлен доступными read-only свидетельствами. После разрешённого подтверждения host можно принимать обычную FBS/QR-поверхность на реально найденных активных синтетических заказах. Полный сценарий first-CZ → confirmed → clear нельзя честно объявить принятым через текущий код эмулятора; для него уже есть отдельные PostgreSQL-сценарии, но они не заменяют stage/browser acceptance. Код, эмулятор, ключи и исторические данные в этой задаче не менялись.

## Дополнение: фактический маршрут подтверждён 08.09.2026, 13:47 МСК

После отдельного узкого разрешения root прочитан **только** `settings.wildberries_marketplace_api_base` внутри уже работающего staging API через Railway SSH. Это устраняет прежнюю неопределённость маршрута API, описанную выше. Ни вывод environment/variables, ни чтение конфигурации целиком, ни управление ключами не выполнялись. CLI использовал существующую авторизацию SSH.

Сначала прочитаны локальные `railway --help`, `railway ssh --help`, `railway status --help`, сверены project/environment/service с `tmp/staging-readiness.md`. Свежий `railway status --project c28e681d-4535-4c96-ac97-c7b600a7f8e4 --environment 58a08b66-1290-45a2-8737-e3d7408389e5 --json` подтвердил project `loyal-wonder`, environment `production` (это установленный staging-контур), backend service WMS `e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc`.

Активный deployment `ebfa35d1-e2c4-41bb-bd57-93ac8ed37f5a`: `SUCCESS`, instance `86fd1cb0-9ea7-45c3-a18c-2a8b0095c8b6` — `RUNNING`, commit `5c371f39ccd836be96f85d4ffb68b8e52d5864cf`, branch `staging`, root `/backend`. SSH был привязан именно к этому instance через `--deployment-instance`.

Удалённый Python импортировал Settings, разобрал единственное разрешённое поле через `urllib.parse.urlsplit` и вывел только scheme/hostname/port, независимо от наличия userinfo/query. Результат, exit code 0:

```json
{"scheme": "http", "hostname": "wb-emulator.railway.internal", "port": 8000}
```

Артефакты: `tmp/review-first40/staging-fbs-route-runtime.txt` (только обезличенный маршрут и exit code), `tmp/review-first40/route-status-metadata.json` (Railway deployment/service metadata, не variables).

Свежий список сервисов этого environment: **WMS, web, wb-emulator, Postgres**. Отдельного сервиса worker/beat не обнаружено; отдельный worker-route поэтому не проверялся. Это утверждение о сервисах Railway, не инвентаризация процессов внутри WMS-контейнера. Для браузерных FBS-вызовов API маршрут на эмулятор доказан. Ограничения эмулятора, необходимость сверить конкретного синтетического селлера/состав поставки и отсутствие выполненных этим агентом операторских мутаций остаются в силе.
