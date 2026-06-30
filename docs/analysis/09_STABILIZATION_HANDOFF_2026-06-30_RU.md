# Срез стабилизации WMS — handoff для Composer/Cursor Autopilot

Дата среза: 2026-06-30  
Рабочий репозиторий: `/Users/deniscivkunov/Desktop/WMS `  
Текущая ветка на момент среза: `hotfix/deploy-wb-sync-nonfatal`

Важно: в пути к реальному рабочему дереву есть пробел в конце имени папки: `WMS `. Перед любыми командами проверять `pwd`.

## 0. Главные правила для следующего запуска

1. Разработка и агенты — только `gpt-5.4-mini`.
2. Тяжёлые модели запрещены для разработки. Допустимы только для оркестрации/проверки, если без этого реально нельзя.
3. Не расширять объём работ. Работать по подтверждённым багам из:
   - `docs/analysis/08_confirmed_bug_stabilization_autopilot_RU.md`
4. Не превращать это в общий рефакторинг. Исправлять только конкретные баги и связанные тесты.
5. Не считать задачу закрытой без локального гейта или явного указания, почему гейт не запускался.
6. Если Composer поднимает агентов, каждому агенту давать узкую независимую задачу из backlog-документа, чтобы не было конфликтов в одних и тех же файлах.
7. Перед коммитом/деплоем внимательно посмотреть `git status` и `git diff`: в рабочем дереве есть как новые файлы, так и изменения от нескольких агентов.

## 1. Что пользователь хотел получить

Проблема пользователя: после предыдущей работы требования разъехались, потрачено много времени, есть риск снова получить кашу вместо продукта. Поэтому текущая стратегия:

1. Не пытаться восстановить все абстрактные требования за 3 дня.
2. Зафиксировать только те баги, которые уже точно известны и подтверждены.
3. Описать их в формате, который Composer/Cursor Autopilot может выполнять мультиагентно.
4. Быстро поднять тестовую среду, желательно Railway, чтобы не ждать долгих деплоев и не ломать рабочую среду, где уже работают люди.
5. Исправлять баги маленькими независимыми задачами, с проверкой.

Главный backlog для исполнения уже создан:

`docs/analysis/08_confirmed_bug_stabilization_autopilot_RU.md`

Railway-документ уже создан:

`docs/analysis/RAILWAY_STAGING_RU.md`

Этот файл — не новый backlog. Это оперативный срез: что уже сделано, что осталось, где риски, какие команды запускать дальше.

## 2. Состояние Railway/test environment

Railway-подготовка в коде сделана. **2026-06-30 (поздний срез):** ветка `hotfix/deploy-wb-sync-nonfatal` запушена на GitHub; Railway CLI через `npx @railway/cli` доступен (логин `chivkunov.d@gmail.com`), но **WMS-проект на Railway ещё не создан/не привязан** (`railway link`). Smoke-скрипт: `scripts/railway-staging-smoke.sh` (нужен `WMS_STAGING_URL`).

Исторические причины задержки деплоя:

1. Railway CLI не был установлен/доступен.
2. Попытки через `npx` сначала упирались в проблемы npm/места на диске.
3. На Mac было 100% заполнение диска, около 113 MB свободно.
4. После очистки старых `.cursor/wt` стало около 4.2 GB свободно.
5. После освобождения места CLI-деплой ещё не был повторён, потому что пользователь попросил срочно сделать handoff перед окончанием лимита.

Что уже добавлено для Railway:

1. `backend/Dockerfile.railway`
2. `frontend/Dockerfile.railway`
3. `frontend/deploy/Caddyfile.railway`
4. `docs/analysis/RAILWAY_STAGING_RU.md`
5. production/staging настройки CORS и DATABASE_URL в backend.

Backend Railway поведение:

1. Нормализует `postgresql://...` и `postgres://...` в `postgresql+psycopg_async://...`.
2. Поддерживает `WMS_CORS_ORIGINS`.
3. FastAPI CORS берёт origins из settings.
4. `backend/Dockerfile.railway` слушает `$PORT`.
5. Backend контейнер перед стартом делает `alembic upgrade head`.

Frontend Railway поведение:

1. `frontend/Dockerfile.railway` собирает SPA.
2. Caddy слушает `:{$PORT}`.
3. `/api/*` проксируется в `WMS_API_UPSTREAM`.

Минимальные Railway env vars:

Backend/api service:

```text
DATABASE_URL
JWT_SECRET_KEY
WMS_SECRETS_FERNET_KEY
WMS_CORS_ORIGINS
WMS_BOOTSTRAP_ADMIN
WMS_BOOTSTRAP_ADMIN_EMAIL
WMS_BOOTSTRAP_ADMIN_PASSWORD
WMS_BOOTSTRAP_ORG_NAME
WMS_BOOTSTRAP_ORG_SLUG
```

Опционально:

```text
CELERY_BROKER_URL
WMS_AUTO_CREATE_SCHEMA
```

Frontend/web service:

```text
WMS_API_UPSTREAM
```

Railway сам даёт:

```text
PORT
```

Рекомендуемый порядок поднятия Railway:

1. Создать Railway project.
2. Добавить Railway PostgreSQL plugin.
3. Создать backend service из `backend/Dockerfile.railway`.
4. Пробросить `DATABASE_URL` из Postgres в backend.
5. Прописать backend secrets/bootstrap env vars.
6. Создать frontend service из `frontend/Dockerfile.railway`.
7. Прописать `WMS_API_UPSTREAM` на backend public/internal URL.
8. Добавить frontend URL в `WMS_CORS_ORIGINS`.
9. Первый старт backend сделать с bootstrap admin.
10. После первого успешного старта выключить/убрать bootstrap admin env vars, чтобы не держать лишний риск.

Если CLI снова не поднимется быстро, делать через Railway UI. Кодовая подготовка уже есть.

## 3. Что уже сделано и считается закрытым

### STAGE-00 — Railway staging config

Статус: сделано.

Файлы:

1. `backend/app/core/settings.py`
2. `backend/app/main.py`
3. `backend/tests/test_settings_prod_gate.py`
4. `backend/Dockerfile.railway`
5. `frontend/Dockerfile.railway`
6. `frontend/deploy/Caddyfile.railway`
7. `docs/analysis/RAILWAY_STAGING_RU.md`

Проверки, которые проходили:

```bash
backend/.venv/bin/ruff check --cache-dir /private/tmp/wms-ruff-cache backend/app/core/settings.py backend/app/main.py backend/tests/test_settings_prod_gate.py
MYPY_CACHE_DIR=/private/tmp/wms-mypy-cache backend/.venv/bin/mypy --follow-imports=skip --ignore-missing-imports backend/app/core/settings.py backend/app/main.py backend/tests/test_settings_prod_gate.py
backend/.venv/bin/pytest backend/tests/test_settings_prod_gate.py
```

Результат pytest settings gate: `7 passed`.

Frontend build-проверка для Railway проходила через workaround:

```bash
cd frontend
./node_modules/.bin/tsc -p tsconfig.app.json --noEmit
./node_modules/.bin/tsc -p tsconfig.node.json --noEmit
./node_modules/.bin/vite build --configLoader runner --outDir /private/tmp/wms-frontend-dist
```

Обычный `npm run build` в sandbox может падать на `EPERM` при записи в `node_modules/.tmp/*.tsbuildinfo`. Это похоже на sandbox/permissions, а не на продуктовую ошибку. Для проверки использовать `--noEmit` и `--outDir /private/tmp/...`.

### STAB-IN-BE-01 — несколько открытых коробов в приёмке

Статус: сделано.

Файлы:

1. `backend/app/services/inbound_intake_box_service.py`
2. `backend/app/services/inbound_intake_service.py`
3. `backend/tests/test_inbound_intake_box_ondemand.py`
4. `backend/tests/test_inbound_intake_api_be03.py`

Что исправлено:

1. Убран singleton/open-box restriction.
2. `POST /boxes` может создать несколько видимых коробов.
3. `open_box_by_barcode` больше не закрывает другой короб автоматически.
4. Скан в конкретный короб пишет именно в этот короб.
5. `complete_receiving` больше не требует закрыть все короба.

Проверки от агента:

```bash
cd backend
ruff check .
pytest tests/test_inbound_intake_box_ondemand.py tests/test_inbound_box_acceptance.py tests/test_inbound_intake_api_be03.py
```

Результат targeted pytest: `14 passed`.

Примечание: один backend mypy в другом запуске падал на старые unrelated `import-untyped` по `celery` и `fitz`. Это не относится к этой задаче.

### STAB-IN-FE-01 — UI приёмки: много открытых коробов

Статус: сделано.

Агент: `019f1775-1d57-7462-b08b-e7d7439008c1`.

Файлы:

1. `frontend/src/screens/ff/FfInboundRequestView.tsx`
2. `frontend/src/screens/ff/FfInboundBoxAddDialog.tsx`
3. `frontend/tests-e2e/inbound-receiving-v2.spec.ts`

Что исправлено:

1. Кнопка создания короба создаёт новый короб, даже если уже есть открытые короба.
2. Завершение приёмки больше не блокируется открытыми коробами.
3. На экране рендерятся все открытые короба отдельными карточками.
4. У каждой карточки есть собственная кнопка `Добавить товары`.
5. Диалог добавления товаров привязан к конкретному `boxId`.
6. В диалоге выровнена терминология: заголовок `Добавить товары`, убраны старые тексты вокруг “закрыть короб”.
7. E2E заменён на сценарий трёх коробов, открытия второго по его кнопке, отдельного наполнения и общего скана на уровне документа.

Промежуточный конфликт, который уже был исправлен в основном потоке:

1. В `FfInboundRequestView.tsx` был duplicate `boxId` в `openBoxAddDialog(boxId?: string)`.
2. Локальная переменная результата создания короба переименована в `createdBoxId`.
3. После этого frontend TypeScript/Vite build прошёл.

Проверки от агента:

```bash
cd frontend
npm run build
npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts tests-e2e/ff-inbound-boxes.spec.ts tests-e2e/ff-inbound-box-intake.spec.ts
```

Результат e2e: `13 passed`.

### STAB-SORT-BE-01 — остаток в зоне сортировки

Статус: сделано.

Первый агент упал из-за `Selected model is at capacity`. Задача была перезапущена на `gpt-5.4-mini` и завершена.

Файлы:

1. `backend/app/api/inbound_intake.py`
2. `backend/app/services/inbound_intake_service.py`
3. `backend/tests/test_inbound_intake_service_sort_be01.py`
4. `backend/tests/test_inbound_distribution.py`

Что исправлено:

1. После завершения приёмки сохраняется видимый остаток в зоне сортировки.
2. API отдаёт `sorting_remaining_qty` в summary/detail.
3. Частичная раскладка уменьшает остаток.
4. Полная раскладка делает остаток равным нулю.
5. Добавлен mixed loose/box сценарий без double count.

Проверки от агента:

```bash
cd backend
ruff check .
mypy .
pytest tests/test_inbound_intake_service_sort_be01.py tests/test_inbound_distribution.py
```

Агент сообщил, что все эти проверки прошли.

### STAB-CZ-FE-01 — настройки порогов ЧЗ перенесены с пула на товар

Статус: сделано.

Первый агент не смог применить изменения из-за sandbox/write confusion. Изменение было завершено в основном потоке.

Файлы:

1. `frontend/src/screens/shared/HonestSignPoolPage.tsx`
2. `frontend/src/screens/shared/HonestSignProductPage.tsx`
3. `frontend/tests-e2e/ff-honest-sign.spec.ts`
4. `frontend/tests-e2e/ff-honest-sign-pool.spec.ts`

Что исправлено:

1. С pool page удалён блок thresholds (`ff-honest-sign-pool-thresholds` больше не должен рендериться).
2. Удалены неиспользуемые state/save function/type для thresholds на pool page.
3. На product page добавлен threshold editor для personal pools.
4. Если personal pool один, используется обычная threshold form.
5. Если personal pools несколько, появляется select `ff-honest-sign-product-threshold-pool`, где выбирается пул, чей threshold редактируется.
6. Multi-pool e2e теперь редактирует threshold на product page.
7. Pool spec проверяет, что threshold block отсутствует на pool page.

Проверки из основного потока:

```bash
cd frontend
./node_modules/.bin/tsc -p tsconfig.app.json --noEmit
./node_modules/.bin/tsc -p tsconfig.node.json --noEmit
./node_modules/.bin/vite build --configLoader runner --outDir /private/tmp/wms-frontend-dist-cz2
```

Результат: прошло. Vite дал только chunk size warning.

### STAB-REPRINTS-FE-01 — убрать отдельную навигацию “Перепечатки”

Статус: сделано.

Файлы:

1. `frontend/src/layouts/AuthedAppLayout.tsx`
2. `frontend/tests-e2e/ff-marking-defect.spec.ts`

Что исправлено:

1. Из FF sidebar убран отдельный пункт `Перепечатки`.
2. `nav-ff-honest-sign-reprints` больше не должен отображаться.
3. Прямой route `/app/ff/honest-sign/reprints` сохранён.
4. E2E теперь проверяет отсутствие nav item и использует direct route для контекстных проверок.

Проверки от агента:

```bash
cd frontend
npm run build
npm run test:e2e -- tests-e2e/ff-marking-defect.spec.ts
```

Результат: прошло.

### STAB-IN-FE-02 — кнопка завершения приёмки

Статус: сделано (волна A, 2026-06-30). Proof: `inbound-receiving-v2.spec.ts`.

### STAB-SORT-FE-01 — frontend остаток зоны сортировки

Статус: сделано (волна A). Proof: `ff-reception-sorting` + `ff-sorting-product-centric` 4/4.

### STAB-OUT-BE-01 — outbound backend

Статус: сделано (волна A, код не менялся). Proof: marketplace_unload pytest 30/30.

### STAB-OUT-FE-01 — outbound frontend

Статус: сделано. Proof: `stab-inbound-sort-outbound.spec.ts` 1/1.

### STAB-CZ-FE-02 — список товаров ЧЗ

Статус: сделано (волна A). Proof: `ff-honest-sign.spec.ts`.

### STAB-PRINT-FE-01 — единый конструктор печати

Статус: сделано (волна A). Proof: `ff-marking-print-constructor.spec.ts` и связанные e2e.

### STAB-IN-FE-03 — UX модалки добавления в короб

Статус: сделано (2026-06-30).

Файлы: `FfInboundBoxAddDialog.tsx`, `FfProductLineCells.tsx`, mock photo в `wildberries_client.py`, `ff-inbound-box-intake.spec.ts`.

Proof: `STAB-IN-FE-03 box add modal…` 1/1; inbound e2e 9/9.

### STAB-E2E-01 / STAB-E2E-02 — финальные e2e

Статус: сделано. Proof: `stab-inbound-sort-outbound.spec.ts`, `stab-cz-ui-print.spec.ts` по 1/1.

## 4. Что ещё не сделано

**Продуктовых STAB-задач из `08_confirmed_bug_stabilization_autopilot_RU.md` не осталось.**

Остаётся только операционное:

### Railway staging smoke

Статус: **не пройден** — WMS-проект на Railway не создан/не привязан (`railway list` не показывает WMS; нужен `railway link` + deploy).

Шаги:

1. Поднять services по `docs/analysis/RAILWAY_STAGING_RU.md`.
2. Задеплоить ветку `hotfix/deploy-wb-sync-nonfatal` (или merge в main + deploy).
3. `WMS_STAGING_URL=https://… ./scripts/railway-staging-smoke.sh`.
4. Ручной smoke: логин bootstrap admin → приёмка → ЧЗ.

### Незакоммиченный WIP

Локально могут быть незакоммиченные spec/handoff/TASKLOG — перед merge проверить `git status`.

---

*Ниже — архив утреннего среза §4 (задачи, которые позже закрыты в волне A).*

### STAB-IN-FE-02 — кнопка завершения приёмки

Статус: ~~не начинали~~ → закрыто (см. §3).

Статус: ~~частично~~ → закрыто (см. §3 STAB-IN-FE-03).

Статус: ~~не начинали~~ → закрыто (см. §3).

## 5. Текущее рабочее дерево

На момент последнего `git status --short --branch`:

```text
## hotfix/deploy-wb-sync-nonfatal...origin/hotfix/deploy-wb-sync-nonfatal
 M backend/app/api/inbound_intake.py
 M backend/app/core/settings.py
 M backend/app/main.py
 M backend/app/services/inbound_intake_box_service.py
 M backend/app/services/inbound_intake_service.py
 M backend/tests/test_inbound_distribution.py
 M backend/tests/test_inbound_intake_api_be03.py
 M backend/tests/test_inbound_intake_box_ondemand.py
 M backend/tests/test_inbound_intake_service_sort_be01.py
 M backend/tests/test_settings_prod_gate.py
 M frontend/src/layouts/AuthedAppLayout.tsx
 M frontend/src/screens/ff/FfInboundBoxAddDialog.tsx
 M frontend/src/screens/ff/FfInboundRequestView.tsx
 M frontend/src/screens/shared/HonestSignPoolPage.tsx
 M frontend/src/screens/shared/HonestSignProductPage.tsx
 M frontend/tests-e2e/ff-honest-sign-pool.spec.ts
 M frontend/tests-e2e/ff-honest-sign.spec.ts
 M frontend/tests-e2e/ff-marking-defect.spec.ts
 M frontend/tests-e2e/inbound-receiving-v2.spec.ts
?? WMS_REQUIREMENTS_TRACKER_RU.md
?? backend/Dockerfile.railway
?? docs/analysis/07_cz_ux_review_fix_tasks_autopilot_RU.md
?? docs/analysis/08_confirmed_bug_stabilization_autopilot_RU.md
?? docs/analysis/RAILWAY_STAGING_RU.md
?? frontend/Dockerfile.railway
?? frontend/deploy/Caddyfile.railway
?? review/
```

Перед продолжением обновить статус:

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
git status --short --branch
```

## 6. Команды проверки, которые стоит запустить следующему Composer

Сначала быстрый статус:

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
pwd
git status --short --branch
```

Frontend type/build gate без sandbox-проблем с `.tmp`:

```bash
cd "/Users/deniscivkunov/Desktop/WMS /frontend"
./node_modules/.bin/tsc -p tsconfig.app.json --noEmit
./node_modules/.bin/tsc -p tsconfig.node.json --noEmit
./node_modules/.bin/vite build --configLoader runner --outDir /private/tmp/wms-frontend-dist-handoff
```

Backend Railway settings gate:

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
backend/.venv/bin/pytest backend/tests/test_settings_prod_gate.py
```

Backend inbound/sorting targeted tests:

```bash
cd "/Users/deniscivkunov/Desktop/WMS /backend"
ruff check .
pytest tests/test_inbound_intake_box_ondemand.py tests/test_inbound_box_acceptance.py tests/test_inbound_intake_api_be03.py
pytest tests/test_inbound_intake_service_sort_be01.py tests/test_inbound_distribution.py
```

Frontend inbound e2e, если окружение поднято:

```bash
cd "/Users/deniscivkunov/Desktop/WMS /frontend"
npm run test:e2e -- tests-e2e/inbound-receiving-v2.spec.ts tests-e2e/ff-inbound-boxes.spec.ts tests-e2e/ff-inbound-box-intake.spec.ts
```

Frontend ЧЗ/reprints e2e, если окружение поднято:

```bash
cd "/Users/deniscivkunov/Desktop/WMS /frontend"
npm run test:e2e -- tests-e2e/ff-honest-sign.spec.ts tests-e2e/ff-honest-sign-pool.spec.ts tests-e2e/ff-marking-defect.spec.ts
```

## 7. Что проверить вручную в diff перед продолжением

Особенно важно посмотреть эти файлы:

```bash
cd "/Users/deniscivkunov/Desktop/WMS "
git diff -- frontend/src/screens/ff/FfInboundRequestView.tsx frontend/src/screens/ff/FfInboundBoxAddDialog.tsx frontend/tests-e2e/inbound-receiving-v2.spec.ts
git diff -- backend/app/api/inbound_intake.py backend/app/services/inbound_intake_service.py backend/tests/test_inbound_intake_service_sort_be01.py backend/tests/test_inbound_distribution.py
git diff -- frontend/src/screens/shared/HonestSignPoolPage.tsx frontend/src/screens/shared/HonestSignProductPage.tsx frontend/tests-e2e/ff-honest-sign.spec.ts frontend/tests-e2e/ff-honest-sign-pool.spec.ts
git diff -- backend/app/core/settings.py backend/app/main.py backend/Dockerfile.railway frontend/Dockerfile.railway frontend/deploy/Caddyfile.railway
```

Проверить, что:

1. В `FfInboundRequestView.tsx` нет повторного объявления `boxId`.
2. Старые блокировки “закрыть короб перед завершением” не вернулись.
3. На pool page ЧЗ нет threshold editor.
4. На product page ЧЗ threshold editor работает для одного и нескольких personal pools.
5. `sorting_remaining_qty` не ломает старые DTO/типы.
6. Railway CORS не открыт слишком широко для production.

## 8. Рекомендуемая следующая волна агентов

**STAB backlog закрыт.** Следующий шаг — не код, а инфраструктура:

1. Создать/привязать Railway project WMS (`railway link`).
2. Deploy ветки `hotfix/deploy-wb-sync-nonfatal`.
3. `WMS_STAGING_URL=… ./scripts/railway-staging-smoke.sh`.
4. Ручной smoke критического пути.
5. PR → main, обновить `WMS_REQUIREMENTS_TRACKER_RU.md` по результатам smoke.

~~Волна A / B / финальная e2e — выполнены.~~

## 9. Готовый prompt для Composer

```text
Ты Composer/Cursor Autopilot в проекте WMS.

Рабочая папка: /Users/deniscivkunov/Desktop/WMS 
Важно: в имени папки WMS есть пробел в конце. Сначала проверь pwd.

Модель для всех builder/dev агентов: только gpt-5.4-mini.
Тяжёлые модели запрещены. Не использовать тяжёлые модели для разработки.

Главный backlog:
docs/analysis/08_confirmed_bug_stabilization_autopilot_RU.md

Оперативный handoff:
docs/analysis/09_STABILIZATION_HANDOFF_2026-06-30_RU.md

Railway/staging:
docs/analysis/RAILWAY_STAGING_RU.md

Задача:
1. Прочитай handoff.
2. Обнови git status.
3. Не трогай уже закрытые задачи, кроме проверки/минимальной фиксации конфликтов.
4. Запусти следующую волну независимых mini-агентов:
   - STAB-IN-FE-02
   - STAB-SORT-FE-01
   - STAB-OUT-BE-01
   - STAB-CZ-FE-02
5. Если видишь file conflict, не запускай конфликтующие задачи параллельно.
6. После каждой задачи требуй targeted tests.
7. После волны запусти общий frontend type/build gate и backend targeted tests.
8. Подготовь Railway staging deploy. Если CLI недоступен, дай точные шаги через Railway UI и env vars.
9. Не расширяй scope. Не делай общий рефакторинг.
```

## 10. Что НЕ делать

1. Не начинать “улучшение архитектуры” вместо фикса багов.
2. Не пытаться заново переписать весь процессный документ.
3. Не менять продуктовую модель данных шире, чем нужно конкретной задаче.
4. Не удалять чужие изменения из рабочего дерева.
5. Не считать `npm run build` sandbox `EPERM` продуктовой ошибкой без перепроверки через noEmit/outDir workaround.
6. Не деплоить в живую среду, где уже работают люди, пока не поднят отдельный staging.
7. Не использовать heavy models для builder-агентов.

## 11. Короткий итог состояния

Уже закрыто (полный STAB backlog):

1. Railway code/config preparation (STAGE-00).
2. Приёмка: короба BE/FE, завершение, модалка короба (STAB-IN-*).
3. Сортировка BE/FE (STAB-SORT-*).
4. Отгрузка из буфера BE/FE (STAB-OUT-*).
5. ЧЗ: пороги, строка товара, печать, без «Перепечатки» в меню (STAB-CZ-*, STAB-PRINT-*, STAB-REPRINTS-*).
6. Финальные e2e STAB-E2E-01/02.

Осталось:

1. **Railway staging smoke** — проект WMS не привязан, живой URL не проверен.
2. **Merge/commit** незакоммиченного WIP в git.
3. **Обновить tracker** после smoke на staging.

Главный риск:

Документ `09` обновлён 2026-06-30 вечером; при расхождении с `SESSION_HANDOFF.md` приоритет у более свежего `SESSION_HANDOFF.md`.
