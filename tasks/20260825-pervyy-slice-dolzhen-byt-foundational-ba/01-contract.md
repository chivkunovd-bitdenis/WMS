# CALL74 · Контракт S-32: подключение Ozon в существующих настройках селлера

Статус: архитектурный контракт до production-разработки. Этот документ не является кодом, макетом нового экрана или доказательством работающей интеграции.

## Нормативная рамка и доказательства

- Владелец требует встраивать Ozon в текущий WMS и запрещает менять экран или физический процесс без доказанного обязательного отличия: `tasks/ozon-module-20260824/OWNER_FINAL_PROMPT.txt`.
- Практический контракт принят 44/44: Ozon подключает seller owner/admin только в существующем `/seller/settings`; в S0 один active account на `(seller, marketplace)`, но backend должен быть account-scoped; новая роль, permission, страница, вкладка, modal, workspace или dashboard запрещены: `tasks/ozon-module-20260824/OWNER_PRACTICAL_PROCESS_QUESTIONS.md`, вопросы 1–5.
- Итоговый ledger разрешает использовать только 857 доказанных строк; 193 `BLOCKED` не создают полей, controls или процессов: `tasks/ozon-module-20260824/LEAD_PROCESS_FAILURE.md`.
- Принятое research подтверждает обязательную пару заголовков `Client-Id` + `Api-Key`, существование read-only `POST /v1/seller/info` с пустой request shape и ноль выполненных provider calls. Возможности конкретного аккаунта, expiry и вложенная семантика ответов не доказаны: `docs/runs/ozon-module-20260824/ROOT_ACCEPTED_OPERATIONAL_RESEARCH.json`, `tasks/ozon-module-20260824/operational-research/OZON_RESEARCH_UNKNOWN_LEDGER.md`, `tasks/ozon-module-20260824/operational-research/OZON_READ_ONLY_CAPABILITY_EVIDENCE.json`.
- Текущий код S-32 показывает WB-card и карточку Честного Знака только при `permissions.settings`; WB-card уже имеет состояние наличия ключа, замену и ручную синхронизацию: `frontend/src/screens/v2/SellerSettingsScreen.tsx`.
- Backend WB уже даёт нужные паттерны доступа, tenant-проверки, маски наличия и Fernet-шифрования, но его таблица и API WB-specific и остаются без изменений: `backend/app/api/wildberries_integration.py`, `backend/app/services/wildberries_credentials_service.py`, `backend/app/services/integration_fernet.py`, `backend/app/models/seller_wildberries_credentials.py`.

## Primary user и его работа

Primary user — владелец кабинета селлера или сотрудник этого же селлера, которому уже выдан permission `settings`. Его работа в этом slice — один раз безопасно связать Ozon account с текущим WMS seller, затем видеть, действительно ли сохранённая пара ещё проходит проверку. Он не управляет здесь остатками, заказами, FBS-этапами или отгрузкой: эти операции принадлежат другим существующим поверхностям и не нужны для работы «подключить аккаунт».

FF admin не является пользователем этой карточки. Его административная роль не даёт доступа к секретам seller connection. Это сохраняет принятый actor split: seller owner/admin обслуживает connection, FF admin позже работает с общим FBS pool и publication только на существующих FF-экранах.

## Нормальный процесс шаг за шагом

1. Пользователь с permission `settings` открывает привычный `/seller/settings`. Он остаётся на том же экране, потому что его задача относится к настройкам существующего seller, а не к отдельному Ozon workspace.
2. В текущей зоне marketplace integrations сразу после неизменённой WB-card и перед неизменённой карточкой Честного Знака он видит компактную карточку `Ozon`. Такое соседство позволяет обслуживать обе marketplace connections в одном месте и не переносит пользователя в новую навигацию.
3. Если Ozon не подключён, внутри самой карточки видны ровно два обязательных поля: `Client-Id` и password-поле `Api-Key`, а также кнопка `Подключить`. Account selector не показывается: S0 разрешает один account на marketplace для seller, поэтому выбор не является пользовательской работой.
4. Пользователь вводит оба значения и нажимает `Подключить`. WMS сначала выполняет единственную read-only provider-проверку `POST /v1/seller/info`; это нужно, чтобы не сохранить заведомо неверную пару и не создавать никакого Ozon business state.
5. Только после успешного 2xx WMS сохраняет account в primary S0 slot, шифрует `Api-Key`, очищает оба поля формы и показывает `Подключено` и время последней успешной проверки. Raw `Api-Key` и raw `Client-Id` обратно не показываются: для работы пользователя достаточно знать, что текущий seller подключён; повторная выдача идентификаторов увеличила бы риск утечки.
6. В подключённом состоянии доступны три точечных действия в той же карточке: `Проверить подключение`, `Заменить данные`, `Отключить`. Проверка повторяет только read-only вызов; замена раскрывает два поля inline в этой же карточке; отключение раскрывает inline-подтверждение, а не modal.
7. При успешной замене старая пара атомарно заменяется новой. При любой ошибке проверки candidate-пары старая рабочая пара остаётся неизменной, потому что пользователь пытался обновить connection, а не отключить действующую интеграцию.

## Ошибки и частичные состояния

- `Client-Id` пуст: поле получает текст `Введите Client-Id.`, provider call и запись в БД не выполняются.
- `Api-Key` пуст: поле получает текст `Введите Api-Key.`, provider call и запись в БД не выполняются.
- Ozon отвечает 401/403 на read-only validation: карточка показывает `Ozon не подтвердил Client-Id и Api-Key. Проверьте оба значения.` Candidate не сохраняется; прежняя пара, если была, остаётся рабочей записью без изменения статуса.
- Сеть, timeout, 429 или 5xx: карточка показывает `Не удалось проверить подключение Ozon. Сохранённые данные не изменены; попробуйте ещё раз.` Это частичное состояние «проверка сейчас недоступна», а не утверждение, что credential неверен.
- Stored-пара перестала проходить ручную проверку: WMS фиксирует status `invalid`, время и безопасный error code; карточка сохраняет действия `Заменить данные` и `Отключить`. Секрет и provider response не показываются.
- Stored-пару сейчас нельзя проверить из-за transport/rate limit/provider 5xx: status `unavailable`; это не переписывается в `invalid`, чтобы оператор не сделал ложный вывод о ключе.
- Двойной click или повтор того же `PUT`: итогом остаётся одна primary account row; кнопка блокируется на время запроса, а replay не создаёт второй account.
- Отключение: inline-подтверждение защищает от случайного удаления. Повторный `DELETE` также успешен и не создаёт ошибку.
- Пользователь без `settings`, другой seller, другой tenant или FF admin получает 403/404 fail-closed; наличие account не раскрывается.
- `last_sync`, `last_sync_error` и `expires_at` показываются только когда соответствующий факт реально записан доказанным producer. В этом foundational slice producer синхронизации и доказанного expiry нет, поэтому этих строк в карточке нет.

## Граница WMS, Ozon и ручных действий

### WMS

WMS проверяет текущего пользователя и effective seller, валидирует непустые inputs, делает один read-only account request, шифрует секрет, хранит tenant/seller/account scope и безопасные audit/status поля, возвращает только публичный status. WMS не использует сохранённую пару для stocks, orders, products, FBS/FBO, labels или sync в этом slice.

### Ozon

Ozon принимает `Client-Id` и `Api-Key` только в заголовках read-only `POST /v1/seller/info` и отвечает HTTP-status. WMS не интерпретирует недоказанные nested response fields, не хранит response body и не делает provider mutation.

### Человек руками

Seller owner/admin сам получает значения в своём кабинете Ozon и вручную вводит их в WMS. WMS и агент не открывают credential cabinet, не выпускают, не ротируют и не отзывают ключ. Если Ozon требует изменить права или перевыпустить credential, это остаётся ручным внешним действием владельца.

## Данные и API

Точный технический контракт расположен в `02-api-data-contract.md`. Пользовательский минимум таков:

- account имеет стабильный внутренний `id`, `tenant_id`, `seller_id`, `marketplace`, скрытый S0 `account_slot=primary`, внешний account identifier и зашифрованный secret;
- API существует только под `/integrations/ozon/self/account` и всегда выводит публичный status без credential values;
- create/update — один idempotent `PUT`; disconnect — idempotent `DELETE`; ручная проверка — `POST .../test-connection`; чтение — `GET`;
- future multiplicity подготовлена account id/slot scope в данных, но S0 route и UI адресуют только `primary` и не показывают selector.

## Переиспользуемые части WMS

- `SellerSettingsScreen` и его существующий conditional block по `permissions.settings`: пользователь остаётся на знакомом экране.
- MUI `Paper`, `Stack`, `TextField`, `Button`, `Alert`, существующие spacing/max-width: новая карточка выглядит как соседняя WB-card, а не как redesign.
- `apiUrl`, `authHeaders` и `readApiErrorMessage`: запросы и понятные ошибки остаются единообразными; `frontend/src/api.ts` включён в границу как shared S-32 file, хотя изменение ожидается только при реальной необходимости.
- `assert_seller_permission(..., PERM_SETTINGS)`, `get_effective_seller_id` и роль `FULFILLMENT_SELLER`: новая permission не появляется.
- `integration_fernet.encrypt_secret/decrypt_secret`: новый криптографический механизм не создаётся.
- tenant-check pattern из WB credentials service: account читается и меняется только после проверки seller в tenant.

Не переиспользуется как storage `SellerWildberriesCredentials`: его WB-specific поля и one-row primary key не дают generic account scope. WB таблица, service, routes, copy, controls и tests не мигрируют и не меняют поведение.

## Варианты и цена

### Вариант A — отдельная `seller_ozon_credentials`, как WB

Цена: минимальная, ориентировочно 5–7 production/test файлов. Быстро даёт один Ozon key на seller, но следующая marketplace или второй account потребуют новой таблицы, новых routes и переноса downstream mappings. Пользователь сейчас не увидит разницы, но данные снова будут привязаны к provider, а foundational цель не будет выполнена.

### Вариант B — generic `marketplace_accounts` с primary S0 slot

Цена: средняя, 10–14 production/migration/test файлов и один аккуратный migration. Пользователь всё равно видит одну компактную Ozon-card, но downstream data уже сможет ссылаться на стабильный account id. Будущий multi-account потребует нового product decision и UI/API, но не перепривязки базовой account identity. Это выбранный вариант.

### Вариант C — общий marketplace integration framework и dashboard

Цена: высокая, затрагивает навигацию, WB API/model, общий settings UX и много regression surfaces. Он создаёт запрещённые screen/tab/dashboard и меняет WB ради будущей абстракции, которой S0-пользователь не просил.

## Выбранное решение и почему

Выбран вариант B: generic account row с provider=`ozon` и скрытым `account_slot=primary`, плюс provider-specific read-only adapter. Он решает реальную работу пользователя — подключить один Ozon account на текущем S-32 — и одновременно делает identity account-scoped для будущих mappings/orders/bindings. UI остаётся provider-specific и компактным; generic capability dashboard не появляется. WB не переносится, потому что сохранение его текущего поведения важнее архитектурной симметрии в этом slice.

## Сознательные non-goals

- Не менять WB-card, WB routes, WB credential table/service, WB sync и copy.
- Не создавать новый screen, route, tab, modal, drawer, workspace, marketplace dashboard или account selector.
- Не менять Честный Знак, FBS stages, подбор, сортировку, ячейки, упаковку, короба, отгрузку, FBO, возвраты, stock pools, allocations и labels.
- Не синхронизировать Ozon products/orders/stocks, не делать stock write и любую provider mutation.
- Не реализовывать expiry, capabilities, warehouse/delivery/return-point discovery или аналитику: факты BLOCKED.
- Не мигрировать существующие WB credentials в generic table и не делать speculative backfill.
- Не открывать Ozon credential cabinet и не управлять ключами за пользователя.

## Риски и меры

- Риск утечки: secret может попасть в response, log или test snapshot. Мера: Pydantic outputs без credential fields, redacted error mapper, запрет логирования request headers/body, assertions по response/log и encrypted-at-rest test.
- Риск cross-tenant доступа: account id или seller relation может обойти tenant. Мера: self routes не принимают seller/account id; service всегда фильтрует `tenant_id + seller_id + marketplace + primary slot`.
- Риск двойной записи от повторного click. Мера: уникальный key primary slot, transaction/lock и idempotent PUT/DELETE.
- Риск ложного удаления рабочей пары при неудачной замене. Мера: candidate сначала проверяется снаружи транзакции, persistence выполняется только после success.
- Риск ошибочно считать provider outage неверным credential. Мера: раздельные `invalid` и `unavailable`, разные тексты и HTTP codes.
- Риск незаметной регрессии WB/S-32. Мера: существующий WB Playwright path остаётся и дополняется проверкой неизменных testids/copy/actions.
- Риск принять недоказанный response field за capability. Мера: validation зависит только от method/path/read-only classification и HTTP class; response body не парсится.

## Вопросы владельцу без нового gate

Эти вопросы не блокируют developer после принятия контракта ведущим; зафиксированные defaults действуют, пока владелец явно их не изменит.

1. Нужно ли когда-либо показывать masked Client-Id после подключения? Default S0: нет, только `Подключено`, чтобы не распространять account identifier.
2. Нужно ли физически удалять audit row при отключении? Default S0: нет; ciphertext очищается, row сохраняет кто/когда отключил connection.
3. Нужен ли отдельный текст о правах ключа Ozon? Default S0: нет, потому что точный scope/capability конкретного аккаунта BLOCKED; показывается только результат read-only connection validation.

## Точное задание на кликабельный React-прототип

Сделать отдельный, не-production clickable prototype только существующей зоны S-32. Не менять application code, routes или shared shell.

1. Воспроизвести текущий `/seller/settings`: заголовок `Настройки`, неизменную WB-card с существующими testids/copy/actions и неизменную карточку Честного Знака. Между ними вставить Ozon `Paper` с тем же `maxWidth: 720`, padding и вертикальным rhythm.
2. Реализовать fixture states: `disconnected`, `editing`, `checking`, `connected`, `invalid`, `unavailable`, `disconnect-confirm`. Не добавлять tabs, modal, drawer, toast center, dashboard tiles или account selector.
3. `disconnected`: inline `Client-Id`, password `Api-Key`, primary `Подключить`. Empty-submit показывает точные field errors из этого контракта без смены страницы.
4. `checking`: inputs и buttons disabled, на primary action spinner и текст `Проверяем…`; это объясняет пользователю, что WMS ждёт read-only confirmation, а не уже сохранил connection.
5. `connected`: status `Подключено`, `Последняя проверка: <дата/время>`, buttons `Проверить подключение`, `Заменить данные`, `Отключить`. Не показывать Client-Id/API key, last sync или expiry.
6. `editing`: два поля раскрываются внутри той же card; `Сохранить новые данные` и `Отмена`. Failure возвращает точный error, сохраняет connected summary прежней пары.
7. `invalid` и `unavailable`: один компактный `Alert` внутри card с точными текстами; actions замены/проверки остаются доступны. Не добавлять capability list.
8. `disconnect-confirm`: inline строка `Отключить Ozon от этого селлера?` и buttons `Отключить`/`Отмена`; после confirm — `disconnected` и success `Ozon отключён.`
9. Permission fixture `settings=false`: целиком отсутствуют WB/Ozon/Честный Знак cards, как в текущем S-32; staff-section сохраняет своё существующее conditional behavior.
10. Добавить стабильные prototype testids с prefix `seller-settings-ozon-`: `card`, `client-id`, `api-key`, `connect`, `status`, `test`, `edit`, `disconnect`, `disconnect-confirm`, `error`. Все клики работают только на local fixture state, без network/provider calls.

Прототип принимается только если он демонстрирует перечисленные transitions на одном S-32 и визуально не меняет WB/Честный Знак. Скриншот, статический макет или новый Ozon screen не засчитываются.
