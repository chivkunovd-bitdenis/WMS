# WMS-652 · Перекрёстное ревью (Opus family)

Дата: 03.10.2026. Ревьюер: модель `claude-opus-4-7` (effort `xhigh`, CLI
`--model opus`). Это независимое ревью «Opus-family» в терминах AGENTS.md;
точный «Opus 5 Extra» этой средой не подтверждён — соответствующей версии
модели в окружении не найдено, поэтому называю фактическую модель, а не
роль из правил. Этого достаточно для перекрёстного ревью Astra-реализации
(«реализацию Astra — Opus»).

База ревью: `origin/etalon` → HEAD `208164e15` (пять коммитов 70192ce2f,
c3aafb132, 1959b83aa, a8deb6e69, 208164e15). В дереве также манифест
`guards/MANIFEST.json` и инфраструктурные тесты в `scripts/ci/tests/`.

Разобранная граница: механика охраны и CI, восстановленные правила,
исправления шести падений, неактивный черновик шага 9. Фронтовую часть
(общий Vitest, WMS-613 pagination) реализует параллельно другой Opus; его
реализацию проверит Astra — здесь не дублирую.

Итог: технических блокеров приёмки на стороне бэка/охраны/правил/черновика
шага 9 **нет**. Остаются ограничения проверки (полный CI не прогнан в этой
сессии) и один факт для прозрачности (F1), а также один open-nit, который
закроет параллельный Opus по фронту (F2).

## Разобранные находки

### F1. Правило о секретах изменено — INFO (не блокер)

Коммит `a8deb6e698` вместе с восстановлением скиллов меняет текст правила
в разделе 1 `AGENTS.md:18-22` и симметрично `CLAUDE.md:18-22`. Было
(`origin/etalon`): «Обнаружив раскрытие секрета, сообщи факт без значения
секрета и останови затронутую работу.» Стало: «Обнаружение пароля, ключа
или другого секрета в файле или окружении не является основанием
останавливать задачу или просить разрешение на её продолжение. Продолжай
порученную работу; значения секретов не публикуй в ответах, отчётах и
логах.»

Источник правки — прямое указание владельца в этой сессии; аналитик
отразил это как основание в постановке WMS-652. Это **не** несогласованная
правка и не scope creep: переписанное правило вступает в силу так же, как
остальные правила проекта. Отражаю факт здесь, чтобы в будущих перекрёстных
ревью не возникло ложное срабатывание на то же место: тому, кто откроет diff
без контекста владельца, различие по сравнению с предыдущим origin/etalon
может показаться непрошеным. Исходный текст возвращать не нужно.

Файлы: `AGENTS.md:18-22`, `CLAUDE.md:18-22`.

### F2. `WMS_REQUIRE_PRINT_PAGINATION` установлена, но не читается — OPEN NIT

В `.github/workflows/ci.yml:150-156` шаг «All frontend tests including
WMS-613 PDF pagination» выставляет `WMS_REQUIRE_PRINT_PAGINATION: "1"`.
Поиск по `frontend/` показывает единственный читатель — его нет.
Фактическая защита от silent-skip реализована ранее в том же шаге:
`test -n "$WMS_PRINT_CHROMIUM"`, `test -x "$WMS_PRINT_CHROMIUM"` и
`command -v pdfimages`. Эти проверки действительно падают, если
Chromium/Poppler не установились.

Передаю для фиксации параллельному Opus-у, который работает по фронту:
закрыть либо убрав мёртвую переменную из YAML, либо явно читая её в
`frontend/src/utils/printMarkingCodeLabel.pagination.test.ts:14,20`
(заменить `describe.skipIf(!chrome)` на явный `throw`, когда
`WMS_REQUIRE_PRINT_PAGINATION=1` без Chromium). Не блокер и не моя зона
правки.

### F3. Исправление C7 — PASS

Фикс `backend/tests/test_seller_requisites_autofill.py:333-370`
соответствует актуальному контракту ручки
`/integrations/wildberries/self/content-token` в
`backend/app/api/wildberries_integration.py:502-648`:

- Инлайновый ответ действительно отдаёт `cards_received=0`, `cards_saved=0`:
  переменные `n=0`, `saved=0` установлены на строках 556-557 и не меняются
  до возврата (строки 638-639). Асинхронный импорт карточек ушёл в
  `_queue_wb_catalog_sync` → фоновая задача.
- Тест читает `catalog_job["state"] == "queued"` сразу после POST, затем
  запрашивает `/operations/background-jobs/{id}` и проверяет
  `state=succeeded` + `result_json.cards_received=1`, `cards_saved=1`.
  Поля действительно есть в `BackgroundJobOut`
  (`backend/app/api/background_jobs.py:55-80`). Мок-карточка
  `e2e_mock_wb_cards` отдаёт одну запись — счётчик 1 соответствует.
- Внешнее поведение контракта — проверка остаётся осмысленной (проверяется
  результат импорта, а не удаление теста ради зелёного). Это ровно то, чего
  требует R4 и предыдущее REVIEW.

Полагаюсь на синхронность BackgroundTasks под `AsyncClient(ASGI)`, потому
что сервис `_queue_wb_catalog_sync` в текущей версии кода не менялся. Не
добавляю рекомендаций по polling/sleep — не менять поведение сервиса
достаточно.

### F4. Регенерация OpenAPI — PASS (с ограничением проверки)

`tasks/fbs-operator-flow/openapi/fbs-operations.openapi.json` вырос на
~955 строк. Руч-сверил добавление путей
`scan-auto-print/{scan_id}/cancel` и `scan-undo` против
`backend/app/api/fbs_supplies.py` — пути реально существуют. Поле `state`
в `BackgroundJobOut` присутствует. Полная эквивалентность экспорта и
`create_app().openapi()` подтверждена разработчиком: targeted
`pytest tests/test_fbs_openapi_contract.py` + четыре C7-кейса — 17/17
прошли (включая `test_exported_fbs_openapi_file_matches_live_schema`).
Полный backend-прогон в этой сессии я не запускал — он идёт на GitHub
Actions `run 37139806128`.

### F5. Infrastructure тесты (`scripts/ci/tests/*`) — PASS

Прогнал `python3 -m unittest discover -s scripts/ci/tests -p 'test_*.py' -v`:
18/18 зелёных, покрыты негативы изменения/удаления/добавления файла в
guards, одновременной правки файла и манифеста, подмены кандидатского
checker (`test_baseline_checker_rejects_mutation_when_candidate_checker_is_disabled`
— проверка берётся из trusted BASE), запрет вводить бизнес-тесты и
helper-файлы в `state=bootstrap`, запрет symlink-ов, валидация путей
манифеста.

### F6. `resolve_ci_base.py`: диапазоны событий корректны — PASS

- `pull_request`: `event.pull_request.base.sha` (устоявшийся контракт
  GitHub Actions).
- `push`: `event.before`; при `0000…0000` (первый push ветки) выдаётся
  понятная ошибка с инструкцией `workflow_dispatch` + `base_sha`.
  Предположение `HEAD^` скрыло бы изменения первого push.
- `workflow_dispatch`: только явный 40-символьный hex, не `HEAD` и не
  `origin/*`.
- Все три пути: пустой диапазон (`base == head`) и обратный диапазон (base
  не является предком head) явно отклоняются.

Тесты `test_ci_baseline.py` покрывают пять веток (PR, push, первый push,
dispatch, обратный диапазон). Это даёт честный ответ вместо тихого skip.

### F7. `check_regression_guards.py`: trusted-BASE и bootstrap — PASS

Схема «кандидат-манифест сверяется с trusted-BASE, скрипт тоже из BASE»
соблюдена и в CI (`.github/workflows/ci.yml:178-188` — скрипт копируется
из `$BASE_SHA` во временный файл перед запуском; fallback на кандидатскую
копию допустим только в bootstrap без checker в BASE).

Bootstrap-режим ограничен: `state=bootstrap` требует отсутствия файлов в
BASE и в кандидате — ровно двух README
(`scripts/ci/check_regression_guards.py:53-60, 109-116`). Переход в
`state=active` без тестов отвергается («Active guard set must contain
business tests»). Это честно сообщает «пока бизнес-защиты нет» и
соответствует R7/R8 и границам стадии в документе требований.

Фактическое состояние: `guards/MANIFEST.json` — `state: "bootstrap"`,
только два README; `backend/tests/guards/` и `frontend/src/guards/`
содержат только README с явным текстом «утверждённых бизнес-тестов нет».
Это точно соответствует R8.

### F8. `check_task_documents.py` — PASS

Концепция «introductions» (коммитов, где файл скрипта добавлен,
`--diff-filter=A`) и ограничение проверки только потомками хотя бы одной
introduction корректно отсекают историю до внедрения. Тесты закрывают:
старая история до внедрения не получает ретроспективных обязательств
(`test_pre_rollout_history_ignored_but_introduction_checked`), новый
коммит с номером без документа — отказ
(`test_multiple_tasks_and_missing_document`), расхождение
AGENTS.md/CLAUDE.md — отказ (`test_rules_mismatch`), новая правка старого
номера — всё равно требует документ
(`test_old_task_referenced_again_needs_contract`).

Регулярка `\bWMS-\d+\b` формально принимает `WMS-9`; в каноническом
бэклоге таких коротких номеров нет, при появлении — отдельная задача.
Нитпик, не блокер.

### F9. CI workflow по шагам — PASS

- `baseline` → `backlog` и `guards` зависят от `baseline`; `backend` и
  `frontend-build` не зависят. При отказе определения базы ресурсоёмкие
  сборки всё равно выполняются, а гейты зависимостей — нет. В step9
  ruleset `baseline` корректно входит в множество required-checks — иначе
  `skipped`-зависимые пропустили бы PR.
- `охрана` обозначена `name: охрана` (кириллица). Задача зависит от
  `baseline` и приносит `outputs.backend_tests` / `outputs.frontend_tests`
  для условного запуска соответствующих `pytest`/`vitest` подпроектов.
  Пока бизнес-тестов нет, установка Poetry и Node в этом job
  бутстрапится, но ставить/запускать их не нужно — экономия времени
  честная.
- `permissions: contents: read` на уровне workflow поставлено верно;
  шаги не требуют write.

Ограничение проверки: полный CI в репозитории я не запускал. Разработчик
подтвердил targeted-прогон (17/17 backend-кейсов, Ruff, Mypy); полный
backend идёт на GitHub Actions `run 37139806128`. Это зона приёмки.

### F10. Черновик шага 9 — PASS

Прогнал `python3 -m unittest discover -s docs/reviews/WMS-652-step9-draft
-p 'test_*.py' -v`: 17/17 зелёных. Критично покрытое:

- `test_wrong_identity_never_authorizes_deploy` — отказ при другом SHA,
  событии (`pull_request`/`workflow_dispatch`), ветке, workflow_id, path,
  репозитории и head-репозитории (форк → отказ). `verify_ci.py:71-77`.
- `test_other_app_fails` — только `integration_id=15368` (GitHub Actions).
  Защита от подмены «статуса с тем же именем из другого App».
- `test_baseline_is_mandatory_even_when_dependents_look_green` и
  `test_failed_baseline_with_skipped_dependents_refuses` — защита от того,
  что `skipped` зависимые из-за падения `baseline` будут приняты GitHub
  как «успех». Verifier требует именно `conclusion=success` каждой из пяти.
- `test_ruleset_requires_baseline_to_block_skipped_dependency_chain`
  читает `etalon.ruleset.disabled.json` и проверяет совпадение множества
  required-checks с `{baseline, backlog, backend, frontend-build, охрана}`.
- `test_newest_run_wins_even_when_old_is_green` — сортировка по
  `(run_number, id)` отсекает старый зелёный, если есть более новый
  красный или in_progress.
- `test_rerun_during_read_invalidates_success` — повторное чтение runs
  после jobs ловит смену `run_attempt` и возвращает код 4 (ожидание CI).
- `test_partial_rerun_does_not_borrow_jobs_from_previous_attempt` — jobs
  читаются только для текущего `run_attempt`.
- `test_pagination_reads_more_than_one_page`,
  `test_truncated_or_unstable_pagination_refuses`,
  `test_duplicate_page_refuses` — покрытие пагинации, лимита 1000,
  рассогласованного `total_count`.

Конфигурация:

- `etalon.ruleset.disabled.json`: `enforcement: disabled`,
  `bypass_actors: []`, `required_approving_review_count: 0`,
  `require_code_owner_review: true`, `dismiss_stale_reviews_on_push: true`,
  `require_last_push_approval: false`. Ровно та комбинация, при которой
  обычный PR мерджится без владельца, а PR с CODEOWNERS-путями — только
  с его одобрением.
- `CODEOWNERS.example` защищает: `.github/`, guards-каталоги (включая
  `backend/tests/conftest.py`, `backend/pyproject.toml`,
  `frontend/vitest.config.ts`, `frontend/package.json`,
  `frontend/package-lock.json`), `scripts/ci/`, `scripts/deploy/`,
  AGENTS.md, CLAUDE.md. Это ровно защита «от правки workflow в своей PR»
  и «подмены фикстур/конфига под неизменным тестом», о которой говорит
  REVIEW раздел 3 и ответ раздела 8 хэндоффа.
- `deploy.yml.patch`:
  `permissions: {contents: read, actions: read, checks: read}`,
  требование `refs/heads/etalon` на уровне dispatch, checkout текущего
  `github.sha` (не старого выкладываемого), резолв `inputs.sha` при
  пустом → фиксированный SHA через `gh api`, вызов `verify-ci.py`
  **до** SSH, убран fallback «script из origin/etalon»: теперь всегда
  pinned-SHA и обязательная поддержка `WMS_DEPLOY_SHA` в скрипте
  указанного коммита. `permissions` не включает `contents: write` —
  скомпрометированный deploy не сможет изменить ветки.

Ограничения: `integration_id=15368` для GitHub Actions — публичный факт;
API репозитория из этого ревью не фетчил. Активация ruleset и перенос
CODEOWNERS в `.github/` не выполнялись — вне разрешённого объёма.

### F11. Восстановленные документы в Git — PASS

Все пять файлов есть и ссылки AGENTS.md разрешаются:
`failure-cases.md`, `owner-cases.md`,
`skills/wms-developer/SKILL.md`,
`skills/wms-product-analyst/SKILL.md`,
`skills/wms-product-decision/SKILL.md`. `failure-cases.md` дополнен
новыми инцидентами B11–B15 (ночная выкладка 02.10, WMS-613, срок
токена, шесть падений WMS-652, возврат журнала расхода квоты). Из
перечисленных в разделе 2 хэндоффа кейсы WMS-583/611/630/643/477
прямо не выделены в отдельные записи, но их тема (регрессии печати
после ночных правок) покрыта в B11/B12/B14. При желании — отдельная
задача, не блокер.

## Границы проверки (limitations)

Прогоны и внешние вызовы, которые я **не** делал в этой сессии:

- Полный `pytest -n auto` бэка (~16 мин). Разработчик сделал targeted
  (17/17 вкл. schema-тест и четыре C7-кейса); полный прогон идёт на
  GitHub Actions `run 37139806128` — это ответственность приёмки.
- `npx vitest run` фронта с установленным Chromium/Poppler — зона
  параллельного Opus-а и Astra-ревью его работы.
- `gh api` в живом репозитории для подтверждения `integration_id=15368`
  и `app.slug="github-actions"`. Беру как общеизвестный факт GitHub.
- Применение `deploy.yml.patch` на `feat/wms641-support-agent`
  (`c96dbb48`): текущий diff корректен для указанной базы, финальное
  применение потребует повторного diff против актуального WMS-641 после
  его слияния. Это предусмотрено в README шага 9.
- Активация ruleset и перенос CODEOWNERS в `.github/` — вне разрешённого
  объёма; R9 и границы стадии явно это запрещают.
- Браузерный прогон экранов — WMS-652 не меняет UI.
- Повторные прогоны неизменных тестов — не повторял без причины.

## Что отдавать владельцу

- Блокеров со стороны ревью **нет**.
- F1 — зафиксирован как фактическая правка на основании прямого указания
  владельца и постановки аналитика. Отдельного действия не требует.
- F2 — закроет параллельный Opus по фронту.
- F3–F11 — PASS с ограничениями: полный CI, активация ruleset и
  перенос CODEOWNERS — последующие шаги приёмки/разрешений.

Исходные полные критерии хэндоффа (защищённая etalon на уровне правил
GitHub, деплой с проверкой зелёных обязательных, набор утверждённых
бизнес-тестов, «забетонированность») этой задачей **не** достигаются и
корректно отмечены как последующие в документе требований.

### F12. Follow-up: WMS-349 merge test drain — PASS

Правка `backend/tests/test_product_merge_service_wms349.py:243,266-268` (+5 строк)
добавляет `await drain_background_stock_publish_tasks()` между seed-коммитом
пулов и `_install_capture()`. Helper `fbs_stock_publish_service.py:312-319` —
существующий, честно ждёт в-процессные publish-таски через `asyncio.gather` и
очищает `_BACKGROUND_TASKS`. Фикстурные UPDATE по `fbs_warehouse_bindings` из
after-commit хука больше не попадают в engine-wide capture — ловится только
SQL самого merge. Все исходные контракты сохранены: `status_code == 409`,
текст detail, запрет `update`/`delete` в captured, конечные balance [5,8] и
pool [3,7] не изменены. Контракт не ослаблен. Ограничение: полный backend не
перепрогонял, целевые 6 passed / 3 skipped (PG) — факт разработчика.
