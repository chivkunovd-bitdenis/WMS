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

**Специфицировано, но не проверено в браузере:**

* поведение вставки Ctrl+V / Cmd+V как inline-изображения. Компонент
  `ChatComposer` действительно вешает `onPaste` и вытаскивает файлы из
  `event.clipboardData.items` для `kind === 'file'` с типом `image/*`.
  По контракту с браузером это тот же путь, что использует любой
  веб-мессенджер, но живая проверка возможна только в реальном браузере,
  а в этой сессии он не запускался. Явно называю это неверифицированным.
* переход по клику из `AttachedDocCard` на страницу документа. Маршруты
  реально существуют (`ff/fbs`, `ff/inbound`, `ff/mp-shipments`), но
  открывающие эти документы экраны сегодня используют внутренние состояния
  для выбора текущей поставки/заказа. Мы передаём id как query-параметр
  `?open=...`; принимающая сторона его игнорирует до отдельной задачи.
  То есть навигация уходит на список — не на конкретный документ.
  Поднимать это в отдельную мелкую задачу («экраны документов должны
  открывать сущность по `?open=id`») будет проще.
* полноценная страница `ff/chat` глазами оператора. Собрана и собирается,
  но без ручной проверки в браузере не могу сказать, красиво ли выглядит
  на 1440. Функционально работает поверх тех же endpoint'ов, что и диалог.
* добавление кнопки «Написать сообщение» на страницу приёмки, разгрузки
  МП и на карточку заказа FBS. Механически это одна и та же строка кода —
  подключить `ChatOpenButton` с соответствующей `attached_document`. В
  этом коммите ограничился одним самым очевидным местом (рабочее
  пространство поставки FBS), чтобы не расползаться по чужим экранам без
  явной постановки.
* биллинг / лимиты хранилища вложений. В коде стоит лимит 25 МБ на файл
  (`MAX_ATTACHMENT_BYTES`) и 10 вложений на сообщение. Не тарифицируется
  отдельно, потому что владелец такого требования пока не давал.

## Итог

Ветка `feat/wms397-chat-mvp`, HEAD `346f6a51`, четыре последовательных
коммита от `71c903ca`:

1. `71c903ca` — модели и миграция.
2. `d16e8589` — сервисный слой с проверками прав и идемпотентностью.
3. `d73c05f0` — REST-эндпоинты.
4. `b547f360` — тесты (`test_chat_api.py`, 9 сценариев) + правка
   партиционного индекса на SQLite.
5. `346f6a51` — фронтенд: экран `ff/chat`, диалог, композер, кнопка
   на рабочем пространстве FBS.

Ветка готова к пушу на origin. Пуш не выполнен автоматически — оставлено
на явное распоряжение владельца, как принято в проекте.
