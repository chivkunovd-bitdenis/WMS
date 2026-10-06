# WMS-666 C11: существование исходной поставки на стенде

06.10.2026 **12:54:59 UTC** штатный Railway CLI/app reader подтвердил существование `9b3993c3-dffd-5f14-b7b0-2ccf0f495b57` в базе стенда. Перед SQL проверены проект `loyal-wonder` (`c28e681d-4535-4c96-ac97-c7b600a7f8e4`), его environment `production` (`58a08b66-1290-45a2-8737-e3d7408389e5`), backend WMS (`e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc`) и web domain `web-production-9e7c1.up.railway.app`. Это установленный Railway-стенд; VPS и другие проекты не использовались. Runtime повторно подтвердил те же project/environment/service IDs; соединение допущено только к PostgreSQL `postgres.railway.internal`.

Найдена ровно одна строка: **WMS617 ozon**, marketplace **ozon**, status **assembling**, source **wms**. Tenant `9c31f3f4-ce62-4c1f-891a-295b278f1e69`, seller `e29e0469-9c4c-5487-9fdd-7b17087be9fc`, warehouse `307c0ccd-9a6b-41df-9180-f8ed68022237`.

Состав: `WMS617-000010` — SKU617105,3шт; `WMS617-000011` — SKU617106,1шт; `WMS617-000012` — SKU617104,1шт. Все три заказа Ozon, локальный status `in_supply`. Их точные order/position IDs сохранены в `result.json`.

Reader опубликован до исполнения: `1090159614abbac76fd1f3e9e4b4cd3f4537966a`. Вся SQL-транзакция `REPEATABLE READ, READ ONLY`, сервер подтвердил `transaction_read_only=on`; затем rollback. Записей в БД, запросов маркетплейсу, выпуска токенов, чтения/изменения кабинетов секретов, изменения переменных или новой авторизации не было. CLI существующего remote reader отработал с exit0; сырой stderr не публикуется, только длина/hash.

Подтверждено только существование и состав исходного объекта C11. Пользовательская доступность после входа, установленная общая версия и UI-приёмка ещё не проверены. Новый seed не требуется. Дальше обычный вход сотрудника и проверка описанных C11 входов на общей версии стенда; пароли не добываем, токены не создаём, авторизацию не обходим. Общий candidate/CI и production не изменялись.
