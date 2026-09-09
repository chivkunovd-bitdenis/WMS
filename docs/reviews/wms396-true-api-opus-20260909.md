# WMS-396: Opus CLI max, True API review 09.09.2026

Reviewed e57401e0 against production054897e2; source integrated as5457d187/7801f611.
Actual reviewer claude-opus-4-7, effortmax, session e4e0a5b1-2d0b-42bc-8dd9-3b919ef15f6b.
CLI success, 31 turns, 695582 ms. Provider metadata also records a 21-output-token
Haiku auxiliary call; the review response and reasoning are Opus. No code or
credentials were changed by this review.

Coordinator interpretation: no confirmed code blocker remains; positive live
True API acceptance is still missing and must not be claimed complete. Process-local
pacing is an explicitly open limitation. The review's suggestion to set Celery
concurrency=1 is NOT applied: setting it on the shared worker would serialize other
warehouse tasks too. A task name alone does not create a separate worker/queue.
No token issuance, signing-key changes or credential updates are authorized by
this report. Review recommendations are evidence for review, not instructions.

The exact final review text follows.

---

Проверил разбор изменения `e57401e0` (True API приёмки) относительно продакшн-точки `054897e2` только чтением кода и тестов. Реальных запросов к markirovka.crpt.ru не делал, стенд/браузер не открывал, секреты не читал и не расшифровывал — оценка ниже строится на исходниках, а не на живом ответе провайдера.

## Итог

**Reviewed SHA: `e57401e0` (ветка `codex/wms396-true-api`, backend worktree). Сравнение против прод-базы `054897e2`.**

Блокеров в самом коде True API-адаптера и в правке гонки я не нашёл. Отдельно от кода остаётся ровно один настоящий блокер выпуска — отсутствие живой проверки токена/КМ; про него ниже отдельным пунктом.

## Что проверено и подтверждено

- **Контракт `/cises/info` и `/cises/check`** — узкий адаптер `backend/app/services/true_api_marking_check.py:1-183`. `info` посылает массив «коротких» КИ (AI01+AI21 до первого GS), `check` — оригинальные полные КМ в `codes`. Сохранённые байты и `\x1d` не переписываются. Base URL `https://markirovka.crpt.ru/api/v3/true-api`, batch до 1000, интервал 2 с. Совпадает с [официальным описанием True API](https://docs.crpt.ru/gismt/True_API/) в `docs/reviews/wms396-live-check-readiness.md:15-23,45-51`.
- **Смешанный ответ crypto** (`parse_crypto`, `true_api_marking_check.py:50-73`). Зелёный только при `result: bool` явно и одном из двух форматов: `quantity == len(codes)` без `codes` (агрегат) или `result: false` + список невалидных `codes`. Любая двусмысленность (`quantity: True`, `quantity: 1`, `result: 1`, дубликаты, чужой КИ, невозможность однозначно отобразить короткий КИ на единственный полный КМ) → все `None`, значит `unavailable`. Тест `test_crypto_aggregate_requires_complete_unambiguous_answer` и `test_crypto_short_invalid_code_cannot_identify_two_different_signatures` (`backend/tests/test_true_api_marking_check.py:26-52`) покрывают эти ветки.
- **Строгий fail-closed для «introduced»** (`interpret`, `true_api_marking_check.py:93-128`): зелёный ставится только при `outer == "INTRODUCED"` и `verified is True` (не `1`, не строка), при пустом `ogvs` и отсутствии `errorCode`/`errorMessage`. Тесты `test_status_and_crypto_are_separate_required_confirmations` и `test_info_reordering_duplicates_unknown_and_per_code_errors` (`backend/tests/test_true_api_marking_check.py:55-93`) закрывают это.
- **Смешанные ответы info по позициям и дублям** (`parse_info`, `true_api_marking_check.py:76-90`) — сопоставление по `requestedCis`==`cis`, отсутствующие/дублирующиеся ключи выкидываются. Проверено.
- **Изоляция tenant/seller** — в основном загрузчике (`inbound_marking_service.py:469-484`) `MarkingCodeEvent.tenant_id == tenant_id, MarkingCode.tenant_id == tenant_id`; `get_cz_token_for_seller` (`seller_marking_credentials_service.py:227-244`) дополнительно фильтрует по `Seller.tenant_id` и `SellerMarkingCredentials.tenant_id`. Двойная преграда. Расшифровывается только `cz_token_enc`; OMS/marketplace секреты не трогаются. Тест `test_credential_scope_and_only_cz_is_decrypted` (`backend/tests/test_true_api_marking_check.py:174-189`) явно проверяет невозможность прочитать OMS/MP и правильный tenant-scope.
- **HTTP всегда вне DB-транзакции** — `_run_check_job` открывает `httpx.AsyncClient` вне сессий (`inbound_marking_service.py:450`), каждый шаг цикла явно закрывает `SessionLocal()` до `await true_api.check_batch(...)`. Никаких открытых сессий во время `_post`.
- **Таймауты** — клиент строит с `timeout=10.0` (`inbound_marking_service.py:450`). Единый на все запросы, что для двух коротких вызовов True API нормально.
- **Отсутствие фоновых авто-повторов** — при 429/401/451/offline/malformed `check_batch` возвращает `unavailable` для всей пачки, worker дописывает статусы в event и в следующей итерации фильтр `pending` пропускает эти события. Никакого автопрогона. Тест `test_http_short_info_full_crypto_and_truthful_unavailability` (`backend/tests/test_true_api_marking_check.py:96-135`) параметризован на 401/429/451/offline/malformed/missing и проверяет ровно эту семантику.
- **Отсутствующий токен и битые КМ никогда не идут в сеть** (`test_missing_token_or_unprojectable_code_never_calls_http`, `backend/tests/test_true_api_marking_check.py:138-146`) — при пустом токене или отсутствии GS-границы результат складывается локально, HTTP не поднимается.
- **Удалённые/добавленные во время проверки коды** — drain-loop (`inbound_marking_service.py:451-513`) на каждой итерации перечитывает pending-attachments и через JOIN на `MarkingCode` отсекает удалённые (нет записи в `marking_codes` — JOIN схлопывает). Регресс покрыт `test_deletion_during_check_and_rescan_are_drained_without_stuck_job` (`backend/tests/test_inbound_marking.py:603-648`).
- **Никакого влияния на склад/резерв/упаковку/UI** — код меняет только `MarkingCodeEvent.meta_json.cz_check`. Ни `MarkingCode.status`, ни `InventoryMovement`, ни `PackagingTask*` не трогаются. Тест `test_background_check_is_idempotent_and_has_no_stock_effect` (`backend/tests/test_inbound_marking.py:127-167`) явно проверяет `count(InventoryMovement) == 0` и сохранённый lifecycle `code.status == "applied"`. Правок фронта в диффе нет.
- **Фикс гонки от Astra** — критичная часть. Правки в `_run_check_job` при сохранении ответа (`inbound_marking_service.py:491-513`): сначала `_request(session, lock=True)` (тот же порядок, что и `schedule_check`), затем `session.get(BackgroundJob, job_id, populate_existing=True)`, затем `MarkingCodeEvent … with_for_update`. Порядок совпадает с `schedule_check` (`inbound_marking_service.py:400-433`), поэтому просроченный worker гарантированно ждёт коммит замены на строке заявки, а после этого перечитывает job уже со свежим `status="failed"` и выходит. Регресс покрыт настоящим PostgreSQL-тестом `test_expired_worker_cannot_overwrite_retry_while_saving_response` (`backend/tests/test_true_api_marking_check.py:233-329`): pytest.skip на SQLite, реальное чтение `pg_stat_activity.wait_event_type='Lock'`, две сессии, отдельная монки на `check_batch` — контроль, что финальный ответ приходит от повторной проверки, а не от протухшего worker'а.

## Явно принятое ограничение — процессный лимит частоты

`_PACING = MarketplaceBackoff()` в `true_api_marking_check.py:21` и `_blocked_until: dict[str, float]` в `backend/app/services/marketplace_provider.py:66-82` — это словарь в памяти одного процесса. `docker-compose.prod.yml:87-106` запускает `celery_worker` командой `celery -A app.celery_app worker --loglevel=info` без ограничения concurrency, то есть у Celery по умолчанию N=CPU процессов, каждый со своим `_PACING`. При параллельных задачах от разных worker-процессов интервал 2 с между запросами по одному токену селлера **не гарантируется**.

**Реальный эффект на выпуск**: сервер ЧЗ при превышении вернёт 429, `check_batch` уже переводит это в `unavailable` с человеческой причиной «ограничил частоту запросов», в БД пишется `unavailable`, следующей итерации по этому событию не будет (`pending` фильтр не пропустит), автоматических повторов нет. То есть **никакого ложно-зелёного, никакого штурма ЧЗ**. Оператор видит «недоступен» и жмёт повтор руками. Данных это не портит.

Что реально плохо: под нагрузкой с несколькими одновременными приёмками одного селлера будет больше `unavailable`-ответов, чем при общем ограничителе. Это UX-деградация, а не потеря товара. Минимальный безопасный шаг, если это станет практической проблемой на живом токене: включить в Celery `--concurrency=1` для `wms.inbound_marking_check` (`backend/app/tasks/background_jobs.py:104-108` — очередь по умолчанию), либо явно закрепить эту задачу за отдельным worker-контейнером с `--concurrency=1`. Ни новых таблиц, ни Redis-лимитеров, ни счётчиков заводить не нужно, и это остаётся конфигурацией деплоя, а не кодом. Как блокер релиза сейчас **не квалифицирую**, но фиксирую как принятое ограничение.

## Не проверено — настоящий блокер валидации

- **Живой позитивный/негативный ответ True API** с валидным JWT участника не воспроизведён в этой ветке. Раздел `docs/reviews/wms396-live-check-readiness.md:31-34` подтверждает, что для точного QA-селлера `50110328…` в tenant `9c31f3f4…` в БД стенда `has_configured_cz_token=false` — то есть даже одна разрешённая проверка сейчас невозможна без выданного участнику токена с подключённой товарной группой. Значит:
  - Правильность обработки реального 200 ответа `/cises/info` и `/cises/check` не подтверждена натурой; кодовая часть корректна, но контракт я сверял по документации, а не по ответу production.
  - Валидность конкретного 401 (истёкший/чужой токен) не проверена руками.
  - HTTP 451 от `mobile.api.crpt.ru`, который зафиксирован ранее, отношения к True API не имеет (это другой хост и другой API).

Это **блокер выпуска реальной приёмки**, но не блокер кода. Устраняется вне кода: выдать зарегистрированному участнику JWT с нужной товарной группой, сохранить `cz_token_enc` через существующий эндпоинт `patch_seller_credentials`, прогнать один разрешённый КИЗ, руками открыть экран приёмки и увидеть `introduced`/`problem`/`unavailable` из настоящего ответа. Только после этого можно утверждать, что интеграция работает end-to-end. Правки в самом коде ради этого не нужны.

## Мелкие наблюдения (не блокеры)

- `interpret` даёт человеческую причину только для `errorCode` 401 и 404 (`true_api_marking_check.py:100-108`). Для, например, 500 в per-code теле status останется «unavailable», а reason — дефолтным «Честный знак не подтвердил статус». Не опасно (fail-closed), но оператору менее информативно. Минимальная правка при желании — добавить ещё одну ветку `elif str(error).startswith("5"): answer["reason"] = "Честный знак вернул временную ошибку…"`. Не обязательно к релизу.
- Заголовок `Retry-After` на 429 не парсится (`true_api_marking_check.py:131-144`). Согласуется с явной установкой «нет автоматических повторов». Оставлять как есть корректно.
- `unavailable()` пишет поле `provider: "true_api"` (`true_api_marking_check.py:24-33`), в UI это поле не выведено (`inbound_marking_service.py:86-99` возвращает только `cz_status`, `cz_reason`, `outer_status`, `checked_at`). Косметика, безопасно.
- Ветка `if not (path == "/cises/info" and response.status_code == 404)` (`true_api_marking_check.py:142`) сознательно не поднимает 404 для info, чтобы разобрать per-code `errorCode`. Соответствует документу.

## Финальный вердикт

Reviewed SHA: **`e57401e0`** против прод `054897e2`.

- Правка гонки протухшего worker'а — **корректна и покрыта настоящим PG-регресс-тестом**; без неё «introduced/старый ответ» действительно затирал бы pending повторной проверки.
- Адаптер True API — **строгий контракт, fail-closed на всём неизвестном, HTTP вне транзакций, tenant/seller изоляция и раздельное разшифровывание только `cz_token` подтверждены кодом и юнит-тестами**.
- **Блокеров в коде не вижу.** Единственный блокер выпуска — внешний: не доказана валидность реального JWT участника ЧЗ и живой ответ `/cises/info`+`/cises/check` в running-контуре. Пока это не сделано, зелёная приёмка КМ live-путём не может быть заявлена. Кодовой правки для снятия этого блокера не требуется.
- **Ограничение process-local pacing** — реальное, но не портит данные и не даёт ложно-зелёного; при первой практической проблеме на живом токене минимальный шаг — `--concurrency=1` у Celery-очереди `wms.inbound_marking_check`, без новых сущностей.

Живьём в браузере и вживую в API я эту ветку не проверял и это специально не выдаю за проверенное.
