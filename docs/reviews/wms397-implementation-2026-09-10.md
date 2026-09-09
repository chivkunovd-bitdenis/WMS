# WMS-397 / WMS-399 — seller ↔ fulfillment chat MVP

Date: 2026-09-10
Branch: `feat/wms397-chat-mvp`
Author: chat-lane worker (Claude Opus 4.7)

## Что сделано

Собран минимальный, но связный внутренний мессенджер между продавцом и
фулфилментом. Работает поверх существующих таблиц пользователей, продавцов
и ролей — никакой второй системы аутентификации, никакой лишней сущности
на документ. Каждый продавец получает ровно один «основной» чат, который
материализуется при первом обращении и живёт под уникальным индексом на
уровне БД. Дополнительные («extra») чаты умеет заводить только FF-админ,
он же назначает участников. Крепление к документу лежит прямо в строке
сообщения как JSON-снапшот — чтобы карточка в ленте не разъезжалась с
переименованиями и удалениями сущностей.

Ниже — что именно поехало в этот PR и что осталось за границей MVP.

## Backend — эндпоинты

Всё под префиксом `/operations/chat`:

| Метод | Путь | Роль | Назначение |
|---|---|---|---|
| GET | `/conversations` | FF или продавец | Список видимых чатов текущего пользователя |
| GET | `/conversations/main?seller_id=` | FF или продавец | Основной чат продавца, создаётся идемпотентно |
| POST | `/conversations/extra` | Только FF-админ | Создать дополнительный чат с участниками |
| GET | `/conversations/{id}` | Читатель | Метаданные чата |
| GET | `/conversations/{id}/participants` | Читатель | Список участников |
| POST | `/conversations/{id}/participants` | Только FF-админ | Добавить участника |
| GET | `/conversations/{id}/messages` | Читатель | Лента сообщений (по возрастанию времени) |
| POST | `/conversations/{id}/messages` | Читатель | Отправить сообщение (идемпотентно по `client_message_id`) |
| PATCH | `/messages/{id}` | Автор | Правка текста |
| POST | `/conversations/{id}/attachments` | Читатель | Загрузить файл или изображение |
| GET | `/attachments/{id}/content` | Автор или читатель чата | Скачать содержимое |

Сериализация: см. `backend/app/api/chat_routes.py` (модели `ConversationOut`,
`MessageOut`, `AttachmentOut`, `ParticipantOut`).

## Модель доступа

1. **Продавец видит только свой seller_id.** Даже если он подсунет чужой
   `seller_id` в query — `get_main_chat` вернёт 403 (`can_read_conversation`
   и явная проверка в роуте).
2. **FF-админ и FF-стафф читают любой чат в своём тенанте.** Это соответствует
   постановке: продавец пишет в ФФ, а не конкретному сотруднику; конкретного
   исполнителя FF выбирает сам.
3. **В extra-чат нужна явная запись `ChatParticipant`.** Иначе продавец,
   находящийся не в этом чате, не увидит его в списке и получит 403 при
   попытке чтения.
4. **Идемпотентность сообщения** — по паре `(author_user_id, client_message_id)`
   с уникальным индексом на уровне БД. Повторный POST с тем же id вернёт
   строку из первой попытки; в тестах есть прямая проверка.
5. **Мультиселлерность документа не нарушается.** Прикреплённая карточка
   документа обязана иметь `seller_id`, равный `seller_id` чата, — иначе
   422 `document_seller_mismatch`. То есть если у документа несколько
   селлеров, а вы пишете в чат конкретного, из карточки видно только его
   контекст.

## Тесты

`backend/tests/test_chat_api.py` — 9 сценариев, все зелёные локально:

```
$ cd backend && .venv/bin/pytest -n auto tests/test_chat_api.py
9 passed, 45 warnings in 14.58s
```

Что покрыто:

| Тест | Проверяет |
|---|---|
| `test_main_chat_is_idempotent_per_seller` | GET main дважды → один и тот же UUID |
| `test_seller_sees_only_own_main_chat` | Продавец А видит только чаты своего seller_id |
| `test_seller_cannot_open_other_sellers_chat` | 403 при чтении чужого чата и при `?seller_id=` |
| `test_post_message_dedupes_on_retry` | Один и тот же `client_message_id` — одна строка |
| `test_attached_document_persists_across_reload` | Второй участник видит карточку документа после перезагрузки |
| `test_attached_document_wrong_seller_rejected` | 422 `document_seller_mismatch` |
| `test_upload_and_download_attachment` | Загрузка → прикрепление к сообщению → скачивание вторым участником |
| `test_edit_message_only_by_author` | PATCH автором ок, чужим — 403 |
| `test_extra_chat_requires_admin_and_hides_from_stranger` | Продавец не может создать extra; посторонний селлер не видит |

Также прогнаны ruff и mypy по всем затронутым файлам — чисто.

### Curl-трассировка (документально)

Приведена «на бумаге», потому что sqlite партиционные индексы уже проверены
интеграционными тестами; для полноты — вот как это выглядит в curl:

```
# 1. FF-админ материализует основной чат селлера
curl -s -H "Authorization: Bearer $ADMIN" \
  "$API/operations/chat/conversations/main?seller_id=$SELLER_ID"

# 2. Отправка сообщения (идемпотентная)
curl -s -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
  -X POST "$API/operations/chat/conversations/$CONV/messages" \
  -d '{"client_message_id":"cli-abcd","text":"Здравствуйте!"}'

# 3. Приложить изображение из буфера обмена (кодируется на клиенте)
curl -s -H "Authorization: Bearer $ADMIN" \
  -X POST "$API/operations/chat/conversations/$CONV/attachments" \
  -F 'file=@paste.png;type=image/png' -F 'is_image=true'

# 4. Приложить карточку документа
curl -s -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
  -X POST "$API/operations/chat/conversations/$CONV/messages" \
  -d '{"client_message_id":"cli-doc-1","text":"К этой поставке",
       "attached_document":{"kind":"fbs_supply","id":"...","title":"...",
         "seller_id":"'$SELLER_ID'"}}'
```

## Миграция

`backend/alembic/versions/20260910_0300_chat_messenger.py` — четыре таблицы:
`chat_conversations`, `chat_participants`, `chat_messages`, `chat_attachments`.
Партиционный уникальный индекс `uq_chat_conversations_main` (`WHERE kind = 'main'`)
работает и на Postgres, и на SQLite (модель обёрнута в `sqlalchemy.text()` —
без этого сборка партиционного WHERE падала на SQLite-диалекте пайтеста).

Проверка выполнена:

* `alembic upgrade 20260908_0257:20260910_0300 --sql` против Postgres —
  сгенерированный DDL валиден, вручную просмотрен.
* Соответствующий `downgrade` — тоже валидный.
* Локально «упереть в head» через `alembic upgrade head` не удалось только
  потому, что более старая миграция в проекте использует ALTER FK, что
  SQLite нативно не поддерживает; это существующая проблема, не наша.
  Тесты используют `Base.metadata.create_all` и проходят.

## Frontend — что затронуто

Новые файлы:

* `frontend/src/components/chat/chatApi.ts`
* `frontend/src/components/chat/AttachedDocCard.tsx`
* `frontend/src/components/chat/ChatComposer.tsx`
* `frontend/src/components/chat/ChatDialog.tsx`
* `frontend/src/components/chat/ChatOpenButton.tsx`
* `frontend/src/components/chat/ChatFeed.tsx`
* `frontend/src/screens/chat/ChatScreen.tsx`

Изменённые файлы:

* `frontend/src/App.tsx` — новый маршрут `ff/chat`, импорт `ChatScreen`.
* `frontend/src/hooks/useAuth.ts` — на типе `Me` появилось опциональное
  поле `id`. Бэкенд уже возвращает его из `/auth/me`; поле нужно, чтобы
  подсветить «мои» сообщения в ленте.
* `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — в заголовке рабочего
  пространства поставки FBS появилась компактная кнопка «Написать
  сообщение» рядом с крестиком. Клик открывает `ChatDialog` для селлера
  поставки, к первому сообщению будет прикреплена карточка `fbs_supply`.
  Таблица заказов FBS **не тронута** — колонки на месте, никаких новых
  чипов/статусов.

Проверено локально: `npx tsc --noEmit -p tsconfig.app.json` — без ошибок,
`npm run build` — успешно (dist собран).

## Что подтверждено кодом, а что — только специфицировано

**Подтверждено автоматическими тестами:**

* идемпотентность основного чата;
* seller-scope на списке и на чтении;
* идемпотентность сообщения по `client_message_id`;
* карточка документа переживает перезагрузку у второго участника;
* отказ при неверном селлере в карточке (422);
* полный round-trip файла: upload → attach → download вторым участником;
* редактирование только автором;
* права на создание extra-чата и его видимость только участникам.

## Второй проход WMS-415 (10.09.2026) — закрытые пробелы

Root-проверка 10.09.2026 (22:02 UTC) зафиксировала три оригинальных
семантических требования владельца, которые первый проход чат-канала оставил
неоформленными. Ниже — что сделано в дополнение.

### Gap 1 — компактная «Написать сообщение» на всех точках входа документов

Первый проход подключил кнопку только в рабочем пространстве FBS-поставки
(`FfFbsSupplyWorkspace.tsx`). Второй проход добавил её ещё в двух местах:

* **Отгрузка на маркетплейс** — заголовок диалога документа в
  `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx` (внутри `<Dialog>`
  на строке 2338). Кнопка появляется только для `docModal === 'marketplace_unload'`
  и когда у документа есть `seller_id`; вложение — `kind: 'marketplace_unload'`
  с номером отгрузки.
* **Приёмка** — панель действий в `frontend/src/screens/ff/FfInboundRequestView.tsx`
  рядом с «Сохранить» / «Закрыть». Вложение — `kind: 'inbound_intake'` с
  номером документа. `App.tsx` теперь пробрасывает `chatAuthHeaders` и
  `currentUserId` во «FF-документ-диалог».
* **Карточка отдельного FBS-заказа как самостоятельного экрана в проекте нет:**
  клик по строке в `FfFbsOrdersScreen.tsx:296–307` открывает уже подключённое
  рабочее пространство поставки (через `supply_id`), в котором кнопка стоит с
  первого прохода. Owner-требование «на карточке заказа FBS» покрыто этой
  цепочкой, отдельный экран заказа заводить не потребовалось.

### Gap 2 — карточка документа ведёт на сам документ, а не на список

`frontend/src/components/chat/AttachedDocCard.tsx` теперь строит целевой
маршрут с тем query-ключом, который каждый экран уже читает для авто-открытия:

* `fbs_order` / `fbs_supply` → `ff/fbs?supply_id=<id>` (потребляется
  `FfFbsOrdersScreen` на 1112 строке).
* `marketplace_unload` / `outbound_shipment` → `ff/mp-shipments?open_mp=<id>`
  (потребляется `FfSuppliesShipmentsPage` на 670 строке).
* `inbound_intake` → `ff/reception?open=<id>`. Раньше `FfInboundQueuePage`
  не читал этот параметр вообще; в этом проходе там добавлен `useEffect`,
  который при первом попадании id в списке строк вызывает существующий
  колбэк `onOpen` и стирает `open=` из URL, чтобы f5 не открывал документ
  повторно и не путал историю браузера.

### Gap 3 — создание extra-чата в UI + добавление участников

Backend-эндпоинт `POST /operations/chat/conversations/extra` был готов с
первого прохода (см. `backend/app/api/chat_routes.py:289–327`), но UI для
него отсутствовал. Второй проход добавил:

* `frontend/src/components/chat/ExtraChatCreateDialog.tsx` — новый компонент.
  Диалог выбирает продавца из уже переданного списка, требует название и
  предлагает multi-select участников. Источник списка — существующий
  `GET /auth/staff-accounts` (FF-стафф, `require_fulfillment_admin`),
  никакой новой ручки.
* `frontend/src/screens/chat/ChatScreen.tsx` — новая опция `isFulfillmentAdmin`
  и кнопка «Новый чат» над «Обновить список». Кнопка скрыта для селлера и
  для FF-стаффа не-админа (бэкенд повторяет то же условие как реальную защиту).
  После успешного создания диалог кладёт новую беседу в начало сайдбара
  и переключает `selectedId`, чтобы оператор попал прямо в неё.

### Gap 4 — браузерная проверка Ctrl+V / Cmd+V и reload

Не выполнена в этой сессии. Причина честная: попытка загрузить в
`claude-in-chrome` staging (`https://web-production-9e7c1.up.railway.app/`)
получила `Permission denied by user` от расширения — доменные права не
предоставлены. Локально одновременно поднимать backend + frontend + БД + двух
пользователей в изолированном воркри без предварительной подготовки в
рамках этой задачи не запускалось. Живая проверка вставки скриншота, второго
участника и перезагрузки остаётся невыполненной. Ответственность передаётся
владельцу либо следующей сессии, у которой будут разрешения браузерного
расширения или уже поднятая инфраструктура.

Код `ChatComposer` вешает `onPaste` и достаёт `image/*` из
`clipboardData.items` (проверено чтением) — по контракту API это тот же
путь, что использует любой веб-мессенджер, но подтверждать «работает»
без реального нажатия Cmd+V я не имею права.

### Gap 5/6 — этот файл и канонический бэклог

Этот файл обновлён (см. настоящий раздел). Карточка WMS-397 в
`docs/KANONICHESKIY_BACKLOG.md` также обновлена: обозначено, что MVP
кода на ветке `feat/wms397-chat-mvp` закрыл первые семантические пробелы,
а браузерная проверка осталась без подтверждения.

**Специфицировано, но не проверено в браузере:**

* поведение вставки Ctrl+V / Cmd+V как inline-изображения — см. gap 4 выше;
* полноценная страница `ff/chat` глазами оператора: собрана, но визуально
  на реальном разрешении оператора я её не смотрел;
* биллинг / лимиты хранилища вложений: в коде стоит `MAX_ATTACHMENT_BYTES`
  (25 МБ) и 10 вложений на сообщение. Тарификация отдельного вопроса от
  владельца пока не имела.

## Итог

Ветка `feat/wms397-chat-mvp`, семь последовательных коммитов от `71c903ca`:

1. `71c903ca` — модели и миграция.
2. `d16e8589` — сервисный слой с проверками прав и идемпотентностью.
3. `d73c05f0` — REST-эндпоинты.
4. `b547f360` — тесты (`test_chat_api.py`, 9 сценариев) + правка
   партиционного индекса на SQLite.
5. `346f6a51` — фронтенд первого прохода: экран `ff/chat`, диалог,
   композер, кнопка на рабочем пространстве FBS.
6. `1d0dfc70` — эта же нота, первая версия.
7. `b1004b0e` — WMS-415, gap 1+2: кнопка на приёмке и отгрузке МП,
   `AttachedDocCard` ведёт на конкретный документ.
8. `0343d40b` — WMS-415, gap 3: диалог создания extra-чата, кнопка
   «Новый чат» для FF-админа.

Ветка готова к пушу на origin.
