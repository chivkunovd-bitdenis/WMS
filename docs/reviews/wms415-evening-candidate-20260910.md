# WMS-415/416: изолированный вечерний кандидат, 10.09.2026

Ветка `codex/wms-evening-release-20260910`, постоянная рабочая копия `.worktrees/wms-evening-release-20260910`. База `origin/etalon` заново получена fetch: `1922a2242ad626a9618cb2b7300e6cf500d25b4d`. Это Git-база, не заявление об одинаковом runtime API после дневного отката. Никаких команд на VPS и никаких публикаций APK эта работа не выполняла.

## Ограниченный состав

Взяты уже принятые изменения из coordinator `f4189fa1`: WMS338/341/329/060/384 — неизменяемый операторский предел над свободным физическим остатком, сохранение поштучного режима, нормальный preview и отдельные ключи складов; WMS349 — защита объединения карточек при параллельном складском движении; WMS062/153–156/174 — основной склад, инвентаризация/пустые места/акт расхождений/признак повреждённого короба; WMS177/179/184/121 — сохранение открытого документа и введённых данных, отказ от устаревших ответов, сброс выбора при смене контекста; уже принятые WMS056/325 факты изменения документов/прав/печати/настроек/счетов/маркировки с ранее исправленными блокировками. Новое расширение аудита не запускалось.

WMS270/377: только доказанное исправление `{client_ip}` в `deploy/Caddyfile.http` из `7e0d136e`, runtime regression сохранён. Остальная принятая auth/ports часть уже есть в etalon-базе. Ранее Caddy2.11.2 проверен автором (`ad5fd018`), повторный цикл не запускался.

Полностью отсутствуют chat397/399 (API, модели, миграция, UI), замороженные111/112 и неподтверждённый автодедуп122. Новый APK добавляет независимый владелец позднее. Нет standalone review-страниц.

Список выбранных source commits сохранён в `artifacts/wms415-evening-20260910/source-commits.json`. Перенос шёл кодовыми diff каждого ограниченного коммита; целые старые ветки не сливались. Все оставшиеся non-chat backend/app файлы совпадают с `f4189fa1`; исключены именно chat routes/model exports/main/object-storage extension. В frontend ручные конфликты разрешены удалением соседнего chat context (imports/buttons/currentUserId), сохраняя navigation/dirty handlers. Неиспользуемый helper fbsSelectionContextChanged не восстановлен: итоговая логика сброса выбора живёт в effect экрана, как в принятом coordinator.

## Миграции

Единственная голова `20260910_0302`; merge-only граф: `0257 -> 0261` (принятая уборка старой квоты) и `0257 -> 0100 -> 0101` (короба/инвентаризация), обе соединены0302. Старые chat0300 и общий merge0301 не включены.0302 не содержит DDL или данных. Последующей chat-ветке необходимо явное согласование графа, а не слепой перенос0301.

0261 удаляет obsolete ledger и is_fbs; перед stage/вечерним выпуском требуется существующий штатный backup и read-only проверка нулевого количества true is_fbs. Сам upgrade останавливается при ненулевом количестве. Downgrade восстанавливает схему, не удалённые исторические строки. Это конкретная граница существующей принятой миграции, не новая задача.

## Один выполненный интеграционный набор

- Ruff backend/app + новая merge-миграция: PASS.
- Mypy app: PASS,270 исходников.
- tsc --noEmit: PASS; npm run build: PASS. Предупреждение о крупном существующем bwip-js chunk не ошибка сборки.
- Три ограниченных тестовых файла: `test_wms121_selection_reset.py`, `test_wms338_legacy_quota_migration.py`, `test_wms417_stock_http_contract.py`: **7 passed,1 skipped,7.95s**. Skip — PostgreSQL-only replay старой миграции, на SQLite не выдан за PASS. Ранее принятый PG replay не повторялся.
- alembic heads: одна0302. git diff --check: PASS.

Локальный полный pytest, новый каскад review и повторные PG lock наборы не запускались. UI нового изолированного кандидата в этой полосе не прокликивался; старые ручные доказательства сохранены отдельно и не выданы за stage. Следующий шаг — один финальный Opus-review нового интегрированного diff, затем разрешённый stage.

## Проверенный staging способ (НЕ выполнен)

GitHub `.github/workflows/deploy.yml` — только manual production workflow; push этой feature-ветки не вызывает VPS deployment. Старый `scripts/railway-staging-deploy.sh` делает push HEAD:staging; его комментарий о production main устарел (реальный prod guard — etalon). Поэтому предпочтителен явный Railway CLI upload exact clean SHA в уже существующие staging services после финального review; не выполнять production workflow и prod-update.sh.

Read-only Railway status в этой сессии подтвердил:

- проект `loyal-wonder`, id `c28e681d-4535-4c96-ac97-c7b600a7f8e4`;
- среда `58a08b66-1290-45a2-8737-e3d7408389e5` называется **production внутри staging проекта Railway**; это не VPS sellerfocus.pro;
- backend `WMS`, service `e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc`, rootDirectory `/backend`;
- web, service `f2ad51a8-009d-488c-9d64-7054072ccac6`, rootDirectory `/frontend`;
- оба используют Dockerfile.railway. WB emulator и Postgres не перевыкладывать.

Read-only preflight перед upload: `railway status --project c28e681d-4535-4c96-ac97-c7b600a7f8e4 --environment 58a08b66-1290-45a2-8737-e3d7408389e5 --json` (выводить только имена/IDs/source root, не variables); `git status --porcelain`, `git rev-parse HEAD`; сверить с SHA финального review; backup/schema preflight отдельной разрешённой stage-операцией.

Из корня чистого release-worktree, ПОСЛЕ review:

```sh
railway up --project c28e681d-4535-4c96-ac97-c7b600a7f8e4 --environment 58a08b66-1290-45a2-8737-e3d7408389e5 --service e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc --detach
railway up --project c28e681d-4535-4c96-ac97-c7b600a7f8e4 --environment 58a08b66-1290-45a2-8737-e3d7408389e5 --service f2ad51a8-009d-488c-9d64-7054072ccac6 --detach
```

Не передавать `--path-as-root`: существующие сервисы уже имеют соответствующий rootDirectory. После завершения проверить deployment status, `/api/health` и хэши runtime app/alembic и frontend assets против exact commit. CLI message сам по себе не доказывает SHA. Никаких изменений ключей/секретов, сетей или production.
