# WMS-417 — сверка Opus5 findings с текущими worktrees

10.09.2026 09:27МСК. Координатор прочитал четыре отчёта целиком (chat, warehouse, auth_audit, mobile_update). Их исходный снимок05:58UTC не равен текущему HEAD/dirty. Это протокол разбора review, не новый бэклог. Все задачи остаются в каноне. Worker DONE не означает приёмку. Stock_merge/cancel_identity добавить после получения.

## Chat — владелец прежний CLI thread01a08850 / PID86312

- 1 (основной чат) — устарело: обе сортировки chat_service:211/229 уже kind.desc().
- 2 (автозагрузка файлов) — исправляется текущим автором: root перечитал ChatAttachmentView, теперь обычный файл ждёт клика (`!is_image && attempt===0`), картинка предзагружается. Есть отмена fetch и revokeObjectURL. Независимо в браузере root ещё не проверял это изменение.
- 3 (N+1 карточек при poll), 4 (висящие draft attachments), 5 (GET ensure-main цикл), 6 (content_type не ограничен) — актуальные участки подтверждены чтением chat_routes/chat_service. Владельцу разобрать до приёмки. Снимок не даёт права убрать ACL: если оптимизировать карточки, сохранить tenant/seller/participant/document права.
- 7 (effective seller) — нужна сверка с deps. У FF get_effective_seller_id возвращает user.seller_id, а не query-selected seller; считать межселлерную утечку недоказанной, но граничный тест нужен.
- 8 (время/порядок) — автор уже исправил и сообщил14passed на обеих БД; окончательный SHA ещё не получен.
- 9 (молчаливый forbidden), 10 (точные переходы), 11 (докстринги/extra participants), 12 (неиспользуемые части) — остаются у владельца для сверки. Автор уже проверил actual supply/inbound/MP/outbound в браузере, но весь пункт10 этим автоматически не закрыт.

## Warehouse — владелец прежний CLI thread01a0885c-a8fc / PID86313

Автор уже прочитал свой Opus5 review и исправляет актуальное. Root перечитал текущие функции: вместо empty_containers используется empty_places; _clear_empty_confirmation вызывается из save, move, found, manual. Поэтому пункты2/5 не переносить на текущий код без проверки.

- 1 — старое ожидание container_has_no_stock заменено автором под разрешённый пересчёт пустой тары; нужна законченная scoped проверка.
- 2/5 — новый empty_places/_clear_empty_confirmation закрывает прежний пробел по коду; ждём тесты/экран.
- 3/6/8 — автор подтвердил и исправил: исключение inbound-тары из удаления по cell, отказ переноса в занятый live destination, comment conflict до mutations; root видит соответствующие проверки795/808/512.
- 4 — массовое обнуление сохраняется с явным предупреждением о всём выбранном месте; не выдавать прежний текст «нетронутые» за текущий контракт. Проверить сценарий оператора до приёмки.
- 7 WMS179 — приёмка обязана сообщать настоящий dirty, общие App/FfSupplies сейчас принадлежат chat. Передать после завершения текущего writer.
- 9 — rollback при commit=False в warehouse_map требует проверки автором; 10 — pytest asyncio_mode=auto в проекте, отсутствие декоратора само по себе не означает skip.
- Дополнительные156/174/177 — проверить видимость/привязку акта, полный ответ damaged-box и переходы/reload. Отсутствие API/App в review packet не доказательство отсутствия реализации.

## Auth/audit — владелец координатор

- 1 ports — предположение о production compose опровергнуто live docker inspect: api/db/redis PortBindings={}, web8088 и seller15174 открыты. Dev compose действительно имел открытые defaults5433/16379/18080; coordinator сделал loopback defaults. Production8088 меняется на проверенный private bridge172.18.0.1; слепой127.0.0.1 отклонён, так как внешний Caddy контейнерный. Конфигурация пока не применялась.
- 2 actor — подтверждено: dict берёт последний Authorization, HTTPBearer первый. Исправление dirty в wms056: middleware только ограничивает lifetime, actor задаётся в get_current_user после проверки пользователя/tenant/subscription; повторный JWT parse удалён. Добавлен HTTP replay с двумя валидными заголовками разных учёток.
- 3 GUC — не подтвердилось. Реальная migration document_event проверяет GUC в триггере UPDATE fbs_supply, чтобы не дублировать system event. Она НЕ запрещает INSERT document_event. Добавлять set_config в явную запись без причины не требуется.
- 4 source — подтверждено и исправлено dirty: известный acting_user даёт SOURCE_USER в create/update staff. Прямой service call без HTTP context покрывается тестом.
- 5 grant-more-than-own — рекомендация меняет смысл существующего полномочия управления сотрудниками. Текущий can_manage_ff_staff явно разрешает settings, а исходный F14 контракт называет его «Настройки и сотрудники». Самостоятельно не сужать это право до набора рабочих операций сотрудника. Для WMS325 это не доказанный новый обход авторизации; при отдельном изменении политики нужен owner contract, не молчаливое изменение доступа.
- 6 proxy — подтверждено и исправлено конфигурацией до deploy: узкий FORWARDED_ALLOW_IPS, Caddy strict trusted proxies и verified client header.9 scoped tests passed включая ASGI two-client/spoof, caddy2.11.2 adaptPASS. Распределённый brute-force по одной почте остаётся ограничением per-IP limiter, канон270 требует доказуемый rate limit, не обещает полного anti-DDoS.
- 7 saturation — намеренный fail-closed при bounded memory. Фиксированные hash buckets из предложения не гарантируют отсутствие denial и создают коллизии разных клиентов. Не подменять это обещанием неуязвимости; high-volume защита отдельно не доказана.
- 8 missing decorators — не дефект текущего запуска:9passed реальных тестов, asyncio_mode=auto.
- Дополнительно: staff creation и packaging rate writers реально есть вне неполного packet. Tie-break id.desc добавлен в историю. Request-password-reset теперь использует тот же limiter ДО scheduling, тест не отправляет почту.

## Mobile — владелец прежний CLI thread01a0884d / PID87082

Root читает только безопасные текущие source-файлы и review. PROGRESS и raw mobile events исключены.

- 1.1 KIZ500 и отсутствиеcommit — не подтвердились описанным сценарием: commit_kiz_pairs:1454-1492 сам ловит FbsKizError и IntegrityError, возвращает error rows, commit/rollback делает внутри. Нельзя добавлять второй commit или менять batch semantics по отсутствующему в packet сервису.
- 1.2 Ozon потеря транзакции — опровергнуто: sync_ozon_orders:962 и sync_ozon_order_statuses:1056 явно commit до return. Route не обязан дублировать их.
- 1.3 pending delivery — актуальный keepRequest всё ещё default-discard для известных4xx вне короткого списка; владельцу проследить meta_validation_fail/checkpoint и сохранять ключ при неопределённом результате. Не проверять на защищённой supply и клиентских данных.
- 1.4 Ozon missing endpoints — снимок устарел: текущие FbsApi/FbsModels уже имеют retry-qr, order_product_ids, ozon_assembled; ViewModel сканирует positions. Это не device proof, автор продолжает emulator flow.
- 1.5 fallback available — проследить service+API; имя optional не доказывает достижимый None. Не подставлять gross при неизвестной доступности.
- 1.6 scope leak — описанная seller-утечка не подтверждена: require_fbs_operator_access=require_packaging_access допускает FF, не seller. Query-priority сам по себе в этом FF-контуре не межселлерная утечка. Граничные тесты сохранить.
- 1.7 scanBox retry — актуально: root прочитал текущую функцию, начало без refresh; владелец исправляет reread при повторе.
- 1.8 tape retry / 1.9 print-view cleanup и sort — владелец сверяет по полным сервисам/актуальному Kotlin. Повторные коды/stock эффекты не приписывать без трассы.
- 401/412: актуальный Kotlin впереди старого канона, но app-update-button/подпись/сохранность serverPIN/document и долгий resume отдельно доказать.402 print-agent и физическая печать отдельно, без нового журнала.

Следующий шаг координатора: получить законченные SHA и owner triage, передать оставшиеся актуальные пункты в следующий resume тех же threads после их штатного завершения. Вторые writers поверх живых процессов не запускаются. Выпуск до сверки актуальных P1/P2 запрещён.
