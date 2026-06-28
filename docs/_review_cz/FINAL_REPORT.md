# Код-ревью «Честный Знак» — финальный отчёт

## Вступление

**Что ревьюилось.** Модуль маркировки «Честный Знак» (CZ) в WMS: импорт КМ, пулы по GTIN, печать/перепечатка/замена, scan-print, verify-pair, прогноз/low-stock, учётки селлера (токены ЧЗ/СУЗ/МП), уведомления. Диапазон `4e82c6b..HEAD` (21 коммит `feat(cz)`, ~125–144 файла, +19248/−687).

**Как.** Два слоя: (1) автоматические гейты — `ruff` / `mypy` / `pytest` (журнал `docs/CHESTNY_ZNAK_REVIEW_RU.md`); (2) многоагентное ревью по 8 измерениям (инварианты, конкурентность, миграции, мультитенант+authz, контракты API, безопасность кредов, фронт, тесты) с состязательной верификацией находок. Все 8 файлов измерений получены и непустые — пробелов в самом ревью нет.

**Общий вердикт: NO-GO до фикса блокеров.** Логика в целом рабочая (pytest: 45 passed), мультитенантность и authz — чисто (0 находок CRITICAL/HIGH), модель безопасности секретов в основе верная. Но есть **6 блокеров**, которые нельзя выпускать в прод: миграция, падающая на PostgreSQL; небезопасный дефолт ключа шифрования; нарушение доменного инварианта И2 (молчаливая автопривязка по GTIN); рантайм-500 вместо 404; неатомарная массовая печать; отсутствие `SKIP LOCKED`. После их устранения — GO с условиями.

### Сводная таблица

| Измерение | #находок | Макс. severity | Статус |
|---|---|---|---|
| Инварианты домена | 6 | 🔴 CRITICAL | Есть блокеры (2 CRIT, 2 HIGH, 2 MED) |
| Конкурентность | 5 (+1 контр) | 🔴 HIGH | Есть блокеры (2 HIGH, 3 MED) |
| Безопасность кредов | 3 | 🔴 HIGH | 1 блокер (1 HIGH, 2 LOW) |
| Миграции | 3 | 🔴 HIGH | 1 блокер (1 HIGH, 2 LOW) |
| Контракты API | 6 | 🟠 HIGH | Важное+мелочи (1 HIGH, 3 MED, 2 LOW) |
| Тесты | 6 | 🟠 HIGH | Важное+мелочи (1 HIGH, 2 MED, 3 LOW) |
| Фронтенд | 2 | 🟡 MEDIUM | Мелочи (1 MED, 1 LOW) |
| Мультитенант / authz / IDOR | 2 | ⚪ LOW/INFO | ЧИСТО (test-only) |
| Гейты (ruff/mypy/pytest) | 14 | 🔴 (см. И2-баг) | ruff 4 + mypy 10; CI красный |

---

## 🔴 Блокеры (нельзя в прод/мёрж пока не починено)

1. **Миграция `print_templates.is_default` падает на PostgreSQL**
   Источник: миграции. `backend/alembic/versions/20260626_0046_print_templates.py:29`.
   `sa.Boolean()` с `server_default=sa.text("0")` — Postgres не приводит integer-литерал к boolean, `alembic upgrade` на проде упадёт на этой ревизии (потеря деплоя). Единственная миграция с `sa.text("0")`; соседние используют `sa.false()`.
   Фикс: заменить на `server_default=sa.false()`.

2. **Ключ шифрования секретов выводится из публичного дефолтного `jwt_secret_key`, нет prod-гейта**
   Источник: безопасность кредов. `backend/app/services/integration_fernet.py:13-19`, `backend/app/core/settings.py:14-17,33-37`.
   При незаданном `wms_secrets_fernet_key` Fernet-ключ = `sha256(jwt_secret_key)`, а у `jwt_secret_key` дефолт — публичная строка из репозитория. При дефолтном конфиге все токены ЧЗ/СУЗ/МП (`*_enc`) шифруются воспроизводимым из исходников ключом → дамп БД = открытые токены. Enforcement отсутствует, только комментарий.
   Фикс: fail-fast на старте в prod-окружении, если `wms_secrets_fernet_key` не задан или `jwt_secret_key` равен дефолту.

3. **Молчаливая автопривязка товара к коду по GTIN — нарушение инварианта И2**
   Источник: инварианты. `backend/app/services/marking_code_service.py:667-698` (`relink_unlinked_marking_codes`), вызов из `list_inventory` на `:981-982`.
   И2 запрещает угадывать товар по GTIN/названию: связь товар↔код должна быть только ручной (M2M `marking_pool_products`). Здесь `product_id` проставляется автоматически по GTIN и **коммитится в БД при обычном чтении инвентаря**, без действия пользователя.
   Фикс: удалить `relink_unlinked_marking_codes` и вызов из `list_inventory`; остаток выводить через ручную M2M-связь.

4. **`status` query-param затеняет модуль `fastapi.status` → AttributeError/500 вместо 404**
   Источник: инварианты + гейты (mypy `marking_codes.py:721`, подтверждено двумя измерениями). `backend/app/api/marking_codes.py:715` (параметр) и `:721` (использование).
   Параметр `status: str | None` перекрывает импортированный модуль `status`; при ненайденном/чужом пуле `status.HTTP_404_NOT_FOUND` → `AttributeError` → HTTP 500. Маскирует мультитенантную проверку (ветка «чужой tenant → 404» не отрабатывает штатно).
   Фикс: переименовать параметр в `status_filter: Annotated[str | None, Query(alias="status")]` и пробросить в сервис.

5. **`print_all_for_packaging_task` не атомарен: commit на каждую строку → частично отпечатанные задания**
   Источник: конкурентность. `backend/app/services/marking_code_service.py:1536-1567` (цикл) + `:1278` (commit внутри `print_codes_for_packaging_line`).
   Каждая строка коммитится отдельной транзакцией. Ошибка/дефицит на N-й строке оставляет первые строки закоммиченными (коды списаны `STATUS_PRINTED`), задание не завершено, повтор упирается в `already_printed_use_reprint` — невосстановимый частичный результат, потеря/расход КМ.
   Фикс: вынести границу транзакции на уровень `print_all` (один commit в конце); `print_codes_for_packaging_line` без внутреннего commit (флаг или savepoint на строку).

6. **Выдача кодов из пула без `SKIP LOCKED` → ложный дефицит под параллелью**
   Источник: конкурентность (HIGH) + тесты (пробел покрытия, HIGH). `backend/app/services/marking_code_service.py:1211-1223` (`print_codes_for_packaging_line`), тот же паттерн `:2215-2227` (`replace_reprint_request`).
   `FOR UPDATE` + `LIMIT` без `SKIP LOCKED` под READ COMMITTED: два параллельных упаковщика берут одни и те же верхние строки, T2 блокируется и после коммита T1 недобирает N — ложный `shortage` при `allow_partial=False`, хотя свободные коды есть. (Двойной выдачи нет — это плюс.) Сценарий гонки не покрыт тестом (`test_marking_print_pool.py:143` строго последователен).
   Фикс: `.with_for_update(skip_locked=True)` + retry перед возвратом дефицита; добавить тест с `asyncio.gather`.

---

## 🟠 Важное (починить до релиза или сразу после)

1. **`consumption_7d`/прогноз считает копии, а не единицы — занижение прогноза вдвое**
   Источник: инварианты (HIGH). `backend/app/services/marking_code_service.py:1652-1677` (`_pool_consumption_7d_batch`) + событие печати с `copies=2` на `:1267-1275`.
   Расход суммирует `MarkingCodeEvent.copies` (обычно 2 на код), поэтому `forecast_days` занижается вдвое и low-stock даёт ложные срабатывания (нарушение духа И4; сам остаток считается верно).
   Фикс: заменить `func.sum(copies)` на `func.count(func.distinct(code_id))`.

2. **Брак→замена: старый код остаётся `defective`, не доходит до `replaced`**
   Источник: инварианты (HIGH). `backend/app/services/marking_code_service.py:2231-2259` (`replace_reprint_request`).
   Пишется событие `EVENT_REPLACED`, но `old_code.status` остаётся `STATUS_DEFECTIVE` — нелегальный/незавершённый переход машины статусов (DESIGN §5). Счётчик «Брак» в карточке пула завышается заменёнными кодами; рассинхрон журнала и состояния.
   Фикс: после `EVENT_REPLACED` выставить `old_code.status = STATUS_REPLACED`.

3. **`verify_pair_and_apply`: чтение без блокировки → двойное применение + дубль события**
   Источник: конкурентность (MEDIUM). `backend/app/services/marking_code_service.py:2328-2360`.
   Два параллельных скана одной пары читают `status==PRINTED`, оба пишут `STATUS_APPLIED` и два `EVENT_APPLIED`. Нет уникального ограничения на пару (code_id, applied). Идемпотентность применения нарушена.
   Фикс: `.with_for_update()` + перепроверка статуса под локом, либо условный `UPDATE ... WHERE status='printed'` с проверкой rowcount.

4. **Печать/перепечатка не проверяет статус упаковочного задания**
   Источник: инварианты (MEDIUM). `backend/app/services/marking_code_service.py:1113-1289`, reprint-ветка `:1156-1188`.
   Нет проверки `task.status` — можно печатать/резервировать коды для завершённого/отгруженного задания, израсходовав коды «в никуда» (искажение остатка И3). Для сравнения `list_pending_marking_lines` ограничивает `status in (draft, in_progress)`.
   Фикс: guard `if task.status not in ("draft","in_progress"): raise "task_not_active"`.

5. **`approve_reprint_request` пишет `reprinted` без проверки статуса кода**
   Источник: инварианты (MEDIUM). `backend/app/services/marking_code_service.py:2141-2180`.
   В отличие от `replace_reprint_request` (есть страж `STATUS_PRINTED`), здесь код мог стать `applied`/`shipped`/`defective` между созданием заявки и аппрувом — пишется событие, противоречащее состоянию (DESIGN §6 «если ещё валиден»).
   Фикс: симметрично добавить `if code.status != STATUS_PRINTED: raise "code_not_printed"`.

6. **TOCTOU превью↔выдача в `print_all` + расхождение фильтров/двойной счёт по общему пулу**
   Источник: конкурентность (MEDIUM). `backend/app/services/marking_code_service.py:1506-1531` (превью без локов) → `:1536-1567`; `count_available_for_product` `:1100-1108` vs фильтр выдачи `:1205-1209`.
   Превью без локов и без агрегации потребности по общему пулу (две строки по 50 при 60 кодах обе проходят), фильтр превью шире фильтра выдачи → ложное «всё ок» с последующим частичным коммитом.
   Фикс: агрегировать потребность по пулам, согласовать фильтры, превью+выдача в одной транзакции с `FOR UPDATE SKIP LOCKED`.

7. **Импорт SELECT-then-INSERT без `ON CONFLICT` → срыв всего батча при параллельном дубле**
   Источник: конкурентность (MEDIUM). `backend/app/services/marking_code_service.py:910-937` (`import_marking_codes`); есть `uq_marking_codes_tenant_cis`.
   Параллельный/повторный импорт одного CIS: оба проходят SELECT, второй `flush()` ловит `IntegrityError`, без savepoint абортит весь батч (включая выданный `document_number`). Импорт не идемпотентен.
   Фикс: `insert(...).on_conflict_do_nothing(index_elements=["tenant_id","cis_code"]).returning(id)`, как в `next_document_number`.

8. **N+1 + отсутствие пагинации в `/pending-marking`**
   Источник: контракты API (HIGH). `backend/app/services/marking_code_service.py:2381`, эндпоинт `backend/app/api/marking_codes.py:1104`.
   `count_available_for_product` (сам ~3 запроса) в цикле по каждой строке → ~3N round-trip; эндпоинт без `limit/offset` грузит все строки всех draft/in_progress задач. Нагрузка на БД и риск тяжёлого ответа.
   Фикс: батч-подсчёт доступности одним `GROUP BY product_id`; добавить `limit/offset` + `total`.

9. **Нет теста на конкурентную выдачу кодов из пула (И4 / acceptance T1.2)**
   Источник: тесты (HIGH). `backend/tests/test_marking_print_pool.py:143`.
   Единственный «не пересекаются» тест строго последователен (нет `asyncio.gather`); удаление блокировки его не уронит. Регрессия двойной выдачи под гонкой останется незамеченной. (Связан с блокером №6.)
   Фикс: тест с `asyncio.gather` двух печатей по одному пулу с ограниченным остатком; проверить отсутствие дублей и суммарную выдачу ≤ остатка.

10. **Слабые тесты `replace` и shift-lead-гейта на мутациях очереди**
    Источник: тесты (2× MEDIUM). `backend/tests/test_marking_reprint_defect.py:181`; `backend/tests/test_shift_lead.py:71`.
    (а) `test_replace_reprint_request_clears_queue` не проверяет `old_code==defective`/`replaced_by_code_id`/`new_code==printed`/остаток −1/события. (б) Негативный 403-кейс есть только на `GET /reprint-requests`, нет на `replace`/`approve`/`reject` — если на них забыли `require_shift_lead`, тесты не поймают.
    Фикс: дочитать состояние из БД в replace-тесте; добавить 403-тесты на мутирующие действия очереди под не-shift-lead.

---

## 🟡 Мелочи / улучшения

1. **`auto_emit_limit` без верхнего предела**
   Контракты API (MEDIUM). `seller_marking_credentials_service.py:209`, `marking_credentials.py:169`. Принимается любое целое ≥1 (лимит авто-эмиссии КМ фактически снимается опечаткой). Фикс: `1 <= auto_emit_limit <= 100000`.

2. **Неполный маппинг ошибок credentials → возможен 500**
   Контракты API (MEDIUM). `marking_credentials.py:204`. `invalid_auto_introduce` не в whitelist → потенциальный 500 на клиентскую ошибку (сейчас прикрыт верхним слоем). Фикс: добавить код или правило `invalid_*`/`*_empty` → 422.

3. **Нехватка кодов не подсвечивается в списке строк упаковки до открытия диалога**
   Фронтенд (MEDIUM). `frontend/src/screens/ff/FfPackagingPage.tsx:656-668`. Ячейка ЧЗ показывает «дост. N» нейтрально, без сравнения с `qty_need_pack` (DESIGN требует подсветку «сразу»; в превью «печать всех» подсветка уже есть). Фикс: красить `warning.main` при `marking_available_count < qty_need_pack`.

4. **`/pools/{id}/codes` без пагинации**
   Контракты API (MEDIUM). `marking_codes.py:709`, `marking_code_service.py:1830`. Отдаёт все коды пула (десятки тысяч) без `limit/offset`. Фикс: `limit (ge1,le200)=50` + `offset` + `total`.

5. **`is_default` boolean — см. блокер №1** (тот же файл; уже учтено выше, дубль не плодим).

6. **Привязка Fernet-ключа к `jwt_secret_key` смешивает домены секретов**
   Безопасность (LOW). `integration_fernet.py:17-18`. Ротация JWT-секрета молча делает нечитаемыми токены ЧЗ/СУЗ/МП. Фикс: в проде только независимый `wms_secrets_fernet_key`; деривацию — строго dev/test за гейтом (блокер №2).

7. **Расшифровка падает `InvalidToken` без доменной обёртки**
   Безопасность (LOW). `seller_marking_credentials_service.py:237-243`. Риск попадания cipher-text в трейс вызывающего. Фикс: обернуть в `SecretDecryptError` без исходного значения.

8. **Reprint на фронте не показывает нехватку кодов в пуле**
   Фронтенд (LOW, требует подтверждения контракта). `MarkingPrintDialog.tsx:102-111`. Для `reprint=true` `shortage` принудительно 0; если перепечатка тянет из пула — предупреждения нет до ответа бэка. Фикс: учитывать `available` и для reprint, либо явно пометить «коды из ранее выданных».

9. **Создание ресурсов возвращает 200 вместо 201**
   Контракты API (LOW). `marking_codes.py:1296` (`/codes/{id}/defect`), `:485` (`/import`). Фикс: `status_code=201` для defect.

10. **Нет верхнего предела на `units` в layout и число файлов импорта**
    Контракты API (LOW). `marking_codes.py:276`, `print_template_service.py:80`, `marking_codes.py:451`. `copies` (1..10) ограничены, длина `units` и число файлов — нет (потенциальный DoS). Фикс: `units ≤ 20`, файлов ≤ 20.

11. **Нет DB-UNIQUE на пул `(tenant_id, seller_id, gtin)`**
    Миграции (LOW). `20260626_0043_marking_pools.py:137-142` — индекс `unique=False`. Инвариант «один пул = один GTIN» (DESIGN:74) не закреплён в БД; рантайм при гонке может создать дубль пула. Фикс (если инвариант обязателен): `unique=True` после проверки отсутствия дублей.

12. **Мусорный бинарник `tmp_alembic_test.sqlite` не в `.gitignore`**
    Миграции (LOW). `backend/tmp_alembic_test.sqlite` (188 КБ), untracked, не покрыт `.gitignore` — попадёт в коммит при `git add .`. Фикс: удалить + добавить в `.gitignore`.

13. **ruff/mypy красные в CI**
    Гейты. ruff: 4 (`RUF059`, `E501` в `test_marking_reprint_defect.py:166`, `test_marking_verify_pair.py:63` и др.). mypy: 10 в 5 файлах — ключевой `marking_codes.py:721` вынесен в блокер №4; остальные (`:940/942/989` `UUID|None`, `marking_code_service.py:1209` тип `code_filter`, `__all__`-экспорты) — типизация/стиль, проверить `:940/942/989` на None-проглатывание. Фикс: починить ruff/mypy до зелёного CI.

14. **Слабые/тавтологичные тест-ассерты (3× LOW)**
    Тесты. `test_marking_print_all.py:124` (тавтология «in_order», нет проверки `layout`); `test_marking_forecast.py:138` (`unread_count==0` под админом не доказывает видимость селлером); `test_marking_code_events.py:142` (условный `if doc_number:` маскирует потерю номера). Фикс: сопоставлять `line_id`, проверять получателя через API под селлером, ассертить `document_number` безусловно.

---

## Что проверено и чисто (нет находок)

- **Мультитенантность / authz / IDOR — ЧИСТО** (0 CRITICAL/HIGH/MEDIUM): `tenant_id` фильтруется во всех сервисах; роль seller всегда заменяет входной `seller_id` на `effective_seller_id`; `require_shift_lead` реально гейтит reprint на бэке; IDOR по pool/code/request/notification/product/template закрыт (объекты грузятся с проверкой tenant+seller). Единственные 2 находки — LOW/INFO, обе только в коде под E2E-флагом `WMS_AUTO_CREATE_SCHEMA`, в проде не активны.
- **Секреты не утекают в API** — только маски `has_cz_token`/`has_suz_oms_token`/`has_mp_api_key`; эндпоинта выдачи расшифрованных секретов нет; шифрование at-rest применяется на записи; личный ключ ЭЦП не хранится (И7); секреты не логируются.
- **Секретов на фронте нет** — только булевы флаги наличия.
- **Раскладка печати на фронте — КОРРЕКТНА** (главный инвариант): пара одинаковых КМ внутри единицы, следующий код — между единицами (`expandLayoutTape`, покрыто юнит-тестом).
- **`next_document_number`** — атомарный `on_conflict_do_update` поверх уникального ключа, без TOCTOU (контр-находка конкурентности).
- **Цепочка миграций 0041→0052** — линейная, без разрывов/циклов/дублей; бэкфилл кодов в пулы есть (0043); симметрия up/down корректна; FK проиндексированы; NOT-NULL колонки имеют `server_default` (кроме синтаксиса `is_default`, блокер №1).
- **И1/И3** (остаток на пул, не на товар), **И4** (нет двойного списания самого КМ при N копиях — проблема только в метрике расхода), **И6** (событие на каждый переход статуса) — подтверждены.
- **Контракты в целом** — `response_model` почти везде; `copies`/`duplicate_copies` ограничены; `/ledger` и `/notifications` пагинированы; маппинг ошибок дефолтит в 422, not-found→404, размер→413, тип файла→415.
- **pytest** — 45 passed (marking+notification+print сабсет): доменная логика рабочая.

## Пробелы ревью

Пробелов нет: все 8 файлов измерений (`find-concurrency`, `find-security_secrets`, `find-invariants`, `find-migrations`, `find-tenancy_authz`, `find-api_contracts`, `find-frontend`, `find-tests`) присутствуют, непустые и содержательны. Гейты (ruff/mypy/pytest) выполнены. Отдельные находки помечены «требует подтверждения» (None-проглатывание `marking_codes.py:940/942/989`; контракт reprint на фронте; достижимость `invalid_auto_introduce`) — их стоит закрыть в рамках фикса.

## Рекомендация: NO-GO до устранения блокеров → затем GO с условиями

**Обязательно к фиксу перед мёржем/продом (блокеры):**
1. `20260626_0046_print_templates.py:29` — `sa.false()` вместо `sa.text("0")` (иначе деплой упадёт).
2. Prod-гейт на `wms_secrets_fernet_key`/`jwt_secret_key` в `settings.py` (иначе токены де-факто незашифрованы).
3. Удалить автопривязку по GTIN из `list_inventory` (нарушение И2, молчаливая запись в БД).
4. Переименовать `status`-параметр в `marking_codes.py:715` (иначе 500 вместо 404, маскирует tenancy-проверку).
5. Атомарность `print_all_for_packaging_task` (один commit; иначе частично отпечатанные задания, потеря КМ).
6. `SKIP LOCKED` при выдаче из пула + тест на гонку (иначе ложный дефицит под параллелью).

**Условия для GO после блокеров:** закрыть «Важное» №1–7 до релиза (особенно прогноз-вдвое, статус `replaced`, идемпотентность `verify_pair`/импорта, guard статуса задания) либо сразу после с явным тикетом; починить ruff/mypy до зелёного CI; добавить тесты на гонку и shift-lead-мутации. «Мелочи» — бэклог.
